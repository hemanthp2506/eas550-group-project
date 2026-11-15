#!/usr/bin/env bash
# Download the Olist archive, verify its SHA-256 against docs/source_manifest.json and
# extract only the in-scope CSV files into data/raw/olist/ (git-ignored).
# Usage: scripts/download_olist.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URL="https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
RAW="$ROOT/data/raw"
ZIP="$RAW/brazilian-ecommerce.zip"
OUT="$RAW/olist"
EXPECTED="$(sed -n 's/.*"sha256": "\([0-9a-f]\{64\}\)".*/\1/p' "$ROOT/docs/source_manifest.json" | head -n 1)"
FILES=(
  olist_customers_dataset.csv
  olist_orders_dataset.csv
  olist_order_items_dataset.csv
  olist_products_dataset.csv
  olist_sellers_dataset.csv
  product_category_name_translation.csv
)

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

mkdir -p "$RAW" "$OUT"
if [[ ! -f "$ZIP" ]]; then
  echo "downloading $URL"
  curl -fSL --retry 3 -o "$ZIP.part" "$URL"
  mv "$ZIP.part" "$ZIP"
fi

ACTUAL="$(sha256 "$ZIP")"
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "checksum mismatch for $ZIP" >&2
  echo "  expected $EXPECTED" >&2
  echo "  actual   $ACTUAL" >&2
  echo "The published archive changed; review it and update docs/source_manifest.json." >&2
  exit 1
fi
echo "archive sha256 OK ($ACTUAL)"

unzip -o -q "$ZIP" "${FILES[@]}" -d "$OUT"
echo "extracted ${#FILES[@]} files into $OUT"
