"""
Shared fixtures for service-layer unit tests.

No Postgres is available (models use postgresql UUID/JSONB), so services are
exercised against a mocked ``AsyncSession``.

Helpers:
    make_result(...)  -- build a fake ``Result`` supporting the accessors the
                         services use (``scalars().all()``, ``scalar_one_or_none()``,
                         ``scalar()``, ``scalar_one()``).
    mock_db           -- ``AsyncMock(spec=AsyncSession)``; ``execute`` is an
                         AsyncMock you configure via ``mock_db.execute.side_effect
                         = [make_result(...), ...]`` (one entry per call, in order).
                         ``add`` is a plain MagicMock (sync on AsyncSession).
    compile_sql(stmt) -- render a statement with the PostgreSQL dialect to a
                         ``(sql, params)`` tuple for asserting on filters/paging.
    executed_stmt(db, n=0) -- the statement passed to the n-th ``db.execute`` call.
"""

from typing import Any, Dict, Tuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession


def make_result(
    scalars: Any = None, scalar_one_or_none: Any = None, scalar: Any = None
) -> MagicMock:
    """Fake SQLAlchemy Result.

    ``scalars`` is the list returned by ``result.scalars().all()``.
    ``scalar_one_or_none`` feeds ``result.scalar_one_or_none()`` (also
    ``scalar_one()``); ``scalar`` feeds ``result.scalar()``.
    """
    result = MagicMock(name="Result")
    result.scalars.return_value.all.return_value = list(scalars or [])
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.scalar_one.return_value = scalar_one_or_none
    result.scalar.return_value = scalar
    return result


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mocked AsyncSession with an AsyncMock ``execute`` and ``get``."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.get = AsyncMock(return_value=None)
    return db


def compile_sql(stmt: Any) -> Tuple[str, Dict[str, Any]]:
    """Compile ``stmt`` for PostgreSQL; return (sql_text, bind_params)."""
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def executed_stmt(db: AsyncMock, n: int = 0) -> Any:
    """Statement passed as first positional arg to the n-th ``db.execute`` call."""
    return db.execute.call_args_list[n].args[0]
