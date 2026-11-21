"""Unit tests for FinancialService and financial schemas (mocked AsyncSession)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.models.financial_record import FinancialRecord
from backend.schemas.financial_record import (
    FinancialRecordCreate,
    FinancialRecordFilter,
    FinancialRecordResponse,
    FinancialRecordUpdate,
)
from backend.services.financial_service import FinancialService
from tests.unit.conftest import compile_sql, make_result


def _fields(**kw):
    base = dict(
        type="expense", amount=Decimal("10.00"), date=date(2026, 1, 1), category="ops"
    )
    base.update(kw)
    return base


def _record(**kw):
    return FinancialRecord(**_fields(**kw))


def _create(**kw):
    return FinancialRecordCreate(**_fields(**kw))


@pytest.mark.unit
class TestSchemas:
    def test_defaults(self):
        c = _create()
        assert c.currency == "USD" and c.project_id is None
        # Approval fields are server-owned: not part of the create payload.
        assert "approval_status" not in c.model_dump()
        assert "approved_by" not in c.model_dump()

    @pytest.mark.parametrize(
        "kw",
        [
            {"approval_status": "approved"},
            {"approval_status": "pending"},
            {"approved_by": "6f1c2a7e-0d4b-4c1e-9a52-3b8e2f7d9c10"},
        ],
    )
    @pytest.mark.parametrize("schema", ["create", "update"])
    def test_approval_fields_rejected(self, kw, schema):
        """Clients cannot set approval state; only approve/reject can."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            if schema == "create":
                _create(**kw)
            else:
                FinancialRecordUpdate(**kw)

    def test_response_still_exposes_approval_fields(self):
        assert {"approval_status", "approved_by"} <= set(
            FinancialRecordResponse.model_fields
        )

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

    def test_negative_amount_accepted(self):
        # Negative amounts are valid (refunds, credits, reversals), on write and
        # on read; only the min_amount/max_amount filters require ge=0.
        assert _create(amount="-5.00").amount == Decimal("-5.00")
        assert FinancialRecordUpdate(amount="-5.00").amount == Decimal("-5.00")

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
    async def test_create_sets_fields(self, mock_db):
        pid = uuid4()
        rec = await FinancialService.create_financial_record(
            mock_db,
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
        # Not set from the payload; the column default stores "pending".
        assert rec.approval_status is None and rec.approved_by is None
        assert FinancialRecord.__table__.c.approval_status.default.arg == "pending"
        mock_db.add.assert_called_once_with(rec)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_get_found_and_missing(self, mock_db):
        rec = _record()
        rid = uuid4()
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        assert await FinancialService.get_financial_record(mock_db, rid) is rec
        sql, params = compile_sql(mock_db.execute.call_args.args[0])
        assert "financial_records.id" in sql and rid in params.values()
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await FinancialService.get_financial_record(mock_db, rid) is None

    async def test_update_partial(self, mock_db):
        rec = _record(category="ops", amount=Decimal("10.00"))
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        out = await FinancialService.update_financial_record(
            mock_db, uuid4(), FinancialRecordUpdate(amount=Decimal("12.50"))
        )
        assert out is rec
        assert rec.amount == Decimal("12.50") and rec.category == "ops"
        mock_db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_update_missing(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        out = await FinancialService.update_financial_record(
            mock_db, uuid4(), FinancialRecordUpdate(amount=Decimal("1"))
        )
        assert out is None
        mock_db.commit.assert_not_awaited()

    async def test_delete(self, mock_db):
        rec = _record()
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        assert await FinancialService.delete_financial_record(mock_db, uuid4()) is True
        mock_db.delete.assert_awaited_once_with(rec)
        mock_db.commit.assert_awaited_once()

    async def test_delete_missing(self, mock_db):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert await FinancialService.delete_financial_record(mock_db, uuid4()) is False
        mock_db.delete.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestApprovalWorkflow:
    async def test_approve_sets_status_and_approver(self, mock_db):
        rec = _record(approval_status="pending")
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        aid = uuid4()
        out = await FinancialService.approve_financial_record(mock_db, uuid4(), aid)
        assert out is rec
        assert rec.approval_status == "approved" and rec.approved_by == aid
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(rec, ["project", "approver"])

    async def test_reject_sets_status_and_approver(self, mock_db):
        rec = _record(approval_status="pending")
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        aid = uuid4()
        out = await FinancialService.reject_financial_record(mock_db, uuid4(), aid)
        assert out is rec
        assert rec.approval_status == "rejected" and rec.approved_by == aid

    @pytest.mark.parametrize(
        "method", ["approve_financial_record", "reject_financial_record"]
    )
    async def test_missing_record_returns_none(self, mock_db, method):
        mock_db.execute.return_value = make_result(scalar_one_or_none=None)
        assert (
            await getattr(FinancialService, method)(mock_db, uuid4(), uuid4()) is None
        )
        mock_db.commit.assert_not_awaited()
        mock_db.refresh.assert_not_awaited()

    async def test_amount_unchanged_by_approval(self, mock_db):
        rec = _record(amount=Decimal("250.75"))
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        await FinancialService.approve_financial_record(mock_db, uuid4(), uuid4())
        assert rec.amount == Decimal("250.75")

    async def test_characterize_reapproval_overwrites_without_guard(self, mock_db):
        """Current behaviour: no state-transition guard; rejected -> approved is allowed."""
        first, second = uuid4(), uuid4()
        rec = _record(approval_status="rejected", approved_by=first)
        mock_db.execute.return_value = make_result(scalar_one_or_none=rec)
        await FinancialService.approve_financial_record(mock_db, uuid4(), second)
        assert rec.approval_status == "approved" and rec.approved_by == second


@pytest.mark.unit
@pytest.mark.asyncio
class TestList:
    async def test_pagination_total_and_order(self, mock_db):
        items = [_record(), _record()]
        mock_db.execute.side_effect = [
            make_result(scalar=12),
            make_result(scalars=items),
        ]
        out, total = await FinancialService.list_financial_records(
            mock_db, page=2, page_size=2
        )
        assert out == items and total == 12
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "ORDER BY financial_records.date DESC" in sql
        assert "WHERE" not in sql
        assert sorted(params.values()) == [2, 2]
        count_sql, _ = compile_sql(mock_db.execute.call_args_list[0].args[0])
        assert "count(*)" in count_sql

    async def test_all_filters_and_operators(self, mock_db):
        pid = uuid4()
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
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
        await FinancialService.list_financial_records(mock_db, filters=f)
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
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

    async def test_zero_min_amount_is_applied(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await FinancialService.list_financial_records(
            mock_db, filters=FinancialRecordFilter(min_amount=Decimal("0"))
        )
        sql, params = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "financial_records.amount >=" in sql
        assert Decimal("0") in params.values()

    async def test_empty_filter_no_where(self, mock_db):
        mock_db.execute.side_effect = [make_result(scalar=0), make_result()]
        await FinancialService.list_financial_records(
            mock_db, filters=FinancialRecordFilter()
        )
        sql, _ = compile_sql(mock_db.execute.call_args_list[1].args[0])
        assert "WHERE" not in sql
