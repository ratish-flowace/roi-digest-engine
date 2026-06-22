# Flowace ROI Dashboard Generator

Automatically generates a polished, self-contained workforce ROI dashboard from a Flowace Workforce Efficiency CSV export. No manual work — feed it a CSV, get back a shareable HTML file in ~12 seconds.

## How it works

```
CSV export
    ↓
Python parses metrics (accuracy guaranteed — no LLM math)
    ↓
GLM-5 via AWS Bedrock writes all narrative content:
  executive summary · hero paragraph · team insights ·
  recommendations · at-risk analysis · financial impact
    ↓
Python renders complete interactive HTML dashboard
```

## Project structure

```
flowace-roi/
├── roi/
│   ├── __init__.py          # public API: generate_roi_html()
│   ├── config.py            # default region and model
│   ├── parser.py            # CSV parsing + metric computation
│   ├── enricher.py          # derived intelligence (deltas, severity, recovery)
│   ├── agent.py             # AWS Bedrock + ROI Analyst agent
│   └── renderer.py          # HTML rendering (template + JS patches)
├── generate_roi.py          # CLI entry point (35 lines)
├── dashboard_template.html  # Flowace dashboard template
├── run.sh                   # convenience run script
└── .env                     # AWS credentials (not committed)
```

## Quick start

**1. Add AWS credentials to `.env`:**
```
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
```

**2. Run:**
```bash
./run.sh report.csv "Acme Corp"
# Output: acme_corp_roi.html
```

Or with full options:
```bash
./run.sh report.csv "Acme Corp" acme_roi.html
```

The script sets up the virtual environment and installs dependencies automatically on first run.

## CLI

```bash
# Activate venv first
source .venv/bin/activate

python generate_roi.py report.csv --company "Acme Corp"
python generate_roi.py report.csv --company "Acme Corp" --output acme_roi.html
python generate_roi.py report.csv --company "Acme Corp" --region ap-south-1 --model zai.glm-5
```

## Platform / API integration

```python
from roi import generate_roi_html

html = generate_roi_html(
    csv_path="report.csv",
    company="Acme Corp",
    region="ap-south-1",   # AWS Bedrock region
    model_id="zai.glm-5",  # Bedrock model
)

# Save, serve as HTTP response, upload to S3 — anything
with open("acme_roi.html", "w") as f:
    f.write(html)
```

To swap the data source from CSV to a platform API, replace `parse_csv()` in `roi/parser.py` with a function that returns the same dict schema. Everything else stays unchanged.

## Dashboard sections

| Section | Content | Source |
|---|---|---|
| Executive Summary | 5–6 sentence leadership briefing | LLM |
| Hero | Headline stat + 2–3 sentence narrative | LLM |
| Key Takeaway | Single most important action with numbers | LLM |
| KPI Strip | 6 cards with RAG indicators (🟢🟡🔴 vs org avg) | Python |
| Working Hours Timeline | Top 15 employees by logged hours | Python |
| Team Cards | Per-team metrics + AI insight, clickable | LLM + Python |
| Individual Drill-down | Full per-person table + team narrative | LLM + Python |
| Employees Needing Attention | At-risk employees, paginated, severity badges | LLM + Python |
| What To Do Next | 3 specific named recommendations | LLM |
| Quadrant Analysis | Activity % × Productivity % scatter, interactive | Python |

## RAG indicators

All RAG dots are relative to the org's own average — no hardcoded thresholds.

| Colour | Meaning |
|---|---|
| 🟢 Green | Within 3 pts of org average or better |
| 🟡 Yellow | 3–10 pts below org average |
| 🔴 Red | More than 10 pts below org average |

## AWS setup

The IAM user/role needs:
```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:ap-south-1::foundation-model/zai.glm-5"
}
```

## Dependencies

```bash
pip install boto3
```

Only `boto3` is required. No LangChain, no other frameworks.

## Fallback behaviour

If the Bedrock call fails or returns malformed JSON, the pipeline falls back to deterministic text generated from the pre-computed metrics. The dashboard still renders correctly — all numbers remain accurate.
