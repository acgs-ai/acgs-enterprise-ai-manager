# Governance Framework

## Overview

The ACGS Enterprise Manager uses the ACGS-Lite constitutional governance framework to provide fail-closed enforcement with tamper-evident audit trails for all AI operations. The framework implements the MACI pattern (Monitor-Approve-Control-Inspect) to ensure AI operations are safe, compliant, and auditable.

## MACI Pattern

### Monitor Phase
**Purpose**: Detect and classify operations requiring governance oversight

```
Incoming Operation
    ↓
Pattern Matching → Rules Engine
    ↓
Severity Classification → CRITICAL | HIGH | MEDIUM | LOW
    ↓
Context Extraction → Domain, Action, Confidence, etc.
```

**Key Features**:
- Real-time pattern matching against constitutional rules
- Automatic severity classification
- Context-aware detection (confidence scores, amounts, batch sizes)

### Approve Phase
**Purpose**: Human-in-the-loop approval for sensitive operations

```
Requires Approval?
    ↓ Yes
Approval Request → Human Reviewer
    ↓
Approval Response → Approved | Rejected | Timeout
    ↓
Audit Logging
```

**Key Features**:
- Configurable approval timeout (default: 1 hour)
- Approval escalation on timeout
- Complete audit trail of approval workflow

### Control Phase
**Purpose**: Enforce governance decisions with fail-closed safety

```
Governance Decision
    ↓
ALLOW → Operation Proceeds
BLOCK → Operation Rejected
REQUIRE_APPROVAL → Approval Workflow
    ↓
Enforcement Logging
```

**Key Features**:
- Fail-closed by default (blocks on violations)
- Explicit allow required for operations to proceed
- Graceful degradation on system errors

### Inspect Phase
**Purpose**: Maintain tamper-evident audit trail for compliance

```
All Operations
    ↓
Audit Entry Creation
    ↓
Cryptographic Chaining (SHA-256)
    ↓
Immutable Storage (7-year retention)
    ↓
Integrity Verification
```

**Key Features**:
- Cryptographic hash chaining prevents tampering
- 7-year retention for compliance
- Query and inspection capabilities
- Chain integrity verification

## Governance Rules

### Rule Structure

```yaml
rules:
  - id: rule-identifier
    pattern: "regex pattern to match"
    severity: CRITICAL|HIGH|MEDIUM|LOW
    action: BLOCK|REQUIRE_APPROVAL|VALIDATE|AUDIT
    description: "Human-readable description"
    maci_phase: MONITOR|APPROVE|CONTROL|INSPECT
    context_checks:
      confidence_threshold: 0.70
      amount_limit: 10000
      batch_size_limit: 100
```

### Critical Safety Rules

#### 1. No Harmful Actions
```yaml
id: no-harmful-actions
pattern: "harm|kill|destroy|attack"
severity: CRITICAL
action: BLOCK
description: "Block operations with harmful intent"
```

**Rationale**: Prevents AI from executing operations that could cause harm to systems, data, or users.

#### 2. PII Protection
```yaml
id: pii-protection
pattern: "\\b\\d{3}-\\d{2}-\\d{4}\\b|\\b[A-Z]{2}\\d{6,9}\\b"
severity: CRITICAL
action: BLOCK
description: "Block operations exposing PII (SSN, passport numbers)"
```

**Rationale**: Prevents accidental exposure of personally identifiable information.

#### 3. Unauthorized Data Deletion
```yaml
id: unauthorized-deletion
pattern: "DELETE|DROP|TRUNCATE"
severity: HIGH
action: REQUIRE_APPROVAL
description: "Require approval for data deletion operations"
```

**Rationale**: Prevents accidental or malicious data loss.

### Financial Rules

#### 4. Financial Transaction Limits
```yaml
id: financial-transaction-limit
pattern: "transaction|payment|transfer"
severity: HIGH
action: VALIDATE
context_checks:
  amount_limit: 10000
description: "Validate financial transactions above $10,000"
```

**Rationale**: Requires approval for large financial transactions to prevent fraud.

#### 5. Budget Approval Threshold
```yaml
id: budget-approval
pattern: "budget|expense|cost"
severity: MEDIUM
action: REQUIRE_APPROVAL
context_checks:
  amount_limit: 5000
description: "Require approval for expenses above $5,000"
```

### Infrastructure Rules

#### 6. Infrastructure Changes
```yaml
id: infrastructure-changes
pattern: "infrastructure|server|database|network"
severity: HIGH
action: REQUIRE_APPROVAL
description: "Require approval for infrastructure modifications"
```

**Rationale**: Prevents unauthorized changes to critical infrastructure.

#### 7. Access Control Validation
```yaml
id: access-control
pattern: "permission|access|role|grant"
severity: HIGH
action: VALIDATE
description: "Validate access control modifications"
```

### AI-Specific Rules

