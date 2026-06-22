#!/usr/bin/env python3
"""
Flowace ROI Dashboard Generator — CLI entry point.

Usage:
    python generate_roi.py input.csv --company "Acme Corp" [--output roi.html]

For platform/API integration, import directly:
    from roi import generate_roi_html
"""

import argparse
import os
import re
import sys

from roi import generate_roi_outputs, DEFAULT_REGION, DEFAULT_MODEL_ID


def main():
    p = argparse.ArgumentParser(
        description="Generate Flowace ROI outputs from a Workforce Efficiency CSV.\n"
                    "Produces both an interactive dashboard and an email-safe digest."
    )
    p.add_argument("csv",        help="Path to the Workforce Efficiency CSV export")
    p.add_argument("--company",  "-c", default="Flowace Tenant",
                   help="Company / tenant name shown in the dashboard")
    p.add_argument("--output",   "-o", default="",
                   help="Dashboard output path (default: outputs/<company>_roi.html)")
    p.add_argument("--region",   default=DEFAULT_REGION,
                   help=f"AWS Bedrock region (default: {DEFAULT_REGION})")
    p.add_argument("--model",    default=DEFAULT_MODEL_ID,
                   help=f"Bedrock model ID (default: {DEFAULT_MODEL_ID})")
    p.add_argument("--no-email", action="store_true",
                   help="Skip generating the email digest")
    args = p.parse_args()

    if not os.path.exists(args.csv):
        print(f"Error: file not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    slug        = re.sub(r'[^a-z0-9]', '_', args.company.lower())
    outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
    dash_out    = args.output or os.path.join(outputs_dir, f"{slug}_roi.html")
    email_out   = os.path.join(outputs_dir, f"{slug}_email.html")

    outputs = generate_roi_outputs(args.csv, args.company, args.region, args.model)

    with open(dash_out, "w", encoding="utf-8") as f:
        f.write(outputs["dashboard"])
    print(f"  Dashboard → {dash_out}  ({len(outputs['dashboard']):,} chars)", file=sys.stderr)

    if not args.no_email:
        with open(email_out, "w", encoding="utf-8") as f:
            f.write(outputs["email"])
        print(f"  Email     → {email_out}  ({len(outputs['email']):,} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
