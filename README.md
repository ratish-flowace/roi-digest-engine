# Flowace ROI Dashboard Generator

Generates a polished, self-contained workforce ROI dashboard from a Flowace data source — either a CSV export or the live API. No manual work — feed it data, get back a shareable HTML file in ~12 seconds.

## How it works

```
CSV export  OR  Flowace API
        ↓
Python parses + computes all metrics (no LLM math)
        ↓
GLM-5 via AWS Bedrock writes all narrative content:
  executive summary · hero paragraph · team insights ·
  recommendations · at-risk analysis · financial impact
        ↓
Python renders interactive HTML dashboard + email digest
```

## Project structure

```
flowace-roi/
├── roi/
│   ├── __init__.py          # public API
│   ├── config.py            # env-backed defaults
│   ├── parser.py            # CSV → metrics dict
│   ├── api_parser.py        # Flowace API → metrics dict
│   ├── enricher.py          # derived fields (deltas, severity, recovery)
│   ├── agent.py             # AWS Bedrock ROI analyst
│   ├── renderer.py          # interactive HTML dashboard
│   ├── email_renderer.py    # email-safe static digest
│   └── uploader.py          # S3 upload + presigned URL
├── generate_roi.py          # single-company CLI
├── batch_generate.py        # multi-company CLI
├── dashboard_template.html  # Flowace dashboard template
├── run.sh                   # convenience wrapper
└── .env                     # credentials (not committed)
```

## Quick start

**1. Add credentials to `.env`:**
```
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
FLOWACE_API_TOKEN=your_token
```

**2. Run:**
```bash
# CSV mode
./run.sh report.csv "Acme Corp"

# API mode
./run.sh --api "Acme Corp" --start 2026-06-01 --end 2026-06-26
```

Both produce `outputs/acme_corp_roi.html` and `outputs/acme_corp_email.html`.

The script sets up a virtual environment and installs dependencies automatically on first run.

## CLI — single company

```bash
source .venv/bin/activate

# CSV mode
python generate_roi.py report.csv --company "Acme Corp"
python generate_roi.py report.csv --company "Acme Corp" --no-email

# API mode
python generate_roi.py --api --start 2026-06-01 --end 2026-06-26 --company "Acme Corp"
python generate_roi.py --api --start 2026-06-01 --end 2026-06-26 --company "Acme Corp" \
  --origin https://acme.flowace.in

# Generate + get a shareable link
python generate_roi.py --api --start 2026-06-01 --end 2026-06-26 --company "Acme Corp" \
  --share --bucket my-s3-bucket
```

**All flags:**

| Flag | Default | Description |
|---|---|---|
| `--company` / `-c` | `Flowace Tenant` | Company name shown in the dashboard |
| `--output` / `-o` | `outputs/<slug>_roi.html` | Custom dashboard output path |
| `--region` | `ap-south-1` | AWS Bedrock region |
| `--model` | `zai.glm-5` | Bedrock model ID |
| `--no-email` | — | Skip the email digest |
| `--api` | — | Use live API instead of CSV |
| `--token` | `FLOWACE_API_TOKEN` | Flowace API auth token |
| `--start` | — | Report start date `YYYY-MM-DD` (API mode) |
| `--end` | — | Report end date `YYYY-MM-DD` (API mode) |
| `--origin` | `https://gozo.flowace.in` | Tenant origin URL (API mode) |
| `--api-url` | `FLOWACE_API_URL` | API base URL |
| `--ga4-id` | `GA4_MEASUREMENT_ID` | GA4 Measurement ID |
| `--pixel-url` | `TRACKING_PIXEL_URL` | Email tracking pixel URL |
| `--share` | — | Upload to S3 and print a presigned link |
| `--share-expiry` | `7` | Link expiry in days (max 7) |
| `--bucket` | `S3_BUCKET` | S3 bucket for sharing |

## CLI — batch (multiple companies)

Generate reports for multiple companies in one command. Each company needs a name and its Flowace origin URL.

**Inline:**
```bash
python batch_generate.py \
  "Acme Corp:https://acme.flowace.in" \
  "Beta Inc:https://beta.flowace.in" \
  --start 2026-06-01 --end 2026-06-26
```

**From a CSV file:**
```bash
python batch_generate.py --from-file companies.csv \
  --start 2026-06-01 --end 2026-06-26
```

`companies.csv` format:
```
company,origin
Acme Corp,https://acme.flowace.in
Beta Inc,https://beta.flowace.in
```

