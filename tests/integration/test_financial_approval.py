"""
Financial approval identity, through the real ``backend.main.app``.

The approver is the active user whose ``external_subject`` equals the verified
token subject; a client-supplied approver_id or approval field is never trusted,
and there is no fallback to a users.id lookup.
"""

import operator
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from backend.database import get_db
from backend.main import app
from backend.models.user import User
from backend.services.financial_service import FinancialService
from tests.integration._auth_helpers import _bearer

pytestmark = pytest.mark.integration

SUB = "auth0|alice"
ALICE_ID = UUID("6f1c2a7e-0d4b-4c1e-9a52-3b8e2f7d9c10")
OTHER = "11111111-2222-3333-4444-555555555555"
RECORD_ID = "00000000-0000-0000-0000-000000000001"
NOT_PROVISIONED = {"detail": "Approver identity not provisioned"}


def _user(user_id, external_subject, is_active=True) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id, external_subject=external_subject, is_active=is_active
    )


def _record(status: str, approver: UUID) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=UUID(RECORD_ID),
        type="expense",
        amount="10.00",
        currency="USD",
        date=date(2026, 1, 1),
        category="ops",
        project_id=None,
        description=None,
        additional_data=None,
        approval_status=status,
        approved_by=approver,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def users(client):
    """The users table the approver query runs against.

    ``holder.rows`` defaults to alice (sub ``auth0|alice``) plus an active user
    whose id and external_subject are both OTHER, so honouring ``?approver_id``
    would be visible. ``holder.subjects`` records each queried subject.
    """
    holder = SimpleNamespace(
        rows=[_user(ALICE_ID, SUB), _user(UUID(OTHER), OTHER)],
        subjects=[],
        sessions=[],
    )

    async def _execute(statement):
        assert statement.column_descriptions[0]["entity"] is User
        clause = statement.whereclause
        assert clause.left.compare(User.__table__.c.external_subject)
        assert clause.operator is operator.eq
        subject = clause.right.value
        holder.subjects.append(subject)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [
            row for row in holder.rows if row.external_subject == subject
        ]
        return result

    async def _fake_db():
        session = AsyncMock()
        session.add = MagicMock()
        session.execute = AsyncMock(side_effect=_execute)
        holder.sessions.append(session)
        yield session

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _fake_db
    yield holder
    app.dependency_overrides[get_db] = previous


@pytest.fixture
def service(monkeypatch):
    approve = AsyncMock(side_effect=lambda db, rid, aid: _record("approved", aid))
    reject = AsyncMock(side_effect=lambda db, rid, aid: _record("rejected", aid))
    monkeypatch.setattr(FinancialService, "approve_financial_record", approve)
    monkeypatch.setattr(FinancialService, "reject_financial_record", reject)
    return SimpleNamespace(approve=approve, reject=reject)


def _manager(make_token, sub=SUB):
    return _bearer(make_token(role="manager", sub=sub))


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize("query", ["", f"?approver_id={OTHER}"])
def test_approver_is_token_subject(client, make_token, users, service, action, query):
    response = client.post(
        f"/api/v1/financial/{RECORD_ID}/{action}{query}",
        headers=_manager(make_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["approved_by"] == str(ALICE_ID)
    mock = getattr(service, action)
    mock.assert_awaited_once()
    assert mock.await_args.args[2] == ALICE_ID
    assert users.subjects == [SUB]
    users.sessions[0].get.assert_not_awaited()


@pytest.mark.parametrize("action", ["approve", "reject"])
@pytest.mark.parametrize(
    "sub, rows",
    [
        # sub equals a users.id, but no row has it as external_subject
        (str(ALICE_ID), [_user(ALICE_ID, SUB)]),
        (SUB, []),  # no users row for sub
        (SUB, [_user(ALICE_ID, SUB, is_active=False)]),  # deactivated
        (SUB, [_user(ALICE_ID, SUB, is_active=None)]),  # NULL is not active
        # two rows share the subject: ambiguous, so nobody is the approver
        (SUB, [_user(ALICE_ID, SUB), _user(uuid4(), SUB)]),
    ],
    ids=[
        "id-not-subject",
        "missing-row",
        "inactive-row",
        "null-active",
        "duplicate-subject",
    ],
)
def test_unprovisioned_approver_is_403(
    client, make_token, users, service, action, sub, rows
):
    users.rows = rows + [_user(UUID(OTHER), OTHER)]

    response = client.post(
        f"/api/v1/financial/{RECORD_ID}/{action}?approver_id={OTHER}",
        headers=_manager(make_token, sub=sub),
    )

    assert response.status_code == 403
    assert response.json() == NOT_PROVISIONED
    assert users.subjects == [sub]
    users.sessions[0].get.assert_not_awaited()
    service.approve.assert_not_awaited()
    service.reject.assert_not_awaited()


@pytest.mark.parametrize(
    "field, value",
    [("approval_status", "approved"), ("approved_by", OTHER)],
)
def test_update_cannot_set_approval_fields(
    client, make_token, monkeypatch, field, value
):
    update = AsyncMock()
    monkeypatch.setattr(FinancialService, "update_financial_record", update)

    response = client.put(
        f"/api/v1/financial/{RECORD_ID}",
        json={"category": "ops", field: value},
        headers=_manager(make_token),
    )

    assert response.status_code == 422
    assert field in response.text
    update.assert_not_awaited()


@pytest.mark.parametrize(
    "field, value",
    [("approval_status", "approved"), ("approved_by", OTHER)],
)
def test_create_cannot_set_approval_fields(
    client, make_token, monkeypatch, field, value
):
    create = AsyncMock()
    monkeypatch.setattr(FinancialService, "create_financial_record", create)

    response = client.post(
        "/api/v1/financial/",
        json={
            "type": "expense",
            "amount": "10.00",
            "date": "2026-01-01",
            "category": "ops",
            field: value,
        },
        headers=_manager(make_token),
    )

    assert response.status_code == 422
    assert field in response.text
    create.assert_not_awaited()


def test_create_without_approval_fields_is_accepted(client, make_token, monkeypatch):
    create = AsyncMock(return_value=_record("pending", None))
    monkeypatch.setattr(FinancialService, "create_financial_record", create)

    response = client.post(
        "/api/v1/financial/",
        json={
            "type": "expense",
            "amount": "10.00",
            "date": "2026-01-01",
            "category": "ops",
        },
        headers=_manager(make_token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["approval_status"] == "pending"
    assert response.json()["approved_by"] is None
    payload = create.await_args.args[1]
    assert "approval_status" not in payload.model_dump()
