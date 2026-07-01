"""AWS Bedrock integration and ROI Analyst agent."""

import json
import re
import sys

import boto3
from botocore.config import Config

from .parser import _fh, _num_in


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
You are a senior workforce enablement analyst writing a value digest for a customer.
Show the value Flowace surfaced this month and where it can help next: lead with wins,
frame gaps as coaching opportunities, never as failures or problems.

STRICT NUMBER RULE: Use ONLY numbers that appear verbatim in the input below. Never
compute, derive, annualize, sum, average, convert to money or FTEs, or reformat any
number. Do not invent dollar values, ROI multiples, headcount/FTE equivalents, or
per-year figures. Every number in your output must be copied exactly from the input.

WRITING STYLE: Write like a sharp human analyst — natural, concise, confident. Vary
sentence structure. Avoid clunky or robotic constructions (e.g. never write
"coaching conversations could support 118 people" — write "118 people would benefit
from coaching"). Every sentence should read cleanly out loud.

VOCABULARY: Vary how you describe development — don't repeat "coaching" in every
sentence. Rotate among: enablement, a manager conversation, targeted support, a
1:1, focused follow-up, unlocking potential. Keep the tone warm and forward-looking.

Respond ONLY with a JSON object. No markdown fences, no explanation."""

_ANALYST_PROMPT = """\
Produce a value digest for {company}. Warm, confident, enablement-focused voice.

PERIOD: {period}
PEOPLE: {n} active on the platform · {dormant} dormant seats · {coverage_line}
ORG AVERAGES: productivity {prod_pct}% · activity {act_pct}% · idle {idle_pct}%
STANDOUT TEAM: {top_team} at {top_team_prod}% productivity
LOWEST TEAM (coaching opportunity): {bottom_team} at {bottom_team_prod}% productivity
UNLOCKABLE CAPACITY: {capacity_fmt} hours — the recoverable slice of idle time. This is a
SUBSET of total idle ({idle_fmt} hours); never call this the total idle figure.
COACHING OPPORTUNITIES: {at_risk_count} people are below the org average on both activity and productivity
UNDER-COVERED TEAMS: {under_covered_line}

TEAMS (best→worst productivity, delta vs org avg):
{teams_summary}

PEOPLE WHO'D BENEFIT FROM COACHING:
{at_risk_summary}

Return ONLY this JSON:
{{
  "headline": "<10 words or less — the single most valuable thing Flowace surfaced>",
  "executive_summary": "<5-6 sentences for a CEO, in this order: (1) the win — standout team and org productivity, (2) the value Flowace surfaced — {capacity_fmt} hours of unlockable capacity and where it sits, (3) where coaching helps most — reference the {at_risk_count} coaching opportunities, (4) the single most valuable next step. Warm, plain English. Only numbers from above.>",
  "hero_narrative": "<2-3 sentences, max 80 words. Open on the strongest win, then the capacity Flowace surfaced this month and where to act. Only numbers from above.>",
  "key_takeaway": "<one sharp sentence: the value surfaced and the highest-impact next move. Only numbers from above.>",
  "financial_insight": "<one sentence framing {capacity_fmt} hours as recoverable capacity Flowace pinpointed this month — capacity and hours only, NO money, NO FTEs, NO annualizing.>",
  "adoption_insight": "<one sentence nudging activation of the {dormant} dormant seats — the capacity those unused seats could add. Only numbers from above.>",
  "coverage_insight": "<one sentence on teams not yet fully covered (see UNDER-COVERED TEAMS) and the upside of extending visibility. If none listed, return an empty string.>",
  "team_insights": {{
    "<team_name>": "<one sharp sentence citing their numbers as a strength or a coaching opportunity>"
  }},
  "team_narratives": {{
    "<team_name>": "<2-3 plain sentences a manager wants to read: is the team healthy, the main strength, where coaching helps most. Only numbers from above.>"
  }},
  "recommendations": [
    "<action framed as enablement — name the team/person, cite the metric, state the upside (e.g. where a manager conversation will help most)>",
    "<action #2>",
    "<action #3>"
  ],
  "at_risk_detail": {{
    "<name>": "<one supportive sentence: their prod% vs {prod_pct}% and act% vs {act_pct}% org avg, framed as a coaching opportunity>"
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

    coverage_pct = en.get("coverage_pct")
    coverage_line = (f"{coverage_pct}% platform coverage"
                     if coverage_pct is not None else "coverage data not available")
    under_covered = en.get("under_covered_teams", [])
    under_covered_line = (
        ", ".join(f"{t['name']} ({t['active']}/{t['enabled']} active)" for t in under_covered)
        if under_covered else "none — all teams well covered"
    )

    prompt = _ANALYST_PROMPT.format(
        company=company,
        period=f"{data['period_start']} – {data['period_end']} ({data['period_days']} days)",
        n=org["n"], dormant=en.get("dormant_count", data["inactive_count"]),
        coverage_line=coverage_line,
        prod_pct=org["productivity_pct"], act_pct=org["activity_pct"],
        idle_pct=org["idle_pct"],
        top_team=en["top_team"], top_team_prod=en["top_team_prod"],
        bottom_team=en["bottom_team"], bottom_team_prod=en["bottom_team_prod"],
        capacity_fmt=_num_in(en["unlockable_capacity_h"]),
        idle_fmt=_num_in(org["idle"]),
        at_risk_count=len(data["at_risk"]),
        under_covered_line=under_covered_line,
        teams_summary=teams_summary, at_risk_summary=at_risk_summary,
    )

    try:
        text, usage = _converse(client, model_id, _ANALYST_SYSTEM, prompt,
                                max_tokens=2500, temp=0.6)
        print(f"    in={usage.get('inputTokens','?')} out={usage.get('outputTokens','?')}",
              file=sys.stderr)
        text = _strip_json(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            result = {}
            for key in ["headline", "hero_narrative", "key_takeaway", "financial_insight",
                        "executive_summary", "adoption_insight", "coverage_insight"]:
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
    at_risk_count = len(data["at_risk"])
    dormant = en.get("dormant_count", data.get("inactive_count", 0))
    under_covered = en.get("under_covered_teams", [])
    return {
        "headline": f"{org['productivity_pct']}% productivity across {org['n']} people",
        "executive_summary": (
            f"This month covers {org['n']} active people over {data['period_days']} days "
            f"({data['period_start']} – {data['period_end']}). "
            f"{en['top_team']} led the way at {en['top_team_prod']}% productivity, with the "
            f"organization averaging {org['productivity_pct']}% productivity and {org['activity_pct']}% activity. "
            f"Flowace surfaced {en['unlockable_capacity_fmt']} of unlockable capacity and pinpointed where it sits. "
            f"{en['bottom_team']} at {en['bottom_team_prod']}% is where coaching helps most, alongside "
            f"{at_risk_count} individual coaching opportunities. "
            f"The most valuable next step is a manager conversation with those teams to convert that capacity."
        ),
        "hero_narrative": (
            f"This month {company}'s {org['n']} active people delivered {org['productivity_pct']}% "
            f"productivity, led by {en['top_team']} at {en['top_team_prod']}%. "
            f"Flowace surfaced {en['unlockable_capacity_fmt']} of unlockable capacity and pinpointed "
            f"where a manager conversation — starting with {en['bottom_team']} — will help most."
        ),
        "key_takeaway": (
            f"Flowace surfaced {en['unlockable_capacity_fmt']} of unlockable capacity this month — "
            f"start with {en['bottom_team']} to convert it."
        ),
        "financial_insight": f"{en['unlockable_capacity_fmt']} of recoverable capacity Flowace pinpointed this month.",
        "adoption_insight": (
            f"{dormant} seats are dormant this month — activating them unlocks the capacity those unused seats represent."
            if dormant else ""
        ),
        "coverage_insight": (
            f"{len(under_covered)} team{'s' if len(under_covered) != 1 else ''} "
            f"({', '.join(t['name'] for t in under_covered)}) are not yet fully covered — "
            f"extending visibility there surfaces more of the picture."
            if under_covered else ""
        ),
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
                [f"Start a manager conversation with {en['bottom_team']} — at {teams[-1]['idle_pct']}% idle, "
                 f"it's where coaching will unlock the most capacity."]
                if en["bottom_team"] else []
            ),
            f"Replicate {en['top_team']}'s winning workflow patterns across other teams.",
            f"Schedule supportive 1:1s with the {at_risk_count} coaching opportunities identified this month.",
        ],
        "at_risk_detail": {
            u["name"]: f"prod={u['productivity_pct']}%, act={u['activity_pct']}%"
            for u in data["at_risk"]
        },
    }
