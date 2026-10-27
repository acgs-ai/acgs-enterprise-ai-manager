"""Unit tests for FinancialService and financial schemas (mocked AsyncSession)."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from backend.models.financial_record import FinancialRecord
from backend.schemas.financial_record import (
    FinancialRecordCreate,
    FinancialRecordFilter,
    FinancialRecordResponse,
    FinancialRecordUpdate,
)
from backend.services.financial_service import FinancialService


def _sql(stmt):
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def _result(one=None, items=None, scalar=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = one
    r.scalars.return_value.all.return_value = items or []
    r.scalar.return_value = scalar
    return r


def _record(**kw):
    base = dict(
        type="expense", amount=Decimal("10.00"), date=date(2026, 1, 1), category="ops"
    )
    base.update(kw)
    return FinancialRecord(**base)


def _create(**kw):
    base = dict(
        type="expense", amount=Decimal("10.00"), date=date(2026, 1, 1), category="ops"
    )
    base.update(kw)
    return FinancialRecordCreate(**base)


@pytest.fixture
def db():
    session = MagicMock()
    session.add = MagicMock()
    for name in ("commit", "refresh", "delete", "execute", "flush"):
        setattr(session, name, AsyncMock())
    return session


@pytest.mark.unit
class TestSchemas:
    def test_defaults(self):
        c = _create()
        assert c.currency == "USD" and c.approval_status == "pending"
        assert c.project_id is None and c.approved_by is None

    @pytest.mark.parametrize(
        "t", ["expense", "revenue", "budget_allocation", "invoice", "payment"]
    )
    def test_valid_types(self, t):
        assert _create(type=t).type == t

    @pytest.mark.parametrize(
        "kw",
        [
            {"type": "refund"},
            {"approval_status": "maybe"},
            {"currency": "US"},
            {"currency": "USDX"},
            {"category": ""},
            {"category": "x" * 101},
            {"amount": "abc"},
            {"date": "not-a-date"},
        ],
    )
    def test_invalid_fields(self, kw):
        with pytest.raises(ValidationError):
            _create(**kw)

    def test_amount_keeps_decimal_precision(self):
        c = _create(amount="1234567.89")
        assert c.amount == Decimal("1234567.89") and isinstance(c.amount, Decimal)

    def test_string_date_coerced(self):
        assert _create(date="2026-03-04").date == date(2026, 3, 4)

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: backend/schemas/financial_record.py:23 amount has no ge=0 constraint; "
        "negative amounts accepted (FinancialRecordFilter.min_amount/max_amount do enforce ge=0)",
    )
    def test_negative_amount_rejected(self):
        with pytest.raises(ValidationError):
            _create(amount="-5.00")

    def test_update_all_optional_and_validates(self):
        assert FinancialRecordUpdate().model_dump(exclude_unset=True) == {}
        with pytest.raises(ValidationError):
            FinancialRecordUpdate(approval_status="x")
        with pytest.raises(ValidationError):
            FinancialRecordUpdate(currency="E")

    def test_filter_amount_bounds_non_negative(self):
        with pytest.raises(ValidationError):
            FinancialRecordFilter(min_amount=-1)
        with pytest.raises(ValidationError):
            FinancialRecordFilter(max_amount=Decimal("-0.01"))
        assert FinancialRecordFilter(min_amount=0).min_amount == 0

    def test_response_from_attributes(self):
        rec = _record(
            id=uuid4(),
            currency="USD",
            approval_status="pending",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        r = FinancialRecordResponse.model_validate(rec)
        assert r.amount == Decimal("10.00") and r.category == "ops"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCrud:
    async def test_create_sets_fields(self, db):
        pid = uuid4()
        rec = await FinancialService.create_financial_record(
            db,
            _create(
                amount="99.95",
                currency="EUR",
                project_id=pid,
                description="d",
                additional_data={"po": 1},
            ),
        )
        assert isinstance(rec, FinancialRecord)
        assert rec.amount == Decimal("99.95") and rec.currency == "EUR"
        assert rec.project_id == pid and rec.additional_data == {"po": 1}
        assert rec.approval_status == "pending"
        db.add.assert_called_once_with(rec)
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_get_found_and_missing(self, db):
        rec = _record()
        rid = uuid4()
        db.execute.return_value = _result(one=rec)
        assert await FinancialService.get_financial_record(db, rid) is rec
        sql, params = _sql(db.execute.call_args.args[0])
        assert "financial_records.id" in sql and rid in params.values()
        db.execute.return_value = _result(one=None)
        assert await FinancialService.get_financial_record(db, rid) is None

    async def test_update_partial(self, db):
        rec = _record(category="ops", amount=Decimal("10.00"))
        db.execute.return_value = _result(one=rec)
        out = await FinancialService.update_financial_record(
            db, uuid4(), FinancialRecordUpdate(amount=Decimal("12.50"))
        )
        assert out is rec
        assert rec.amount == Decimal("12.50") and rec.category == "ops"
        db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_update_missing(self, db):
        db.execute.return_value = _result(one=None)
        out = await FinancialService.update_financial_record(
            db, uuid4(), FinancialRecordUpdate(amount=Decimal("1"))
        )
        assert out is None
        db.commit.assert_not_awaited()

    async def test_delete(self, db):
        rec = _record()
        db.execute.return_value = _result(one=rec)
        assert await FinancialService.delete_financial_record(db, uuid4()) is True
        db.delete.assert_awaited_once_with(rec)
        db.commit.assert_awaited_once()

    async def test_delete_missing(self, db):
        db.execute.return_value = _result(one=None)
        assert await FinancialService.delete_financial_record(db, uuid4()) is False
        db.delete.assert_not_awaited()
        db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestApprovalWorkflow:
    async def test_approve_sets_status_and_approver(self, db):
        rec = _record(approval_status="pending")
        db.execute.return_value = _result(one=rec)
        aid = uuid4()
        out = await FinancialService.approve_financial_record(db, uuid4(), aid)
        assert out is rec
        assert rec.approval_status == "approved" and rec.approved_by == aid
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_reject_sets_status_and_approver(self, db):
        rec = _record(approval_status="pending")
        db.execute.return_value = _result(one=rec)
        aid = uuid4()
        out = await FinancialService.reject_financial_record(db, uuid4(), aid)
        assert out is rec
        assert rec.approval_status == "rejected" and rec.approved_by == aid

    @pytest.mark.parametrize(
        "method", ["approve_financial_record", "reject_financial_record"]
    )
    async def test_missing_record_returns_none(self, db, method):
        db.execute.return_value = _result(one=None)
        assert await getattr(FinancialService, method)(db, uuid4(), uuid4()) is None
        db.commit.assert_not_awaited()
        db.refresh.assert_not_awaited()

    async def test_amount_unchanged_by_approval(self, db):
        rec = _record(amount=Decimal("250.75"))
        db.execute.return_value = _result(one=rec)
        await FinancialService.approve_financial_record(db, uuid4(), uuid4())
        assert rec.amount == Decimal("250.75")

    async def test_characterize_reapproval_overwrites_without_guard(self, db):
        """Current behaviour: no state-transition guard; rejected -> approved is allowed."""
        first, second = uuid4(), uuid4()
        rec = _record(approval_status="rejected", approved_by=first)
        db.execute.return_value = _result(one=rec)
        await FinancialService.approve_financial_record(db, uuid4(), second)
        assert rec.approval_status == "approved" and rec.approved_by == second


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_pagination_total_and_order(self, db):
        items = [_record(), _record()]
        db.execute.side_effect = [_result(scalar=12), _result(items=items)]
        out, total = await FinancialService.list_financial_records(
            db, page=2, page_size=2
        )
        assert out == items and total == 12
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "ORDER BY financial_records.date DESC" in sql
        assert "WHERE" not in sql
        assert sorted(params.values()) == [2, 2]
        count_sql, _ = _sql(db.execute.call_args_list[0].args[0])
        assert "count(*)" in count_sql

    async def test_all_filters_and_operators(self, db):
        pid = uuid4()
        db.execute.side_effect = [_result(scalar=0), _result()]
        f = FinancialRecordFilter(
            type="invoice",
            approval_status="approved",
            project_id=pid,
            category="tra",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 6, 30),
            min_amount=Decimal("10"),
            max_amount=Decimal("500"),
        )
        await FinancialService.list_financial_records(db, filters=f)
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "financial_records.date >=" in sql and "financial_records.date <=" in sql
        assert (
            "financial_records.amount >=" in sql
            and "financial_records.amount <=" in sql
        )
        assert "financial_records.category ILIKE" in sql
        vals = list(params.values())
        assert (
            "%tra%" in vals and pid in vals and "invoice" in vals and "approved" in vals
        )
        assert date(2026, 1, 1) in vals and date(2026, 6, 30) in vals
        assert Decimal("10") in vals and Decimal("500") in vals

    async def test_zero_min_amount_is_applied(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await FinancialService.list_financial_records(
            db, filters=FinancialRecordFilter(min_amount=Decimal("0"))
        )
        sql, params = _sql(db.execute.call_args_list[1].args[0])
        assert "financial_records.amount >=" in sql
        assert Decimal("0") in params.values()

    async def test_empty_filter_no_where(self, db):
        db.execute.side_effect = [_result(scalar=0), _result()]
        await FinancialService.list_financial_records(
            db, filters=FinancialRecordFilter()
        )
        sql, _ = _sql(db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql
