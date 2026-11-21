"""
Fail-closed behaviour of the acgs-lite layer in ACGSIntegration.

Init-failure tests force ACGS_AVAILABLE on and make engine construction raise,
so they run with or without acgs-lite installed. Tests marked requires_acgs use
the real acgs-lite engine and the real config/governance_rules.yaml.
"""

import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

import backend.governance.acgs_integration as acgs_integration
from backend.governance.acgs_integration import ACGSIntegration

REAL_CONSTITUTION = (
    Path(__file__).resolve().parents[2] / "config" / "governance_rules.yaml"
)
MODULE_PATH = Path(acgs_integration.__file__)

# What the rules engine returns when nothing matches: isolates the acgs layer.
ALLOW_ALL = {
    "valid": True,
    "violations": [],
    "requires_approval": False,
    "matched_rules": [],
}


def _raise_engine(*args, **kwargs):
    raise RuntimeError("secret-engine-detail /private/path")


@pytest.fixture
def broken_acgs_engine(monkeypatch):
    """acgs-lite counts as installed, but building the engine raises.

    The constitution builder is stubbed so the failure is always the
    GovernanceEngine constructor, with or without acgs-lite installed.
    """
    monkeypatch.setattr(acgs_integration, "ACGS_AVAILABLE", True)
    monkeypatch.setattr(acgs_integration, "ACGS_IMPORT_ERROR", None)
    monkeypatch.setattr(
        acgs_integration, "build_acgs_constitution", lambda path: object()
    )
    monkeypatch.setattr(
        acgs_integration, "GovernanceEngine", _raise_engine, raising=False
    )


@pytest.fixture
def stub_acgs_lite(tmp_path, monkeypatch):
    """Install a stub acgs_lite package; restore every acgs_lite* module after."""
    saved = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "acgs_lite"}
    for key in saved:
        del sys.modules[key]
    monkeypatch.syspath_prepend(str(tmp_path))

    def _install(init_source):
        package = tmp_path / "acgs_lite"
        package.mkdir()
        (package / "__init__.py").write_text(init_source)

    yield _install
    for key in [k for k in sys.modules if k.split(".")[0] == "acgs_lite"]:
        del sys.modules[key]
    sys.modules.update(saved)


