#!/usr/bin/env python3
"""
Batch ROI dashboard generator for multiple companies.

Pass companies as positional args (Name:https://origin) or from a CSV file.

Usage:
  python batch_generate.py "Acme Corp:https://acme.flowace.in" "Beta:https://beta.flowace.in" \\
      --start 2026-06-01 --end 2026-06-26

  python batch_generate.py --from-file companies.csv \\
      --start 2026-06-01 --end 2026-06-26 --share --bucket my-bucket

companies.csv format:
  company,origin
  Acme Corp,https://acme.flowace.in
  Beta Inc,https://beta.flowace.in
"""

import argparse
import csv
import os
import re
import sys

from roi import generate_roi_outputs_from_api, DEFAULT_REGION, DEFAULT_MODEL_ID
from roi.config import FLOWACE_API_TOKEN, FLOWACE_API_URL, S3_BUCKET


def parse_companies(positional: list[str], from_file: str) -> list[tuple[str, str]]:
    companies = []
    if from_file:
        with open(from_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                companies.append((row["company"].strip(), row["origin"].strip()))
    for entry in positional:
        if ":" not in entry:
            print(f"Error: '{entry}' must be in format 'Company Name:https://origin'", file=sys.stderr)
            sys.exit(1)
        name, origin = entry.split(":", 1)
        companies.append((name.strip(), origin.strip()))
    return companies


def main():
    p = argparse.ArgumentParser(
        description="Batch-generate ROI dashboards for multiple companies via Flowace API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("companies", nargs="*",
                   help="One or more 'Company Name:https://origin.flowace.in' entries")
    p.add_argument("--from-file", default="",
                   help="CSV file with columns: company, origin")

    p.add_argument("--start",   required=True, help="Report start date YYYY-MM-DD")
    p.add_argument("--end",     required=True, help="Report end date YYYY-MM-DD")
    p.add_argument("--token",   default="",    help="Flowace API token. Overrides FLOWACE_API_TOKEN.")
    p.add_argument("--api-url", default="",    help=f"API base URL (default: {FLOWACE_API_URL})")
    p.add_argument("--region",  default=DEFAULT_REGION)
    p.add_argument("--model",   default=DEFAULT_MODEL_ID)
    p.add_argument("--ga4-id",  default="",    help="GA4 Measurement ID")
    p.add_argument("--no-email", action="store_true", help="Skip email digest")

    p.add_argument("--share",        action="store_true",
                   help="Upload each dashboard to S3 and print a presigned link")
    p.add_argument("--share-expiry", type=int, default=7,
                   help="Presigned link expiry in days, max 7 (default: 7)")
    p.add_argument("--bucket",       default="",
                   help="S3 bucket name. Overrides S3_BUCKET env var.")

    args = p.parse_args()

    companies = parse_companies(args.companies, args.from_file)
    if not companies:
        print("Error: provide at least one company as arg or via --from-file", file=sys.stderr)
        sys.exit(1)

    token    = args.token or FLOWACE_API_TOKEN
    base_url = args.api_url or FLOWACE_API_URL
    bucket   = args.bucket or S3_BUCKET

    if not token:
        print("Error: --token or FLOWACE_API_TOKEN env var required", file=sys.stderr)
        sys.exit(1)
    if args.share and not bucket:
        print("Error: --bucket or S3_BUCKET env var required for --share", file=sys.stderr)
        sys.exit(1)

    outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    results = []

    for i, (company, origin) in enumerate(companies, 1):
        print(f"\n[{i}/{len(companies)}] {company}  ({origin})", file=sys.stderr)
        slug = re.sub(r"[^a-z0-9]", "_", company.lower())

        try:
            outputs = generate_roi_outputs_from_api(
                token, args.start, args.end, company,
                origin=origin,
                base_url=base_url,
                region=args.region,
                model_id=args.model,
                ga4_id=args.ga4_id,
            )
        except Exception as e:
            print(f"  ✗ Failed: {e}", file=sys.stderr)
            results.append({"company": company, "status": "failed", "error": str(e)})
            continue

        dash_out  = os.path.join(outputs_dir, f"{slug}_roi.html")
        email_out = os.path.join(outputs_dir, f"{slug}_email.html")

        with open(dash_out, "w", encoding="utf-8") as f:
            f.write(outputs["dashboard"])
        print(f"  Dashboard → {dash_out}", file=sys.stderr)

        if not args.no_email:
            with open(email_out, "w", encoding="utf-8") as f:
                f.write(outputs["email"])
            print(f"  Email     → {email_out}", file=sys.stderr)

        share_url = None
        if args.share:
            from roi.uploader import upload_and_sign
            expiry_days = min(args.share_expiry, 7)
            share_url = upload_and_sign(
                outputs["dashboard"], slug, bucket, args.region, expiry_days * 86400
            )
            print(f"  Shared    → {share_url}  (expires in {expiry_days}d)", file=sys.stderr)

        results.append({
            "company":   company,
            "status":    "ok",
            "dashboard": dash_out,
            "share_url": share_url,
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 60, file=sys.stderr)
    print(f"Done  {sum(1 for r in results if r['status'] == 'ok')}/{len(results)} succeeded\n", file=sys.stderr)
    for r in results:
        if r["status"] == "ok":
            line = f"  ✓  {r['company']}"
            if r["share_url"]:
                line += f"\n     {r['share_url']}"
            print(line, file=sys.stderr)
        else:
            print(f"  ✗  {r['company']}  — {r['error']}", file=sys.stderr)

    if args.share:
        print("\nShare links (stdout):")
        for r in results:
            if r["status"] == "ok" and r["share_url"]:
                print(f"{r['company']}\t{r['share_url']}")


if __name__ == "__main__":
    main()