**With share links:**
```bash
python batch_generate.py --from-file companies.csv \
  --start 2026-06-01 --end 2026-06-26 \
  --share --bucket my-s3-bucket
```

Output: progress per company to stderr, share links tab-separated to stdout (pipeable to a file).

## Sharing via hosted link

Add `--share` to any run to upload the dashboard to S3 and get back a time-limited URL. The link opens the full interactive dashboard in any browser — no server setup needed.

```bash
python generate_roi.py report.csv --company "Acme Corp" --share --bucket my-bucket
```

```
  Dashboard → outputs/acme_corp_roi.html  (312,455 chars)
  Shared    → https://my-bucket.s3.amazonaws.com/...  (expires in 7d)
```

The URL is printed to stdout so it can be piped: `... --share | pbcopy`

S3 presigned URLs expire after a maximum of **7 days**. Use `--share-expiry N` to set fewer days.

## Platform / API integration

```python
from roi import generate_roi_html, generate_roi_outputs_from_api

# From CSV
html = generate_roi_html("report.csv", "Acme Corp")

# From API
outputs = generate_roi_outputs_from_api(
    token="xxx",
    start_date="2026-06-01",
    end_date="2026-06-26",
    company="Acme Corp",
    origin="https://acme.flowace.in",
)
# outputs["dashboard"] → full interactive HTML
# outputs["email"]     → email-safe digest HTML
```

## Analytics tracking

Both outputs support opt-in tracking. Set environment variables in `.env` or pass as CLI flags. If neither is set, HTML is generated with no tracking code.

### Dashboard (GA4)

```bash
# .env
GA4_MEASUREMENT_ID=G-XXXXXXXXXX

# or per-run
python generate_roi.py report.csv --company "Acme Corp" --ga4-id G-XXXXXXXXXX
```

Events fired automatically when a recipient opens the dashboard:

| Event | What it captures |
|---|---|
| `page_view` | Report opened — includes `company_name` and `report_date` |
| `scroll_section` | Each section as it scrolls into view |
| `time_on_page` | Heartbeat every 30s up to 5 min |
| `cta_click` | Any button or link clicked |

**One-time GA4 admin step:** register two Event-scoped custom dimensions in GA4 → Admin → Custom definitions: `company_name` and `report_date`. Events fire without this step but you won't be able to filter by company until they're registered.

### Email digest (tracking pixel)

```bash
TRACKING_PIXEL_URL=https://your-endpoint/pixel.gif
```

Embeds a 1×1 invisible image. When opened, the email client fetches:
```
https://your-endpoint/pixel.gif?company=Acme+Corp&type=email_open&date=18+Jun+2026
```

The pixel URL can point to any endpoint — your own server, a Cloudflare Worker, or a no-code webhook (Zapier, Make).

## AWS setup

The IAM user/role needs the following permissions:

```json
{
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": "arn:aws:bedrock:ap-south-1::foundation-model/zai.glm-5"
}
```

For sharing via S3, also add:
```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject"],
  "Resource": "arn:aws:s3:::my-bucket/reports/*"
}
```

## Dashboard sections

| Section | Content | Source |
|---|---|---|
| Executive Summary | 5–6 sentence leadership briefing | LLM |
| Hero | Headline stat + narrative | LLM |
| Key Takeaway | Single most important action with numbers | LLM |
| KPI Strip | 6 cards with RAG indicators vs org average | Python |
| Working Hours Timeline | Top 15 employees by logged hours | Python |
| Team Cards | Per-team metrics + AI insight, clickable | LLM + Python |
| Individual Drill-down | Full per-person table + team narrative | LLM + Python |
| Employees Needing Attention | At-risk employees, paginated, severity badges | LLM + Python |
| What To Do Next | 3 specific named recommendations | LLM |
| Quadrant Analysis | Activity % × Productivity % scatter, interactive | Python |

## RAG indicators

All thresholds are relative to the org's own average — no hardcoded values.

| Colour | Meaning |
|---|---|
| 🟢 Green | Within 3 pts of org average or better |
| 🟡 Yellow | 3–10 pts below org average |
| 🔴 Red | More than 10 pts below org average |

## Dependencies

```bash
pip install boto3
```

Only `boto3` is required. No LangChain, no other frameworks.

## Fallback behaviour

If the Bedrock call fails or returns malformed JSON, the pipeline falls back to deterministic text generated from the pre-computed metrics. The dashboard still renders correctly — all numbers remain accurate.
