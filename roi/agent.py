"""AWS Bedrock integration and ROI Analyst agent."""

import json
import re
import sys

import boto3
from botocore.config import Config

from .parser import _fh


# ── Bedrock helpers ───────────────────────────────────────────────────────────

def _bedrock(region: str):
    return boto3.client(
        "bedrock-runtime", region_name=region,
        config=Config(read_timeout=120, connect_timeout=10),
    )

def _converse(client, model_id: str, system_text: str, user_text: str,
              max_tokens: int, temp: float = 0.3):
    resp = client.converse(
        modelId=model_id,
        system=[{"text": system_text}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temp},
    )
    text = (
        resp.get("output", {})
            .get("message", {})
            .get("content", [{}])[0]
            .get("text", "")
            .strip()
    )
    if not text:
        raise ValueError("Empty or malformed response from Bedrock")
    usage = resp.get("usage", {})
    return text, usage

def _strip_json(text: str) -> str:
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    return text.rstrip("`").strip()


# ── Analyst prompts ───────────────────────────────────────────────────────────

_ANALYST_SYSTEM = """\
You are a senior workforce ROI analyst. You receive pre-computed workforce metrics.
All numbers are already calculated — interpret them, find patterns, derive business impact.
Respond ONLY with a JSON object. No markdown fences, no explanation."""

_ANALYST_PROMPT = """\
Analyze this workforce data for {company} and produce structured ROI intelligence.

PERIOD: {period}
EMPLOYEES: {n} active ({inactive} inactive)
ORG AVERAGES: productivity {prod_pct}% · activity {act_pct}% · idle {idle_pct}%
HOURS: logged {logged} · productive {productive} · idle {idle}
IDLE RECOVERY POTENTIAL: {idle_recovery_h}h recoverable if idle drops to org activity ratio

TEAMS (sorted best→worst productivity, delta vs org avg):
{teams_summary}

AT-RISK (below avg on both activity AND productivity):
{at_risk_summary}

Return ONLY this JSON:
{{
  "headline": "<10 words or less — the single most important fact about this workforce>",
  "executive_summary": "<5-6 sentences for a VP or CEO. No jargon. Cover: what period, how many people, headline productivity number, the one standout team, the one problem that needs attention, and the single most important action. Plain English. Specific numbers.>",
  "hero_narrative": "<2-3 sentences max 80 words. Lead with the strongest positive, then the key opportunity. Specific numbers.>",
  "key_takeaway": "<one sharp, specific, actionable sentence with numbers>",
  "financial_insight": "<one sentence on the business value of recovering idle hours — use concrete numbers>",
  "team_insights": {{
    "<team_name>": "<one sharp sentence about this team — cite their specific numbers and what it means>"
  }},
  "team_narratives": {{
    "<team_name>": "<2-3 plain English sentences a team manager would want to read when they click into their team. Cover: is the team healthy, what is the main strength, what is the main concern. No jargon. Specific numbers.>"
  }},
  "recommendations": [
    "<specific action — name the team/person, cite the metric gap, state the expected outcome>",
    "<specific action #2>",
    "<specific action #3>"
  ],
  "at_risk_detail": {{
    "<name>": "<one sentence: their prod% vs {prod_pct}% avg, act% vs {act_pct}% avg, priority level>"
  }}
}}"""


# ── Analyst agent ─────────────────────────────────────────────────────────────

