# API Reference

## Overview

The ACGS Enterprise Manager API is a RESTful API built with FastAPI. All endpoints return JSON responses and follow standard HTTP status codes.

**Base URL**: `http://localhost:8000` (development)

**API Documentation**: 
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Authentication

Most endpoints require authentication via JWT tokens.

### Login

```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}
```

**Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Using Authentication

Include the token in the Authorization header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Core Domain APIs

### Projects API

#### List Projects

```http
GET /api/projects
Authorization: Bearer {token}
```

**Query Parameters**:
- `status` (optional): Filter by status (planning, active, on_hold, completed, cancelled)
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Enterprise Platform Upgrade",
      "description": "Modernize core infrastructure",
      "status": "active",
      "start_date": "2026-01-01",
      "end_date": "2026-12-31",
      "budget": 500000.00,
      "actual_cost": 125000.00,
      "owner_id": "user-uuid",
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-04-25T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

#### Create Project

```http
POST /api/projects
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "New Project",
  "description": "Project description",
  "status": "planning",
  "start_date": "2026-05-01",
  "end_date": "2026-12-31",
  "budget": 100000.00
}
```

#### Get Project

```http
GET /api/projects/{project_id}
Authorization: Bearer {token}
```

#### Update Project

```http
PUT /api/projects/{project_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "status": "active",
  "actual_cost": 25000.00
}
```

#### Delete Project

```http
DELETE /api/projects/{project_id}
Authorization: Bearer {token}
```

### Tasks API

#### List Tasks

```http
GET /api/tasks
Authorization: Bearer {token}
```

**Query Parameters**:
- `status`: Filter by status (todo, in_progress, blocked, review, done, cancelled)
- `priority`: Filter by priority (low, medium, high, urgent)
- `assignee_id`: Filter by assignee
- `project_id`: Filter by project
- `limit`, `offset`: Pagination

#### Create Task

```http
POST /api/tasks
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "Implement user authentication",
  "description": "Add JWT-based authentication",
  "status": "todo",
  "priority": "high",
  "project_id": "project-uuid",
  "assignee_id": "user-uuid",
  "due_date": "2026-05-15",
  "estimated_hours": 16
}
```

#### Get Task

```http
GET /api/tasks/{task_id}
Authorization: Bearer {token}
```

#### Update Task

```http
PUT /api/tasks/{task_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "status": "in_progress",
  "actual_hours": 8
}
```

### IT Assets API

#### List Assets

```http
GET /api/assets
Authorization: Bearer {token}
```

**Query Parameters**:
- `type`: Filter by type (server, workstation, laptop, network_device, storage, software_license, other)
- `status`: Filter by status (active, maintenance, retired, disposed)
- `owner_id`: Filter by owner
- `project_id`: Filter by project

#### Create Asset

```http
POST /api/assets
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Production Server 01",
  "type": "server",
  "status": "active",
  "owner_id": "user-uuid",
  "project_id": "project-uuid",
  "lifecycle_stage": "operational",
  "specifications": {
    "cpu": "Intel Xeon 16-core",
    "ram": "64GB",
    "storage": "2TB SSD"
  }
}
```

### Infrastructure API

#### List Infrastructure

```http
GET /api/infrastructure
Authorization: Bearer {token}
```

**Query Parameters**:
- `type`: Filter by type (compute, network, storage, database, security, monitoring)
- `status`: Filter by status (operational, degraded, down, maintenance)

#### Create Infrastructure

```http
POST /api/infrastructure
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Production Database Cluster",
  "type": "database",
  "status": "operational",
  "capacity": {
    "connections": 200,
    "storage_gb": 1000
  },
  "configuration": {
    "version": "PostgreSQL 14",
    "replication": "primary-replica"
  }
}
```

### Financial Records API

#### List Financial Records

```http
GET /api/financial
Authorization: Bearer {token}
```

**Query Parameters**:
- `type`: Filter by type (expense, revenue, budget_allocation, invoice, payment)
- `project_id`: Filter by project
- `approval_status`: Filter by status (pending, approved, rejected)
- `date_from`, `date_to`: Date range filter

#### Create Financial Record

