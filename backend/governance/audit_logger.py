"""
Tamper-Evident Audit Logger
Implements cryptographic audit trails for governance decisions.
"""

import fcntl
import json
import logging
import hashlib
import re
import tempfile
from contextlib import contextmanager
from typing import Dict, Any, Iterator, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)

# Only daily chain files take part in the hash chain; anything else in the
# directory (e.g. a planted "audit_zzz.jsonl") is ignored.
AUDIT_FILE_RE = re.compile(r"^audit_\d{4}-\d{2}-\d{2}\.jsonl$")
LOCK_FILE_NAME = ".audit.lock"
HEAD_FILE_NAME = "chain_head.json"
TAIL_READ_BLOCK = 64 * 1024


class AuditLogger:
    """
    Tamper-evident audit logger for governance framework.

    Implements cryptographic chaining to ensure audit trail integrity.
    Each audit entry includes a hash of the previous entry, creating
    an immutable chain of evidence.

    Several processes (e.g. gunicorn workers) may share one audit directory.
    Every write holds an exclusive ``fcntl.flock`` on ``.audit.lock`` and
    chains to the head anchor ``chain_head.json`` (``entry_hash``, ``entries``),
    which is updated atomically after each append. ``flock`` is only reliable
    on Linux with a local filesystem; it is not a safe lock on NFS.

    The anchor lets verify_chain_integrity() detect deletion or truncation of
    the newest entries. It sits next to the logs, so it does NOT protect
    against an attacker who can rewrite both the logs and the anchor, or who
    deletes the anchor (a missing anchor is re-seeded from the disk tail with
    only a warning). A trustworthy anchor needs an external store; that is a
    follow-up.
    """

    def __init__(self, audit_dir: Optional[str] = None):
        """
        Initialize audit logger.

        Args:
            audit_dir: Directory for audit logs. Resolution order: this argument,
                then the ACGS_AUDIT_DIR environment variable, then
                backend/governance/audit_logs.
        """
        if audit_dir is None:
            audit_dir = os.environ.get("ACGS_AUDIT_DIR") or os.path.join(
                os.path.dirname(__file__), "audit_logs"
            )

        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self.current_log_file = self._get_current_log_file()
        with self._chain_lock(fcntl.LOCK_EX):
            self.last_hash, _ = self._reconcile_head()

        logger.info(f"Audit logger initialized: {self.audit_dir}")

    @contextmanager
    def _chain_lock(self, operation: int) -> Iterator[None]:
        """Hold flock(operation) on the directory lock file.

        The file is opened per acquisition: flock is per open file description,
        so a shared descriptor would not exclude threads or forked workers.
        """
        # O_NOFOLLOW: a symlink planted under the lock name must not be opened.
        fd = os.open(
            self.audit_dir / LOCK_FILE_NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        try:
            fcntl.flock(fd, operation)
            yield
        finally:
            os.close(fd)  # releases the lock

    def _read_head(self) -> Optional[Tuple[str, int]]:
        """Return the head anchor, or None if absent. Raise if it is corrupt."""
        try:
            raw = (self.audit_dir / HEAD_FILE_NAME).read_text()
        except FileNotFoundError:
            return None
        try:
            head = json.loads(raw)
        except ValueError:
            raise ValueError("audit chain head anchor is corrupt")
        entry_hash = head.get("entry_hash") if isinstance(head, dict) else None
        entries = head.get("entries") if isinstance(head, dict) else None
        if (
            not isinstance(entry_hash, str)
            or not entry_hash
            or not isinstance(entries, int)
            or isinstance(entries, bool)
            or entries < 0
        ):
            raise ValueError("audit chain head anchor is corrupt")
        return entry_hash, entries

    def _write_head(self, entry_hash: str, entries: int) -> None:
        """Replace the head anchor atomically (tmp file, fsync, os.replace)."""
        path = self.audit_dir / HEAD_FILE_NAME
        # mkstemp creates the file with O_EXCL under an unpredictable name, so
        # a symlink planted in the audit dir can never be followed or truncated.
        fd, tmp = tempfile.mkstemp(
            dir=self.audit_dir, prefix=f".{HEAD_FILE_NAME}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"entry_hash": entry_hash, "entries": entries}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
        dir_fd = os.open(self.audit_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    @staticmethod
    def _parse_chain_line(raw: bytes) -> Optional[Dict[str, Any]]:
        """Parse one log line; None unless it is an object with an entry_hash."""
        try:
            entry = json.loads(raw.decode(errors="replace"))
        except ValueError:
            return None
        if not isinstance(entry, dict):
            return None
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str) or not entry_hash:
            return None
        return entry

    def _tail_entry(self) -> Optional[Dict[str, Any]]:
        """Newest valid entry on disk, reading each file backwards in blocks."""
        for log_file in reversed(self._chain_files()):
            with open(log_file, "rb") as f:
                pos = f.seek(0, os.SEEK_END)
                partial = b""
                while pos > 0:
                    step = min(TAIL_READ_BLOCK, pos)
                    pos -= step
                    f.seek(pos)
                    lines = (f.read(step) + partial).split(b"\n")
                    # lines[0] may continue in the previous block.
                    partial = lines[0] if pos > 0 else b""
                    complete = lines[1:] if pos > 0 else lines
                    for raw in reversed(complete):
                        entry = self._parse_chain_line(raw)
                        if entry is not None:
                            return entry
        return None

    def _count_entries(self) -> int:
        """Count entries the way verify_chain_integrity() does (JSON objects)."""
        total = 0
        for log_file in self._chain_files():
            with open(log_file, "r", errors="replace") as f:
                for line in f:
                    try:
                        if isinstance(json.loads(line), dict):
                            total += 1
                    except ValueError:
                        continue
        return total

    def _reconcile_head(self) -> Tuple[str, int]:
        """Return (head hash, entry count) to chain to. Caller holds LOCK_EX.

        - No anchor (first run or upgrade): seed from the disk tail and write
          the anchor.
        - Tail entry chains to the anchor and verifies: a writer died between
          append and anchor update; adopt it.
        - Any other mismatch: keep chaining to the anchor so the break stays
          visible to verify_chain_integrity(), and log an error.
        """
        head = self._read_head()
        if head is None:
            last_hash = self._get_last_hash()
            entries = self._count_entries()
            if last_hash == "GENESIS" and entries == 0:
                return "GENESIS", 0
            logger.warning(
                f"Audit chain head anchor missing in {self.audit_dir}; "
                "bootstrapped from the log files on disk"
            )
            self._write_head(last_hash, entries)
            return last_hash, entries

        head_hash, entries = head
        tail = self._tail_entry()
        if tail is not None and tail["entry_hash"] == head_hash:
            return head
        if (
            tail is not None
            and tail.get("previous_hash") == head_hash
            and self._compute_entry_hash(tail) == tail["entry_hash"]
        ):
            logger.warning(
                "Audit chain head anchor was one entry behind the log "
                "(interrupted write); adopting the last entry"
            )
            self._write_head(tail["entry_hash"], entries + 1)
            return tail["entry_hash"], entries + 1
        logger.error(
            "Audit chain head anchor does not match the newest log entry; "
            "log files may have been deleted or truncated. Chaining to the anchor."
        )
        return head

    def _get_current_log_file(self) -> Path:
        """Get current audit log file path (one per day)."""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        return self.audit_dir / f"audit_{date_str}.jsonl"

    def _chain_files(self) -> List[Path]:
        """Daily chain files (audit_YYYY-MM-DD.jsonl), oldest first."""
        return sorted(
            p for p in self.audit_dir.iterdir() if AUDIT_FILE_RE.match(p.name)
        )

    def _get_last_hash(self) -> str:
        """
        Get hash of last audit entry for chain integrity.

        Seeds from the newest valid entry across the daily chain files (not
        only today's), so the chain continues across day boundaries the same
        way verify_chain_integrity() walks it. Corrupt or empty trailing lines
        are skipped in favour of the previous valid entry.
        """
        for log_file in reversed(self._chain_files()):
            try:
                # errors="replace": a stray invalid byte must not stop the logger
                # from starting; the damaged line fails JSON parsing below.
                with open(log_file, "r", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError as e:
                logger.error(f"Error reading last hash from {log_file}: {e}")
                continue
            for line in reversed(lines):
                try:
                    entry = json.loads(line)
                except ValueError:
                    if line.strip():
                        logger.error(f"Skipping corrupt audit line in {log_file}")
                    continue
                entry_hash = (
                    entry.get("entry_hash") if isinstance(entry, dict) else None
                )
                if isinstance(entry_hash, str) and entry_hash:
                    return entry_hash
                logger.error(f"Skipping audit entry without hash in {log_file}")

        return "GENESIS"

    def _compute_entry_hash(self, entry: Dict[str, Any]) -> str:
        """
        Compute cryptographic hash of audit entry.

        Args:
            entry: Audit entry dict

        Returns:
            SHA-256 hash hex string
        """
        # Create deterministic JSON string
        entry_copy = entry.copy()
        entry_copy.pop("entry_hash", None)  # Remove hash field if present

        entry_json = json.dumps(entry_copy, sort_keys=True)
        return hashlib.sha256(entry_json.encode()).hexdigest()

    def _write_audit_entry(self, entry: Dict[str, Any]) -> str:
        """
        Write audit entry to log file with cryptographic chaining.

        Args:
            entry: Audit entry to write

        Returns:
            Entry hash
        """
        try:
            with self._chain_lock(fcntl.LOCK_EX):
                # Chain to the shared head, not this process's last write, so
                # concurrent workers extend one chain.
                head_hash, entries = self._reconcile_head()
                self.current_log_file = self._get_current_log_file()

                entry["previous_hash"] = head_hash
                entry["entry_hash"] = self._compute_entry_hash(entry)
                line = (json.dumps(entry) + "\n").encode()

                # O_NOFOLLOW: a symlink planted under today's file name must
                # not redirect audit entries into another file.
                log_fd = os.open(
                    self.current_log_file,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                    0o644,
                )
                with os.fdopen(log_fd, "ab") as f:
                    # A torn last line (crash mid-write) would otherwise be
                    # glued to this entry and make it unparseable. Terminate
                    # it instead; the fragment stays in the file as evidence.
                    if f.tell() > 0:
                        with open(self.current_log_file, "rb") as tail:
                            tail.seek(-1, os.SEEK_END)
                            if tail.read(1) != b"\n":
                                line = b"\n" + line
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())

                self._write_head(entry["entry_hash"], entries + 1)
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
            raise

        # Only a durably written entry advances the chain.
        self.last_hash = entry["entry_hash"]
        return entry["entry_hash"]

    def log_decision(
        self,
        operation: str,
        context: Dict[str, Any],
        validation_result: Dict[str, Any],
        agent_id: str,
        duration_ms: float,
    ) -> str:
        """
        Log a governance decision to audit trail.

        Args:
            operation: Operation that was validated
            context: Operation context
            validation_result: Validation result
            agent_id: AI agent identifier
            duration_ms: Validation duration in milliseconds

        Returns:
            Decision ID (entry hash)
        """
        entry = {
            "type": "DECISION",
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": agent_id,
            "operation": operation[:500],  # Truncate for storage
            "context": self._sanitize_context(context),
            "validation_result": {
                "valid": validation_result.get("valid"),
                "action": validation_result.get("action"),
                "violations": validation_result.get("violations", []),
                "matched_rules": validation_result.get("matched_rules", []),
            },
            "duration_ms": duration_ms,
        }

        decision_id = self._write_audit_entry(entry)
        logger.info(f"Logged decision: {decision_id[:16]}")

        return decision_id

    def log_approval_request(self, approval_request: Dict[str, Any]) -> str:
        """
        Log an approval request to audit trail.

        Args:
            approval_request: Approval request details

        Returns:
            Entry hash
        """
        entry = {
            "type": "APPROVAL_REQUEST",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": approval_request["request_id"],
            "agent_id": approval_request["agent_id"],
            "operation": approval_request["operation"][:500],
            "context": self._sanitize_context(approval_request.get("context", {})),
            "timeout_seconds": approval_request["timeout_seconds"],
            "status": approval_request["status"],
        }

        entry_hash = self._write_audit_entry(entry)
        logger.info(f"Logged approval request: {approval_request['request_id']}")

        return entry_hash

    def log_approval_response(
        self,
        request_id: str,
        approved: bool,
        approver: str,
        reason: Optional[str] = None,
    ) -> str:
        """
        Log an approval response to audit trail.

        Args:
            request_id: Original approval request ID
            approved: Whether request was approved
            approver: Identifier of approver
            reason: Optional reason for decision

        Returns:
            Entry hash
        """
        entry = {
            "type": "APPROVAL_RESPONSE",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "approved": approved,
            "approver": approver,
            "reason": reason,
        }

        entry_hash = self._write_audit_entry(entry)
        logger.info(
            f"Logged approval response: {request_id} - {'APPROVED' if approved else 'DENIED'}"
        )

        return entry_hash

    def log_enforcement(self, operation: str, action: str, reason: Any) -> str:
        """
        Log enforcement action to audit trail.

        Args:
            operation: Operation that was enforced
            action: Enforcement action taken
            reason: Reason for enforcement

        Returns:
            Entry hash
        """
        entry = {
            "type": "ENFORCEMENT",
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation[:500],
            "action": action,
            "reason": str(reason)[:1000],
        }

        entry_hash = self._write_audit_entry(entry)
        logger.info(f"Logged enforcement: {action}")

        return entry_hash

    def query_audit_trail(
        self,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        entry_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query audit trail with filters.

        Args:
            agent_id: Filter by agent ID
            start_time: Filter by start time
            end_time: Filter by end time
            entry_type: Filter by entry type
            limit: Maximum number of entries to return

        Returns:
            List of matching audit entries
        """
        results = []

        # Get all log files in date range
        log_files = self._chain_files()

        for log_file in log_files:
            try:
                with open(log_file, "r", errors="replace") as f:
                    for line in f:
                        if len(results) >= limit:
                            break

                        # Skip a malformed line (verify_chain_integrity flags
                        # it) instead of dropping the rest of the file.
                        try:
                            entry = json.loads(line)
                            if not isinstance(entry, dict):
                                raise TypeError("Audit log entry is not a JSON object")
                            entry_time = datetime.fromisoformat(entry["timestamp"])
                        except (
                            json.JSONDecodeError,
                            KeyError,
                            TypeError,
                            ValueError,
                        ) as e:
                            logger.warning(
                                f"Skipping malformed audit entry in {log_file}: {e}"
                            )
                            continue

                        # Apply filters
                        if agent_id and entry.get("agent_id") != agent_id:
                            continue

                        if entry_type and entry.get("type") != entry_type:
                            continue

                        if start_time and entry_time < start_time:
                            continue

                        if end_time and entry_time > end_time:
                            continue

                        results.append(entry)

            except Exception as e:
                logger.error(f"Error reading log file {log_file}: {e}")

        return results[:limit]

    def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Verify cryptographic integrity of audit chain.

        The final hash and entry count must also match the head anchor; a
        mismatch (e.g. the newest file was deleted) is a ``head_mismatch`` link.

        Returns:
            Dict with verification results:
                - valid: bool
                - total_entries: int
                - broken_links: List[Dict]
        """
        # Shared lock: no writer can be mid-append or mid-anchor-update.
        with self._chain_lock(fcntl.LOCK_SH):
            broken_links, total_entries, last_hash = self._walk_chain()
            try:
                head = self._read_head()
            except ValueError as e:
                broken_links.append({"type": "head_mismatch", "error": str(e)})
            else:
                if head is None and total_entries > 0:
                    broken_links.append(
                        {"type": "head_mismatch", "error": "head anchor missing"}
                    )
                elif head is not None and head != (last_hash, total_entries):
                    broken_links.append(
                        {
                            "type": "head_mismatch",
                            "expected_head": head[0],
                            "actual_head": last_hash,
                            "expected_entries": head[1],
                            "actual_entries": total_entries,
                        }
                    )

        return {
            "valid": len(broken_links) == 0,
            "total_entries": total_entries,
            "broken_links": broken_links,
        }

    def _walk_chain(self) -> Tuple[List[Dict[str, Any]], int, Any]:
        """Walk every chain file; return (broken links, entry count, last hash)."""
        broken_links = []
        total_entries = 0
        previous_hash = "GENESIS"

        log_files = self._chain_files()

        for log_file in log_files:
            try:
                with open(log_file, "r", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        # A malformed line is a broken link; keep walking so
                        # later entries are still verified against the last
                        # valid hash (writers skip malformed lines the same way).
                        try:
                            entry = json.loads(line)
                            if not isinstance(entry, dict):
                                raise ValueError("entry is not a JSON object")
                        except ValueError as e:
                            broken_links.append(
                                {
                                    "file": str(log_file),
                                    "line": line_num,
                                    "type": "malformed",
                                    "error": str(e),
                                }
                            )
                            continue
                        total_entries += 1

                        # Verify previous hash matches
                        if entry.get("previous_hash") != previous_hash:
                            broken_links.append(
                                {
                                    "file": str(log_file),
                                    "line": line_num,
                                    "expected_previous": previous_hash,
                                    "actual_previous": entry.get("previous_hash"),
                                }
                            )

                        # Verify entry hash
                        stored_hash = entry.get("entry_hash")
                        computed_hash = self._compute_entry_hash(entry)

                        if stored_hash != computed_hash:
                            broken_links.append(
                                {
                                    "file": str(log_file),
                                    "line": line_num,
                                    "type": "hash_mismatch",
                                    "expected_hash": computed_hash,
                                    "actual_hash": stored_hash,
                                }
                            )

                        previous_hash = stored_hash

            except Exception as e:
                logger.error(f"Error verifying {log_file}: {e}")
                broken_links.append({"file": str(log_file), "error": str(e)})

        return broken_links, total_entries, previous_hash

    @staticmethod
    def _sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize context to remove sensitive data before logging.

        Args:
            context: Original context

        Returns:
            Sanitized context
        """
        sanitized = {}
        sensitive_keys = {"password", "token", "secret", "api_key", "credential"}

        for key, value in context.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized
