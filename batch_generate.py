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
  company,origin[,token]
  Acme Corp,https://acme.flowace.in,<token>
  Beta Inc,https://beta.flowace.in,<token>
"""

import argparse
import csv
import os
import re
import sys

from roi import generate_roi_outputs_from_api, DEFAULT_REGION, DEFAULT_MODEL_ID
from roi.config import FLOWACE_API_TOKEN, FLOWACE_API_URL, S3_BUCKET


def parse_companies(positional: list[str], from_file: str) -> list[tuple[str, str, str]]:
    # returns list of (company, origin, token) — token may be ""
    companies = []
    if from_file:
        with open(from_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                token = row.get("token", "").strip()
                companies.append((row["company"].strip(), row["origin"].strip(), token))
    for entry in positional:
        if ":" not in entry:
            print(f"Error: '{entry}' must be in format 'Company Name:https://origin'", file=sys.stderr)
            sys.exit(1)
        name, origin = entry.split(":", 1)
        companies.append((name.strip(), origin.strip(), ""))
    return companies


def main():
    p = argparse.ArgumentParser(
        description="Batch-generate ROI dashboards for multiple companies via Flowace API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("companies", nargs="*",
                   help="One or more 'Company Name:https://origin.flowace.in' entries")
    p.add_argument("--from-file", default="",
                   help="CSV file with columns: company, origin[, token]")

    p.add_argument("--start",   required=True, help="Report start date YYYY-MM-DD")
    p.add_argument("--end",     required=True, help="Report end date YYYY-MM-DD")
    p.add_argument("--token",   default="",    help="Fallback API token if not in CSV. Overrides FLOWACE_API_TOKEN.")
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

    fallback_token = args.token or FLOWACE_API_TOKEN
    base_url       = args.api_url or FLOWACE_API_URL
    bucket         = args.bucket or S3_BUCKET

    if args.share and not bucket:
        print("Error: --bucket or S3_BUCKET env var required for --share", file=sys.stderr)
        sys.exit(1)

    outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    results = []

    for i, (company, origin, row_token) in enumerate(companies, 1):
        token = row_token or fallback_token
        if not token:
            print(f"  ✗ No token for {company} — skipping", file=sys.stderr)
            results.append({"company": company, "status": "failed", "error": "no token"})
            continue

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

        share_url = None
        if args.share:
            from roi.uploader import upload_and_sign
            expiry_days = min(args.share_expiry, 7)
            share_url = upload_and_sign(
                outputs["dashboard"], slug, bucket, args.region, expiry_days * 86400
            )
            print(f"  Shared    → {share_url}  (expires in {expiry_days}d)", file=sys.stderr)

        if not args.no_email:
            from roi.email_renderer import append_cta
            email_html = append_cta(outputs["email"], share_url or "")
            with open(email_out, "w", encoding="utf-8") as f:
                f.write(email_html)
            print(f"  Email     → {email_out}", file=sys.stderr)

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
        links_file = os.path.join(outputs_dir, "share_links.txt")
        with open(links_file, "w", encoding="utf-8") as lf:
            for r in results:
                if r["status"] == "ok" and r["share_url"]:
                    lf.write(f"{r['company']}\t{r['share_url']}\n")
        print(f"\nShare links → {links_file}", file=sys.stderr)
        for r in results:
            if r["status"] == "ok" and r["share_url"]:
                print(f"{r['company']}\t{r['share_url']}")


if __name__ == "__main__":
    main()