```http
POST /api/financial
Authorization: Bearer {token}
Content-Type: application/json

{
  "type": "expense",
  "amount": 5000.00,
  "currency": "USD",
  "date": "2026-04-25",
  "category": "software_licenses",
  "project_id": "project-uuid",
  "approval_status": "pending",
  "description": "Annual software licenses"
}
```

### Documents API

#### List Documents

```http
GET /api/documents
Authorization: Bearer {token}
```

**Query Parameters**:
- `type`: Filter by type (specification, report, policy, procedure, contract, other)
- `owner_id`: Filter by owner
- `tags`: Filter by tags (comma-separated)

#### Create Document

```http
POST /api/documents
Authorization: Bearer {token}
Content-Type: application/json

{
  "title": "System Architecture Document",
  "content": "Document content...",
  "type": "specification",
  "tags": ["architecture", "technical", "v1.0"],
  "owner_id": "user-uuid"
}
```

#### Upload Document File

```http
POST /api/documents/{document_id}/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: <binary file data>
```

## AI Services APIs

### Recommendations API

#### Get Recommendations

```http
GET /api/ai/recommendations
Authorization: Bearer {token}
```

**Query Parameters**:
- `domain`: Filter by domain (tasks, assets, infrastructure, projects, financial, documents)
- `entity_id`: Get recommendations for specific entity
- `status`: Filter by status (pending, accepted, rejected, implemented)

**Response**:
```json
{
  "items": [
    {
      "id": "rec-uuid",
      "domain": "tasks",
      "entity_type": "task",
      "entity_id": "task-uuid",
      "suggestion": "Consider increasing priority due to approaching deadline",
      "confidence": 0.85,
      "rationale": "Task is 80% complete with 2 days remaining",
      "status": "pending",
      "created_at": "2026-04-25T10:00:00Z"
    }
  ]
}
```

#### Provide Feedback

```http
POST /api/ai/recommendations/{recommendation_id}/feedback
Authorization: Bearer {token}
Content-Type: application/json

{
  "accepted": true,
  "feedback": "Good suggestion, implemented immediately"
}
```

### Autonomous Operations API

#### List Autonomous Operations

```http
GET /api/ai/operations
Authorization: Bearer {token}
```

**Query Parameters**:
- `type`: Filter by type (recommendation, autonomous_action, learning, analysis)
- `approval_status`: Filter by status (pending, approved, rejected, auto_approved)
- `date_from`, `date_to`: Date range

#### Request Autonomous Operation

```http
POST /api/ai/operations
Authorization: Bearer {token}
Content-Type: application/json

{
  "type": "autonomous_action",
  "domain": "tasks",
  "operation": "auto_assign_tasks",
  "context": {
    "project_id": "project-uuid",
    "criteria": "workload_balance"
  }
}
```

**Response**:
```json
{
  "operation_id": "op-uuid",
  "status": "pending_approval",
  "governance_check": {
    "valid": false,
    "violations": [
      {
        "rule_id": "ai-autonomous-gate",
        "severity": "HIGH",
        "action": "REQUIRE_APPROVAL"
      }
    ]
  },
  "approval_required": true,
  "approval_timeout": 3600
}
```

## Governance APIs

### Rules API

#### List Governance Rules

```http
GET /api/governance/rules
Authorization: Bearer {token}
```

**Response**:
```json
{
  "rules": [
    {
      "id": "no-harmful-actions",
      "pattern": "harm|kill|destroy|attack",
      "severity": "CRITICAL",
      "action": "BLOCK",
      "description": "Block operations with harmful intent",
      "maci_phase": "CONTROL"
    }
  ],
  "total": 15
}
```

### Audit Trail API

#### Query Audit Trail

```http
GET /api/governance/audit
Authorization: Bearer {token}
```

**Query Parameters**:
- `agent_id`: Filter by AI agent
- `start_time`, `end_time`: Time range (ISO 8601)
- `entry_type`: Filter by type (validation, enforcement, approval_request, approval_response)
- `limit`, `offset`: Pagination

