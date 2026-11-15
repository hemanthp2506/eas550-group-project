"""Database setup commands: create the schema from sql/schema.sql, or rebuild it.

    uv run olist-db init [--create-database]   # empty database -> schema
    uv run olist-db reset --yes                 # DROP both schemas, then init (destroys data)
"""

from __future__ import annotations

import argparse

from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from .config import SCHEMA_SQL, database_url, describe, get_engine

SCHEMAS = ("olist", "ingest")


def apply_schema(engine: Engine) -> None:
    """Execute sql/schema.sql in a single transaction (all objects or none)."""
    ddl = SCHEMA_SQL.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execution_options(no_parameters=True).exec_driver_sql(ddl)


def schema_exists(engine: Engine) -> bool:
    with engine.connect() as conn:
        found = conn.execute(
            text("SELECT count(*) FROM pg_namespace WHERE nspname = ANY(:names)"),
            {"names": list(SCHEMAS)},
        ).scalar_one()
    return found > 0


def create_database_if_missing(name: str) -> bool:
    """CREATE DATABASE needs autocommit and a connection to another database."""
    admin = get_engine(database="postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).first()
            if exists:
                return False
            quoted = conn.dialect.identifier_preparer.quote(name)
            conn.exec_driver_sql(f"CREATE DATABASE {quoted}")
            return True
    finally:
        admin.dispose()


def drop_schemas(engine: Engine) -> None:
    with engine.begin() as conn:
        for schema in SCHEMAS:
            conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="olist-db", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create the olist and ingest schemas in an empty database")
    init.add_argument("--create-database", action="store_true",
                      help="create the target database first if it does not exist")
    reset = sub.add_parser("reset", help="drop the olist and ingest schemas and recreate them")
    reset.add_argument("--yes", action="store_true", help="confirm that all loaded data is deleted")
    args = parser.parse_args(argv)

    url = database_url()
    if args.command == "init" and args.create_database:
        created = create_database_if_missing(url.database)
        print(f"database {url.database!r}: {'created' if created else 'already exists'}")

    engine = get_engine()
    try:
        if args.command == "reset":
            if not args.yes:
                parser.error("reset deletes all loaded data; re-run with --yes to confirm")
            drop_schemas(engine)
            print("dropped schemas: " + ", ".join(SCHEMAS))
        elif schema_exists(engine):
            print(f"{describe(url)} already has the olist/ingest schemas; "
                  "use 'olist-db reset --yes' to rebuild (this deletes loaded data).")
            return 1
        try:
            apply_schema(engine)
        except ProgrammingError as exc:
            print(f"schema.sql failed: {exc.orig}")
            return 1
        print(f"applied {SCHEMA_SQL.name} to {describe(url)}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
