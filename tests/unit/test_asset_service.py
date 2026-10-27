"""Unit tests for ITAssetService, asset schemas and the ITAsset model."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.asset import ITAsset
from backend.schemas.asset import (
    ITAssetCreate,
    ITAssetFilter,
    ITAssetResponse,
    ITAssetUpdate,
)
from backend.services.asset_service import ITAssetService
from tests.unit.conftest import compile_sql, executed_stmt, make_result


@pytest.mark.unit
class TestAssetSchemas:
    def test_create_defaults(self):
        a = ITAssetCreate(name="srv1", type="server")
        assert a.status == "active"
        assert a.specifications == {}
        assert a.lifecycle_stage is None

    def test_type_required_and_validated(self):
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x")
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="toaster")

    @pytest.mark.parametrize(
        "t",
        [
            "server",
            "workstation",
            "laptop",
            "network_device",
            "storage",
            "software_license",
            "other",
        ],
    )
    def test_all_types_accepted(self, t):
        assert ITAssetCreate(name="x", type=t).type == t

    def test_status_and_lifecycle_validated(self):
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="server", status="broken")
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="server", lifecycle_stage="ancient")
        with pytest.raises(ValidationError):
            ITAssetUpdate(status="broken")
        with pytest.raises(ValidationError):
            ITAssetFilter(type="toaster")

    def test_cost_bounds(self):
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="server", purchase_cost=Decimal("-1"))
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="server", purchase_cost=Decimal("1e10"))
        ok = ITAssetCreate(name="x", type="server", purchase_cost=Decimal("0"))
        assert ok.purchase_cost == 0

    def test_name_and_location_length(self):
        with pytest.raises(ValidationError):
            ITAssetCreate(name="", type="server")
        with pytest.raises(ValidationError):
            ITAssetCreate(name="x", type="server", location="l" * 256)

    def test_update_only_set_fields(self):
        assert ITAssetUpdate(location="DC1").model_dump(exclude_unset=True) == {
            "location": "DC1"
        }

    def test_response_from_attributes(self):
        aid = uuid4()
        obj = SimpleNamespace(
            id=aid,
            name="n",
            type="laptop",
            status="active",
            location=None,
            owner_id=None,
            project_id=None,
            purchase_date=None,
            purchase_cost=None,
            lifecycle_stage=None,
            warranty_expiry=None,
            specifications={},
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        assert ITAssetResponse.model_validate(obj).id == aid


@pytest.mark.unit
class TestAssetModel:
    def test_columns(self):
        assert ITAsset.__tablename__ == "it_assets"
        c = ITAsset.__table__.c
        assert not c.name.nullable and not c.type.nullable
        assert c.status.default.arg == "active"
        assert c.owner_id.foreign_keys and c.project_id.foreign_keys

    def test_repr(self):
        r = repr(ITAsset(name="srv", type="server"))
        assert "srv" in r and "server" in r


@pytest.mark.unit
class TestAssetServiceCrud:
    @pytest.mark.asyncio
    async def test_create_sets_fields_and_refreshes_relations(self, mock_db):
        owner = uuid4()
        data = ITAssetCreate(
            name="srv1",
            type="server",
            location="DC1",
            owner_id=owner,
            purchase_date=date(2026, 1, 1),
            purchase_cost=Decimal("999.99"),
            lifecycle_stage="new",
            specifications={"cpu": 8},
        )
        asset = await ITAssetService.create_asset(mock_db, data)

        mock_db.add.assert_called_once_with(asset)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(asset, ["owner", "project", "tasks"])
        assert isinstance(asset, ITAsset)
        assert (asset.name, asset.type, asset.status) == ("srv1", "server", "active")
        assert asset.location == "DC1" and asset.owner_id == owner
        assert asset.purchase_cost == Decimal("999.99")
        assert asset.lifecycle_stage == "new"
        assert asset.specifications == {"cpu": 8}

    @pytest.mark.asyncio
    async def test_get_found_without_relations(self, mock_db):
        aid = uuid4()
        asset = ITAsset(name="a", type="server")
        mock_db.execute.return_value = make_result(scalar_one_or_none=asset)
        assert await ITAssetService.get_asset(mock_db, aid) is asset
        stmt = executed_stmt(mock_db)
        sql, params = compile_sql(stmt)
        assert "WHERE it_assets.id =" in sql and aid in params.values()
        assert not stmt._with_options

    @pytest.mark.asyncio
    async def test_get_with_relations_adds_loader_options(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await ITAssetService.get_asset(mock_db, uuid4(), True) is None
        assert len(executed_stmt(mock_db)._with_options) == 3

    @pytest.mark.asyncio
    async def test_update_applies_only_provided_and_bumps_updated_at(self, mock_db):
        old = datetime(2020, 1, 1)
        asset = ITAsset(name="a", type="server", location="DC1", updated_at=old)
        mock_db.execute.return_value = make_result(scalar_one_or_none=asset)

        out = await ITAssetService.update_asset(
            mock_db, uuid4(), ITAssetUpdate(status="maintenance")
        )

        assert out is asset
        assert asset.status == "maintenance"
        assert asset.location == "DC1" and asset.name == "a"
        assert asset.updated_at > old
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(asset)

    @pytest.mark.asyncio
    async def test_update_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await ITAssetService.update_asset(mock_db, uuid4(), ITAssetUpdate(name="x"))
            is None
        )
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_found(self, mock_db):
        asset = ITAsset(name="a", type="server")
        mock_db.execute.return_value = make_result(scalar_one_or_none=asset)
        assert await ITAssetService.delete_asset(mock_db, uuid4()) is True
        mock_db.delete.assert_awaited_once_with(asset)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await ITAssetService.delete_asset(mock_db, uuid4()) is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
class TestAssetServiceList:
    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, mock_db):
        items = [ITAsset(name="a", type="server")]
        mock_db.execute.side_effect = [
            make_result(scalar=42),
            make_result(scalars=items),
        ]
        out, total = await ITAssetService.list_assets(mock_db)
        assert out == items and total == 42

    @pytest.mark.asyncio
    async def test_defaults_paging_order_no_where_no_options(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ITAssetService.list_assets(mock_db)
        stmt = executed_stmt(mock_db, 1)
        sql, params = compile_sql(stmt)
        assert "WHERE" not in sql
        assert "ORDER BY it_assets.created_at DESC" in sql
        assert sorted(params.values()) == [0, 50]
        assert not stmt._with_options

    @pytest.mark.asyncio
    async def test_pagination_offset(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ITAssetService.list_assets(mock_db, page=4, page_size=25)
        _, params = compile_sql(executed_stmt(mock_db, 1))
        assert sorted(params.values()) == [25, 75]

    @pytest.mark.asyncio
    async def test_include_relations_adds_options_to_page_query_only(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ITAssetService.list_assets(mock_db, include_relations=True)
        assert not executed_stmt(mock_db, 0)._with_options
        assert len(executed_stmt(mock_db, 1)._with_options) == 3

    @pytest.mark.asyncio
    async def test_all_filters_applied_to_count_and_page(self, mock_db):
        owner, proj = uuid4(), uuid4()
        filters = ITAssetFilter(
            type="server",
            status="active",
            lifecycle_stage="aging",
            owner_id=owner,
            project_id=proj,
            location="rack",
            search="dell",
        )
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ITAssetService.list_assets(mock_db, filters)

        for i in (0, 1):
            sql, params = compile_sql(executed_stmt(mock_db, i))
            for frag in (
                "it_assets.type =",
                "it_assets.status =",
                "it_assets.lifecycle_stage =",
                "it_assets.owner_id =",
                "it_assets.project_id =",
                "it_assets.location ILIKE",
                "it_assets.name ILIKE",
            ):
                assert frag in sql, frag
            vals = list(params.values())
            for v in ("server", "active", "aging", owner, proj, "%rack%", "%dell%"):
                assert v in vals, v

    @pytest.mark.asyncio
    async def test_single_filter_only_emits_that_condition(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await ITAssetService.list_assets(mock_db, ITAssetFilter(status="retired"))
        sql, _ = compile_sql(executed_stmt(mock_db, 1))
        assert "it_assets.status =" in sql
        assert "it_assets.type =" not in sql
        assert "ILIKE" not in sql
