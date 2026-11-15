"""Ingest the documented Olist subset into PostgreSQL.

    uv run olist-ingest                    # full documented subset (~10k orders)
    uv run olist-ingest --max-orders 200   # small slice first, to check before the full load
    uv run olist-ingest --dry-run          # validate and report only; no database writes

Steps: verify source checksums against docs/source_manifest.json -> apply the subset rule ->
validate and normalize (rejections and corrections are logged) -> in ONE transaction upsert
the nine tables parent-first and write the run's audit rows. Rerunning with unchanged input
inserts and updates nothing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, text

from .config import DEFAULT_DATA_DIR, SOURCE_MANIFEST, database_url, describe, get_engine
from .load import LoadCounts, load_table
from .source import archive_sha256, check_manifest, load_sources
from .subset import DEFAULT_MODULUS, describe_rule
from .validate import LOAD_ORDER, ValidatedSubset, validate_subset


@dataclass
class RunResult:
    run_id: int | None
    subset: ValidatedSubset
    loads: dict[str, LoadCounts] = field(default_factory=dict)


def _audit_rows(run_id: int, subset: ValidatedSubset, loads: dict[str, LoadCounts]):
    files = [
        {"run_id": run_id, "file_name": s.file_name, "sha256": s.sha256,
         "size_bytes": s.size_bytes, "rows_read": s.rows_read,
         "rows_in_subset": s.rows_in_subset, "rows_rejected": s.rows_rejected,
         "rows_corrected": s.rows_corrected}
        for s in subset.file_stats.values()
    ]
    tables = [
        {"run_id": run_id, "table_name": name, "rows_loaded": c.loaded,
         "rows_inserted": c.inserted, "rows_updated": c.updated, "rows_unchanged": c.unchanged}
        for name, c in loads.items()
    ]
    measures = [{"run_id": run_id, "measure_name": k, "measure_value": v}
                for k, v in subset.measures.items()]
    issues = [
        {"run_id": run_id, "source_file": i.source_file, "source_row": i.source_row,
         "record_key": i.record_key, "rule_code": i.rule, "outcome": i.action,
         "detail": json.dumps(i.detail, default=str, sort_keys=True)}
        for i in subset.issues
    ]
    return files, tables, measures, issues


def run_ingest(engine: Engine, data_dir: Path = DEFAULT_DATA_DIR, *,
               max_orders: int | None = None, modulus: int = DEFAULT_MODULUS,
               manifest: Path | None = SOURCE_MANIFEST, dry_run: bool = False) -> RunResult:
    sources = load_sources(data_dir)
    if manifest is not None:
        problems = check_manifest(sources, manifest)
        if problems:
            raise SystemExit("Source files differ from the manifest:\n  " + "\n  ".join(problems)
                             + "\nRe-download, or pass --allow-source-change and update the manifest.")
    subset = validate_subset(sources, modulus=modulus, max_orders=max_orders)
    if dry_run:
        return RunResult(None, subset)

    with engine.begin() as conn:
        run_id = conn.execute(
            text("INSERT INTO ingest.runs (subset_rule, max_orders, source_archive_sha256) "
                 "VALUES (:rule, :max_orders, :sha) RETURNING run_id"),
            {"rule": describe_rule(modulus, max_orders), "max_orders": max_orders,
             "sha": archive_sha256(manifest) if manifest is not None else None},
        ).scalar_one()

    try:
        with engine.begin() as conn:  # all nine tables and the audit rows commit together
            loads = {name: load_table(conn, name, subset.frames[name], key)
                     for name, key in LOAD_ORDER}
            files, tables, measures, issues = _audit_rows(run_id, subset, loads)
            conn.execute(text(
                "INSERT INTO ingest.source_files (run_id, file_name, sha256, size_bytes, rows_read, "
                "rows_in_subset, rows_rejected, rows_corrected) VALUES (:run_id, :file_name, "
                ":sha256, :size_bytes, :rows_read, :rows_in_subset, :rows_rejected, :rows_corrected)"),
                files)
            conn.execute(text(
                "INSERT INTO ingest.table_loads (run_id, table_name, rows_loaded, rows_inserted, "
                "rows_updated, rows_unchanged) VALUES (:run_id, :table_name, :rows_loaded, "
                ":rows_inserted, :rows_updated, :rows_unchanged)"), tables)
            conn.execute(text(
                "INSERT INTO ingest.run_measures (run_id, measure_name, measure_value) "
                "VALUES (:run_id, :measure_name, :measure_value)"), measures)
            if issues:
                conn.execute(text(
                    "INSERT INTO ingest.data_issues (run_id, source_file, source_row, record_key, "
                    "rule_code, outcome, detail) VALUES (:run_id, :source_file, :source_row, "
                    ":record_key, :rule_code, :outcome, CAST(:detail AS jsonb))"), issues)
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(text("UPDATE ingest.runs SET status = 'failed', finished_at = now(), "
                              "error_message = :msg WHERE run_id = :run_id"),
                         {"msg": str(exc)[:2000], "run_id": run_id})
        raise
    with engine.begin() as conn:
        conn.execute(text("UPDATE ingest.runs SET status = 'succeeded', finished_at = now() "
                          "WHERE run_id = :run_id"), {"run_id": run_id})
    return RunResult(run_id, subset, loads)


def format_report(result: RunResult, target: str) -> str:
    subset = result.subset
    lines = []
    if result.run_id is None:
        lines.append(f"dry run (nothing written); target would be {target}")
    else:
        lines.append(f"run {result.run_id} succeeded -> {target}")
    lines.append("")
    lines.append(f"{'source file':42} {'read':>8} {'in subset':>10} {'rejected':>9} {'corrected':>10}")
    for s in subset.file_stats.values():
        lines.append(f"{s.file_name:42} {s.rows_read:>8} {s.rows_in_subset:>10} "
                     f"{s.rows_rejected:>9} {s.rows_corrected:>10}")
    lines.append("")
    if result.loads:
        lines.append(f"{'table':26} {'loaded':>8} {'inserted':>9} {'updated':>8} {'unchanged':>10}")
        for name, c in result.loads.items():
            lines.append(f"olist.{name:20} {c.loaded:>8} {c.inserted:>9} {c.updated:>8} {c.unchanged:>10}")
    else:
        lines.append("validated rows per table: " + ", ".join(
            f"{name}={len(frame)}" for name, frame in subset.frames.items()))
    lines.append("")
    tally: dict[tuple[str, str, str], int] = {}
    for issue in subset.issues:
        k = (issue.action, issue.rule, issue.source_file)
        tally[k] = tally.get(k, 0) + 1
    if tally:
        lines.append("data-quality decisions (action, rule, source file: rows):")
        for (action, rule, source), n in sorted(tally.items()):
            lines.append(f"  {action:9} {rule:34} {source}: {n}")
    else:
        lines.append("data-quality decisions: none (no rows rejected or corrected)")
    lines.append("")
    lines.append("source totals: " + ", ".join(f"{k}={v}" for k, v in subset.measures.items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="olist-ingest", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="folder holding the extracted Olist CSV files")
    parser.add_argument("--max-orders", type=int, default=None,
                        help="load only the first N subset orders (by order_id) as a trial slice")
    parser.add_argument("--dry-run", action="store_true", help="validate and report; write nothing")
    parser.add_argument("--allow-source-change", action="store_true",
                        help="skip the checksum comparison with docs/source_manifest.json")
    args = parser.parse_args(argv)
    if args.max_orders is not None and args.max_orders < 1:
        parser.error("--max-orders must be at least 1")

    url = database_url()
    engine = get_engine()
    try:
        result = run_ingest(engine, args.data_dir, max_orders=args.max_orders,
                            manifest=None if args.allow_source_change else SOURCE_MANIFEST,
                            dry_run=args.dry_run)
    finally:
        engine.dispose()
    print(format_report(result, describe(url)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
