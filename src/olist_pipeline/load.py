"""Rerun-safe loading: pandas ``to_sql(if_exists="append")`` into the existing designed tables,
with a PostgreSQL upsert as the duplicate-handling strategy.

For every row:  INSERT ... ON CONFLICT (primary key) DO UPDATE SET <non-key columns>
                WHERE (current non-key values) IS DISTINCT FROM (incoming values)

so a new key is inserted, a changed row is updated in place, and an unchanged row is not
touched at all (no new row version). ``RETURNING (xmax = 0)`` tells inserts from updates;
rows that return nothing were unchanged. The tables are never dropped or replaced.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Connection, literal_column, text, tuple_
from sqlalchemy import types as sqltypes
from sqlalchemy.dialects.postgresql import insert

SCHEMA = "olist"
CHUNK_ROWS = 1000  # keeps each multi-row INSERT far below PostgreSQL's 65,535 parameter limit

# Base types of the designed columns (domains resolve to their base type), so pandas sends
# every value with the type the table declares instead of guessing from Python objects.
_BASE_TYPES = {
    "text": sqltypes.Text,
    "smallint": sqltypes.SmallInteger,
    "integer": sqltypes.Integer,
    "bigint": sqltypes.BigInteger,
    "date": sqltypes.Date,
    "timestamp without time zone": sqltypes.DateTime,
}


def column_types(conn: Connection, table: str) -> dict[str, sqltypes.TypeEngine]:
    rows = conn.execute(text(
        "SELECT column_name, data_type, numeric_precision, numeric_scale "
        "FROM information_schema.columns WHERE table_schema = :schema AND table_name = :table"),
        {"schema": SCHEMA, "table": table}).all()
    if not rows:
        raise RuntimeError(f"{SCHEMA}.{table} does not exist; run 'olist-db init' first")
    return {
        name: sqltypes.Numeric(precision, scale) if data_type == "numeric"
        else _BASE_TYPES[data_type]()
        for name, data_type, precision, scale in rows
    }


@dataclass
class LoadCounts:
    loaded: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def _upsert_method(primary_key: list[str], counts: LoadCounts):
    """Build a pandas ``to_sql`` insertion method that upserts and counts the outcome."""

    def method(pd_table, conn: Connection, keys: list[str], data_iter) -> int:
        rows = [dict(zip(keys, values)) for values in data_iter]
        if not rows:
            return 0
        table = pd_table.table
        stmt = insert(table).values(rows)
        non_key = [column for column in keys if column not in primary_key]
        if non_key:
            changed = tuple_(*(table.c[c] for c in non_key)).is_distinct_from(
                tuple_(*(stmt.excluded[c] for c in non_key)))
            stmt = stmt.on_conflict_do_update(
                index_elements=primary_key,
                set_={c: stmt.excluded[c] for c in non_key},
                where=changed,
            )
        else:  # key-only table (olist.customers): nothing can change
            stmt = stmt.on_conflict_do_nothing(index_elements=primary_key)
        returned = conn.execute(stmt.returning(literal_column("(xmax = 0)").label("inserted")))
        flags = [bool(row.inserted) for row in returned]
        counts.inserted += sum(flags)
        counts.updated += len(flags) - sum(flags)
        counts.unchanged += len(rows) - len(flags)
        return len(flags)

    return method


def load_table(conn: Connection, table: str, frame: pd.DataFrame,
               primary_key: list[str]) -> LoadCounts:
    """Append one validated frame into olist.<table> inside the caller's transaction."""
    if frame.duplicated(primary_key).any():  # one statement may not touch the same key twice
        raise ValueError(f"{table}: duplicate primary keys survived validation")
    counts = LoadCounts(loaded=len(frame))
    declared = column_types(conn, table)
    unknown = set(frame.columns) - set(declared)
    if unknown:
        raise ValueError(f"{table}: columns not in the designed table: {sorted(unknown)}")
    frame.to_sql(
        table,
        conn,
        schema=SCHEMA,
        if_exists="append",  # the designed table must already exist; never "replace"
        index=False,
        chunksize=CHUNK_ROWS,
        dtype={column: declared[column] for column in frame.columns},
        method=_upsert_method(primary_key, counts),
    )
    return counts
