"""
ACGS-Lite Governance Framework Integration
Enterprise AI Agent Constitutional Governance

This module provides the main integration point for the acgs-lite governance framework,
implementing the MACI pattern (Monitor-Approve-Control-Inspect) for AI agent operations.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

import yaml

from .rules_engine import RulesEngine
from .audit_logger import AuditLogger

# Set when acgs-lite is installed but importing it failed (broken install,
# missing name, internal import error). Treated as an engine init failure.
ACGS_IMPORT_ERROR: Optional[str] = None
try:
    from acgs_lite import Constitution, GovernanceEngine, ViolationAction

    ACGS_AVAILABLE = True
except ImportError as e:
    ACGS_AVAILABLE = False
    if isinstance(e, ModuleNotFoundError) and e.name == "acgs_lite":
        logging.warning("acgs-lite not installed. Install with: pip install acgs-lite")
    else:
        ACGS_IMPORT_ERROR = f"{type(e).__name__}: {e}"
        logging.error(f"acgs-lite is installed but failed to import: {e}")

logger = logging.getLogger(__name__)

# App rule action -> acgs-lite workflow action. Only BLOCK blocks in acgs-lite.
# REQUIRE_APPROVAL, VALIDATE (context thresholds), AUDIT and PROTECT are
# enforced by RulesEngine; acgs-lite cannot express approval gates or context
# thresholds, so it only warns on them instead of turning them into blocks.
_ACGS_WORKFLOW_ACTIONS = {
    "BLOCK": "block",
    "REQUIRE_APPROVAL": "warn",
    "VALIDATE": "warn",
    "AUDIT": "warn",
    "PROTECT": "warn",
}
_ACGS_SEVERITIES = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}
# One alternative of an app pattern that is a plain literal (no regex syntax),
# so it maps exactly to an acgs-lite keyword (case-insensitive substring).
_LITERAL_ALTERNATIVE = re.compile(r"[A-Za-z0-9_]+(?:[ \-]+[A-Za-z0-9_]+)*")

# Generic on purpose: violations reach API 403 bodies.
_ENGINE_UNAVAILABLE_VIOLATION = {
    "rule_id": "acgs-engine-unavailable",
    "severity": "CRITICAL",
    "description": "Governance engine unavailable; operation blocked",
    "action": "BLOCK",
}


def build_acgs_constitution(constitution_path: str) -> "Constitution":
    """
    Convert this app's governance_rules.yaml schema into an acgs-lite Constitution.

    App rules carry ``pattern`` (regex), ``action`` and ``description``;
    acgs-lite rules need ``text``. Rules are emitted as ``keywords`` (a
    constitution made only of acgs-lite pattern rules never matches in the
    pure-Python engine). A pattern maps only if it is an alternation of plain
    literals ("harm|kill|rm -rf"), which is exactly a keyword list, matched
    case-insensitively as a substring. Anything that cannot be mapped faithfully
    (regex syntax, context matching, unknown action/severity, missing pattern)
    raises, so the caller fails closed instead of dropping the rule.
    """
    with open(constitution_path, "r") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise TypeError("constitution must be a YAML mapping")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("constitution 'rules' must be a non-empty list")

    acgs_rules = []
    seen_ids = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise TypeError(f"rule at index {index} must be a mapping")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"rule at index {index} has no valid 'id'")
        if rule_id in seen_ids:
            raise ValueError(f"duplicate rule id {rule_id!r}")
        seen_ids.add(rule_id)

        action = rule.get("action", "BLOCK")
        if action not in _ACGS_WORKFLOW_ACTIONS:
            raise ValueError(f"rule {rule_id}: unknown action {action!r}")
        severity = rule.get("severity", "MEDIUM")
        if severity not in _ACGS_SEVERITIES:
            raise ValueError(f"rule {rule_id}: unknown severity {severity!r}")
        if "context_key" in rule or "context_pattern" in rule:
            raise ValueError(f"rule {rule_id}: context matching cannot be mapped")
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"rule {rule_id}: no pattern to map")
        keywords = pattern.split("|")
        if not all(_LITERAL_ALTERNATIVE.fullmatch(k) for k in keywords):
            raise ValueError(f"rule {rule_id}: pattern is not a literal alternation")

        acgs_rules.append(
            {
                "id": rule_id,
                "text": str(rule.get("description") or rule_id),
                "severity": _ACGS_SEVERITIES[severity],
                "keywords": keywords,
                "workflow_action": ViolationAction(_ACGS_WORKFLOW_ACTIONS[action]),
                "category": str(rule.get("maci_phase", "general")).lower(),
                "metadata": {"app_action": action},
            }
        )

    return Constitution.from_dict(
        {
            "name": "acgs-enterprise-manager",
            "rules": acgs_rules,
            "metadata": {
                "constitutional_hash": str(data.get("constitutional_hash", ""))
            },
        }
    )


class ACGSIntegration:
    """
    Main integration class for ACGS-Lite governance framework.

    Implements fail-closed enforcement with tamper-evident audit trails.
    All AI operations must pass governance validation before execution.
    """

    def __init__(
        self,
        constitution_path: Optional[str] = None,
        fail_closed: bool = True,
        audit_enabled: bool = True,
        audit_dir: Optional[str] = None,
    ):
        """
        Initialize ACGS governance integration.

        Args:
            constitution_path: Path to YAML constitution file
            fail_closed: If True, block operations on validation failure (default: True)
            audit_enabled: If True, enable tamper-evident audit logging (default: True)
            audit_dir: Audit log directory (default: see AuditLogger resolution order)
        """
        self.fail_closed = fail_closed
        self.audit_enabled = audit_enabled

        # Set default constitution path
        if constitution_path is None:
            constitution_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config",
                "governance_rules.yaml",
            )

        self.constitution_path = constitution_path

        # Initialize components
        self.rules_engine = RulesEngine(constitution_path)
        self.audit_logger = AuditLogger(audit_dir) if audit_enabled else None

        # Initialize acgs-lite engine if available. Not installed is a
        # supported fallback (RulesEngine alone enforces, itself fail-closed);
        # installed but unbuildable is an error and sets acgs_init_error.
        self.acgs_engine = None
        self.acgs_init_error: Optional[str] = None
        if ACGS_AVAILABLE:
            self._initialize_acgs_engine()
        elif ACGS_IMPORT_ERROR is not None:
            self.acgs_init_error = ACGS_IMPORT_ERROR
            logger.error(f"ACGS engine unavailable, import failed: {ACGS_IMPORT_ERROR}")
        else:
            logger.warning("Running in fallback mode without acgs-lite")

    def _initialize_acgs_engine(self):
        """Initialize the acgs-lite governance engine."""
        try:
            constitution = build_acgs_constitution(self.constitution_path)
            # strict=False: blocking violations come back in the result
            # instead of raising, so validate_operation reports them.
            self.acgs_engine = GovernanceEngine(constitution, strict=False)

            logger.info(
                f"ACGS governance engine initialized with constitution: {self.constitution_path}"
            )
        except Exception as e:
            self.acgs_engine = None
            self.acgs_init_error = f"{type(e).__name__}: {e}"
            logger.error(
                f"Failed to initialize ACGS engine from {self.constitution_path}: "
                f"{self.acgs_init_error}"
            )

    def validate_operation(
        self,
        operation: str,
        context: Dict[str, Any],
        agent_id: str = "default",
        stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate an AI operation against governance rules (MACI: Monitor phase).

        Args:
            operation: Description of the operation to validate
            context: Additional context for validation
            agent_id: Identifier for the AI agent
            stage: "request" or "output" (see RulesEngine.validate); None
                applies every rule. Recorded in the audited context.

        Returns:
            Dict containing validation result with keys:
                - valid: bool
                - action: str (ALLOW, BLOCK, REQUIRE_APPROVAL)
                - violations: List[Dict]
                - decision_id: str
        """
        start_time = datetime.utcnow()

        if stage is not None:
            context = {**context, "stage": stage}

        # Validate using rules engine
        validation_result = self.rules_engine.validate(operation, context, stage=stage)

        # If acgs-lite is available, use it for additional validation
        if self.acgs_engine is not None:
            try:
                acgs_result = self.acgs_engine.validate(
                    operation, agent_id=agent_id, context=context
                )
                # Merge results (fail-closed: if either fails, operation is blocked)
                if not acgs_result.valid:
                    validation_result["valid"] = False
                    validation_result["violations"].extend(
                        [
                            {
                                "rule_id": v.rule_id,
                                "severity": str(
                                    getattr(v.severity, "value", v.severity)
                                ).upper(),
                                "description": v.rule_text,
                                "action": "BLOCK",
                                "source": "acgs-lite",
                            }
                            for v in acgs_result.violations
                        ]
                    )
            except Exception as e:
                logger.error(f"ACGS validation error: {e}")
                if self.fail_closed:
                    validation_result["valid"] = False
                    validation_result["violations"].append(
                        {
                            "rule_id": "system-error",
                            "severity": "CRITICAL",
                            # Generic: reaches API 403 bodies; detail is logged.
                            "description": "Governance validation error; operation blocked",
                        }
                    )
        elif self.acgs_init_error is not None:
            # acgs-lite is installed but its engine could not be built: never
            # treat the missing layer as a pass.
            if self.fail_closed:
                logger.error(
                    "ACGS engine unavailable; blocking operation (fail-closed)"
                )
                validation_result["valid"] = False
                validation_result["violations"].append(
                    dict(_ENGINE_UNAVAILABLE_VIOLATION)
                )
            else:
                logger.warning(
                    "ACGS engine unavailable; fail_closed=False, "
                    "rules engine decides alone"
                )

        # Determine action based on validation
        if not validation_result["valid"]:
            action = "BLOCK" if self.fail_closed else "WARN"
        elif validation_result.get("requires_approval", False):
            action = "REQUIRE_APPROVAL"
        else:
            action = "ALLOW"

        validation_result["action"] = action

        # Log to audit trail
        if self.audit_logger:
            decision_id = self.audit_logger.log_decision(
                operation=operation,
                context=context,
                validation_result=validation_result,
                agent_id=agent_id,
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )
            validation_result["decision_id"] = decision_id

        return validation_result

    def request_approval(
        self,
        operation: str,
        context: Dict[str, Any],
        agent_id: str = "default",
        timeout_seconds: int = 3600,
    ) -> Dict[str, Any]:
        """
        Request human approval for an operation (MACI: Approve phase).

        Args:
            operation: Description of the operation requiring approval
            context: Additional context for approval decision
            agent_id: Identifier for the AI agent
            timeout_seconds: Approval timeout in seconds

        Returns:
            Dict containing approval request details
        """
        approval_request = {
            "request_id": self._generate_request_id(),
            "operation": operation,
            "context": context,
            "agent_id": agent_id,
            "requested_at": datetime.utcnow().isoformat(),
            "timeout_seconds": timeout_seconds,
            "status": "PENDING",
        }

        if self.audit_logger:
            self.audit_logger.log_approval_request(approval_request)

        logger.info(f"Approval requested: {approval_request['request_id']}")

        return approval_request

    def enforce_decision(
        self, validation_result: Dict[str, Any], operation: str
    ) -> bool:
        """
        Enforce governance decision (MACI: Control phase).

        Args:
            validation_result: Result from validate_operation
            operation: The operation to enforce

        Returns:
            True if operation is allowed to proceed, False otherwise
        """
        action = validation_result.get("action", "BLOCK")

        if action == "ALLOW":
            logger.info(f"Operation allowed: {operation[:100]}")
            return True
        elif action == "BLOCK":
            logger.warning(f"Operation blocked: {operation[:100]}")
            if self.audit_logger:
                self.audit_logger.log_enforcement(
                    operation=operation,
                    action="BLOCKED",
                    reason=validation_result.get("violations", []),
                )
            return False
        elif action == "REQUIRE_APPROVAL":
            logger.info(f"Operation requires approval: {operation[:100]}")
            # In production, this would integrate with approval workflow
            return False
        else:
            # Unknown action - fail closed
            logger.error(f"Unknown action: {action}. Failing closed.")
            return False

    def inspect_audit_trail(
        self,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Inspect audit trail (MACI: Inspect phase).

        Args:
            agent_id: Filter by agent ID
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of records to return

        Returns:
            List of audit records
        """
        if not self.audit_logger:
            logger.warning("Audit logging not enabled")
            return []

        return self.audit_logger.query_audit_trail(
            agent_id=agent_id, start_time=start_time, end_time=end_time, limit=limit
        )

    def get_governance_status(self) -> Dict[str, Any]:
        """
        Get current governance framework status.

        Returns:
            Dict containing status information
        """
        return {
            "acgs_available": ACGS_AVAILABLE,
            "acgs_engine_initialized": self.acgs_engine is not None,
            "acgs_init_error": self.acgs_init_error is not None,
            "fail_closed": self.fail_closed,
            "audit_enabled": self.audit_enabled,
            "constitution_path": self.constitution_path,
            "rules_count": len(self.rules_engine.rules) if self.rules_engine else 0,
        }

    @staticmethod
    def _generate_request_id() -> str:
        """Generate unique request ID."""
        import uuid

        return f"req_{uuid.uuid4().hex[:16]}"


# Singleton instance for application-wide use
_governance_instance: Optional[ACGSIntegration] = None


def get_governance() -> ACGSIntegration:
    """Get or create the global governance instance."""
    global _governance_instance
    if _governance_instance is None:
        _governance_instance = ACGSIntegration()
    return _governance_instance


def initialize_governance(
    constitution_path: Optional[str] = None,
    fail_closed: bool = True,
    audit_enabled: bool = True,
) -> ACGSIntegration:
    """
    Initialize the global governance instance.

    Args:
        constitution_path: Path to YAML constitution file
        fail_closed: If True, block operations on validation failure
        audit_enabled: If True, enable tamper-evident audit logging

    Returns:
        Initialized ACGSIntegration instance
    """
    global _governance_instance
    _governance_instance = ACGSIntegration(
        constitution_path=constitution_path,
        fail_closed=fail_closed,
        audit_enabled=audit_enabled,
    )
    return _governance_instance
