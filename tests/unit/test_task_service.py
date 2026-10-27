"""Unit tests for TaskService, task schemas and the Task model."""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.asset import ITAsset
from backend.models.infrastructure import Infrastructure
from backend.models.task import Task
from backend.schemas.task import (
    TaskCreate,
    TaskFilter,
    TaskLinkRequest,
    TaskResponse,
    TaskUpdate,
)
from backend.services.task_service import TaskService
from tests.unit.conftest import compile_sql, executed_stmt, make_result


@pytest.mark.unit
class TestTaskSchemas:
    def test_create_defaults(self):
        t = TaskCreate(title="T")
        assert (t.status, t.priority, t.tags) == ("todo", "medium", [])

    def test_title_validated(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="")
        with pytest.raises(ValidationError):
            TaskCreate(title="x" * 256)
        with pytest.raises(ValidationError):
            TaskCreate()

    @pytest.mark.parametrize(
        "s", ["todo", "in_progress", "blocked", "review", "done", "cancelled"]
    )
    def test_valid_statuses(self, s):
        assert TaskCreate(title="T", status=s).status == s

    def test_invalid_status_priority(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="T", status="finished")
        with pytest.raises(ValidationError):
            TaskCreate(title="T", priority="critical")
        with pytest.raises(ValidationError):
            TaskUpdate(status="finished")
        with pytest.raises(ValidationError):
            TaskFilter(priority="critical")

    def test_hours_bounds(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="T", estimated_hours=Decimal("-1"))
        with pytest.raises(ValidationError):
            TaskCreate(title="T", actual_hours=Decimal("1000"))
        assert TaskCreate(title="T", estimated_hours=Decimal("999.99")).estimated_hours

    def test_update_only_set_fields(self):
        assert TaskUpdate(priority="high").model_dump(exclude_unset=True) == {
            "priority": "high"
        }

    def test_filter_search_max_length(self):
        with pytest.raises(ValidationError):
            TaskFilter(search="x" * 256)

    def test_link_request_relationship_type(self):
        eid = uuid4()
        assert TaskLinkRequest(entity_id=eid, relationship_type="uses").entity_id == eid
        with pytest.raises(ValidationError):
            TaskLinkRequest(entity_id=eid, relationship_type="hates")
        with pytest.raises(ValidationError):
            TaskLinkRequest(entity_id="not-a-uuid")

    def test_response_from_attributes(self):
        obj = SimpleNamespace(
            id=uuid4(),
            title="T",
            description=None,
            status="done",
            priority="low",
            assignee_id=None,
            project_id=None,
            due_date=None,
            estimated_hours=None,
            actual_hours=None,
            tags=["a"],
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
            completed_at=None,
        )
        assert TaskResponse.model_validate(obj).tags == ["a"]


@pytest.mark.unit
class TestTaskModel:
    def test_columns_and_relationships(self):
        assert Task.__tablename__ == "tasks"
        assert not Task.__table__.c.title.nullable
        rels = {r.key for r in Task.__mapper__.relationships}
        assert {"assignee", "project", "assets", "infrastructure"} <= rels

    def test_repr(self):
        r = repr(Task(title="Fix", status="todo"))
        assert "Fix" in r and "todo" in r


