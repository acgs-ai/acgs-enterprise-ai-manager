# ACGS Enterprise Manager - Testing Guide

## Overview

This document describes the testing strategy and infrastructure for the ACGS Enterprise Manager project.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and utilities
├── unit/                    # Unit tests (70% of test suite)
│   ├── test_acgs_integration.py
│   ├── test_audit_logger.py
│   └── test_rules_engine.py
├── integration/             # Integration tests (20% of test suite)
│   ├── test_api_endpoints.py
│   └── test_governance_integration.py
├── e2e/                     # End-to-end tests (10% of test suite)
│   └── test_workflows.py
└── governance/              # Governance-specific tests
    └── test_governance_compliance.py
```

## Running Tests

### Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# E2E tests only
pytest -m e2e

# Governance tests only
pytest -m governance
```

### Run Tests with Coverage

```bash
pytest --cov=backend --cov-report=html --cov-report=term-missing
```

View coverage report: `open htmlcov/index.html`

### Run Tests in Parallel

```bash
pytest -n auto
```

## Test Markers

- `@pytest.mark.unit` - Unit tests for individual components
- `@pytest.mark.integration` - Integration tests for API endpoints
- `@pytest.mark.e2e` - End-to-end tests for complete workflows
- `@pytest.mark.governance` - Tests for governance framework
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.requires_db` - Tests requiring database connection
- `@pytest.mark.requires_acgs` - Tests requiring acgs-lite framework

## Coverage Requirements

- **Minimum coverage**: 80%
- **Target coverage**: 90%+
- CI pipeline will fail if coverage drops below 80%

## Writing Tests

### Test Naming Convention

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

### Example Unit Test

```python
import pytest
from backend.module import MyClass

@pytest.mark.unit
class TestMyClass:
    def test_initialization(self):
        """Test MyClass initializes correctly."""
        obj = MyClass()
        assert obj is not None
    
    def test_method_behavior(self):
        """Test method returns expected result."""
        obj = MyClass()
        result = obj.method()
        assert result == expected_value
```

### Example Integration Test

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_endpoint():
    """Test API endpoint returns correct response."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/endpoint")
        assert response.status_code == 200
```

## TDD Workflow

Follow the Red-Green-Refactor cycle:

1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to pass the test
3. **REFACTOR**: Improve code quality while keeping tests green

## CI Pipeline

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`

CI pipeline includes:
- Linting (flake8)
- Code formatting check (black)
- Type checking (mypy)
- Unit tests
- Integration tests
- Governance tests
- Coverage reporting

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

- `temp_dir` - Temporary directory for test files
- `sample_governance_rules` - Sample governance rules YAML
- `sample_context` - Sample context for governance tests
- `mock_agent_id` - Mock agent ID for testing

## Best Practices

1. **One behavior per test** - Each test should verify exactly one thing
2. **Descriptive test names** - Test names should describe expected behavior
3. **Arrange-Act-Assert** - Structure tests clearly
4. **Use fixtures** - Reuse common setup via fixtures
5. **Mock external dependencies** - Isolate units under test
6. **Test edge cases** - Include boundary conditions and error cases
7. **Keep tests fast** - Unit tests should run in milliseconds
8. **Independent tests** - Tests should not depend on each other

## Troubleshooting

### Tests fail with import errors

```bash
# Ensure backend is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Coverage not reaching 80%

```bash
# Generate detailed coverage report
pytest --cov=backend --cov-report=term-missing

# Identify uncovered lines and add tests
```

### Tests are slow

```bash
# Run tests in parallel
pytest -n auto

# Skip slow tests during development
pytest -m "not slow"
```
