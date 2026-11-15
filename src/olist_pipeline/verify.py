"""Run sql/verify.sql, evaluate its checks and save the evidence.

    uv run olist-verify                                       # print the report
    uv run olist-verify --label run1 --out docs/evidence      # also save .md and .json
    uv run olist-verify --label run2 --out docs/evidence --compare run1

``--compare`` fails if any table fingerprint or reconciled measure differs from the earlier
evidence file, which proves a rerun left the logical data unchanged (row counts alone would
miss an updated value). The exit code is 1 when an ``error`` check fails.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine

from .config import VERIFY_SQL, database_url, get_engine

BLOCK = re.compile(r"^-- name: (?P<name>\w+)\s*\n-- title: (?P<title>.+?)\s*\n", re.MULTILINE)


@dataclass
class Block:
    name: str
    title: str
    sql: str
    columns: list[str] | None = None
    rows: list[tuple] | None = None


def parse_blocks(sql_text: str) -> list[Block]:
    matches = list(BLOCK.finditer(sql_text))
    blocks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sql_text)
        body = sql_text[match.end():end].strip()
        blocks.append(Block(match["name"], match["title"], body))
    return blocks


def run_blocks(engine: Engine, blocks: list[Block]) -> list[Block]:
    with engine.connect() as conn:
        conn = conn.execution_options(no_parameters=True)
        for block in blocks:
            result = conn.exec_driver_sql(block.sql)
            block.columns = list(result.keys())
            block.rows = [tuple(row) for row in result]
        conn.rollback()  # read-only: nothing to keep
    return blocks


def _fmt(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S%z")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return str(value).replace("|", "\\|")


def _same(observed, expected) -> bool:
    if observed is None or expected is None:
        return observed is expected
    return Decimal(str(observed)) == Decimal(str(expected))


def evaluate(blocks: list[Block]) -> list[dict]:
    checks = []
    for block in blocks:
        if not block.name.startswith("check_"):
            continue
        for check_name, severity, observed, expected in block.rows:
            ok = _same(observed, expected)
            status = "PASS" if ok else ("FAIL" if severity == "error" else "WARN")
            checks.append({"block": block.name, "check": check_name, "severity": severity,
                           "observed": _fmt(observed), "expected": _fmt(expected),
                           "status": status})
    return checks


def snapshot(blocks: list[Block]) -> dict:
    """The comparable part of the evidence: fingerprints and reconciled measures."""
    by_name = {b.name: b for b in blocks}
    fingerprints = {row[0]: {"rows": int(row[1]), "md5": row[2]}
                    for row in by_name["fingerprints"].rows}
    measures = {row[0].removeprefix("source vs database: "): _fmt(row[2])
                for row in by_name["check_measures"].rows}
    return {"fingerprints": fingerprints, "measures": measures}


def compare(current: dict, previous: dict) -> list[dict]:
    out = []
    for kind in ("fingerprints", "measures"):
        for key in sorted(set(current[kind]) | set(previous[kind])):
            before, after = previous[kind].get(key), current[kind].get(key)
            out.append({"item": f"{kind[:-1]}: {key}", "before": json.dumps(before),
                        "after": json.dumps(after), "same": before == after})
    return out


def _table(columns: list[str], rows: list[tuple]) -> list[str]:
    if not rows:
        return ["_(no rows)_"]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in rows]
    return lines


def render(label: str, target: str, blocks: list[Block], checks: list[dict],
           comparison: list[dict] | None, compare_label: str | None) -> str:
    failed = [c for c in checks if c["status"] == "FAIL"]
    warned = [c for c in checks if c["status"] == "WARN"]
    lines = [
        f"# Verification evidence: {label}",
        "",
        f"- generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- database: `{target}`",
        f"- checks: {len(checks)} total, {len(checks) - len(failed) - len(warned)} pass, "
        f"{len(warned)} warn (known source anomalies), {len(failed)} fail",
        "",
    ]
    if comparison is not None:
        changed = [c for c in comparison if not c["same"]]
        lines += [f"## Comparison with `{compare_label}`", "",
                  f"{len(comparison) - len(changed)} of {len(comparison)} fingerprints/measures identical"
                  + (" (logical data unchanged)." if not changed else "; DIFFERENCES below."), ""]
        lines += _table(["item", "before", "after", "same"],
                        [(c["item"], c["before"], c["after"], "yes" if c["same"] else "NO")
                         for c in comparison])
        lines.append("")
    for block in blocks:
        lines += [f"## {block.title}", "", f"<sub>`{block.name}` in sql/verify.sql</sub>", ""]
        if block.name.startswith("check_"):
            rows = [(c["check"], c["severity"], c["observed"], c["expected"], c["status"])
                    for c in checks if c["block"] == block.name]
            lines += _table(["check", "severity", "observed", "expected", "status"], rows)
        else:
            lines += _table(block.columns, block.rows)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="olist-verify", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="adhoc", help="evidence label, e.g. slice, run1, run2")
    parser.add_argument("--out", type=Path, help="folder to write verify_<label>.md/.json into")
    parser.add_argument("--compare", metavar="LABEL",
                        help="compare fingerprints/measures with <out>/verify_<LABEL>.json")
    args = parser.parse_args(argv)
    if args.compare and not args.out:
        parser.error("--compare needs --out (the folder holding the earlier evidence)")

    url = database_url()
    target = f"{url.host}:{url.port}/{url.database}"
    engine = get_engine()
    try:
        blocks = run_blocks(engine, parse_blocks(VERIFY_SQL.read_text(encoding="utf-8")))
    finally:
        engine.dispose()
    checks = evaluate(blocks)
    current = snapshot(blocks)
    comparison = None
    if args.compare:
        previous = json.loads((args.out / f"verify_{args.compare}.json").read_text())
        comparison = compare(current, previous)

    report = render(args.label, target, blocks, checks, comparison, args.compare)
    print(report)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"verify_{args.label}.md").write_text(report + "\n", encoding="utf-8")
        payload = {"label": args.label, "database": target, **current, "checks": checks}
        if comparison is not None:
            payload["comparison_with"] = args.compare
            payload["comparison"] = comparison
        (args.out / f"verify_{args.label}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    failed = any(c["status"] == "FAIL" for c in checks)
    changed = comparison is not None and not all(c["same"] for c in comparison)
    return 1 if failed or changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
