"""Shared fixtures: each test gets a brand-new database with sql/schema.sql applied.

The tests need a reachable PostgreSQL (the docker-compose service, or the CI service) and
are skipped when none is configured.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy.exc import OperationalError

from olist_pipeline.config import get_engine
from olist_pipeline.db import apply_schema


def hex_id(label: str) -> str:
    """Deterministic, obviously synthetic 32-hex identifier."""
    return hashlib.md5(label.encode("utf-8")).hexdigest()


@pytest.fixture
def fresh_db():
    try:
        admin = get_engine(database="postgres", isolation_level="AUTOCOMMIT")
        conn = admin.connect()
    except (OperationalError, SystemExit) as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")
    name = f"olist_test_{uuid.uuid4().hex[:12]}"
    conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = get_engine(database=name)
    try:
        apply_schema(engine)
        yield engine
    finally:
        engine.dispose()
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.close()
        admin.dispose()
