"""Unit tests for ProjectService, project schemas and the Project model."""

from datetime import date, datetime
from types import SimpleNamespace
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.project import Project
from backend.schemas.project import (
    ProjectCreate,
    ProjectFilter,
    ProjectResponse,
    ProjectUpdate,
)
from backend.services.project_service import ProjectService
from tests.unit.conftest import compile_sql, executed_stmt, make_result


@pytest.mark.unit
class TestProjectSchemas:
    def test_create_defaults(self):
        p = ProjectCreate(name="Alpha")
        assert p.status == "planning"
        assert p.team == []
        assert p.budget is None

    @pytest.mark.parametrize("bad", ["", "x" * 256])
    def test_name_length_validated(self, bad):
        with pytest.raises(ValidationError):
            ProjectCreate(name=bad)

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="A", status="bogus")
        with pytest.raises(ValidationError):
            ProjectUpdate(status="bogus")
        with pytest.raises(ValidationError):
            ProjectFilter(status="bogus")

    def test_negative_budget_rejected(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="A", budget=Decimal("-1"))
        with pytest.raises(ValidationError):
            ProjectUpdate(actual_cost=Decimal("-0.01"))

    def test_update_tracks_only_set_fields(self):
        u = ProjectUpdate(name="New")
        assert u.model_dump(exclude_unset=True) == {"name": "New"}

    def test_response_from_attributes(self):
        pid = uuid4()
        obj = SimpleNamespace(
            id=pid,
            name="A",
            description=None,
            status="active",
            start_date=None,
            end_date=None,
            budget=None,
            actual_cost=None,
            team=[],
            owner_id=None,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 2),
        )
        resp = ProjectResponse.model_validate(obj)
        assert resp.id == pid and resp.status == "active"


@pytest.mark.unit
class TestProjectModel:
    def test_table_and_columns(self):
        assert Project.__tablename__ == "projects"
        cols = Project.__table__.c
        assert not cols.name.nullable
        assert cols.status.default.arg == "planning"
        assert cols.owner_id.foreign_keys

    def test_repr(self):
        p = Project(name="Alpha", status="active")
        assert "Alpha" in repr(p) and "active" in repr(p)


@pytest.mark.unit
class TestProjectServiceCrud:
    @pytest.mark.asyncio
    async def test_create_project_persists_all_fields(self, mock_db):
        owner = uuid4()
        data = ProjectCreate(
            name="Alpha",
            status="active",
            budget=Decimal("100.50"),
            team=[{"id": "x"}],
            owner_id=owner,
            start_date=date(2026, 1, 1),
        )
        project = await ProjectService.create_project(mock_db, data)

        mock_db.add.assert_called_once_with(project)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(project)
        assert isinstance(project, Project)
        assert project.name == "Alpha"
        assert project.status == "active"
        assert project.budget == Decimal("100.50")
        assert project.team == [{"id": "x"}]
        assert project.owner_id == owner
        assert project.start_date == date(2026, 1, 1)

    @pytest.mark.asyncio
    async def test_get_project_found_and_query_filters_id(self, mock_db):
        pid = uuid4()
        proj = Project(name="A")
        mock_db.execute.return_value = make_result(scalar_one_or_none=proj)

        assert await ProjectService.get_project(mock_db, pid) is proj
        sql, params = compile_sql(executed_stmt(mock_db))
        assert "WHERE projects.id =" in sql
        assert pid in params.values()

    @pytest.mark.asyncio
    async def test_get_project_not_found_returns_none(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await ProjectService.get_project(mock_db, uuid4()) is None

    @pytest.mark.asyncio
    async def test_update_applies_only_provided_fields(self, mock_db):
        proj = Project(name="Old", status="planning", description="keep")
        mock_db.execute.return_value = make_result(scalar_one_or_none=proj)

        out = await ProjectService.update_project(
            mock_db, uuid4(), ProjectUpdate(name="New", status="active")
        )

        assert out is proj
        assert proj.name == "New"
        assert proj.status == "active"
        assert proj.description == "keep"
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(proj)

    @pytest.mark.asyncio
    async def test_update_explicit_none_clears_field(self, mock_db):
        proj = Project(name="Old", description="bye")
        mock_db.execute.return_value = make_result(scalar_one_or_none=proj)
        await ProjectService.update_project(
            mock_db, uuid4(), ProjectUpdate(description=None)
        )
        assert proj.description is None
        assert proj.name == "Old"

    @pytest.mark.asyncio
    async def test_update_not_found_returns_none_without_commit(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await ProjectService.update_project(
                mock_db, uuid4(), ProjectUpdate(name="x")
            )
            is None
        )
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_found(self, mock_db):
        proj = Project(name="A")
        mock_db.execute.return_value = make_result(scalar_one_or_none=proj)
        assert await ProjectService.delete_project(mock_db, uuid4()) is True
        mock_db.delete.assert_awaited_once_with(proj)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await ProjectService.delete_project(mock_db, uuid4()) is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
class TestProjectServiceList:
    @pytest.mark.asyncio
    async def test_list_returns_items_and_total(self, mock_db):
        items = [Project(name="a"), Project(name="b")]
        mock_db.execute.side_effect = [
            make_result(scalar=7),
            make_result(scalars=items),
        ]
        out, total = await ProjectService.list_projects(mock_db)
        assert out == items and total == 7
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_list_no_filters_default_paging_and_order(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        out, total = await ProjectService.list_projects(mock_db)
        assert out == [] and total == 0
        count_sql, _ = compile_sql(executed_stmt(mock_db, 0))
        assert "count(*)" in count_sql and "WHERE" not in count_sql
        sql, params = compile_sql(executed_stmt(mock_db, 1))
        assert "WHERE" not in sql
        assert "ORDER BY projects.created_at DESC" in sql
        assert sorted(params.values()) == [0, 50]  # offset 0, limit 50

    @pytest.mark.asyncio
    async def test_list_pagination_offset(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ProjectService.list_projects(mock_db, page=3, page_size=10)
        _, params = compile_sql(executed_stmt(mock_db, 1))
        assert sorted(params.values()) == [10, 20]

    @pytest.mark.asyncio
    async def test_list_all_filters_applied_to_count_and_page(self, mock_db):
        owner = uuid4()
        filters = ProjectFilter(
            status="active",
            owner_id=owner,
            search="foo",
            start_after=date(2026, 1, 1),
            end_before=date(2026, 12, 31),
        )
        mock_db.execute.side_effect = [make_result(scalar=1), make_result()]
        await ProjectService.list_projects(mock_db, filters)

        for i in (0, 1):
            sql, params = compile_sql(executed_stmt(mock_db, i))
            assert "projects.status =" in sql
            assert "projects.owner_id =" in sql
            assert "projects.name ILIKE" in sql
            assert "projects.description ILIKE" in sql
            assert "projects.start_date >=" in sql
            assert "projects.end_date <=" in sql
            assert "active" in params.values()
            assert owner in params.values()
            assert "%foo%" in params.values()
            assert date(2026, 1, 1) in params.values()
            assert date(2026, 12, 31) in params.values()

    @pytest.mark.asyncio
    async def test_list_empty_filter_object_adds_no_where(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ProjectService.list_projects(mock_db, ProjectFilter())
        sql, _ = compile_sql(executed_stmt(mock_db, 1))
        assert "WHERE" not in sql