#### 8. AI Confidence Threshold
```yaml
id: ai-confidence-threshold
pattern: ".*"
severity: HIGH
action: VALIDATE
context_checks:
  confidence_threshold: 0.70
description: "Block AI operations with confidence below 70%"
```

**Rationale**: Ensures AI only acts when sufficiently confident.

#### 9. Autonomous Operations Gate
```yaml
id: ai-autonomous-gate
pattern: "autonomous|auto_.*"
severity: HIGH
action: REQUIRE_APPROVAL
description: "Require approval for autonomous AI operations"
```

**Rationale**: Human oversight for AI autonomous actions.

#### 10. AI Learning Operations
```yaml
id: ai-learning-audit
pattern: "learn|train|feedback|model_update"
severity: MEDIUM
action: AUDIT
description: "Audit all AI learning operations"
```

**Rationale**: Track AI learning for compliance and debugging.

### Compliance Rules

#### 11. Data Retention Policy
```yaml
id: data-retention
pattern: "delete|purge|archive"
severity: MEDIUM
action: VALIDATE
context_checks:
  retention_days_min: 90
  retention_days_max: 2555  # 7 years
description: "Enforce data retention policy (90 days - 7 years)"
```

**Rationale**: Compliance with data retention regulations.

#### 12. Cross-Domain Data Access
```yaml
id: cross-domain-access
pattern: ".*"
severity: MEDIUM
action: AUDIT
description: "Audit cross-domain data access"
```

**Rationale**: Track data access patterns for security audits.

## Configuration

### Environment Variables

```bash
# Enable governance framework
GOVERNANCE_RULES_PATH=config/governance_rules.yaml
FAIL_CLOSED=true
AUDIT_ENABLED=true

# Audit configuration
AUDIT_LOG_DIR=backend/governance/audit_logs
AUDIT_RETENTION_DAYS=2555  # 7 years

# Approval configuration
APPROVAL_TIMEOUT_SECONDS=3600
APPROVAL_ESCALATION_ENABLED=true
```

### Governance Rules File

Edit `config/governance_rules.yaml`:

```yaml
# Enforcement configuration
enforcement:
  default_action: BLOCK
  fail_mode: CLOSED
  require_explicit_allow: true

# Audit configuration
audit:
  enabled: true
  tamper_evident: true
  retention_days: 2555
  log_all_decisions: true

# Approval configuration
approval:
  timeout_seconds: 3600
  escalation_enabled: true
  escalation_timeout_seconds: 7200

# Rules
rules:
  - id: custom-rule
    pattern: "your pattern"
    severity: HIGH
    action: REQUIRE_APPROVAL
    description: "Your rule description"
    maci_phase: CONTROL
```

## Usage Examples

### Validating an Operation

```python
from backend.governance import get_governance

governance = get_governance()

# Validate operation
result = governance.validate_operation(
    operation="Update user profile",
    context={
        "domain": "users",
        "action": "update",
        "user_id": "user-123"
    },
    agent_id="ai_agent_1"
)

if result['valid']:
    # Operation allowed
    print("Operation validated")
else:
    # Operation blocked
    print(f"Blocked: {result['violations']}")
```

### Requesting Approval

```python
# Request approval for sensitive operation
approval_request = governance.request_approval(
    operation="DELETE FROM tasks WHERE project_id = 'proj-123'",
    context={
        "domain": "tasks",
        "action": "bulk_delete",
        "project_id": "proj-123",
        "count": 50
    },
    agent_id="ai_agent_1",
    timeout_seconds=3600
)

print(f"Approval request ID: {approval_request['request_id']}")
print(f"Timeout: {approval_request['timeout_at']}")
```

### Logging Approval Response

```python
# Human approver responds
governance.audit_logger.log_approval_response(
    request_id=approval_request['request_id'],
    approved=True,
    approver="admin@example.com",
    reason="Approved after verification"
)
```

### Querying Audit Trail

```python
from datetime import datetime, timedelta

# Query last 24 hours
audit_entries = governance.inspect_audit_trail(
    agent_id="ai_agent_1",
    start_time=datetime.now() - timedelta(days=1),
    limit=100
)

for entry in audit_entries:
    print(f"{entry['timestamp']}: {entry['operation']} - {entry['result']}")
```

### Verifying Audit Chain Integrity

```python
# Verify chain integrity
integrity = governance.audit_logger.verify_chain_integrity()

print(f"Chain valid: {integrity['valid']}")
print(f"Total entries: {integrity['total_entries']}")
print(f"First entry: {integrity['first_entry']}")
print(f"Last entry: {integrity['last_entry']}")

if not integrity['valid']:
    print(f"Chain breaks detected: {integrity['chain_breaks']}")
```

## Integration with AI Services

### AI Recommendation Engine

All recommendations are validated against governance rules:

