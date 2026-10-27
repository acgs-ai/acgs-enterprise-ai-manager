"""
TaskMetrics must use the task status values the API accepts ("done"), not
"completed", which no task can have.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from backend.reports.task_metrics import TaskMetrics


def _db():
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = 0
    result.all.return_value = []
    db.execute.return_value = result
    return db


def _queries(db):
    return [
        str(
            call.args[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        for call in db.execute.call_args_list
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,args",
    [
        ("get_completion_rate", ()),
        ("get_completion_trend", ()),
        ("get_average_completion_time", ()),
    ],
)
async def test_completed_means_status_done(method, args):
    db = _db()
    await getattr(TaskMetrics, method)(db, *args)

    sql = "\n".join(_queries(db))
    assert "tasks.status = 'done'" in sql
    assert "completed'" not in sql


@pytest.mark.asyncio
async def test_overdue_excludes_done_and_cancelled():
    db = _db()
    await TaskMetrics.get_overdue_tasks(db)

    queries = _queries(db)
    assert len(queries) == 2
    for sql in queries:
        assert "tasks.status NOT IN ('done', 'cancelled')" in sql
        assert "completed'" not in sql
