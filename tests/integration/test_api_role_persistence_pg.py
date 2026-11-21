"""
Role boundary against a real PostgreSQL database (opt-in).

Skipped unless ACGS_TEST_DATABASE_URL points at a PostgreSQL server, e.g.
``postgresql://postgres:postgres@localhost:5432/postgres``. The role needs
CREATEDB: each run creates its own uniquely named database on that server,
applies database/migrations/*.sql, and drops it afterwards, so no existing
database is read or written.

Requests go through the real AuthMiddleware, RBACMiddleware, get_db and
TaskService; rows are read back with plain SQL on a separate connection.
Governance is stubbed to ALLOW so the role policy is the only 403 source.
"""

import asyncio
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import backend.database as database
import backend.middleware.governance_interceptor as governance_interceptor
from backend.database import get_db
from backend.main import app
from tests.integration.test_api_auth import (  # noqa: F401  (fixtures)
    _MISSING,
    _bearer,
    auth_env,
    make_token,
    rsa_keys,
)

DATABASE_URL_ENV = "ACGS_TEST_DATABASE_URL"
MIGRATIONS = sorted(
    (Path(__file__).resolve().parents[2] / "database" / "migrations").glob("*.sql")
)
ORIGINAL_TITLE = "original title"
NEW_TITLE = "edited by an authorized caller"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_db,
    pytest.mark.skipif(
        not os.environ.get(DATABASE_URL_ENV),
        reason=f"set {DATABASE_URL_ENV} to run against PostgreSQL",
    ),
]


def _run(coro):
    return asyncio.run(coro)


async def _connect(url):
    import asyncpg

    return await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host or "localhost",
        port=url.port or 5432,
        database=url.database,
    )


@pytest.fixture(scope="module")
def pg_url():
    """Create a throwaway database with the real migrations; drop it after."""
    server = make_url(os.environ[DATABASE_URL_ENV])
    name = f"acgs_role_test_{uuid.uuid4().hex[:12]}"
    test_url = server.set(drivername="postgresql+asyncpg", database=name)

    async def setup():
        admin = await _connect(server)
        try:
            await admin.execute(f'CREATE DATABASE "{name}"')
        finally:
            await admin.close()
        conn = await _connect(test_url)
        try:
            for migration in MIGRATIONS:
                await conn.execute(migration.read_text())
        finally:
            await conn.close()

    async def teardown():
        admin = await _connect(server)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()

    assert MIGRATIONS, "no migrations found"
    try:
        _run(setup())
        yield test_url
    finally:
        _run(teardown())


@pytest.fixture(autouse=True)
def allow_governance(monkeypatch):
    governance = MagicMock()
    governance.validate_operation.return_value = {
        "action": "ALLOW",
        "violations": [],
        "decision_id": "d-test",
    }
    monkeypatch.setattr(governance_interceptor, "get_governance", lambda: governance)
    return governance


@pytest.fixture
def client(auth_env, pg_url, monkeypatch):  # noqa: F811
    # The real get_db, bound to the throwaway database. NullPool: TestClient
    # may run each request on a new event loop, so connections are not reused.
    engine = create_async_engine(pg_url, poolclass=NullPool)
    monkeypatch.setattr(
        database,
        "AsyncSessionLocal",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    assert get_db not in app.dependency_overrides
    yield TestClient(app, raise_server_exceptions=False)
    _run(engine.dispose())


@pytest.fixture
def task_id(pg_url):
    """Insert a fresh task row; return its id."""

    async def insert():
        conn = await _connect(pg_url)
        try:
            return await conn.fetchval(
                "INSERT INTO tasks (title) VALUES ($1) RETURNING id", ORIGINAL_TITLE
            )
        finally:
            await conn.close()

    return _run(insert())


def _row(pg_url, task_id):
    async def fetch():
        conn = await _connect(pg_url)
        try:
            return await conn.fetchrow(
                "SELECT title, updated_at FROM tasks WHERE id = $1", task_id
            )
        finally:
            await conn.close()

    return _run(fetch())


def _edit(client, task_id, token):
    return client.put(
        f"/api/v1/tasks/{task_id}", json={"title": NEW_TITLE}, headers=_bearer(token)
    )


def test_admin_edit_is_persisted(client, make_token, pg_url, task_id):  # noqa: F811
    response = _edit(client, task_id, make_token(role="admin"))

    assert response.status_code == 200, response.text
    assert _row(pg_url, task_id)["title"] == NEW_TITLE


def test_admin_delete_is_persisted(client, make_token, pg_url, task_id):  # noqa: F811
    response = client.delete(
        f"/api/v1/tasks/{task_id}", headers=_bearer(make_token(role="admin"))
    )

    assert response.status_code == 204, response.text
    assert _row(pg_url, task_id) is None


@pytest.mark.parametrize(
    "role",
    ["viewer", _MISSING, "Admin", ["admin"]],
    ids=["viewer", "missing", "Admin", "list"],
)
def test_viewer_edit_and_delete_leave_row_unchanged(
    client, make_token, pg_url, task_id, allow_governance, role  # noqa: F811
):
    before = _row(pg_url, task_id)
    token = make_token(role=role)

    edit = _edit(client, task_id, token)
    delete = client.delete(f"/api/v1/tasks/{task_id}", headers=_bearer(token))

    assert edit.status_code == 403
    assert delete.status_code == 403
    after = _row(pg_url, task_id)
    assert after is not None
    assert after["title"] == ORIGINAL_TITLE
    assert after["updated_at"] == before["updated_at"]
    allow_governance.validate_operation.assert_not_called()
    # Still authenticated: the viewer can read the unchanged row.
    read = client.get(f"/api/v1/tasks/{task_id}", headers=_bearer(token))
    assert read.status_code == 200, read.text
    assert read.json()["title"] == ORIGINAL_TITLE


# The search-index trigger fires on every write to these tables; before
# migration 003 it raised 'record "new" has no field ...' on all of them.
TRIGGER_CASES = [
    ("tasks", "INSERT INTO tasks (title, description, tags) VALUES ($1, 'body', NULL)"),
    ("projects", "INSERT INTO projects (name, description) VALUES ($1, 'body')"),
    ("it_assets", "INSERT INTO it_assets (name, type) VALUES ($1, 'laptop')"),
    (
        "infrastructure",
        "INSERT INTO infrastructure (name, type) VALUES ($1, 'compute')",
    ),
    (
        "documents",
        "INSERT INTO documents (title, type, content) VALUES ($1, 'report', 'body')",
    ),
]


@pytest.mark.parametrize(
    "table,insert", TRIGGER_CASES, ids=[c[0] for c in TRIGGER_CASES]
)
def test_search_index_trigger_on_every_domain_table(pg_url, table, insert):
    title_col = "title" if table in ("tasks", "documents") else "name"

    async def scenario():
        conn = await _connect(pg_url)
        try:
            entity_id = await conn.fetchval(insert + " RETURNING id", "first")
            await conn.execute(
                f"UPDATE {table} SET {title_col} = 'second' WHERE id = $1", entity_id
            )
            return await conn.fetch(
                "SELECT title, tags FROM search_index"
                " WHERE entity_type = $1 AND entity_id = $2",
                table,
                entity_id,
            )
        finally:
            await conn.close()

    rows = _run(scenario())
    assert len(rows) == 1
    assert rows[0]["title"] == "second"
    assert rows[0]["tags"] == "[]"  # NULL or absent tags index as an empty array
