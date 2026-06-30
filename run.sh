#!/usr/bin/env bash
# Flowace ROI Dashboard Generator
#
# CSV mode:
#   ./run.sh report.csv "Acme Corp"
#   ./run.sh report.csv "Acme Corp" acme_roi.html
#
# API mode:
#   ./run.sh --api "Acme Corp" --start 2026-06-01 --end 2026-06-26
#   ./run.sh --api "Acme Corp" --start 2026-06-01 --end 2026-06-26 --token "xxx"
#
# Batch mode:
#   ./run.sh --batch --from-file companies.csv --start 2026-06-01 --end 2026-06-30 --share

set -e

# ── Config ────────────────────────────────────────────────────────────────────
VENV_DIR="$(dirname "$0")/.venv"
PYTHON="$VENV_DIR/bin/python3"
ENV_FILE="$(dirname "$0")/.env"

# ── Load credentials from .env if present ────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

# ── Setup venv if missing ─────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
  echo "Setting up virtual environment…"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install boto3 --quiet
  echo "Dependencies installed."
fi

# ── Route: batch mode, API mode, or CSV mode ─────────────────────────────────
if [ "${1:-}" = "--batch" ]; then
  shift
  "$PYTHON" batch_generate.py "$@"
elif [ "${1:-}" = "--api" ]; then
  COMPANY="${2:-Flowace Tenant}"
  shift 2
  "$PYTHON" generate_roi.py --api --company "$COMPANY" "$@"
else
  CSV="${1:-}"
  COMPANY="${2:-Flowace Tenant}"
  OUTPUT="${3:-}"

  if [ -z "$CSV" ]; then
    echo "CSV mode:    ./run.sh <csv_file> [company_name] [output_file]"
    echo "API mode:    ./run.sh --api <company_name> --start YYYY-MM-DD --end YYYY-MM-DD"
    echo "Batch mode:  ./run.sh --batch --from-file companies.csv --start YYYY-MM-DD --end YYYY-MM-DD [--share]"
    exit 1
  fi

  if [ ! -f "$CSV" ]; then
    echo "Error: CSV file not found: $CSV"
    exit 1
  fi

  SLUG=$(echo "$COMPANY" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g')
  OUTPUT="${OUTPUT:-$(dirname "$0")/outputs/${SLUG}_roi.html}"

  "$PYTHON" generate_roi.py "$CSV" --company "$COMPANY" --output "$OUTPUT"
fi
