"""Unit tests for InfrastructureService and infrastructure schemas (mocked AsyncSession)."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.infrastructure import Infrastructure
from backend.schemas.infrastructure import (
    InfrastructureCreate,
    InfrastructureFilter,
    InfrastructureResponse,
    InfrastructureUpdate,
)
from backend.services.infrastructure_service import InfrastructureService
from tests.unit.conftest import compile_sql, make_result


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
    async def test_create_sets_fields_and_commits(self, mock_db):
        data = InfrastructureCreate(
            name="db1",
            type="database",
            location="eu",
            dependencies=["net"],
            capacity={"cpu": 4},
        )
        infra = await InfrastructureService.create_infrastructure(mock_db, data)
        assert isinstance(infra, Infrastructure)
        assert (infra.name, infra.type, infra.status) == (
            "db1",
            "database",
            "operational",
        )
        assert infra.dependencies == ["net"] and infra.capacity == {"cpu": 4}
        mock_db.add.assert_called_once_with(infra)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(infra, ["tasks"])

    async def test_get_found_and_filters_by_id(self, mock_db):
        obj = Infrastructure(name="a", type="compute")
        mock_db.execute.return_value = make_result(scalar_one_or_none=obj)
        iid = uuid4()
        assert await InfrastructureService.get_infrastructure(mock_db, iid) is obj
        sql, params = compile_sql(mock_db.execute.call_args.args[0])
        assert "WHERE infrastructure.id" in sql
        assert iid in params.values()

    async def test_get_not_found_returns_none(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await InfrastructureService.get_infrastructure(mock_db, uuid4()) is None

    async def test_delete_found(self, mock_db):
        obj = Infrastructure(name="a", type="compute")
        mock_db.execute.return_value = make_result(scalar_one_or_none=obj)
        assert (
            await InfrastructureService.delete_infrastructure(mock_db, uuid4()) is True
        )
        mock_db.delete.assert_awaited_once_with(obj)
        mock_db.commit.assert_awaited_once()

    async def test_delete_missing_does_not_touch_db(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await InfrastructureService.delete_infrastructure(mock_db, uuid4()) is False
        )
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdate:
    async def test_partial_update_only_set_fields(self, mock_db):
        obj = Infrastructure(
            name="old", type="compute", status="operational", location="us"
        )
        mock_db.execute.return_value = make_result(scalar_one_or_none=obj)
        out = await InfrastructureService.update_infrastructure(
            mock_db, uuid4(), InfrastructureUpdate(status="degraded")
        )
        assert out is obj
        assert obj.status == "degraded"
        assert obj.name == "old" and obj.location == "us"
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(obj, ["tasks"])

    async def test_explicit_none_clears_field(self, mock_db):
        obj = Infrastructure(name="old", type="compute", location="us")
        mock_db.execute.return_value = make_result(scalar_one_or_none=obj)
        await InfrastructureService.update_infrastructure(
            mock_db, uuid4(), InfrastructureUpdate(location=None)
        )
        assert obj.location is None

    async def test_empty_update_changes_nothing(self, mock_db):
        obj = Infrastructure(name="old", type="compute")
        mock_db.execute.return_value = make_result(scalar_one_or_none=obj)
        await InfrastructureService.update_infrastructure(
            mock_db, uuid4(), InfrastructureUpdate()
        )
        assert obj.name == "old"

    async def test_update_missing_returns_none_no_commit(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        out = await InfrastructureService.update_infrastructure(
            mock_db, uuid4(), InfrastructureUpdate(name="x")
        )
        assert out is None
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_no_filters_pagination_and_total(self, mock_db):
        items = [Infrastructure(name="a", type="compute")]
        mock_db.execute.side_effect = [
            make_result(scalar=7),
            make_result(scalars=items),
        ]
        out, total = await InfrastructureService.list_infrastructure(
            mock_db, page=3, page_size=10
        )
        assert out == items and total == 7
        count_sql, _ = compile_sql(mock_db.execute.call_args_list[0].args[0])
        assert "count(*)" in count_sql
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql
        assert "ORDER BY infrastructure.created_at DESC" in sql
        assert sorted(params.values()) == [10, 20]  # limit=10, offset=20

    async def test_all_filters_applied(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        f = InfrastructureFilter(
            type="storage", status="down", location="eu", search="web"
        )
        out, total = await InfrastructureService.list_infrastructure(mock_db, filters=f)
        assert out == [] and total == 0
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        for col in ("type", "status", "location", "name"):
            assert f"infrastructure.{col}" in sql
        assert "storage" in params.values() and "down" in params.values()
        assert "%eu%" in params.values() and "%web%" in params.values()
        # filters also scope the count query
        count_sql, _ = compile_sql(mock_db.execute.call_args_list[0].args[0])
        assert "infrastructure.type" in count_sql

    async def test_empty_filter_object_adds_no_where(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await InfrastructureService.list_infrastructure(
            mock_db, filters=InfrastructureFilter()
        )
        sql, _ = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql

    async def test_returns_list_type(self, mock_db):
        mock_db.execute.side_effect = [
            make_result(scalar=1),
            make_result(scalars=(Infrastructure(name="a", type="compute"),)),
        ]
        out, _ = await InfrastructureService.list_infrastructure(mock_db)
        assert isinstance(out, list)

    async def test_search_also_matches_configuration(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await InfrastructureService.list_infrastructure(
            mock_db, filters=InfrastructureFilter(search="x")
        )
        # Count and list queries both match name OR configuration (as text).
        for call in mock_db.execute.call_args_list:
            where = compile_sql(call.args[0])[0].split("WHERE")[1]
            assert "infrastructure.name ILIKE" in where
            assert " OR " in where
            assert "CAST(infrastructure.configuration AS VARCHAR) ILIKE" in where