**Response**:
```json
{
  "entries": [
    {
      "id": "audit-uuid",
      "timestamp": "2026-04-25T10:00:00Z",
      "agent_id": "ai_agent_1",
      "operation": "auto_assign_task",
      "entry_type": "validation",
      "result": "blocked",
      "governance_decision": {
        "valid": false,
        "violations": ["ai-autonomous-gate"]
      },
      "previous_hash": "abc123...",
      "hash": "def456..."
    }
  ],
  "total": 100,
  "chain_valid": true
}
```

#### Verify Audit Chain Integrity

```http
GET /api/governance/audit/verify
Authorization: Bearer {token}
```

**Response**:
```json
{
  "valid": true,
  "total_entries": 1523,
  "first_entry": "2026-01-01T00:00:00Z",
  "last_entry": "2026-04-25T10:00:00Z",
  "chain_breaks": []
}
```

## Search and Reporting APIs

### Unified Search API

```http
GET /api/search
Authorization: Bearer {token}
```

**Query Parameters**:
- `q`: Search query (required)
- `domains`: Comma-separated domains to search (optional)
- `limit`, `offset`: Pagination

**Response**:
```json
{
  "results": [
    {
      "domain": "projects",
      "entity_type": "project",
      "entity_id": "project-uuid",
      "title": "Enterprise Platform Upgrade",
      "snippet": "...matching text...",
      "score": 0.95
    },
    {
      "domain": "tasks",
      "entity_type": "task",
      "entity_id": "task-uuid",
      "title": "Implement authentication",
      "snippet": "...matching text...",
      "score": 0.87
    }
  ],
  "total": 2
}
```

### Reports API

#### List Reports

```http
GET /api/reports
Authorization: Bearer {token}
```

#### Generate Report

```http
POST /api/reports/generate
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Monthly Project Status",
  "domains": ["projects", "tasks", "financial"],
  "metrics": ["completion_rate", "budget_utilization", "task_velocity"],
  "filters": {
    "date_from": "2026-04-01",
    "date_to": "2026-04-30"
  }
}
```

## Workflows API

### List Workflows

```http
GET /api/workflows
Authorization: Bearer {token}
```

### Trigger Workflow

```http
POST /api/workflows/{workflow_id}/trigger
Authorization: Bearer {token}
Content-Type: application/json

{
  "context": {
    "project_id": "project-uuid"
  }
}
```

## Health and Status

### Health Check

```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "governance": "active"
}
```

### System Status

```http
GET /api/status
Authorization: Bearer {token}
```

**Response**:
```json
{
  "uptime": 86400,
  "database": {
    "status": "connected",
    "connections": 15,
    "max_connections": 100
  },
  "governance": {
    "status": "active",
    "rules_loaded": 15,
    "audit_entries": 1523
  }
}
```

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": {
      "field": "email",
      "issue": "Invalid email format"
    }
  }
}
```

### HTTP Status Codes

- `200 OK`: Successful request
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid input data
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions or governance blocked
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

### Governance-Specific Errors

When an operation is blocked by governance:

```json
{
  "error": {
    "code": "GOVERNANCE_BLOCKED",
    "message": "Operation blocked by governance rules",
    "governance_decision": {
      "valid": false,
      "violations": [
        {
          "rule_id": "ai-confidence-threshold",
          "severity": "HIGH",
          "action": "BLOCK",
          "reason": "AI confidence below threshold (0.65 < 0.70)"
        }
      ]
    }
  }
}
```

## Rate Limiting

API requests are rate-limited:
- **Authenticated**: 1000 requests/hour
- **Unauthenticated**: 100 requests/hour

Rate limit headers:
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 995
X-RateLimit-Reset: 1714032000
```

## Pagination

List endpoints support pagination:

```http
GET /api/projects?limit=20&offset=40
```

Response includes pagination metadata:
```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "offset": 40,
  "has_more": true
}
```

## Filtering and Sorting

Most list endpoints support filtering and sorting:

```http
GET /api/tasks?status=in_progress&priority=high&sort=-created_at
```

- Prefix with `-` for descending sort
- Multiple filters are AND-ed together

## Webhooks (Future)

Webhook support is planned for:
- Project status changes
- Task completions
- Governance approvals
- AI recommendations

## SDK Support (Future)

Official SDKs planned for:
- Python
- JavaScript/TypeScript
- Go

## Interactive Documentation

For interactive API exploration, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
