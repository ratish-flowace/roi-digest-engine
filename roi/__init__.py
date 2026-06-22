"""
Flowace ROI Dashboard Generator
--------------------------------
Public API for platform integration:

    from roi import generate_roi_html
    html = generate_roi_html(csv_path, company, region, model_id)
"""

import sys

from .config import DEFAULT_REGION, DEFAULT_MODEL_ID
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
        "dashboard": render_html(company, data, insights),
        "email":     render_email_html(company, data, insights),
    }


def generate_roi_html(
    csv_path: str,
    company: str,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """Convenience wrapper — returns dashboard HTML only."""
    return generate_roi_outputs(csv_path, company, region, model_id)["dashboard"]


def generate_email_digest(
    csv_path: str,
    company: str,
    region: str = DEFAULT_REGION,
    model_id: str = DEFAULT_MODEL_ID,
) -> str:
    """Convenience wrapper — returns email digest HTML only."""
    return generate_roi_outputs(csv_path, company, region, model_id)["email"]
