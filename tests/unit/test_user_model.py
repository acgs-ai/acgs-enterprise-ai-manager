"""
Unit tests for the users table: model vs database/schema.sql vs migration 004.
"""

import re
from pathlib import Path

import pytest

from backend.models.user import User

pytestmark = pytest.mark.unit

DATABASE = Path(__file__).resolve().parents[2] / "database"


def _users_block() -> str:
    sql = (DATABASE / "schema.sql").read_text()
    return re.search(r"CREATE TABLE users \((.*?)\n\);", sql, re.DOTALL).group(1)


def test_model_columns_match_schema_sql():
    sql_columns = set()
    for line in _users_block().splitlines():
        m = re.match(r"\s+([a-z_]+)\s+[A-Z]", line)
        if m:
            sql_columns.add(m.group(1))
    assert sql_columns == {c.name for c in User.__table__.columns}


def test_external_subject_is_nullable_unique_and_indexed():
    column = User.__table__.c.external_subject
    assert column.nullable is True
    assert column.unique is True
    assert column.index is True


def test_schema_sql_external_subject_is_nullable_unique():
    line = next(
        line.strip()
        for line in _users_block().splitlines()
        if line.strip().startswith("external_subject ")
    )
    assert line == "external_subject TEXT,"
    # Uniqueness comes from one index whose name matches migration 004, so the
    # migration is a no-op on a database built from schema.sql.
    schema = (DATABASE / "schema.sql").read_text()
    migration = (DATABASE / "migrations" / "004_user_external_subject.sql").read_text()
    index = "CREATE UNIQUE INDEX idx_users_external_subject"
    assert schema.count(f"{index} ON users(external_subject);") == 1
    assert "IF NOT EXISTS idx_users_external_subject" in migration


def test_migration_004_adds_external_subject_idempotently():
    sql = (DATABASE / "migrations" / "004_user_external_subject.sql").read_text()
    code = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert re.search(
        r"ALTER TABLE users ADD COLUMN IF NOT EXISTS external_subject TEXT;", code
    )
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS \w+\s+ON users\(external_subject\);",
        code,
    )
    # No backfill: the subject mapping is provisioned by an administrator.
    assert "UPDATE" not in code.upper()
