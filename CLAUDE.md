# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Generates two outputs from a Flowace Workforce Efficiency CSV:
1. `outputs/<company>_roi.html` — full interactive dashboard (attach to email)
2. `outputs/<company>_email.html` — email-safe static digest (embed in email body)

Python computes all metrics. GLM-5 via AWS Bedrock writes all narrative content.

## Commands

```bash
# Run (sets up venv automatically on first run)
./run.sh report.csv "Acme Corp"

# CLI directly
source .venv/bin/activate
python generate_roi.py report.csv --company "Acme Corp"
python generate_roi.py report.csv --company "Acme Corp" --no-email   # dashboard only

# Install deps
python3 -m venv .venv && .venv/bin/pip install boto3
```

## Package structure

```
roi/
├── config.py          # DEFAULT_REGION, DEFAULT_MODEL_ID
├── parser.py          # CSV → metrics dict. Entry: parse_csv(path)
├── enricher.py        # Derived fields (deltas, severity, recovery). Entry: enrich(data)
├── agent.py           # Bedrock + analyst agent. Entry: call_analyst(data, company, region, model_id)
├── renderer.py        # Interactive HTML. Entry: render_html(company, data, insights)
├── email_renderer.py  # Email-safe HTML. Entry: render_email_html(company, data, insights)
└── __init__.py        # Public API: generate_roi_outputs(), generate_roi_html(), generate_email_digest()
```

## Architecture

```
parse_csv()     → data dict (all numbers, no LLM)
enrich(data)    → adds _prod_delta, _severity, idle_recovery_h per team/at-risk
call_analyst()  → GLM-5 writes: executive_summary, hero_narrative, key_takeaway,
                  financial_insight, team_insights, team_narratives, recommendations, at_risk_detail
render_html()       → loads dashboard_template.html, patches JS/CSS, returns full HTML
render_email_html() → table-based, inline-styles, no JS, email-client safe
```

## Key constraints

- **Never let LLM compute numbers** — all metrics are Python-computed before any LLM call
- **dashboard_template.html** is the Flowace UI template — do not modify its core CSS/JS structure; patch via `renderer.py` only
- **Email renderer rules**: no `<script>`, no CSS variables, no flexbox/grid, no Google Fonts, all styles must be `style=""` inline
- **Outputs always go to `outputs/`** — never write HTML to project root
- **AWS credentials** in `.env` — never commit this file

## Data flow

`parse_csv()` returns a dict with keys: `organization`, `teams`, `at_risk`, `enriched`, `period_*`, `generated_at`, `inactive_count`. After `call_analyst()`, `data` also gets `team_insights`, `team_narratives`, `at_risk_detail`, `benchmarks`.

## Swapping data source

`parse_csv()` in `roi/parser.py` is the only data ingestion point. Replace it with an API fetch that returns the same dict schema and the rest of the pipeline is unchanged.

## Model / region

Set in `roi/config.py`. Override at CLI with `--model` and `--region`.
Current default: `zai.glm-5` on `ap-south-1`.
