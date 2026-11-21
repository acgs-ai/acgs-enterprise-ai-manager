"""
Rule-Based Validation Engine
Implements pattern matching and validation logic for governance rules.
"""

import math
import re
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime
import yaml

logger = logging.getLogger(__name__)

# Rule actions the engine accepts (case-sensitive, as validate() compares them).
KNOWN_ACTIONS = frozenset({"BLOCK", "REQUIRE_APPROVAL", "VALIDATE", "AUDIT", "PROTECT"})

# Every key a rule may carry. Anything else (e.g. a "patern:" typo, or a key
# the engine does not enforce) is a load error: it would otherwise load
# cleanly and silently never match or check anything.
ALLOWED_RULE_KEYS = frozenset(
    {
        # Enforced
        "id",
        "pattern",
        "context_key",
        "context_pattern",
        "action",
        "validation",
        "applies_to",
        # Metadata (value-checked)
        "severity",
        "description",
        "maci_phase",
        "approval_required",
    }
)
KNOWN_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})
KNOWN_MACI_PHASES = frozenset({"MONITOR", "APPROVE", "CONTROL", "INSPECT"})
# Stages a rule can be scoped to via applies_to. "request" is the middleware
# check before a handler runs; "output" is the check on what a handler produced.
KNOWN_STAGES = frozenset({"request", "output"})
NUMERIC_VALIDATION_KEYS = frozenset(
    {
        "min_confidence",
        "max_amount",
        "require_approval_above",
        "max_batch_size",
        "min_retention_days",
        "max_retention_days",
    }
)
ALLOWED_VALIDATION_KEYS = NUMERIC_VALIDATION_KEYS | {"require_explanation"}