```python
# Generate recommendation
recommendation = ai_recommender.generate_recommendation(
    domain="tasks",
    entity_id="task-123",
    context={"priority": "high", "deadline": "2026-05-01"}
)

# Governance validation
result = governance.validate_operation(
    operation=f"AI recommendation: {recommendation['suggestion']}",
    context={
        "domain": "tasks",
        "action": "recommend",
        "confidence": recommendation['confidence']
    },
    agent_id="ai_recommender"
)

if result['valid']:
    # Store recommendation
    save_recommendation(recommendation)
else:
    # Log blocked recommendation
    log_blocked_recommendation(recommendation, result['violations'])
```

### AI Autonomous Operations

Autonomous operations require governance gate approval:

```python
# Request autonomous operation
operation = {
    "type": "auto_assign_tasks",
    "project_id": "proj-123",
    "criteria": "workload_balance"
}

# Governance check
result = governance.validate_operation(
    operation=f"Autonomous: {operation['type']}",
    context={
        "domain": "tasks",
        "action": "autonomous",
        "operation_type": operation['type']
    },
    agent_id="ai_autonomous"
)

if result['valid']:
    # Execute autonomous operation
    execute_autonomous_operation(operation)
elif result['requires_approval']:
    # Request human approval
    approval = governance.request_approval(
        operation=f"Autonomous: {operation['type']}",
        context=operation,
        agent_id="ai_autonomous"
    )
    # Wait for approval...
else:
    # Blocked
    log_blocked_operation(operation, result['violations'])
```

## Compliance and Auditing

### Regulatory Alignment

The governance framework supports compliance with:

#### EU AI Act
- **High-Risk AI Systems**: Human oversight for autonomous operations
- **Transparency**: Complete audit trail of AI decisions
- **Accountability**: Tamper-evident logs for regulatory review

#### SOC 2
- **Security**: Access control validation and audit
- **Availability**: Fail-closed enforcement prevents unauthorized changes
- **Confidentiality**: PII protection rules

#### ISO 27001
- **Information Security**: Comprehensive audit trail
- **Access Control**: Validation of permission changes
- **Incident Management**: Audit logs for security incidents

### Audit Reports

Generate compliance reports:

```python
# Generate monthly audit report
report = governance.generate_audit_report(
    start_date="2026-04-01",
    end_date="2026-04-30",
    include_sections=[
        "summary",
        "violations",
        "approvals",
        "ai_operations"
    ]
)

# Export to PDF
report.export_pdf("audit_report_2026_04.pdf")
```

### Audit Retention

Audit logs are retained for 7 years (2,555 days) for compliance:

```bash
# Audit log files
backend/governance/audit_logs/
├── audit_2026-04-25.jsonl
├── audit_2026-04-24.jsonl
└── ...

# Automatic cleanup after 7 years
# Configured in governance_rules.yaml:
# audit.retention_days: 2555
```

## Troubleshooting

### Operation Blocked Unexpectedly

```python
# Check which rule blocked the operation
result = governance.validate_operation(operation, context, agent_id)

for violation in result['violations']:
    print(f"Rule: {violation['rule_id']}")
    print(f"Severity: {violation['severity']}")
    print(f"Reason: {violation['reason']}")
```

### Audit Chain Integrity Failed

```python
# Verify chain and identify breaks
integrity = governance.audit_logger.verify_chain_integrity()

if not integrity['valid']:
    for break_point in integrity['chain_breaks']:
        print(f"Chain break at entry {break_point['entry_id']}")
        print(f"Expected hash: {break_point['expected_hash']}")
        print(f"Actual hash: {break_point['actual_hash']}")
```

### Approval Timeout

```python
# Check approval status
approval_status = governance.get_approval_status(request_id)

if approval_status['status'] == 'timeout':
    # Escalate or retry
    governance.escalate_approval(request_id)
```

## Best Practices

1. **Review Rules Regularly**: Update governance rules as requirements evolve
2. **Monitor Audit Logs**: Regular review of audit trail for anomalies
3. **Test Governance**: Include governance tests in CI/CD pipeline
4. **Document Approvals**: Provide clear reasons for approval decisions
5. **Verify Chain Integrity**: Regular integrity checks of audit chain
6. **Tune Thresholds**: Adjust confidence and amount thresholds based on experience
7. **Backup Audit Logs**: Include audit logs in backup strategy

## Performance Considerations

- **Rule Evaluation**: O(n) where n = number of rules (typically <100ms)
- **Audit Logging**: Async writes to avoid blocking operations
- **Chain Verification**: O(n) where n = number of entries (run periodically)
- **Approval Workflow**: Async with timeout handling

## Security

- **Audit Log Protection**: Read-only after creation, cryptographic chaining
- **Rule Configuration**: Restricted to admin users only
- **Approval Authority**: Role-based approval permissions
- **Tamper Detection**: Automatic detection of audit log tampering

## References

- [ACGS-Lite Framework](https://github.com/dislovelhl/acgs-lite)
- [Backend Governance README](../backend/governance/README.md)
- [API Reference](api-reference.md) - Governance API endpoints
- [Architecture](architecture.md) - Governance layer architecture
