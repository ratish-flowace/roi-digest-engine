#!/usr/bin/env python3
"""
Flowace ROI Dashboard Generator — CLI entry point.

CSV mode:  python generate_roi.py report.csv --company "Acme Corp"
API mode:  python generate_roi.py --api --start 2026-06-01 --end 2026-06-26 --company "Acme"
Share:     add --share --bucket my-s3-bucket  to either mode
"""

import argparse
import os
import re
import sys

from roi import (
    generate_roi_outputs,
    generate_roi_outputs_from_api,
    DEFAULT_REGION,
    DEFAULT_MODEL_ID,
)
from roi.config import FLOWACE_API_TOKEN, FLOWACE_API_URL, S3_BUCKET


def main():
    p = argparse.ArgumentParser(
        description=(
            "Generate Flowace ROI dashboard + email digest.\n"
            "CSV mode:  generate_roi.py report.csv --company 'Acme'\n"
            "API mode:  generate_roi.py --api --start 2026-06-01 --end 2026-06-26 --company 'Acme'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Input source ──────────────────────────────────────────────────────────
    p.add_argument("csv", nargs="?", default=None,
                   help="Path to Workforce Efficiency CSV export (CSV mode)")
    p.add_argument("--api",     action="store_true",
                   help="Fetch live data from Flowace API instead of a CSV")
    p.add_argument("--token",   default="",
                   help="Flowace API auth token. Overrides FLOWACE_API_TOKEN env var.")
    p.add_argument("--start",   default="",
                   help="Report start date YYYY-MM-DD (API mode)")
    p.add_argument("--end",     default="",
                   help="Report end date YYYY-MM-DD (API mode)")
    p.add_argument("--api-url", default="",
                   help=f"API base URL (default: {FLOWACE_API_URL})")
    p.add_argument("--origin",  default="",
                   help="Tenant origin URL e.g. https://acme.flowace.in (no trailing slash)")

    # ── Shared options ────────────────────────────────────────────────────────
    p.add_argument("--company",   "-c", default="Flowace Tenant",
                   help="Company / tenant name shown in the dashboard")
    p.add_argument("--output",    "-o", default="",
                   help="Dashboard output path (default: outputs/<company>_roi.html)")
    p.add_argument("--region",    default=DEFAULT_REGION,
                   help=f"AWS Bedrock region (default: {DEFAULT_REGION})")
    p.add_argument("--model",     default=DEFAULT_MODEL_ID,
                   help=f"Bedrock model ID (default: {DEFAULT_MODEL_ID})")
    p.add_argument("--ga4-id",    default="",
                   help="GA4 Measurement ID. Overrides GA4_MEASUREMENT_ID env var.")
    p.add_argument("--pixel-url", default="",
                   help="Tracking pixel URL for email. Overrides TRACKING_PIXEL_URL env var.")
    p.add_argument("--no-email",  action="store_true",
                   help="Skip generating the email digest")

    # ── Share options ─────────────────────────────────────────────────────────
    p.add_argument("--share",        action="store_true",
                   help="Upload dashboard to S3 and print a presigned link")
    p.add_argument("--share-expiry", type=int, default=7,
                   help="Presigned link expiry in days, max 7 (default: 7)")
    p.add_argument("--bucket",       default="",
                   help="S3 bucket name. Overrides S3_BUCKET env var.")

    args = p.parse_args()

    slug        = re.sub(r"[^a-z0-9]", "_", args.company.lower())
    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    dash_out    = args.output or os.path.join(outputs_dir, f"{slug}_roi.html")
    email_out   = os.path.join(outputs_dir, f"{slug}_email.html")

    # ── Route to the correct mode ─────────────────────────────────────────────
    if args.api:
        token = args.token or FLOWACE_API_TOKEN
        if not token:
            print("Error: --token or FLOWACE_API_TOKEN env var required for API mode",
                  file=sys.stderr)
            sys.exit(1)
        if not args.start or not args.end:
            print("Error: --start and --end are required for API mode (YYYY-MM-DD)",
                  file=sys.stderr)
            sys.exit(1)
        base_url = args.api_url or FLOWACE_API_URL
        outputs = generate_roi_outputs_from_api(
            token, args.start, args.end, args.company,
            origin=args.origin,
            base_url=base_url,
            region=args.region,
            model_id=args.model,
            ga4_id=args.ga4_id,
            pixel_url=args.pixel_url,
        )
    else:
        if not args.csv:
            print("Error: provide a CSV path or use --api for live data", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(args.csv):
            print(f"Error: file not found: {args.csv}", file=sys.stderr)
            sys.exit(1)
        outputs = generate_roi_outputs(
            args.csv, args.company, args.region, args.model,
            ga4_id=args.ga4_id,
            pixel_url=args.pixel_url,
        )

    # ── Write outputs ─────────────────────────────────────────────────────────
    os.makedirs(outputs_dir, exist_ok=True)
    with open(dash_out, "w", encoding="utf-8") as f:
        f.write(outputs["dashboard"])
    print(f"  Dashboard → {dash_out}  ({len(outputs['dashboard']):,} chars)", file=sys.stderr)

    if not args.no_email:
        with open(email_out, "w", encoding="utf-8") as f:
            f.write(outputs["email"])
        print(f"  Email     → {email_out}  ({len(outputs['email']):,} chars)", file=sys.stderr)

    # ── Upload + share ────────────────────────────────────────────────────────
    if args.share:
        bucket = args.bucket or S3_BUCKET
        if not bucket:
            print("Error: --bucket or S3_BUCKET env var required for --share", file=sys.stderr)
            sys.exit(1)
        expiry_days = min(args.share_expiry, 7)  # S3 hard limit is 7 days
        from roi.uploader import upload_and_sign
        url = upload_and_sign(
            outputs["dashboard"], slug, bucket, args.region, expiry_days * 86400
        )
        print(f"  Shared    → {url}  (expires in {expiry_days}d)", file=sys.stderr)
        print(url)  # stdout so it can be piped/captured


if __name__ == "__main__":
    main()
