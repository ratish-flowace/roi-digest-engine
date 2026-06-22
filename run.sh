#!/usr/bin/env bash
# Flowace ROI Dashboard Generator
# Usage: ./run.sh <csv_file> [company_name] [output_file]
#
# Examples:
#   ./run.sh report.csv
#   ./run.sh report.csv "Acme Corp"
#   ./run.sh report.csv "Acme Corp" acme_roi.html

set -e

# ── Config ────────────────────────────────────────────────────────────────────
VENV_DIR="$(dirname "$0")/.venv"
PYTHON="$VENV_DIR/bin/python3"
ENV_FILE="$(dirname "$0")/.env"

# ── Args ──────────────────────────────────────────────────────────────────────
CSV="${1:-}"
COMPANY="${2:-Flowace Tenant}"
OUTPUT="${3:-}"

if [ -z "$CSV" ]; then
  echo "Usage: ./run.sh <csv_file> [company_name] [output_file]"
  exit 1
fi

if [ ! -f "$CSV" ]; then
  echo "Error: CSV file not found: $CSV"
  exit 1
fi

# ── Setup venv if missing ─────────────────────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
  echo "Setting up virtual environment…"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install boto3 --quiet
  echo "Dependencies installed."
fi

# ── Load credentials from .env if present ────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
  export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# ── Run ───────────────────────────────────────────────────────────────────────
# Default output goes into outputs/
if [ -z "$OUTPUT" ]; then
  SLUG=$(echo "$COMPANY" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g')
  OUTPUT="$(dirname "$0")/outputs/${SLUG}_roi.html"
fi

ARGS=("$CSV" "--company" "$COMPANY" "--output" "$OUTPUT")

"$PYTHON" generate_roi.py "${ARGS[@]}"
