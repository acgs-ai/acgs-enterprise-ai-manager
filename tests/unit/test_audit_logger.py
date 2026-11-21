"""
Unit tests for AuditLogger
Tests tamper-evident logging and chain integrity.
"""

import pytest
import json
import logging
import multiprocessing
import os
from backend.governance.audit_logger import (
    HEAD_FILE_NAME,
    LOCK_FILE_NAME,
    AuditLogger,
)


def _concurrent_writer(audit_dir: str, worker: int, count: int, start) -> None:
    """Separate-process writer: logger created first, then all start together."""
    audit = AuditLogger(audit_dir)
    assert start.wait(timeout=60)
    for i in range(count):
        audit.log_enforcement(operation=f"w{worker}-{i}", action="BLOCKED", reason="r")


@pytest.mark.unit
@pytest.mark.governance
class TestAuditLogger:
    """Test suite for AuditLogger class."""

    def test_initialization(self, temp_dir):
        """Test AuditLogger initializes correctly."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        assert logger is not None
        assert audit_dir.exists()
        assert logger.last_hash == "GENESIS"

    def test_log_decision(self, temp_dir):
        """Test logging a governance decision."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        operation = "Test operation"
        context = {"user_id": "test_user"}
        validation_result = {
            "valid": True,
            "action": "ALLOW",
            "violations": [],
            "matched_rules": [],
        }

        decision_id = logger.log_decision(
            operation=operation,
            context=context,
            validation_result=validation_result,
            agent_id="test_agent",
            duration_ms=10.5,
        )

        assert decision_id is not None
        assert len(decision_id) == 64  # SHA-256 hash length

    def test_log_approval_request(self, temp_dir):
        """Test logging an approval request."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        approval_request = {
            "request_id": "req_123",
            "agent_id": "test_agent",
            "operation": "Delete data",
            "context": {},
            "timeout_seconds": 3600,
            "status": "PENDING",
        }

        entry_hash = logger.log_approval_request(approval_request)

        assert entry_hash is not None
        assert len(entry_hash) == 64

    def test_log_approval_response(self, temp_dir):
        """Test logging an approval response."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        entry_hash = logger.log_approval_response(
            request_id="req_123",
            approved=True,
            approver="admin_user",
            reason="Authorized operation",
        )

        assert entry_hash is not None

    def test_log_enforcement(self, temp_dir):
        """Test logging an enforcement action."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        entry_hash = logger.log_enforcement(
            operation="Dangerous operation", action="BLOCKED", reason="Rule violation"
        )

        assert entry_hash is not None

    def test_chain_integrity_single_entry(self, temp_dir):
        """Test chain integrity with single entry."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        logger.log_decision(
            operation="Test",
            context={},
            validation_result={"valid": True, "action": "ALLOW"},
            agent_id="test",
            duration_ms=1.0,
        )

        integrity = logger.verify_chain_integrity()

        assert integrity["valid"] is True
        assert integrity["total_entries"] == 1
        assert len(integrity["broken_links"]) == 0

    def test_chain_integrity_multiple_entries(self, temp_dir):
        """Test chain integrity with multiple entries."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        # Log multiple entries
        for i in range(5):
            logger.log_decision(
                operation=f"Test operation {i}",
                context={},
                validation_result={"valid": True, "action": "ALLOW"},
                agent_id="test",
                duration_ms=1.0,
            )

        integrity = logger.verify_chain_integrity()

        assert integrity["valid"] is True
        assert integrity["total_entries"] == 5
        assert len(integrity["broken_links"]) == 0

    def test_query_audit_trail(self, temp_dir):
        """Test querying audit trail with filters."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        # Log entries for different agents
        logger.log_decision(
            operation="Op 1",
            context={},
            validation_result={"valid": True, "action": "ALLOW"},
            agent_id="agent_1",
            duration_ms=1.0,
        )
        logger.log_decision(
            operation="Op 2",
            context={},
            validation_result={"valid": False, "action": "BLOCK"},
            agent_id="agent_2",
            duration_ms=2.0,
        )

        # Query all entries
        all_entries = logger.query_audit_trail()
        assert len(all_entries) == 2

        # Query by agent_id
        agent1_entries = logger.query_audit_trail(agent_id="agent_1")
        assert len(agent1_entries) == 1
        assert agent1_entries[0]["agent_id"] == "agent_1"

    def test_query_audit_trail_by_type(self, temp_dir):
        """Test querying audit trail by entry type."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        logger.log_decision(
            operation="Test",
            context={},
            validation_result={"valid": True, "action": "ALLOW"},
            agent_id="test",
            duration_ms=1.0,
        )
        logger.log_enforcement(operation="Test", action="BLOCKED", reason="Test")

        decision_entries = logger.query_audit_trail(entry_type="DECISION")
        enforcement_entries = logger.query_audit_trail(entry_type="ENFORCEMENT")

        assert len(decision_entries) == 1
        assert len(enforcement_entries) == 1

    def test_sanitize_context_removes_sensitive_data(self, temp_dir):
        """Test context sanitization removes sensitive information."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        sensitive_context = {
            "user_id": "123",
            "password": "secret123",
            "api_key": "key_abc",
            "token": "token_xyz",
        }

        sanitized = logger._sanitize_context(sensitive_context)

        assert sanitized["user_id"] == "123"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["token"] == "***REDACTED***"

    def test_audit_log_file_format(self, temp_dir):
        """Test audit log file is valid JSONL format."""
        audit_dir = temp_dir / "audit_logs"
        logger = AuditLogger(str(audit_dir))

        logger.log_decision(
            operation="Test",
            context={},
            validation_result={"valid": True, "action": "ALLOW"},
            agent_id="test",
            duration_ms=1.0,
        )

        # Read log file directly
        log_file = logger.current_log_file
        with open(log_file, "r") as f:
            line = f.readline()
            entry = json.loads(line)

        assert "type" in entry
        assert "timestamp" in entry
        assert "previous_hash" in entry
        assert "entry_hash" in entry
        assert entry["previous_hash"] == "GENESIS"

    def test_chain_continues_across_day_boundary(self, temp_dir):
        """A new day's log file must chain from the previous day's last entry."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        first.log_enforcement(operation="Day 1", action="BLOCKED", reason="r")
        # Simulate the entry having been written on an earlier day.
        first.current_log_file.rename(audit_dir / "audit_2000-01-01.jsonl")

        second = AuditLogger(str(audit_dir))
        second.log_enforcement(operation="Day 2", action="BLOCKED", reason="r")

        integrity = second.verify_chain_integrity()
        assert integrity["valid"] is True, integrity["broken_links"]
        assert integrity["total_entries"] == 2

    def test_non_daily_files_ignored(self, temp_dir):
        """Files not named audit_YYYY-MM-DD.jsonl neither seed nor join the chain."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        real_hash = first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        # Sorts after any dated file; must not hijack the chain seed.
        planted = {"entry_hash": "f" * 64, "previous_hash": "GENESIS"}
        (audit_dir / "audit_zzz.jsonl").write_text(json.dumps(planted) + "\n")

        second = AuditLogger(str(audit_dir))
        assert second.last_hash == real_hash
        second.log_enforcement(operation="op2", action="BLOCKED", reason="r")

        integrity = second.verify_chain_integrity()
        assert integrity["valid"] is True, integrity["broken_links"]
        assert integrity["total_entries"] == 2
        assert all(
            "audit_zzz" not in link.get("file", "")
            for link in integrity["broken_links"]
        )

    @pytest.mark.parametrize("bad_tail", ["{not json", "", "   "])
    def test_corrupt_last_line_seeds_from_previous_entry(self, temp_dir, bad_tail):
        """A corrupt or empty last line falls back to the last valid entry."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        good_hash = first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        with open(first.current_log_file, "a") as f:
            f.write(bad_tail + "\n")

        second = AuditLogger(str(audit_dir))

        assert second.last_hash == good_hash
        assert second.last_hash != "GENESIS"

    def test_invalid_utf8_does_not_stop_logger_and_is_flagged(self, temp_dir):
        """A stray invalid byte must not crash init, query or verification."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        good_hash = first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        with open(first.current_log_file, "ab") as f:
            f.write(b"\xff\xfe not utf-8\n")

        second = AuditLogger(str(audit_dir))

        assert second.last_hash == good_hash
        assert len(second.query_audit_trail(limit=10)) == 1
        integrity = second.verify_chain_integrity()
        assert integrity["valid"] is False
        assert integrity["broken_links"]

    def test_corrupt_last_file_seeds_from_previous_file(self, temp_dir):
        """A newest daily file with no valid entry does not move the head anchor."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        good_hash = first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        first.current_log_file.rename(audit_dir / "audit_2000-01-01.jsonl")
        (audit_dir / "audit_2000-01-02.jsonl").write_text("{corrupt\n")

        second = AuditLogger(str(audit_dir))

        assert second.last_hash == good_hash

    def test_corrupt_line_flagged_and_chain_still_walked(self, temp_dir):
        """verify_chain_integrity reports the corrupt line and keeps verifying."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        with open(first.current_log_file, "a") as f:
            f.write("{not json\n")

        second = AuditLogger(str(audit_dir))
        second.log_enforcement(operation="op2", action="BLOCKED", reason="r")
        integrity = second.verify_chain_integrity()

        assert integrity["valid"] is False
        assert integrity["total_entries"] == 2
        assert [link.get("type") for link in integrity["broken_links"]] == ["malformed"]
        assert integrity["broken_links"][0]["line"] == 2

    def test_torn_last_line_is_not_glued_to_next_entry(self, temp_dir):
        """A fragment without a newline is terminated before the next entry."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        first.log_enforcement(operation="op", action="BLOCKED", reason="r")
        with open(first.current_log_file, "a") as f:
            f.write('{"type": "DECISION", "torn')

        second = AuditLogger(str(audit_dir))
        decision_id = second.log_decision(
            operation="after crash",
            context={},
            validation_result={"valid": True, "action": "ALLOW"},
            agent_id="agent_after",
            duration_ms=1.0,
        )

        lines = second.current_log_file.read_text().splitlines()
        assert len(lines) == 3
        assert lines[1] == '{"type": "DECISION", "torn'
        last = json.loads(lines[-1])
        assert last["entry_hash"] == decision_id
        found = second.query_audit_trail(agent_id="agent_after")
        assert [e["entry_hash"] for e in found] == [decision_id]

        integrity = second.verify_chain_integrity()
        assert integrity["total_entries"] == 2
        assert [link.get("type") for link in integrity["broken_links"]] == ["malformed"]
        assert integrity["broken_links"][0]["line"] == 2

    def test_concurrent_processes_extend_one_chain(self, temp_dir):
        """4 separate processes x 50 writes on one directory form one valid chain."""
        audit_dir = temp_dir / "audit_logs"
        ctx = multiprocessing.get_context("spawn")
        start = ctx.Event()
        procs = [
            ctx.Process(target=_concurrent_writer, args=(str(audit_dir), w, 50, start))
            for w in range(4)
        ]
        for proc in procs:
            proc.start()
        try:
            start.set()
        finally:
            for proc in procs:
                proc.join(timeout=120)
        assert [proc.exitcode for proc in procs] == [0, 0, 0, 0]

        integrity = AuditLogger(str(audit_dir)).verify_chain_integrity()
        assert integrity["valid"] is True, integrity["broken_links"][:3]
        assert integrity["total_entries"] == 200
        head = json.loads((audit_dir / HEAD_FILE_NAME).read_text())
        assert head["entries"] == 200

    def test_deleted_newest_file_is_detected_via_head_anchor(self, temp_dir):
        """Deleting the newest file no longer reseeds silently from the older one."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        old_hash = first.log_enforcement(operation="old", action="BLOCKED", reason="r")
        first.current_log_file.rename(audit_dir / "audit_2000-01-01.jsonl")
        newest_hash = first.log_enforcement(
            operation="new", action="BLOCKED", reason="r"
        )
        first.current_log_file.unlink()

        second = AuditLogger(str(audit_dir))
        assert second.last_hash == newest_hash

        integrity = second.verify_chain_integrity()
        assert integrity["valid"] is False
        assert integrity["broken_links"] == [
            {
                "type": "head_mismatch",
                "expected_head": newest_hash,
                "actual_head": old_hash,
                "expected_entries": 2,
                "actual_entries": 1,
            }
        ]

        # The next entry chains to the anchor, so the gap stays visible.
        second.log_enforcement(operation="after", action="BLOCKED", reason="r")
        entries = second.query_audit_trail()
        assert entries[-1]["previous_hash"] == newest_hash
        assert second.verify_chain_integrity()["valid"] is False

    def test_crash_between_append_and_anchor_update_recovers(
        self, temp_dir, monkeypatch
    ):
        """An appended entry whose anchor update failed is adopted on restart."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        first.log_enforcement(operation="one", action="BLOCKED", reason="r")

        def _crash(*args, **kwargs):
            raise OSError("simulated crash before anchor update")

        monkeypatch.setattr(first, "_write_head", _crash)
        with pytest.raises(OSError):
            first.log_enforcement(operation="two", action="BLOCKED", reason="r")
        orphan = json.loads(first.current_log_file.read_text().splitlines()[-1])
        head = json.loads((audit_dir / HEAD_FILE_NAME).read_text())
        assert head["entries"] == 1
        assert orphan["previous_hash"] == head["entry_hash"]

        second = AuditLogger(str(audit_dir))
        assert second.last_hash == orphan["entry_hash"]
        assert json.loads((audit_dir / HEAD_FILE_NAME).read_text()) == {
            "entry_hash": orphan["entry_hash"],
            "entries": 2,
        }
        second.log_enforcement(operation="three", action="BLOCKED", reason="r")
        integrity = second.verify_chain_integrity()
        assert integrity["valid"] is True, integrity["broken_links"]
        assert integrity["total_entries"] == 3

    def test_missing_anchor_is_bootstrapped_from_disk(self, temp_dir, caplog):
        """Upgrade path: existing logs without an anchor seed it with a warning."""
        audit_dir = temp_dir / "audit_logs"
        first = AuditLogger(str(audit_dir))
        for i in range(3):
            last = first.log_enforcement(
                operation=f"op{i}", action="BLOCKED", reason="r"
            )
        (audit_dir / HEAD_FILE_NAME).unlink()

        with caplog.at_level(logging.WARNING, logger="backend.governance.audit_logger"):
            second = AuditLogger(str(audit_dir))

        assert second.last_hash == last
        assert json.loads((audit_dir / HEAD_FILE_NAME).read_text()) == {
            "entry_hash": last,
            "entries": 3,
        }
        assert any("bootstrapped" in r.getMessage() for r in caplog.records)
        assert second.verify_chain_integrity()["valid"] is True

    def test_missing_anchor_with_entries_fails_verification(self, temp_dir):
        """verify_chain_integrity flags a deleted anchor when entries exist."""
        audit_dir = temp_dir / "audit_logs"
        audit = AuditLogger(str(audit_dir))
        audit.log_enforcement(operation="op", action="BLOCKED", reason="r")
        (audit_dir / HEAD_FILE_NAME).unlink()

        integrity = audit.verify_chain_integrity()
        assert integrity["valid"] is False
        assert [link["type"] for link in integrity["broken_links"]] == ["head_mismatch"]

    def test_corrupt_anchor_fails_closed(self, temp_dir):
        """A corrupt anchor makes writes raise instead of reseeding the chain."""
        audit_dir = temp_dir / "audit_logs"
        audit = AuditLogger(str(audit_dir))
        audit.log_enforcement(operation="op", action="BLOCKED", reason="r")
        (audit_dir / HEAD_FILE_NAME).write_text("{not json")

        with pytest.raises(ValueError, match="anchor is corrupt"):
            audit.log_enforcement(operation="op2", action="BLOCKED", reason="r")
        integrity = audit.verify_chain_integrity()
        assert integrity["valid"] is False
        assert integrity["total_entries"] == 1

    def test_anchor_write_does_not_follow_planted_symlink(self, temp_dir):
        """A symlink planted under a guessable temp name is never written through."""
        audit_dir = temp_dir / "audit_logs"
        audit = AuditLogger(str(audit_dir))
        victim = temp_dir / "victim.txt"
        victim.write_text("untouched")
        # The name the anchor temp file had when it was derived from the pid.
        (audit_dir / f".{HEAD_FILE_NAME}.{os.getpid()}.tmp").symlink_to(victim)

        audit.log_enforcement(operation="op", action="BLOCKED", reason="r")

        assert victim.read_text() == "untouched"
        assert audit.verify_chain_integrity()["valid"] is True
        leftovers = [
            p.name
            for p in audit_dir.iterdir()
            if p.name.endswith(".tmp") and not p.is_symlink()
        ]
        assert leftovers == []

    def test_lock_file_symlink_is_refused(self, temp_dir):
        """A symlink planted under the lock name makes writes fail closed."""
        audit_dir = temp_dir / "audit_logs"
        audit = AuditLogger(str(audit_dir))
        victim = temp_dir / "victim.txt"
        victim.write_text("untouched")
        (audit_dir / LOCK_FILE_NAME).unlink()
        (audit_dir / LOCK_FILE_NAME).symlink_to(victim)

        with pytest.raises(OSError):
            audit.log_enforcement(operation="op", action="BLOCKED", reason="r")
        assert victim.read_text() == "untouched"

    def test_daily_file_symlink_is_refused(self, temp_dir):
        """A symlink planted under today's file name never receives entries."""
        audit_dir = temp_dir / "audit_logs"
        audit = AuditLogger(str(audit_dir))
        victim = temp_dir / "victim.txt"
        victim.write_text("untouched")
        audit.current_log_file.symlink_to(victim)

        with pytest.raises(OSError):
            audit.log_enforcement(operation="op", action="BLOCKED", reason="r")
        assert victim.read_text() == "untouched"

    def test_audit_dir_from_env(self, temp_dir, monkeypatch):
        """ACGS_AUDIT_DIR is used when no directory argument is given."""
        env_dir = temp_dir / "env_audit"
        monkeypatch.setenv("ACGS_AUDIT_DIR", str(env_dir))

        logger = AuditLogger()

        assert logger.audit_dir == env_dir
        assert env_dir.exists()

    def test_audit_dir_argument_overrides_env(self, temp_dir, monkeypatch):
        """An explicit audit_dir argument wins over ACGS_AUDIT_DIR."""
        monkeypatch.setenv("ACGS_AUDIT_DIR", str(temp_dir / "env_audit"))
        explicit = temp_dir / "explicit_audit"

        logger = AuditLogger(str(explicit))

        assert logger.audit_dir == explicit

    def test_query_audit_trail_continues_past_corrupt_and_invalid_utf8_lines(
        self, temp_dir
    ):
        """A corrupt or non-UTF-8 line must not hide later valid entries in the same file."""
        audit_dir = temp_dir / "audit_logs"
        logger_inst = AuditLogger(str(audit_dir))
        logger_inst.log_enforcement(
            operation="op-before", action="BLOCKED", reason="r1"
        )
        with open(logger_inst.current_log_file, "ab") as f:
            f.write(b"\xff\xfe bad bytes\n{not json\n")
        logger_inst.log_enforcement(operation="op-after", action="ALLOWED", reason="r2")

        entries = logger_inst.query_audit_trail(limit=10)
        assert [e["operation"] for e in entries] == ["op-before", "op-after"]
