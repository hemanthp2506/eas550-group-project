"""Reading the Olist CSV files with provenance (checksum, size, row numbers)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Logical name -> file name inside the Kaggle archive. Reviews, payments and the large
# geolocation file are out of scope for Phase 1.
SOURCE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

ROW = "_source_row"  # 1-based data row number (header excluded), kept for issue reporting


@dataclass
class SourceFile:
    key: str
    path: Path
    sha256: str
    size_bytes: int
    frame: pd.DataFrame = field(repr=False)

    @property
    def name(self) -> str:
        return self.path.name


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    """Read every column as text so nothing is coerced (zip prefixes keep leading zeros).

    Empty cells stay as '' here; validation decides what an empty value means per column.
    utf-8-sig strips the byte-order mark present in the category translation file.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    frame.insert(0, ROW, range(1, len(frame) + 1))
    return frame


def load_sources(data_dir: Path) -> dict[str, SourceFile]:
    missing = [name for name in SOURCE_FILES.values() if not (data_dir / name).is_file()]
    if missing:
        raise SystemExit(
            f"Missing source files in {data_dir}: {', '.join(missing)}. "
            "Run scripts/download_olist.sh first."
        )
    sources = {}
    for key, name in SOURCE_FILES.items():
        path = data_dir / name
        sources[key] = SourceFile(key, path, sha256_of(path), path.stat().st_size, read_csv(path))
    return sources


def check_manifest(sources: dict[str, SourceFile], manifest_path: Path) -> list[str]:
    """Compare file checksums with the committed manifest; return human-readable mismatches."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {entry["file"]: entry["sha256"] for entry in manifest["files"]}
    problems = []
    for source in sources.values():
        want = expected.get(source.name)
        if want is None:
            problems.append(f"{source.name}: not listed in {manifest_path.name}")
        elif want != source.sha256:
            problems.append(f"{source.name}: sha256 {source.sha256} != manifest {want}")
    return problems


def archive_sha256(manifest_path: Path) -> str | None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("archive", {}).get("sha256")