def call_analyst(data: dict, company: str, region: str, model_id: str) -> dict:
    print("  [Agent 1] ROI Analyst…", file=sys.stderr)
    client = _bedrock(region)
    org    = data["organization"]
    en     = data["enriched"]

    teams_summary = "\n".join(
        f"  {t['name']}: prod={t['productivity_pct']}% "
        f"({'+' if t['_prod_delta']>=0 else ''}{t['_prod_delta']} vs avg) "
        f"act={t['activity_pct']}% idle={_fh(t['idle'])} n={t['n']}"
        for t in data["teams"]
    )
    at_risk_summary = "\n".join(
        f"  {u['name']} ({', '.join(u['teams'])}): "
        f"prod={u['productivity_pct']}% act={u['activity_pct']}% severity={u['_severity']}"
        for u in data["at_risk"]
    ) or "  none"

    prompt = _ANALYST_PROMPT.format(
        company=company,
        period=f"{data['period_start']} – {data['period_end']} ({data['period_days']} days)",
        n=org["n"], inactive=data["inactive_count"],
        prod_pct=org["productivity_pct"], act_pct=org["activity_pct"],
        idle_pct=org["idle_pct"],
        logged=en["org_logged_fmt"], productive=en["org_productive_fmt"],
        idle=en["org_idle_fmt"], idle_recovery_h=en["idle_recovery_h"],
        teams_summary=teams_summary, at_risk_summary=at_risk_summary,
    )

    try:
        text, usage = _converse(client, model_id, _ANALYST_SYSTEM, prompt,
                                max_tokens=2500, temp=0.3)
        print(f"    in={usage.get('inputTokens','?')} out={usage.get('outputTokens','?')}",
              file=sys.stderr)
        text = _strip_json(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            result = {}
            for key in ["headline", "hero_narrative", "key_takeaway", "financial_insight",
                        "executive_summary"]:
                m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
                if m:
                    result[key] = m.group(1)
            ti_block = re.search(r'"team_insights"\s*:\s*\{(.*?)\}', text, re.DOTALL)
            if ti_block:
                result["team_insights"] = {}
                for m in re.finditer(r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)"',
                                     ti_block.group(1)):
                    result["team_insights"][m.group(1)] = m.group(2)
            rec_block = re.search(r'"recommendations"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if rec_block:
                result["recommendations"] = re.findall(r'"((?:[^"\\]|\\.)*)"',
                                                        rec_block.group(1))
            if result.get("hero_narrative"):
                print("    (salvaged partial JSON)", file=sys.stderr)
                return {**fallback_insights(data, company), **result}
            raise
    except Exception as e:
        print(f"    [warn] analyst failed: {e}", file=sys.stderr)
        return fallback_insights(data, company)


def fallback_insights(data: dict, company: str) -> dict:
    org   = data["organization"]
    en    = data["enriched"]
    teams = data["teams"]
    return {
        "headline": f"{org['productivity_pct']}% productivity across {org['n']} employees",
        "executive_summary": (
            f"This report covers {org['n']} employees over {data['period_days']} days "
            f"({data['period_start']} – {data['period_end']}). "
            f"The team averaged {org['productivity_pct']}% productivity and {org['activity_pct']}% activity. "
            f"{en['top_team']} is the strongest team at {en['top_team_prod']}% productivity. "
            f"{en['bottom_team']} at {en['bottom_team_prod']}% needs the most attention. "
            f"Recovering {en['idle_recovery_fmt']} of idle time is the highest-impact action available."
        ),
        "hero_narrative": (
            f"Across {org['n']} active employees, {company} achieved {org['productivity_pct']}% "
            f"average productivity and {org['activity_pct']}% activity this period. "
            f"{en['top_team']} leads at {en['top_team_prod']}% while {en['bottom_team']} "
            f"at {en['bottom_team_prod']}% is the key coaching opportunity."
        ),
        "key_takeaway": (
            f"Recovering {en['idle_recovery_fmt']} of productive potential from "
            f"{en['org_idle_fmt']} idle hours is the highest-ROI action this quarter."
        ),
        "financial_insight": f"{en['idle_recovery_fmt']} in recoverable productive capacity.",
        "team_insights": {
            t["name"]: f"{t['productivity_pct']}% productivity, {t['activity_pct']}% activity."
            for t in teams
        },
        "team_narratives": {
            t["name"]: (
                f"{t['name']} has {t['n']} member{'s' if t['n']!=1 else ''} "
                f"and logged {_fh(t['logged'])} this period. "
                f"Productivity is {t['productivity_pct']}% — "
                f"{'above' if t['_prod_delta'] >= 0 else 'below'} the company average "
                f"by {abs(t['_prod_delta'])} points. "
                f"Idle time is {_fh(t['idle'])} ({t['idle_pct']}% of logged hours)."
            )
            for t in teams
        },
        "recommendations": [
            *(
                [f"Investigate idle time in {en['bottom_team']} ({teams[-1]['idle_pct']}% idle rate)."]
                if en["bottom_team"] else []
            ),
            f"Replicate {en['top_team']}'s workflow patterns across lower-performing teams.",
            f"Schedule 1:1s with {len(data['at_risk'])} at-risk employees identified below org average.",
        ],
        "at_risk_detail": {
            u["name"]: f"prod={u['productivity_pct']}%, act={u['activity_pct']}%"
            for u in data["at_risk"]
        },
    }
