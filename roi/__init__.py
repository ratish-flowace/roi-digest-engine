"""
Flowace ROI Dashboard Generator
--------------------------------
Public API for platform integration:

    from roi import generate_roi_html
    html = generate_roi_html(csv_path, company, region, model_id)

    from roi import generate_roi_outputs_from_api
    outputs = generate_roi_outputs_from_api(token, start_date, end_date, company)
"""

import sys

from .config import DEFAULT_REGION, DEFAULT_MODEL_ID, FLOWACE_API_TOKEN, FLOWACE_API_URL
from .parser import parse_csv, _fh
from .enricher import enrich
from .agent import call_analyst
from .renderer import render_html
from .email_renderer import render_email_html


def generate_roi_outputs(
    csv_path: str,
    company: str,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
    ga4_id: str = "",
    pixel_url: str = "",
) -> dict:
    """
    Main pipeline entry point. Runs once and returns both outputs.

    Data source agnostic — swap parse_csv() for an API fetch function
    when the platform API is available; everything else stays unchanged.

    Args:
        csv_path:  Path to Flowace Workforce Efficiency CSV export.
        company:   Tenant / company display name.
        region:    AWS Bedrock region (default: ap-south-1).
        model_id:  Bedrock model ID (default: zai.glm-5).

    Returns:
        {
            "dashboard": "<full interactive HTML>",
            "email":     "<email-safe static HTML digest>",
        }
    """
    print("[1/3] Parsing + enriching metrics…", file=sys.stderr)
    data = parse_csv(csv_path)
    data["org_name"] = company
    data = enrich(data)
    org = data["organization"]
    print(
        f"      {org['n']} employees · {len(data['teams'])} teams · "
        f"prod={org['productivity_pct']}% · activity={org['activity_pct']}% · "
        f"idle={_fh(org['idle'])}",
        file=sys.stderr,
    )

    print("[2/3] Agent 1 (ROI Analyst)…", file=sys.stderr)
    insights = call_analyst(data, company, region, model_id)

    print("[3/3] Rendering outputs…", file=sys.stderr)
    return {
        "dashboard": render_html(company, data, insights, ga4_id=ga4_id),
        "email":     render_email_html(company, data, insights, pixel_url=pixel_url),
    }


def generate_roi_html(
    csv_path: str,
    company: str,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
    ga4_id: str = "",
) -> str:
    """Convenience wrapper — returns dashboard HTML only."""
    return generate_roi_outputs(csv_path, company, region, model_id, ga4_id=ga4_id)["dashboard"]


def generate_email_digest(
    csv_path: str,
    company: str,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
    pixel_url: str = "",
) -> str:
    """Convenience wrapper — returns email digest HTML only."""
    return generate_roi_outputs(csv_path, company, region, model_id, pixel_url=pixel_url)["email"]


def generate_roi_outputs_from_api(
    token: str,
    start_date: str,
    end_date: str,
    company: str,
    origin: str = "https://gozo.flowace.in",
    base_url: str = FLOWACE_API_URL,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
    ga4_id: str = "",
    pixel_url: str = "",
) -> dict:
    """
    API-mode pipeline entry point. Fetches live data from the Flowace
    getDailywiseTimesheet endpoint and returns both outputs.

    Args:
        token:      Flowace Authorization header value.
        start_date: "YYYY-MM-DD"
        end_date:   "YYYY-MM-DD"
        company:    Tenant / company display name.
        base_url:   API root (default: FLOWACE_API_URL from config / env).
        region:     AWS Bedrock region.
        model_id:   Bedrock model ID.

    Returns:
        {"dashboard": "<full interactive HTML>", "email": "<email-safe HTML>"}
    """
    from .api_parser import parse_api  # lazy import keeps startup fast when using CSV mode

    print("[1/3] Fetching + computing metrics from API…", file=sys.stderr)
    data = parse_api(token, start_date, end_date, base_url, origin)
    data["org_name"] = company
    data = enrich(data)
    org = data["organization"]
    print(
        f"      {org['n']} employees · {len(data['teams'])} teams · "
        f"prod={org['productivity_pct']}% · activity={org['activity_pct']}% · "
        f"idle={_fh(org['idle'])}",
        file=sys.stderr,
    )

    print("[2/3] Agent 1 (ROI Analyst)…", file=sys.stderr)
    insights = call_analyst(data, company, region, model_id)

    print("[3/3] Rendering outputs…", file=sys.stderr)
    return {
        "dashboard": render_html(company, data, insights, ga4_id=ga4_id),
        "email":     render_email_html(company, data, insights, pixel_url=pixel_url),
    }
