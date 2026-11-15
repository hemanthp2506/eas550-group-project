"""Paths and database connection settings.

Credentials are read only from environment variables. A local ``.env`` file (git-ignored) is
loaded first if present, without overriding variables that are already set.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"
SCHEMA_SQL = SQL_DIR / "schema.sql"
VERIFY_SQL = SQL_DIR / "verify.sql"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "olist"
SOURCE_MANIFEST = PROJECT_ROOT / "docs" / "source_manifest.json"

_REQUIRED_PG_VARS = ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")


def load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def database_url(database: str | None = None) -> URL:
    """Build the SQLAlchemy URL from DATABASE_URL, or else from the libpq PG* variables."""
    load_env()
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        url = make_url(raw)
        if url.drivername in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
    else:
        missing = [name for name in _REQUIRED_PG_VARS if not os.environ.get(name)]
        if missing:
            raise SystemExit(
                f"Missing environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in, or set DATABASE_URL."
            )
        sslmode = os.environ.get("PGSSLMODE", "").strip()
        url = URL.create(
            "postgresql+psycopg",
            username=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            host=os.environ["PGHOST"],
            port=int(os.environ.get("PGPORT") or 5432),
            database=os.environ["PGDATABASE"],
            query={"sslmode": sslmode} if sslmode else {},
        )
    if database:
        url = url.set(database=database)
    return url


def get_engine(database: str | None = None, **kwargs) -> Engine:
    return create_engine(database_url(database), pool_pre_ping=True, **kwargs)


def describe(url: URL) -> str:
    """Connection target for log lines, with the password hidden."""
    return url.render_as_string(hide_password=True)
