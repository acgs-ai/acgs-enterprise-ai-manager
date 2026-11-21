"""
Unit tests for RulesEngine
Tests pattern matching, validation logic, and rule enforcement.
"""

import pytest
import yaml
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

    @pytest.mark.parametrize(
        "content",
        ["rules: []\n", "rule:\n  - id: x\n    pattern: harm\n", "metadata: {}\n"],
        ids=["empty-list", "rule-typo", "no-rules-key"],
    )
    def test_missing_or_empty_rules_fails_closed(
        self, temp_dir, sample_context, content
    ):
        """A missing or empty rule list must not turn into allow-all."""
        rules_file = temp_dir / "no_rules.yaml"
        rules_file.write_text(content)

        engine = RulesEngine(str(rules_file))
        result = engine.validate("List all users", sample_context)

        assert engine.load_error is not None
        assert engine.rules == []
        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    @pytest.mark.parametrize(
        "rules_yaml",
        [
            '  - pattern: "harm"\n',
            '  - id: ""\n    pattern: "harm"\n',
            '  - id: 42\n    pattern: "harm"\n',
            '  - id: dup\n    pattern: "a"\n  - id: dup\n    pattern: "b"\n',
        ],
        ids=["missing-id", "empty-id", "non-string-id", "duplicate-id"],
    )
    def test_bad_rule_id_fails_closed(self, temp_dir, sample_context, rules_yaml):
        """Every rule needs a unique, non-empty string id."""
        rules_file = temp_dir / "bad_id.yaml"
        rules_file.write_text("rules:\n" + rules_yaml)

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is not None
        for operation in ("harm users", "List all users"):
            result = engine.validate(operation, sample_context)
            assert result["valid"] is False
            assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    def test_unavailable_description_hides_details(self, temp_dir, sample_context):
        """The violation description is generic: no path, no exception text."""
        rules_file = temp_dir / "secret_dir" / "bad.yaml"
        rules_file.parent.mkdir()
        rules_file.write_text(
            'rules:\n  - id: leaky-rule\n    pattern: "harm|("\n    action: BLOCK\n'
        )

        engine = RulesEngine(str(rules_file))
        description = engine.validate("harm", sample_context)["violations"][0][
            "description"
        ]

        assert "leaky-rule" in engine.load_error
        assert description == "Governance constitution unavailable; operation blocked"
        assert str(rules_file) not in description
        assert "secret_dir" not in description
        assert "leaky-rule" not in description
        assert "missing )" not in description

        missing = RulesEngine(str(temp_dir / "secret_dir" / "missing.yaml"))
        description = missing.validate("x", sample_context)["violations"][0][
            "description"
        ]
        assert "missing.yaml" in missing.load_error
        assert "missing.yaml" not in description
        assert "not found" not in description

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

    def test_unknown_action_fails_closed(self, temp_dir, sample_context):
        """A rule with an unknown action (typo) makes the constitution untrusted."""
        rules_file = temp_dir / "typo_action.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: typo-rule\n"
            '    pattern: "harm"\n'
            "    action: BLOK\n"
        )

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is not None
        assert "BLOK" in engine.load_error
        for operation in ("harm users", "List all users"):
            result = engine.validate(operation, sample_context)
            assert result["valid"] is False
            assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    @pytest.mark.parametrize(
        "action", ["BLOCK", "REQUIRE_APPROVAL", "VALIDATE", "AUDIT", "PROTECT"]
    )
    def test_known_actions_load(self, temp_dir, action):
        """Each known action loads without a load error."""
        rules_file = temp_dir / "known_action.yaml"
        validation = "    validation:\n      max_batch_size: 10\n"
        rules_file.write_text(
            "rules:\n"
            "  - id: known-rule\n"
            '    pattern: "example"\n'
            f"    action: {action}\n" + (validation if action == "VALIDATE" else "")
        )

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is None
        assert len(engine.rules) == 1

    def test_missing_action_defaults_to_block(self, temp_dir, sample_context):
        """A rule without an action still loads and blocks on match."""
        rules_file = temp_dir / "no_action.yaml"
        rules_file.write_text('rules:\n  - id: no-action\n    pattern: "harm"\n')

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is None
        assert engine.validate("harm users", sample_context)["valid"] is False

    def test_production_constitution_loads(self):
        """The shipped config loads cleanly (all actions known, all regexes valid)."""
        config = (
            Path(__file__).resolve().parents[2] / "config" / "governance_rules.yaml"
        )

        engine = RulesEngine(str(config))

        assert engine.load_error is None
        assert len(engine.rules) == len(yaml.safe_load(config.read_text())["rules"])

    @pytest.mark.parametrize(
        "rule_yaml",
        [
            '    patern: "harm"\n    action: BLOCK\n',
            '    pattern: "x"\n    action: VALIDATE\n'
            "    validation:\n      max_amont: 5\n",
            '    pattern: "x"\n    action: VALIDATE\n    validation: null\n',
            '    pattern: "x"\n    action: VALIDATE\n    validation: {}\n',
            '    pattern: "x"\n    action: VALIDATE\n',
            '    pattern: "x"\n    action: BLOCK\n'
            "    validation:\n      max_amount: 5\n",
            "    context_key: user_id\n    action: BLOCK\n",
            '    context_pattern: "x"\n    action: BLOCK\n',
            "    action: BLOCK\n    severity: CRITICAL\n",
            '    pattern: "x"\n    severity: SEVERE\n',
            '    pattern: "x"\n    maci_phase: OBSERVE\n',
            '    pattern: "x"\n    action: VALIDATE\n'
            '    validation:\n      max_amount: "5000"\n',
            '    pattern: "x"\n    action: VALIDATE\n'
            "    validation:\n      min_confidence: true\n",
            '    pattern: "x"\n    action: VALIDATE\n'
            "    validation:\n      require_explanation: false\n",
            '    pattern: "x"\n    action: BLOCK\n    approval_required: true\n',
            '    pattern: "x"\n    action: REQUIRE_APPROVAL\n'
            "    approval_required: false\n",
            '    pattern: "x"\n    description: 42\n',
            '    pattern: "x"\n    applies_to: []\n',
            '    pattern: "x"\n    applies_to: [response]\n',
            '    pattern: "x"\n    applies_to: output\n',
            '    pattern: "x"\n    immutable: true\n',
        ],
        ids=[
            "patern-typo",
            "unknown-validation-key",
            "validation-null",
            "validation-empty",
            "validate-without-validation",
            "validation-on-block",
            "context-key-without-pattern",
            "context-pattern-without-key",
            "no-pattern-no-context-key",
            "bad-severity",
            "bad-maci-phase",
            "string-threshold",
            "bool-threshold",
            "require-explanation-false",
            "approval-required-on-block",
            "approval-required-false",
            "non-string-description",
            "applies-to-empty",
            "applies-to-unknown-stage",
            "applies-to-not-a-list",
            "unenforced-key",
        ],
    )
    def test_unusable_rule_keys_fail_closed(self, temp_dir, rule_yaml):
        """Unknown or unusable rule keys make the whole constitution untrusted."""
        rules_file = temp_dir / "strict.yaml"
        rules_file.write_text("rules:\n  - id: strict-rule\n" + rule_yaml)

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is not None
        assert "strict-rule" in engine.load_error
        result = engine.validate("hello", {})
        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "constitution-unavailable"

    def test_metadata_keys_load(self, temp_dir):
        """Allowlisted metadata with valid values loads cleanly."""
        rules_file = temp_dir / "meta.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: meta-rule\n"
            '    pattern: "x"\n'
            "    action: REQUIRE_APPROVAL\n"
            "    severity: LOW\n"
            '    description: "d"\n'
            "    maci_phase: APPROVE\n"
            "    approval_required: true\n"
            "    applies_to: [request, output]\n"
            "  - id: ctx-rule\n"
            "    context_key: user_id\n"
            '    context_pattern: "^admin$"\n'
            "    action: AUDIT\n"
        )

        engine = RulesEngine(str(rules_file))

        assert engine.load_error is None
        assert len(engine.rules) == 2

    @staticmethod
    def _validate_engine(temp_dir, validation_yaml):
        rules_file = temp_dir / "validate.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: check-rule\n"
            '    pattern: "op"\n'
            "    action: VALIDATE\n"
            "    validation:\n" + validation_yaml
        )
        engine = RulesEngine(str(rules_file))
        assert engine.load_error is None
        return engine

    @pytest.mark.parametrize(
        "validation_yaml, context_key",
        [
            ("      min_confidence: 0.5\n", "confidence"),
            ("      max_amount: 100\n", "amount"),
            ("      require_approval_above: 100\n", "amount"),
            ("      max_batch_size: 10\n", "batch_size"),
            ("      min_retention_days: 10\n", "retention_days"),
            ("      max_retention_days: 10\n", "retention_days"),
            ("      require_explanation: true\n", "rationale"),
        ],
    )
    @pytest.mark.parametrize("bad_value", ["absent", None, "", True, float("nan")])
    def test_missing_context_blocks(
        self, temp_dir, validation_yaml, context_key, bad_value
    ):
        """A check whose context is missing or unusable blocks, never defaults."""
        engine = self._validate_engine(temp_dir, validation_yaml)
        context = {} if bad_value == "absent" else {context_key: bad_value}

        result = engine.validate("op", context)

        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "check-rule"
        assert f"context '{context_key}'" in result["violations"][0]["description"]

    def test_max_retention_days(self, temp_dir):
        engine = self._validate_engine(
            temp_dir, "      min_retention_days: 90\n      max_retention_days: 2555\n"
        )

        assert engine.validate("op", {"retention_days": 2555})["valid"] is True
        result = engine.validate("op", {"retention_days": 2556})
        assert result["valid"] is False
        assert "above maximum 2555" in result["violations"][0]["description"]
        assert engine.validate("op", {"retention_days": 89})["valid"] is False

    def test_require_approval_above(self, temp_dir):
        engine = self._validate_engine(
            temp_dir, "      max_amount: 10000\n      require_approval_above: 5000\n"
        )

        at_threshold = engine.validate("op", {"amount": 5000})
        assert at_threshold["valid"] is True
        assert at_threshold["requires_approval"] is False
        assert at_threshold["violations"] == []

        above = engine.validate("op", {"amount": 5000.01})
        assert above["valid"] is True
        assert above["requires_approval"] is True
        assert above["violations"][0]["action"] == "REQUIRE_APPROVAL"
        assert above["violations"][0]["rule_id"] == "check-rule"

        # Over the hard limit: blocked, not merely sent for approval.
        over = engine.validate("op", {"amount": 10001})
        assert over["valid"] is False
        assert over["requires_approval"] is False
        assert over["violations"][0]["action"] == "BLOCK"

    def test_require_explanation(self, temp_dir):
        engine = self._validate_engine(temp_dir, "      require_explanation: true\n")

        assert engine.validate("op", {"rationale": "because"})["valid"] is True
        assert engine.validate("op", {"rationale": "   "})["valid"] is False
        assert engine.validate("op", {"rationale": 42})["valid"] is False

    @staticmethod
    def _staged_engine(temp_dir):
        rules_file = temp_dir / "staged.yaml"
        rules_file.write_text(
            "rules:\n"
            "  - id: output-only\n"
            '    pattern: "recommend"\n'
            "    action: VALIDATE\n"
            "    applies_to: [output]\n"
            "    validation:\n      min_confidence: 0.75\n"
            "  - id: any-stage\n"
            '    pattern: "harm"\n'
            "    action: BLOCK\n"
            "  - id: request-only\n"
            '    pattern: "audit"\n'
            "    action: AUDIT\n"
            "    applies_to: [request]\n"
        )
        engine = RulesEngine(str(rules_file))
        assert engine.load_error is None
        return engine

    def test_no_stage_applies_output_only_rules(self, temp_dir):
        engine = self._staged_engine(temp_dir)

        result = engine.validate("recommend audit", {})

        assert result["valid"] is False
        assert result["matched_rules"] == ["output-only", "request-only"]

    def test_request_stage_skips_only_output_rules(self, temp_dir):
        engine = self._staged_engine(temp_dir)

        result = engine.validate("recommend audit", {}, stage="request")
        assert result["valid"] is True
        assert result["matched_rules"] == ["request-only"]

        # Rules without applies_to still apply at every stage.
        assert engine.validate("harm", {}, stage="request")["valid"] is False
        assert engine.validate("harm", {}, stage="output")["valid"] is False

    def test_output_stage_applies_output_rules(self, temp_dir):
        engine = self._staged_engine(temp_dir)

        low = engine.validate("recommend audit", {"confidence": 0.5}, stage="output")
        assert low["valid"] is False
        assert low["matched_rules"] == ["output-only"]
        high = engine.validate("recommend", {"confidence": 0.9}, stage="output")
        assert high["valid"] is True

    def test_unknown_stage_blocks(self, temp_dir):
        """A stage typo must not silently skip stage-scoped rules."""
        engine = self._staged_engine(temp_dir)

        result = engine.validate("recommend", {"confidence": 0.1}, stage="reqest")

        assert result["valid"] is False
        assert result["violations"][0]["rule_id"] == "invalid-governance-stage"

    def test_shipped_financial_limits(self):
        """The shipped constitution approves above 5000 and blocks above 10000."""
        config = (
            Path(__file__).resolve().parents[2] / "config" / "governance_rules.yaml"
        )
        engine = RulesEngine(str(config))

        assert engine.validate("payment", {"amount": 4000})["valid"] is True
        assert engine.validate("payment", {"amount": 6000})["requires_approval"]
        assert engine.validate("payment", {"amount": 20000})["valid"] is False
        assert engine.validate("payment", {})["valid"] is False

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

        rules_file.write_text('rules:\n  - id: only-rule\n    pattern: "harm"\n')
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