def _is_number(value: Any) -> bool:
    """True for a finite int/float/Decimal; bool is not a number here."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    return math.isfinite(value)


def _check_rule_schema(rule: Dict[str, Any]) -> None:
    """Raise ValueError unless every key of ``rule`` is known and usable."""
    rule_id = rule.get("id")
    unknown = sorted(str(k) for k in set(rule) - ALLOWED_RULE_KEYS)
    if unknown:
        raise ValueError(f"rule {rule_id}: unknown key(s) {unknown}")

    action = rule.get("action", "BLOCK")
    if "severity" in rule and rule["severity"] not in KNOWN_SEVERITIES:
        raise ValueError(f"rule {rule_id}: invalid severity {rule['severity']!r}")
    if "maci_phase" in rule and rule["maci_phase"] not in KNOWN_MACI_PHASES:
        raise ValueError(f"rule {rule_id}: invalid maci_phase {rule['maci_phase']!r}")
    if "description" in rule and not isinstance(rule["description"], str):
        raise ValueError(f"rule {rule_id}: description must be a string")
    if "approval_required" in rule and (
        rule["approval_required"] is not True or action != "REQUIRE_APPROVAL"
    ):
        raise ValueError(
            f"rule {rule_id}: approval_required may only be true on a "
            "REQUIRE_APPROVAL rule"
        )

    # Matching: a rule with neither pattern nor context_key can never match.
    if "pattern" not in rule and "context_key" not in rule:
        raise ValueError(f"rule {rule_id}: needs 'pattern' or 'context_key'")
    if "pattern" in rule and not isinstance(rule["pattern"], str):
        raise ValueError(f"rule {rule_id}: pattern must be a string")
    if ("context_key" in rule) != ("context_pattern" in rule):
        raise ValueError(
            f"rule {rule_id}: context_key and context_pattern must appear together"
        )
    for key in ("context_key", "context_pattern"):
        if key in rule and (not isinstance(rule[key], str) or not rule[key]):
            raise ValueError(f"rule {rule_id}: {key} must be a non-empty string")

    if "applies_to" in rule:
        stages = rule["applies_to"]
        if (
            not isinstance(stages, list)
            or not stages
            or any(stage not in KNOWN_STAGES for stage in stages)
        ):
            raise ValueError(
                f"rule {rule_id}: applies_to must be a non-empty list of "
                f"{sorted(KNOWN_STAGES)}"
            )

    # validation is required on, and only allowed on, VALIDATE rules.
    if action != "VALIDATE":
        if "validation" in rule:
            raise ValueError(
                f"rule {rule_id}: 'validation' is only allowed on VALIDATE rules"
            )
        return
    validation = rule.get("validation")
    if not isinstance(validation, dict) or not validation:
        raise ValueError(f"rule {rule_id}: VALIDATE needs a non-empty 'validation'")
    unknown = sorted(str(k) for k in set(validation) - ALLOWED_VALIDATION_KEYS)
    if unknown:
        raise ValueError(f"rule {rule_id}: unknown validation key(s) {unknown}")
    for key, value in validation.items():
        if key in NUMERIC_VALIDATION_KEYS and not _is_number(value):
            raise ValueError(f"rule {rule_id}: validation {key} must be a number")
    if (
        "require_explanation" in validation
        and validation["require_explanation"] is not True
    ):
        raise ValueError(f"rule {rule_id}: require_explanation must be true")


class RulesEngine:
    """
    Rule-based validation engine for governance framework.

    Validates operations against constitutional rules with pattern matching,
    severity levels, and action enforcement.
    """

    def __init__(self, constitution_path: str):
        """
        Initialize rules engine with constitution file.

        Args:
            constitution_path: Path to YAML constitution file
        """
        self.constitution_path = constitution_path
        self.rules: List[Dict[str, Any]] = []
        self.enforcement_config: Dict[str, Any] = {}
        self.audit_config: Dict[str, Any] = {}
        # Set when the constitution cannot be loaded; validate() then fails closed.
        self.load_error: Optional[str] = None

        self._load_constitution()

    def _load_constitution(self):
        """Load and parse constitution YAML file."""
        self.load_error = None
        try:
            with open(self.constitution_path, "r") as f:
                constitution = yaml.safe_load(f)

            if not isinstance(constitution, dict):
                raise TypeError("constitution must be a YAML mapping")

            # A missing or empty rule list (e.g. a "rule:" typo) must not
            # become allow-all; treat it as an untrusted constitution.
            if "rules" not in constitution:
                raise ValueError("constitution is missing 'rules'")
            rules = constitution["rules"]
            if not isinstance(rules, list):
                raise TypeError("constitution 'rules' must be a list")
            if not rules:
                raise ValueError("constitution 'rules' is empty")

            # Every rule needs a unique, non-empty string id; validate()
            # reports matches by id.
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

            self.rules = rules
            self.enforcement_config = constitution.get("enforcement", {})
            self.audit_config = constitution.get("audit", {})

            # Compile regex patterns. An invalid regex makes the whole
            # constitution untrusted (fail closed via load_error), rather than
            # silently disabling the rule.
            for rule in self.rules:
                # Unknown actions (e.g. a "BLOK" typo) would otherwise match
                # without adding a violation and silently allow. Missing
                # action still defaults to BLOCK in validate().
                action = rule.get("action", "BLOCK")
                if action not in KNOWN_ACTIONS:
                    raise ValueError(
                        f"Unknown action {action!r} in rule {rule.get('id')}"
                    )
                # Runs on the raw YAML keys, before _compiled_pattern is added.
                _check_rule_schema(rule)
                try:
                    if "pattern" in rule:
                        rule["_compiled_pattern"] = re.compile(
                            rule["pattern"], re.IGNORECASE
                        )
                    if rule.get("context_pattern"):
                        re.compile(rule["context_pattern"], re.IGNORECASE)
                except re.error as e:
                    raise ValueError(
                        f"Invalid regex in rule {rule.get('id')}: {e}"
                    ) from e

            logger.info(f"Loaded {len(self.rules)} governance rules")

        except FileNotFoundError:
            self.load_error = f"Constitution file not found: {self.constitution_path}"
            logger.error(self.load_error)
            self.rules = []
        except yaml.YAMLError as e:
            self.load_error = f"Failed to parse constitution YAML: {e}"
            logger.error(self.load_error)
            self.rules = []
        except Exception as e:
            self.load_error = f"Error loading constitution: {e}"
            logger.error(self.load_error)
            self.rules = []

    def validate(
        self, operation: str, context: Dict[str, Any], stage: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate an operation against all governance rules.

        Args:
            operation: Description of the operation to validate
            context: Additional context for validation
            stage: "request" or "output". A rule is skipped only when a stage is
                given and the rule's applies_to does not list it; with no stage,
                or a rule without applies_to, every rule applies.

        Returns:
            Dict containing validation result:
                - valid: bool
                - violations: List[Dict]
                - requires_approval: bool
                - matched_rules: List[str]
        """
        # Fail closed: without a loaded constitution nothing can be validated.
        if self.load_error is not None:
            return {
                "valid": False,
                "violations": [
                    {
                        "rule_id": "constitution-unavailable",
                        "severity": "CRITICAL",
                        # Generic on purpose: this reaches API 403 bodies.
                        # Details stay in load_error and the log.
                        "description": (
                            "Governance constitution unavailable; operation blocked"
                        ),
                        "action": "BLOCK",
                    }
                ],
                "requires_approval": False,
                "matched_rules": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        # An unknown stage (e.g. a "reqest" typo) must not skip stage-scoped rules.
        if stage is not None and stage not in KNOWN_STAGES:
            logger.error(f"Unknown governance stage {stage!r}; blocking")
            return {
                "valid": False,
                "violations": [
                    {
                        "rule_id": "invalid-governance-stage",
                        "severity": "CRITICAL",
                        "description": "Unknown governance stage; operation blocked",
                        "action": "BLOCK",
                    }
                ],
                "requires_approval": False,
                "matched_rules": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

        violations = []
        matched_rules = []
        requires_approval = False

        # Check each rule
        for rule in self.rules:
            if stage is not None and stage not in rule.get("applies_to", KNOWN_STAGES):
                continue

            match_result = self._check_rule(rule, operation, context)

            if match_result["matched"]:
                matched_rules.append(rule["id"])

                action = rule.get("action", "BLOCK")
                severity = rule.get("severity", "MEDIUM")

                if action == "BLOCK":
                    violations.append(
                        {
                            "rule_id": rule["id"],
                            "severity": severity,
                            "description": rule.get("description", "Rule violation"),
                            "pattern": rule.get("pattern", ""),
                            "action": action,
                        }
                    )
                elif action == "REQUIRE_APPROVAL":
                    requires_approval = True
                    violations.append(
                        {
                            "rule_id": rule["id"],
                            "severity": severity,
                            "description": rule.get("description", "Approval required"),
                            "pattern": rule.get("pattern", ""),
                            "action": action,
                        }
                    )
                elif action == "VALIDATE":
                    # Perform additional validation checks
                    validation_result = self._perform_validation(
                        rule, operation, context
                    )
                    if not validation_result["valid"]:
                        violations.append(
                            {
                                "rule_id": rule["id"],
                                "severity": severity,
                                "description": validation_result["reason"],
                                "action": "BLOCK",
                            }
                        )
                    elif validation_result.get("requires_approval"):
                        requires_approval = True
                        violations.append(
                            {
                                "rule_id": rule["id"],
                                "severity": severity,
                                "description": validation_result["reason"],
                                "action": "REQUIRE_APPROVAL",
                            }
                        )

        # Determine overall validity
        # Operation is valid if no blocking violations
        blocking_violations = [v for v in violations if v["action"] == "BLOCK"]

        valid = len(blocking_violations) == 0

        return {
            "valid": valid,
            "violations": violations,
            "requires_approval": requires_approval,
            "matched_rules": matched_rules,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _check_rule(
        self, rule: Dict[str, Any], operation: str, context: Dict[str, Any]
    ) -> Dict[str, bool]:
        """
        Check if a rule matches the operation.

        Args:
            rule: Rule definition
            operation: Operation to check
            context: Additional context

        Returns:
            Dict with 'matched' boolean
        """
        # Pattern matching
        if "_compiled_pattern" in rule and rule["_compiled_pattern"]:
            if rule["_compiled_pattern"].search(operation):
                return {"matched": True}

        # Context-based matching
        if "context_key" in rule:
            context_value = context.get(rule["context_key"])
            if context_value and rule.get("context_pattern"):
                try:
                    pattern = re.compile(rule["context_pattern"], re.IGNORECASE)
                    if pattern.search(str(context_value)):
                        return {"matched": True}
                except re.error:
                    pass

        return {"matched": False}

    def _perform_validation(
        self, rule: Dict[str, Any], operation: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform validation checks defined in rule.

        Args:
            rule: Rule with validation configuration
            operation: Operation being validated
            context: Additional context

        Returns:
            Dict with 'valid' boolean and 'reason' string, plus
            'requires_approval' True when only an approval threshold was hit.

        Missing or unusable context fails closed: a check whose context key is
        absent, None, non-numeric or NaN blocks instead of defaulting to 0.
        Every blocking check runs before the approval check, so an amount above
        max_amount blocks rather than asking for approval.
        """
        validation_config = rule["validation"]

        def number(key: str):
            if context.get(key) is None:
                return None, f"missing context '{key}'"
            if not _is_number(context[key]):
                return None, f"invalid context '{key}'"
            return context[key], None

        # Check confidence threshold
        if "min_confidence" in validation_config:
            confidence, error = number("confidence")
            if error:
                return {"valid": False, "reason": error}
            min_confidence = validation_config["min_confidence"]
            if confidence < min_confidence:
                return {
                    "valid": False,
                    "reason": f"Confidence {confidence} below threshold {min_confidence}",
                }

        # Check amount limits
        if "max_amount" in validation_config:
            amount, error = number("amount")
            if error:
                return {"valid": False, "reason": error}
            max_amount = validation_config["max_amount"]
            if amount > max_amount:
                return {
                    "valid": False,
                    "reason": f"Amount {amount} exceeds limit {max_amount}",
                }

        # Check batch size limits
        if "max_batch_size" in validation_config:
            batch_size, error = number("batch_size")
            if error:
                return {"valid": False, "reason": error}
            max_batch_size = validation_config["max_batch_size"]
            if batch_size > max_batch_size:
                return {
                    "valid": False,
                    "reason": f"Batch size {batch_size} exceeds limit {max_batch_size}",
                }

        # Check retention policy
        if (
            "min_retention_days" in validation_config
            or "max_retention_days" in validation_config
        ):
            retention_days, error = number("retention_days")
            if error:
                return {"valid": False, "reason": error}
            min_retention = validation_config.get("min_retention_days")
            if min_retention is not None and retention_days < min_retention:
                return {
                    "valid": False,
                    "reason": f"Retention {retention_days} days below minimum {min_retention}",
                }
            max_retention = validation_config.get("max_retention_days")
            if max_retention is not None and retention_days > max_retention:
                return {
                    "valid": False,
                    "reason": f"Retention {retention_days} days above maximum {max_retention}",
                }

        # Check explanation (transparency control)
        if validation_config.get("require_explanation"):
            rationale = context.get("rationale")
            if not isinstance(rationale, str) or not rationale.strip():
                return {"valid": False, "reason": "missing context 'rationale'"}

        # Approval threshold: last, after every blocking check passed.
        if "require_approval_above" in validation_config:
            amount, error = number("amount")
            if error:
                return {"valid": False, "reason": error}
            threshold = validation_config["require_approval_above"]
            if amount > threshold:
                return {
                    "valid": True,
                    "requires_approval": True,
                    "reason": f"Amount {amount} above approval threshold {threshold}",
                }

        return {"valid": True, "reason": "Validation passed"}

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """
        Get rule by ID.

        Args:
            rule_id: Rule identifier

        Returns:
            Rule dict or None if not found
        """
        for rule in self.rules:
            if rule.get("id") == rule_id:
                return rule
        return None

    def get_rules_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        """
        Get all rules with specified severity.

        Args:
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW)

        Returns:
            List of matching rules
        """
        return [rule for rule in self.rules if rule.get("severity") == severity]

    def reload_constitution(self):
        """Reload constitution from file."""
        self._load_constitution()
        logger.info("Constitution reloaded")