@pytest.mark.unit
class TestTaskServiceCrud:
    @pytest.mark.asyncio
    async def test_create_task(self, mock_db):
        proj = uuid4()
        task = await TaskService.create_task(
            mock_db,
            TaskCreate(title="T", priority="urgent", project_id=proj, tags=["a", "b"]),
        )
        mock_db.add.assert_called_once_with(task)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(task)
        assert (task.title, task.priority, task.status) == ("T", "urgent", "todo")
        assert task.project_id == proj and task.tags == ["a", "b"]

    @pytest.mark.asyncio
    async def test_get_task_found_and_not_found(self, mock_db):
        tid = uuid4()
        t = Task(title="T")
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        assert await TaskService.get_task(mock_db, tid) is t
        sql, params = compile_sql(executed_stmt(mock_db))
        assert "WHERE tasks.id =" in sql and tid in params.values()
        assert not executed_stmt(mock_db)._with_options

        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await TaskService.get_task(mock_db, tid) is None

    @pytest.mark.asyncio
    async def test_get_task_include_relations(self, mock_db):
        mock_db.execute.return_value = make_result()
        await TaskService.get_task(mock_db, uuid4(), include_relations=True)
        assert len(executed_stmt(mock_db)._with_options) == 4

    @pytest.mark.asyncio
    async def test_update_only_provided_fields(self, mock_db):
        old = datetime(2020, 1, 1)
        t = Task(title="Old", priority="low", status="todo", updated_at=old)
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        out = await TaskService.update_task(
            mock_db, uuid4(), TaskUpdate(title="New", status="in_progress")
        )
        assert out is t
        assert (t.title, t.status, t.priority) == ("New", "in_progress", "low")
        assert t.completed_at is None
        assert t.updated_at > old
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(t)

    @pytest.mark.asyncio
    async def test_update_to_done_sets_completed_at(self, mock_db):
        t = Task(title="T", status="todo")
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        before = datetime.utcnow()
        await TaskService.update_task(mock_db, uuid4(), TaskUpdate(status="done"))
        assert t.status == "done"
        assert t.completed_at is not None and t.completed_at >= before

    @pytest.mark.asyncio
    async def test_update_to_done_keeps_existing_completed_at(self, mock_db):
        done_at = datetime(2020, 1, 1)
        t = Task(title="T", status="done", completed_at=done_at)
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        await TaskService.update_task(mock_db, uuid4(), TaskUpdate(status="done"))
        assert t.completed_at == done_at

    @pytest.mark.asyncio
    async def test_update_other_status_does_not_set_completed_at(self, mock_db):
        t = Task(title="T", status="todo")
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        await TaskService.update_task(mock_db, uuid4(), TaskUpdate(status="review"))
        assert t.completed_at is None

    @pytest.mark.asyncio
    async def test_reopening_done_task_clears_completed_at(self, mock_db):
        t = Task(title="T", status="done", completed_at=datetime(2020, 1, 1))
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        await TaskService.update_task(
            mock_db, uuid4(), TaskUpdate(status="in_progress")
        )
        assert t.completed_at is None

    @pytest.mark.asyncio
    async def test_update_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await TaskService.update_task(mock_db, uuid4(), TaskUpdate(title="x"))
            is None
        )
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_found_and_not_found(self, mock_db):
        t = Task(title="T")
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        assert await TaskService.delete_task(mock_db, uuid4()) is True
        mock_db.delete.assert_awaited_once_with(t)
        mock_db.commit.assert_awaited_once()

        mock_db.delete.reset_mock()
        mock_db.commit.reset_mock()
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await TaskService.delete_task(mock_db, uuid4()) is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
class TestTaskServiceList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, mock_db):
        items = [Task(title="a"), Task(title="b")]
        mock_db.execute.side_effect = [
            make_result(scalar=9),
            make_result(scalars=items),
        ]
        out, total = await TaskService.list_tasks(mock_db)
        assert out == items and total == 9

    @pytest.mark.asyncio
    async def test_defaults_paging_order(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await TaskService.list_tasks(mock_db)
        stmt = executed_stmt(mock_db, 1)
        sql, params = compile_sql(stmt)
        assert "WHERE" not in sql
        assert "ORDER BY tasks.created_at DESC" in sql
        assert sorted(params.values()) == [0, 50]
        assert not stmt._with_options

    @pytest.mark.asyncio
    async def test_pagination_offset(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await TaskService.list_tasks(mock_db, page=2, page_size=5)
        _, params = compile_sql(executed_stmt(mock_db, 1))
        assert sorted(params.values()) == [5, 5]

    @pytest.mark.asyncio
    async def test_include_relations(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await TaskService.list_tasks(mock_db, include_relations=True)
        assert len(executed_stmt(mock_db, 1)._with_options) == 4

    @pytest.mark.asyncio
    async def test_all_filters_applied(self, mock_db):
        a, p = uuid4(), uuid4()
        due_b, due_a = datetime(2026, 12, 31), datetime(2026, 1, 1)
        filters = TaskFilter(
            status="blocked",
            priority="high",
            assignee_id=a,
            project_id=p,
            search="bug",
            tags=["x", "y"],
            due_before=due_b,
            due_after=due_a,
        )
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await TaskService.list_tasks(mock_db, filters)

        for i in (0, 1):
            sql, params = compile_sql(executed_stmt(mock_db, i))
            for frag in (
                "tasks.status =",
                "tasks.priority =",
                "tasks.assignee_id =",
                "tasks.project_id =",
                "tasks.title ILIKE",
                "tasks.description ILIKE",
                "tasks.due_date <=",
                "tasks.due_date >=",
            ):
                assert frag in sql, frag
            # one JSONB containment condition per tag
            assert sql.count("tasks.tags @>") == 2
            vals = list(params.values())
            for v in ("blocked", "high", a, p, "%bug%", due_b, due_a):
                assert v in vals, v

    @pytest.mark.asyncio
    async def test_empty_filter_no_where(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await TaskService.list_tasks(mock_db, TaskFilter(tags=[]))
        sql, _ = compile_sql(executed_stmt(mock_db, 1))
        assert "WHERE" not in sql


@pytest.mark.unit
class TestTaskLinking:
    @pytest.mark.asyncio
    async def test_link_asset_task_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await TaskService.link_asset(mock_db, uuid4(), uuid4()) is None
        mock_db.get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_link_asset_appends_and_commits(self, mock_db):
        t = Task(title="T")
        t.assets = []
        asset = ITAsset(name="a", type="server")
        aid = uuid4()
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        mock_db.get.return_value = asset

        out = await TaskService.link_asset(mock_db, uuid4(), aid)

        assert out is t and t.assets == [asset]
        mock_db.get.assert_awaited_once_with(ITAsset, aid)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(t)
        assert len(executed_stmt(mock_db)._with_options) == 4

    @pytest.mark.asyncio
    async def test_link_asset_already_linked_is_noop(self, mock_db):
        asset = ITAsset(name="a", type="server")
        t = Task(title="T")
        t.assets = [asset]
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        mock_db.get.return_value = asset
        await TaskService.link_asset(mock_db, uuid4(), uuid4())
        assert t.assets == [asset]
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_link_asset_missing_asset_returns_task_unchanged(self, mock_db):
        t = Task(title="T")
        t.assets = []
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        mock_db.get.return_value = None
        assert await TaskService.link_asset(mock_db, uuid4(), uuid4()) is t
        assert t.assets == []
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_link_infrastructure_task_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await TaskService.link_infrastructure(mock_db, uuid4(), uuid4()) is None

    @pytest.mark.asyncio
    async def test_link_infrastructure_appends_and_commits(self, mock_db):
        t = Task(title="T")
        t.infrastructure = []
        infra = Infrastructure(name="i")
        iid = uuid4()
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        mock_db.get.return_value = infra

        out = await TaskService.link_infrastructure(mock_db, uuid4(), iid)

        assert out is t and t.infrastructure == [infra]
        mock_db.get.assert_awaited_once_with(Infrastructure, iid)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(t)

    @pytest.mark.asyncio
    async def test_link_infrastructure_duplicate_and_missing(self, mock_db):
        infra = Infrastructure(name="i")
        t = Task(title="T")
        t.infrastructure = [infra]
        mock_db.execute.return_value = make_result(scalar_one_or_none=t)
        mock_db.get.return_value = infra
        await TaskService.link_infrastructure(mock_db, uuid4(), uuid4())
        assert t.infrastructure == [infra]

        mock_db.get.return_value = None
        await TaskService.link_infrastructure(mock_db, uuid4(), uuid4())
        mock_db.commit.assert_not_awaited()
