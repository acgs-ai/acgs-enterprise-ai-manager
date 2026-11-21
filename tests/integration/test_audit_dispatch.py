"""
Dispatcher-level audit chain tests through the real ``backend.main.app``.

Two real ``ACGSIntegration`` instances share one ``ACGS_AUDIT_DIR``, as two
gunicorn workers would. Requests alternate between them; the audit trail must
still be one valid hash chain. Governance is never stubbed.
"""

import pytest

import backend.governance.acgs_integration as acgs_integration
from backend.governance.acgs_integration import ACGSIntegration
from backend.governance.audit_logger import AuditLogger
from tests.integration._auth_helpers import _bearer

pytestmark = pytest.mark.integration

PATH = "/api/v1/recommendations/domains"


def _decision_id(response) -> str:
    """Decision id from the governance header (allowed) or body (blocked/202)."""
    header = response.headers.get("X-Governance-Decision-ID")
    if header:
        return header
    return response.json()["decision_id"]


def test_two_workers_on_one_audit_dir_keep_one_chain(
    client, make_token, isolated_audit_dir, monkeypatch
):
    # Both created before any request: each starts from the same (empty) head.
    workers = [ACGSIntegration(), ACGSIntegration()]
    assert all(w.audit_logger.audit_dir == isolated_audit_dir for w in workers)
    headers = _bearer(make_token())

    decision_ids = []
    for i in range(6):
        monkeypatch.setattr(acgs_integration, "_governance_instance", workers[i % 2])
        response = client.get(PATH, headers=headers)
        assert response.status_code < 500, response.text
        decision_ids.append(_decision_id(response))

    assert len(set(decision_ids)) == 6
    verifier = AuditLogger(str(isolated_audit_dir))
    integrity = verifier.verify_chain_integrity()
    assert integrity["valid"] is True, integrity["broken_links"]
    assert integrity["total_entries"] >= 6
    trail_hashes = {e["entry_hash"] for e in verifier.query_audit_trail(limit=1000)}
    assert set(decision_ids) <= trail_hashes