def _fresh_integration_module():
    """Execute acgs_integration.py again so its import-time detection reruns."""
    spec = importlib.util.spec_from_file_location(
        "backend.governance._acgs_import_probe", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
@pytest.mark.governance
class TestEngineInitFailure:
    def test_init_failure_blocks_benign_operation(
        self, broken_acgs_engine, sample_governance_rules, caplog
    ):
        """Rules engine alone would ALLOW this; the dead acgs layer must BLOCK it."""
        caplog.set_level(logging.ERROR, logger=acgs_integration.__name__)
        integration = ACGSIntegration(
            constitution_path=str(sample_governance_rules), fail_closed=True
        )

        assert integration.acgs_engine is None
        assert integration.rules_engine.validate("List all users", {})["valid"]

        result = integration.validate_operation("List all users", {}, "agent")

        assert result["valid"] is False
        assert result["action"] == "BLOCK"
        assert any(
            v["rule_id"] == "acgs-engine-unavailable" for v in result["violations"]
        )
        assert integration.enforce_decision(result, "List all users") is False
        # The failure came from the stubbed engine constructor, not elsewhere.
        assert any(
            r.levelno == logging.ERROR and "secret-engine-detail" in r.getMessage()
            for r in caplog.records
        )
        assert integration.get_governance_status()["acgs_init_error"] is True

    def test_init_failure_violation_does_not_leak_error(
        self, broken_acgs_engine, sample_governance_rules
    ):
        integration = ACGSIntegration(constitution_path=str(sample_governance_rules))

        result = integration.validate_operation("List all users", {}, "agent")

        violation = next(
            v for v in result["violations"] if v["rule_id"] == "acgs-engine-unavailable"
        )
        assert "secret-engine-detail" not in violation["description"]
        assert "/private/path" not in violation["description"]

    def test_init_failure_blocks_every_operation(
        self, broken_acgs_engine, sample_governance_rules
    ):
        integration = ACGSIntegration(constitution_path=str(sample_governance_rules))

        for op in ("List all users", "Generate report", "Read dashboard"):
            assert integration.validate_operation(op, {}, "agent")["action"] == "BLOCK"

    def test_init_failure_with_fail_closed_false_defers_to_rules_engine(
        self, broken_acgs_engine, sample_governance_rules, caplog
    ):
        """fail_closed=False: the rules engine decides alone, with a logged warning."""
        caplog.set_level(logging.WARNING, logger=acgs_integration.__name__)
        integration = ACGSIntegration(
            constitution_path=str(sample_governance_rules), fail_closed=False
        )

        benign = integration.validate_operation("List all users", {}, "agent")
        harmful = integration.validate_operation("harm users", {}, "agent")

        assert benign["action"] == "ALLOW"
        assert harmful["action"] == "WARN"
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_not_installed_fallback_uses_rules_engine_only(
        self, monkeypatch, sample_governance_rules
    ):
        """acgs-lite absent: documented fallback, the rules engine still enforces."""
        monkeypatch.setattr(acgs_integration, "ACGS_AVAILABLE", False)
        monkeypatch.setattr(acgs_integration, "ACGS_IMPORT_ERROR", None)
        integration = ACGSIntegration(constitution_path=str(sample_governance_rules))

        assert integration.acgs_engine is None
        assert integration.get_governance_status()["acgs_init_error"] is False
        assert (
            integration.validate_operation("List all users", {}, "agent")["action"]
            == "ALLOW"
        )
        assert (
            integration.validate_operation("harm users", {}, "agent")["action"]
            == "BLOCK"
        )

    def test_validation_exception_does_not_leak_error(
        self, sample_governance_rules, caplog
    ):
        """A runtime engine exception blocks with a generic, detail-free violation."""
        caplog.set_level(logging.ERROR, logger=acgs_integration.__name__)
        integration = ACGSIntegration(constitution_path=str(sample_governance_rules))

        class _RaisingEngine:
            def validate(self, *args, **kwargs):
                raise RuntimeError("secret-validate-detail /private/path")

        integration.acgs_engine = _RaisingEngine()

        result = integration.validate_operation("List all users", {}, "agent")

        assert result["action"] == "BLOCK"
        violation = next(
            v for v in result["violations"] if v["rule_id"] == "system-error"
        )
        assert "secret-validate-detail" not in violation["description"]
        assert "/private/path" not in violation["description"]
        assert any("secret-validate-detail" in r.getMessage() for r in caplog.records)


@pytest.mark.unit
@pytest.mark.governance
class TestAcgsImportClassification:
    """Broken install must fail closed; only a genuinely absent package falls back."""

    @pytest.mark.parametrize(
        "init_source",
        [
            # installed, but lacks a name the integration imports
            "class Constitution:\n    pass\n\n\nclass GovernanceEngine:\n    pass\n",
            # installed, but an internal import fails
            'raise ImportError("internal boom")\n',
            # installed, but one of its own dependencies is missing
            "import acgs_lite_missing_dependency_for_test\n",
        ],
        ids=["missing-name", "internal-importerror", "missing-dependency"],
    )
    def test_broken_install_blocks_under_fail_closed(
        self, stub_acgs_lite, sample_governance_rules, init_source
    ):
        stub_acgs_lite(init_source)
        module = _fresh_integration_module()

        assert module.ACGS_AVAILABLE is False
        assert module.ACGS_IMPORT_ERROR is not None
        integration = module.ACGSIntegration(
            constitution_path=str(sample_governance_rules), fail_closed=True
        )
        result = integration.validate_operation("List all users", {}, "agent")

        assert result["valid"] is False
        assert result["action"] == "BLOCK"
        violation = next(
            v for v in result["violations"] if v["rule_id"] == "acgs-engine-unavailable"
        )
        assert "internal boom" not in violation["description"]
        assert integration.get_governance_status()["acgs_init_error"] is True

    def test_genuinely_absent_package_keeps_fallback(
        self, stub_acgs_lite, sample_governance_rules
    ):
        # None in sys.modules -> ModuleNotFoundError(name="acgs_lite"), the same
        # error as an absent package. stub_acgs_lite restores sys.modules after.
        sys.modules["acgs_lite"] = None
        module = _fresh_integration_module()

        assert module.ACGS_AVAILABLE is False
        assert module.ACGS_IMPORT_ERROR is None
        integration = module.ACGSIntegration(
            constitution_path=str(sample_governance_rules), fail_closed=True
        )

        assert integration.get_governance_status()["acgs_init_error"] is False
        benign = integration.validate_operation("List all users", {}, "agent")
        harmful = integration.validate_operation("harm users", {}, "agent")
        assert benign["action"] == "ALLOW"
        assert harmful["action"] == "BLOCK"


@pytest.mark.unit
@pytest.mark.governance
@pytest.mark.requires_acgs
class TestRealEngine:
    @pytest.fixture(autouse=True)
    def _require_acgs(self):
        pytest.importorskip("acgs_lite")

    def test_real_constitution_initializes_engine(self):
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))

        assert integration.acgs_engine is not None
        status = integration.get_governance_status()
        assert status["acgs_engine_initialized"] is True
        assert status["acgs_init_error"] is False

    def test_acgs_layer_blocks_violation_on_its_own(self, isolated_audit_dir):
        """strict=False returns violations; they still BLOCK, independent of RulesEngine."""
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))
        integration.rules_engine.validate = lambda op, ctx, **kw: {
            **ALLOW_ALL,
            "violations": [],
        }

        result = integration.validate_operation(
            "Attack the database server", {"confidence": 0.9}, "agent"
        )
        assert "decision_id" in result

        assert result["valid"] is False
        assert result["action"] == "BLOCK"
        acgs_violations = [
            v for v in result["violations"] if v.get("source") == "acgs-lite"
        ]
        assert [v["rule_id"] for v in acgs_violations] == ["no-harmful-actions"]
        assert acgs_violations[0]["severity"] == "CRITICAL"
        assert acgs_violations[0]["description"] == (
            "Block any harmful or destructive actions"
        )
        # The audit trail serialized the acgs violation as plain JSON.
        records = [
            json.loads(line)
            for f in isolated_audit_dir.glob("audit_*.jsonl")
            for line in f.read_text().splitlines()
        ]
        logged = [
            v
            for r in records
            for v in r["validation_result"]["violations"]
            if v.get("source") == "acgs-lite"
        ]
        assert logged == acgs_violations

    def test_acgs_layer_blocks_pii_on_its_own(self):
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))
        integration.rules_engine.validate = lambda op, ctx, **kw: {
            **ALLOW_ALL,
            "violations": [],
        }

        result = integration.validate_operation("Export customer SSN list", {}, "agent")

        assert result["action"] == "BLOCK"
        assert any(
            v.get("source") == "acgs-lite" and v["rule_id"] == "no-pii-leakage"
            for v in result["violations"]
        )

    def test_benign_operation_still_allowed(self):
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))

        result = integration.validate_operation(
            "List all users", {"confidence": 0.9}, "agent"
        )

        assert result["valid"] is True
        assert result["action"] == "ALLOW"
        assert result["violations"] == []

    @pytest.mark.parametrize(
        "operation",
        [
            "Deploy new instance",
            "Provision staging cluster",
            "autonomous scaling of cluster",
        ],
    )
    def test_approval_rules_are_not_turned_into_blocks(self, operation):
        """Non-BLOCK app rules map to acgs WARN, so REQUIRE_APPROVAL stays gated."""
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))

        result = integration.validate_operation(operation, {"confidence": 0.9}, "agent")

        assert result["action"] == "REQUIRE_APPROVAL"
        assert not any(v.get("source") == "acgs-lite" for v in result["violations"])

    def test_context_is_passed_to_acgs_engine(self):
        integration = ACGSIntegration(constitution_path=str(REAL_CONSTITUTION))
        seen = {}
        real_validate = integration.acgs_engine.validate

        def spy(action, **kwargs):
            seen.update(kwargs)
            return real_validate(action, **kwargs)

        integration.acgs_engine.validate = spy
        context = {"confidence": 0.9}
        integration.validate_operation("List all users", context, "agent-7")

        assert seen["context"] is context
        assert seen["agent_id"] == "agent-7"

    @pytest.mark.parametrize(
        "rule_yaml",
        [
            # non-literal regex in a pattern: cannot be mapped to keywords
            '  - id: r1\n    pattern: "har+m"\n    action: BLOCK\n',
            # context matching has no acgs-lite equivalent
            '  - id: r1\n    pattern: "harm"\n    context_key: amount\n'
            '    context_pattern: "9+"\n    action: BLOCK\n',
            # unknown severity
            '  - id: r1\n    pattern: "harm"\n    severity: EXTREME\n',
        ],
    )
    def test_unmappable_rule_fails_closed(self, temp_dir, rule_yaml):
        path = temp_dir / "rules.yaml"
        path.write_text("rules:\n" + rule_yaml + '  - id: r2\n    pattern: "kill"\n')
        integration = ACGSIntegration(constitution_path=str(path))

        assert integration.acgs_engine is None
        result = integration.validate_operation("List all users", {}, "agent")
        assert result["action"] == "BLOCK"
