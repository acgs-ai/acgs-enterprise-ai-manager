"""Unit tests for InfrastructureService and infrastructure schemas (mocked AsyncSession)."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from backend.models.infrastructure import Infrastructure
from backend.schemas.infrastructure import (
    InfrastructureCreate,
    InfrastructureFilter,
    InfrastructureResponse,
    InfrastructureUpdate,
)
from backend.services.infrastructure_service import InfrastructureService


def _sql(stmt):
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def _result(one=None, items=None, scalar=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = one
    r.scalars.return_value.all.return_value = items or []
    r.scalar.return_value = scalar
    return r


@pytest.fixture
def db():
    session = MagicMock()
    session.add = MagicMock()
    for name in ("commit", "refresh", "delete", "execute", "flush"):
        setattr(session, name, AsyncMock())
    return session


@pytest.mark.unit
class TestSchemas:
    def test_create_defaults(self):
        c = InfrastructureCreate(name="web", type="compute")
        assert c.status == "operational"
        assert c.dependencies == []
        assert c.capacity is None

    @pytest.mark.parametrize("bad", ["", "x" * 256])
    def test_name_length(self, bad):
        with pytest.raises(ValidationError):
            InfrastructureCreate(name=bad, type="compute")

    def test_invalid_type_and_status(self):
        with pytest.raises(ValidationError):
            InfrastructureCreate(name="a", type="mainframe")
        with pytest.raises(ValidationError):
            InfrastructureCreate(name="a", type="compute", status="broken")

    @pytest.mark.parametrize(
        "t", ["compute", "network", "storage", "database", "security", "monitoring"]
    )
    def test_all_valid_types(self, t):
        assert InfrastructureCreate(name="a", type=t).type == t

    def test_dependencies_default_not_shared(self):
        a = InfrastructureCreate(name="a", type="compute")
        a.dependencies.append("x")
        assert InfrastructureCreate(name="b", type="compute").dependencies == []

    def test_update_all_optional_and_validates(self):
        assert InfrastructureUpdate().model_dump(exclude_unset=True) == {}
        with pytest.raises(ValidationError):
            InfrastructureUpdate(status="nope")
        with pytest.raises(ValidationError):
            InfrastructureUpdate(name="")

    def test_filter_validates_enums(self):
        with pytest.raises(ValidationError):
            InfrastructureFilter(type="bogus")
        assert InfrastructureFilter(status="down").status == "down"

    def test_response_from_attributes(self):
        from datetime import datetime

        obj = MagicMock(
            id=uuid4(),
            name="n",
            type="compute",
            status="down",
            capacity=None,
            location=None,
            dependencies=[],
            configuration=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        obj.name = "n"
        r = InfrastructureResponse.model_validate(obj)
        assert r.status == "down" and r.name == "n"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateGetDelete:
    async def test_create_sets_fields_and_commits(self, db):
        data = InfrastructureCreate(
            name="db1",
            type="database",
            location="eu",
            dependencies=["net"],
            capacity={"cpu": 4},
        )
        infra = await InfrastructureService.create_infrastructure(db, data)
        assert isinstance(infra, Infrastructure)
        assert (infra.name, infra.type, infra.status) == (
            "db1",
            "database",
            "operational",
        )
        assert infra.dependencies == ["net"] and infra.capacity == {"cpu": 4}
        db.add.assert_called_once_with(infra)
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(infra, ["tasks"])

    async def test_get_found_and_filters_by_id(self, db):
        obj = Infrastructure(name="a", type="compute")
        db.execute.return_value = _result(one=obj)
        iid = uuid4()
        assert await InfrastructureService.get_infrastructure(db, iid) is obj
        sql, params = _sql(db.execute.call_args.args[0])
        assert "WHERE infrastructure.id" in sql
        assert iid in params.values()

    async def test_get_not_found_returns_none(self, db):
        db.execute.return_value = _result(one=None)
        assert await InfrastructureService.get_infrastructure(db, uuid4()) is None

    async def test_delete_found(self, db):
        obj = Infrastructure(name="a", type="compute")
        db.execute.return_value = _result(one=obj)
        assert await InfrastructureService.delete_infrastructure(db, uuid4()) is True
        db.delete.assert_awaited_once_with(obj)
        db.commit.assert_awaited_once()

    async def test_delete_missing_does_not_touch_db(self, db):
        db.execute.return_value = _result(one=None)
        assert await InfrastructureService.delete_infrastructure(db, uuid4()) is False
        db.delete.assert_not_awaited()
        db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdate:
    async def test_partial_update_only_set_fields(self, db):
        obj = Infrastructure(
            name="old", type="compute", status="operational", location="us"
        )
        db.execute.return_value = _result(one=obj)
        out = await InfrastructureService.update_infrastructure(
            db, uuid4(), InfrastructureUpdate(status="degraded")
        )
        assert out is obj
        assert obj.status == "degraded"
        assert obj.name == "old" and obj.location == "us"
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(obj, ["tasks"])

    async def test_explicit_none_clears_field(self, db):
        obj = Infrastructure(name="old", type="compute", location="us")
        db.execute.return_value = _result(one=obj)
        await InfrastructureService.update_infrastructure(
            db, uuid4(), InfrastructureUpdate(location=None)
        )
        assert obj.location is None

    async def test_empty_update_changes_nothing(self, db):
        obj = Infrastructure(name="old", type="compute")
        db.execute.return_value = _result(one=obj)
        await InfrastructureService.update_infrastructure(
            db, uuid4(), InfrastructureUpdate()
        )
        assert obj.name == "old"

    async def test_update_missing_returns_none_no_commit(self, db):
        db.execute.return_value = _result(one=None)
        out = await InfrastructureService.update_infrastructure(
            db, uuid4(), InfrastructureUpdate(name="x")
        )
        assert out is None
        db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_no_filters_pagination_and_total(self, db):
        items = [Infrastructure(name="a", type="compute")]
        db.execute.side_effect = [_result(scalar=7), _result(items=items)]
        out, total = await InfrastructureService.list_infrastructure(
            db, page=3, page_size=10
        )
        assert out == items and total == 7
        count_sql, _ = _sql(db.execute.call_args_list[0].args[0])
        assert "count(*)" in count_sql
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql
        assert "ORDER BY infrastructure.created_at DESC" in sql
        assert sorted(params.values()) == [10, 20]  # limit=10, offset=20

    async def test_all_filters_applied(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        f = InfrastructureFilter(
            type="storage", status="down", location="eu", search="web"
        )
        out, total = await InfrastructureService.list_infrastructure(db, filters=f)
        assert out == [] and total == 0
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        for col in ("type", "status", "location", "name"):
            assert f"infrastructure.{col}" in sql
        assert "storage" in params.values() and "down" in params.values()
        assert "%eu%" in params.values() and "%web%" in params.values()
        # filters also scope the count query
        count_sql, _ = _sql(db.execute.call_args_list[0].args[0])
        assert "infrastructure.type" in count_sql

    async def test_empty_filter_object_adds_no_where(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await InfrastructureService.list_infrastructure(
            db, filters=InfrastructureFilter()
        )
        sql, _ = _sql(db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql

    async def test_returns_list_type(self, db):
        db.execute.side_effect = [
            _result(scalar=1),
            _result(items=(Infrastructure(name="a", type="compute"),)),
        ]
        out, _ = await InfrastructureService.list_infrastructure(db)
        assert isinstance(out, list)

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason="BUG: backend/schemas/infrastructure.py:80 documents search as 'name and "
        "configuration' but backend/services/infrastructure_service.py:56-58 only matches name",
    )
    async def test_search_also_matches_configuration(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await InfrastructureService.list_infrastructure(
            db, filters=InfrastructureFilter(search="x")
        )
        sql, _ = _sql(db.execute.call_args_list[1].args[0])
        assert "infrastructure.configuration" in sql.split("WHERE")[1]
