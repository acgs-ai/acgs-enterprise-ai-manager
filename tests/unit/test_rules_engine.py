"""
Unit tests for RulesEngine
Tests pattern matching, validation logic, and rule enforcement.
"""

import pytest
from pathlib import Path
from backend.governance.rules_engine import RulesEngine


@pytest.mark.unit
@pytest.mark.governance
class TestRulesEngine:
    """Test suite for RulesEngine class."""

    def test_initialization_with_valid_constitution(self, sample_governance_rules):
        """Test RulesEngine initializes correctly with valid constitution file."""
        engine = RulesEngine(str(sample_governance_rules))

        assert engine is not None
        assert len(engine.rules) == 3
        assert engine.enforcement_config["fail_mode"] == "CLOSED"
        assert engine.audit_config["enabled"] is True

    def test_initialization_with_missing_file(self, temp_dir):
        """Test RulesEngine handles missing constitution file gracefully."""
        missing_file = temp_dir / "nonexistent.yaml"
        engine = RulesEngine(str(missing_file))

        assert engine.rules == []
        assert engine.load_error is not None
        assert "not found" in engine.load_error

    def test_missing_constitution_fails_closed(self, temp_dir, sample_context):
        """Benign operations are blocked when the constitution file is missing."""
        engine = RulesEngine(str(temp_dir / "nonexistent.yaml"))

        result = engine.validate("List all users", sample_context)

        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "constitution-unavailable"
        assert result["violations"][0]["action"] == "BLOCK"
        assert result["violations"][0]["severity"] == "CRITICAL"

    def test_harmful_operation_blocked_when_constitution_missing(
        self, temp_dir, sample_context
    ):
        """Harmful operations stay blocked when the constitution is missing."""
        engine = RulesEngine(str(temp_dir / "nonexistent.yaml"))

        result = engine.validate("harm users", sample_context)

        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    def test_malformed_yaml_fails_closed(self, temp_dir, sample_context):
        """Unparseable constitution YAML records a load error and blocks."""
        bad_file = temp_dir / "bad.yaml"
        bad_file.write_text("rules: [\n")

        engine = RulesEngine(str(bad_file))
        result = engine.validate("List all users", sample_context)

        assert engine.load_error is not None
        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    def test_empty_file_fails_closed(self, temp_dir, sample_context):
        """A zero-byte constitution is not a constitution; it must block."""
        empty_file = temp_dir / "empty.yaml"
        empty_file.write_text("")

        engine = RulesEngine(str(empty_file))

        assert engine.load_error is not None
        assert engine.validate("List all users", sample_context)["valid"] is False

    def test_empty_rules_list_is_not_an_error(self, temp_dir, sample_context):
        """An explicitly empty rule list loads cleanly (no load error)."""
        rules_file = temp_dir / "empty_rules.yaml"
        rules_file.write_text("rules: []\n")

        engine = RulesEngine(str(rules_file))
        result = engine.validate("List all users", sample_context)

        assert engine.load_error is None
        assert engine.rules == []
        assert result["valid"] is True

    @pytest.mark.parametrize("action", ["BLOCK", "REQUIRE_APPROVAL"])
    def test_invalid_regex_fails_closed(self, temp_dir, sample_context, action):
        """A rule whose pattern does not compile must not silently disable itself."""
        rules_file = temp_dir / "bad_regex.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: bad-rule\n"
            '    pattern: "harm|("\n'
            f"    action: {action}\n"
            "    severity: CRITICAL\n"
        )

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is not None
        assert "bad-rule" in engine.load_error
        for operation in ("harm users", "List all users"):
            result = engine.validate(operation, sample_context)
            assert result["valid"] is False
            assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    def test_invalid_context_pattern_fails_closed(self, temp_dir, sample_context):
        """An invalid context_pattern is also a load error, not a skipped rule."""
        rules_file = temp_dir / "bad_ctx.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: bad-ctx\n"
            "    context_key: user_id\n"
            '    context_pattern: "test_("\n'
            "    action: BLOCK\n"
        )

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is not None
        assert engine.validate("List all users", sample_context)["valid"] is False

    def test_unmatched_operation_allowed_by_default(
        self, sample_governance_rules, sample_context
    ):
        """Pin current policy: operations matching no rule are allowed.

        Default-deny (enforcement.default_action) is a tracked follow-up; if it
        is implemented this test must change deliberately.
        """
        engine = RulesEngine(str(sample_governance_rules))

        result = engine.validate("Read the quarterly calendar", sample_context)

        assert result["valid"] is True
        assert result["matched_rules"] == []
        assert result["violations"] == []

    def test_reload_recovers_after_load_error(self, temp_dir, sample_context):
        """A successful reload clears a previous load error."""
        rules_file = temp_dir / "later.yaml"
        engine = RulesEngine(str(rules_file))
        assert engine.load_error is not None

        rules_file.write_text("rules: []\n")
        engine.reload_constitution()

        assert engine.load_error is None
        assert engine.validate("List all users", sample_context)["valid"] is True

    def test_validate_blocking_operation(self, sample_governance_rules, sample_context):
        """Test validation blocks operations matching BLOCK rules."""
        engine = RulesEngine(str(sample_governance_rules))

        result = engine.validate("This is a dangerous operation", sample_context)

        assert result["valid"] is False
        assert len(result["violations"]) > 0
        assert result["violations"][0]["action"] == "BLOCK"
        assert result["violations"][0]["rule_id"] == "test-block-rule"

    def test_validate_approval_required_operation(
        self, sample_governance_rules, sample_context
    ):
        """Test validation requires approval for REQUIRE_APPROVAL rules."""
        engine = RulesEngine(str(sample_governance_rules))

        result = engine.validate("Delete user data", sample_context)

        assert result["requires_approval"] is True
        assert len(result["violations"]) > 0
        assert result["violations"][0]["action"] == "REQUIRE_APPROVAL"
        assert result["violations"][0]["rule_id"] == "test-approval-rule"

    def test_validate_with_confidence_threshold(self, sample_governance_rules):
        """Test validation enforces confidence thresholds."""
        engine = RulesEngine(str(sample_governance_rules))

        # Low confidence - should fail validation
        low_confidence_context = {"confidence": 0.5}
        result = engine.validate("I recommend this action", low_confidence_context)

        assert result["valid"] is False
        assert any(
            "confidence" in v["description"].lower() for v in result["violations"]
        )

    def test_validate_with_high_confidence(self, sample_governance_rules):
        """Test validation passes with sufficient confidence."""
        engine = RulesEngine(str(sample_governance_rules))

        # High confidence - should pass validation
        high_confidence_context = {"confidence": 0.85}
        result = engine.validate("I recommend this action", high_confidence_context)

        assert result["valid"] is True
        assert "test-validate-rule" in result["matched_rules"]

    def test_validate_safe_operation(self, sample_governance_rules, sample_context):
        """Test validation allows safe operations."""
        engine = RulesEngine(str(sample_governance_rules))

        result = engine.validate("List all users", sample_context)

        assert result["valid"] is True
        assert len(result["violations"]) == 0
        assert result["requires_approval"] is False

    def test_get_rule_by_id(self, sample_governance_rules):
        """Test retrieving rule by ID."""
        engine = RulesEngine(str(sample_governance_rules))

        rule = engine.get_rule("test-block-rule")

        assert rule is not None
        assert rule["id"] == "test-block-rule"
        assert rule["severity"] == "CRITICAL"

    def test_get_rule_by_id_not_found(self, sample_governance_rules):
        """Test retrieving non-existent rule returns None."""
        engine = RulesEngine(str(sample_governance_rules))

        rule = engine.get_rule("nonexistent-rule")

        assert rule is None

    def test_get_rules_by_severity(self, sample_governance_rules):
        """Test filtering rules by severity level."""
        engine = RulesEngine(str(sample_governance_rules))

        critical_rules = engine.get_rules_by_severity("CRITICAL")

        assert len(critical_rules) == 1
        assert critical_rules[0]["id"] == "test-block-rule"

    def test_pattern_matching_case_insensitive(
        self, sample_governance_rules, sample_context
    ):
        """Test pattern matching is case-insensitive."""
        engine = RulesEngine(str(sample_governance_rules))

        result_lower = engine.validate("dangerous operation", sample_context)
        result_upper = engine.validate("DANGEROUS OPERATION", sample_context)
        result_mixed = engine.validate("DaNgErOuS OpErAtIoN", sample_context)

        assert result_lower["valid"] is False
        assert result_upper["valid"] is False
        assert result_mixed["valid"] is False

    def test_reload_constitution(self, sample_governance_rules):
        """Test reloading constitution updates rules."""
        engine = RulesEngine(str(sample_governance_rules))
        initial_count = len(engine.rules)

        engine.reload_constitution()

        assert len(engine.rules) == initial_count
