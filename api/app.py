"""
Flowace ROI Dashboard Generation API.

Endpoints:
  POST /generate        — single company
  POST /generate/batch  — multiple companies (sequential)
  GET  /health

Auth: X-API-Key header on all non-health endpoints.

Run from project root:
  uvicorn api.app:app --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# Ensure project root is importable when invoked directly
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roi import generate_roi_outputs_from_api, DEFAULT_REGION, DEFAULT_MODEL_ID
from roi.config import (
    API_KEY, FLOWACE_API_TOKEN, FLOWACE_API_URL,
    GA4_MEASUREMENT_ID, S3_BUCKET,
)
from roi.email_renderer import append_cta
from roi.uploader import upload_and_sign, upload_file


app = FastAPI(title="Flowace ROI API", version="1.0.0")


@app.on_event("startup")
def _check_config():
    if not API_KEY:
        raise RuntimeError("API_KEY environment variable is not set — refusing to start")


# ── Auth ──────────────────────────────────────────────────────────────────────

def require_api_key(x_api_key: str = Header(...)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request / response models ─────────────────────────────────────────────────

class CompanyItem(BaseModel):
    company: str
    origin: str
    token: Optional[str] = None
    recipients: list[str] = []


class CompanyRequest(CompanyItem):
    start_date: str
    end_date: str
    share_expiry_days: int = Field(default=7, ge=1, le=7)


class BatchRequest(BaseModel):
    start_date: str
    end_date: str
    companies: list[CompanyItem]
    share_expiry_days: int = Field(default=7, ge=1, le=7)


# ── Core pipeline helper ──────────────────────────────────────────────────────

def _run_one(
    company: str,
    origin: str,
    token: Optional[str],
    start_date: str,
    end_date: str,
    recipients: list[str],
    share_expiry_days: int = Field(default=7, ge=1, le=7),
) -> dict:
    resolved_token = token or FLOWACE_API_TOKEN
    if not resolved_token:
        raise ValueError(
            f"No API token for {company!r} — provide 'token' in request or set FLOWACE_API_TOKEN"
        )
    if not S3_BUCKET:
        raise ValueError("S3_BUCKET env var not set")

    slug = re.sub(r"[^a-z0-9]", "_", company.lower())
    ts   = int(time.time())
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    outputs = generate_roi_outputs_from_api(
        token=resolved_token,
        start_date=start_date,
        end_date=end_date,
        company=company,
        origin=origin,
        base_url=FLOWACE_API_URL,
        region=DEFAULT_REGION,
        model_id=DEFAULT_MODEL_ID,
        ga4_id=GA4_MEASUREMENT_ID,
    )

    expiry_seconds = share_expiry_days * 86400
    dashboard_key  = f"reports/{slug}_{ts}.html"
    dashboard_url  = upload_and_sign(
        outputs["dashboard"], slug, S3_BUCKET, DEFAULT_REGION, expiry_seconds, key=dashboard_key
    )

    email_html = append_cta(outputs["email"], dashboard_url)
    email_key  = f"reports/{slug}_{ts}_email.html"
    upload_file(email_html, email_key, S3_BUCKET, DEFAULT_REGION)

    meta = {
        "company":       company,
        "period_start":  start_date,
        "period_end":    end_date,
        "generated_at":  date,
        "dashboard_url": dashboard_url,
        "email_s3_key":  email_key,
        "recipients":    recipients,
    }
    meta_key = f"reports/{slug}_{ts}_meta.json"
    upload_file(json.dumps(meta, indent=2), meta_key, S3_BUCKET, DEFAULT_REGION, "application/json")

    return {
        "company":      company,
        "status":       "ok",
        "dashboard_url": dashboard_url,
        "email_s3_key":  email_key,
        "meta_s3_key":   meta_key,
        "period":        f"{start_date} – {end_date}",
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", dependencies=[Depends(require_api_key)])
def generate(req: CompanyRequest):
    try:
        return _run_one(
            req.company, req.origin, req.token,
            req.start_date, req.end_date, req.recipients,
            req.share_expiry_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[generate] {req.company}: {e}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/batch", dependencies=[Depends(require_api_key)])
async def generate_batch(req: BatchRequest):
    async def _run_item(item: CompanyItem) -> dict:
        try:
            result = await asyncio.to_thread(
                _run_one,
                item.company, item.origin, item.token,
                req.start_date, req.end_date, item.recipients,
                req.share_expiry_days,
            )
            print(f"  ✓  {item.company}", file=sys.stderr)
            return result
        except Exception as e:
            print(f"  ✗  {item.company}: {e}", file=sys.stderr)
            return {"company": item.company, "status": "failed", "error": str(e)}

    results = list(await asyncio.gather(*[_run_item(item) for item in req.companies]))
    succeeded = sum(1 for r in results if r.get("status") == "ok")
    return {
        "results":   results,
        "succeeded": succeeded,
        "failed":    len(results) - succeeded,
    }
