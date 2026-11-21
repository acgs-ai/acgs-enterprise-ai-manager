# System Architecture

## Overview

ACGS Enterprise Manager is a full-stack AI-powered enterprise management platform built on a modular monolith architecture with integrated governance. The system prioritizes integration across six core domains with AI intelligence bounded by constitutional governance rules.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend Layer                            │
│                     Vue.js Application                           │
│              (Unified UI across all domains)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                     API Gateway Layer                            │
│                  FastAPI Application                             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Governance Interceptor Middleware              │  │
│  │         (All AI operations pass through here)            │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
┌────────▼────────┐            ┌────────▼────────┐
│  Domain APIs    │            │  AI Services    │
│                 │            │                 │
│ • Tasks         │            │ • Recommender   │
│ • IT Assets     │            │ • Learning      │
│ • Infrastructure│            │ • Autonomous    │
│ • Projects      │            │   Operations    │
│ • Financial     │            │                 │
│ • Documents     │            └────────┬────────┘
└────────┬────────┘                     │
         │                              │
         │         ┌────────────────────┘
         │         │
┌────────▼─────────▼────────────────────────────────────────────┐
│                  Governance Framework                          │
│                    (ACGS-Lite)                                 │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Monitor  │→ │ Approve  │→ │ Control  │→ │ Inspect  │     │
│  │  Phase   │  │  Phase   │  │  Phase   │  │  Phase   │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
│                                                                 │
│  • Rules Engine    • Audit Logger    • Approval Workflow      │
└────────────────────────┬───────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                    Data Layer                                    │
│                  PostgreSQL Database                             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Shared Data Model                           │  │
│  │  (Cross-domain relationships via foreign keys)           │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Architecture Principles

### 1. Integration-First Design
- **Shared Database**: Single PostgreSQL database with normalized schema
- **Cross-Domain Relationships**: Foreign key constraints enforce referential integrity
- **Unified Search**: Single search index across all domains
- **Unified Reporting**: Multi-domain metrics and analytics

### 2. Governance-Bounded AI
- **Fail-Closed Enforcement**: AI operations blocked by default on rule violations
- **MACI Pattern**: Monitor → Approve → Control → Inspect
- **Tamper-Evident Audit**: Cryptographic chaining of all AI decisions
- **Human-in-the-Loop**: Approval workflow for sensitive operations

### 3. Modular Monolith
- **Single Deployment Unit**: Simplified operations and deployment
- **Domain Separation**: Clear boundaries between business domains
- **Shared Infrastructure**: Common database, auth, and governance
- **Future-Proof**: Can evolve to microservices if needed

## Component Architecture

### Frontend Layer (Vue.js)

```
frontend/
├── src/
│   ├── views/           # Domain-specific views
│   │   ├── tasks/
│   │   ├── assets/
│   │   ├── infrastructure/
│   │   ├── projects/
│   │   ├── financial/
│   │   └── documents/
│   ├── components/      # Reusable components
│   │   ├── common/
│   │   ├── governance/
│   │   └── ai/
│   ├── store/           # Vuex state management
│   ├── router/          # Vue Router configuration
│   └── services/        # API client services
```

**Key Features**:
- Unified navigation across all domains
- Real-time governance status indicators
- AI recommendation display and feedback
- Cross-domain search and reporting

### Backend Layer (FastAPI)

```
backend/
├── main.py              # Application entry point
├── database.py          # Database connection management
├── api/                 # REST API endpoints
│   ├── tasks.py
│   ├── assets.py
│   ├── infrastructure.py
│   ├── projects.py
│   ├── financial.py
│   └── documents.py
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic validation schemas
├── services/            # Business logic layer
│   ├── ai/
│   │   ├── recommender.py
│   │   ├── learning.py
│   │   └── autonomous.py
│   └── workflows/
├── middleware/          # Custom middleware
│   └── governance_interceptor.py
└── governance/          # ACGS-Lite integration
    ├── acgs_integration.py
    ├── rules_engine.py
    └── audit_logger.py
```

**Key Features**:
- Async/await for high concurrency
- Automatic API documentation (OpenAPI/Swagger)
- Dependency injection for testability
- Middleware-based governance enforcement

### Governance Layer (ACGS-Lite)

```
┌─────────────────────────────────────────────────────────────┐
│                    Governance Pipeline                       │
└─────────────────────────────────────────────────────────────┘

1. MONITOR Phase
   ↓
   [Incoming AI Operation]
   ↓
   [Pattern Matching] → Rules Engine
   ↓
   [Severity Classification] → CRITICAL | HIGH | MEDIUM | LOW

2. APPROVE Phase
   ↓
   [Requires Approval?] → Yes → [Human Approval Workflow]
                       → No  → Continue

3. CONTROL Phase
   ↓
   [Context Validation] → Confidence, Amounts, Batch Sizes
   ↓
   [Enforcement Decision] → ALLOW | BLOCK | REQUIRE_APPROVAL
   ↓
   [Fail-Closed Check] → Block on violations

4. INSPECT Phase
   ↓
   [Audit Logging] → Tamper-Evident Chain
   ↓
   [Compliance Recording] → 7-year retention
```

**Governance Rules Categories**:
- **Safety**: Harmful actions, PII protection, unauthorized deletions
- **Financial**: Transaction limits, approval thresholds
- **Infrastructure**: Change management, access control
- **AI-Specific**: Confidence thresholds, autonomous operation gates
- **Compliance**: Data retention, audit integrity, regulatory alignment

### Data Layer (PostgreSQL)

```
Core Domains (6):
├── projects (Central Hub)
├── tasks
├── it_assets
├── infrastructure
├── financial_records
└── documents

Supporting Entities (8):
├── users
├── governance_rules
├── ai_operations
├── audit_trail
├── recommendations
├── workflows
├── search_index
└── reports

Cross-Domain Relationships:
├── task_assets (M:N)
├── task_infrastructure (M:N)
├── project_infrastructure (M:N)
└── document_links (Polymorphic M:N)
```

**Database Features**:
- UUID primary keys for distributed ID generation
- JSONB fields for flexible metadata
- GIN indexes for full-text search
- Foreign key constraints for referential integrity
- Automatic timestamp triggers
- Search index synchronization triggers

## Data Flow Patterns

### 1. Standard CRUD Operation

```
User Request
    ↓
API Endpoint (FastAPI)
    ↓
Validation (Pydantic Schema)
    ↓
Business Logic (Service Layer)
    ↓
Database (SQLAlchemy ORM)
    ↓
Response (JSON)
```

### 2. AI-Powered Operation

```
User Request
    ↓
API Endpoint
    ↓
AI Service (Recommender/Learning/Autonomous)
    ↓
Governance Interceptor Middleware
    ↓
ACGS-Lite Validation
    ├─→ BLOCK → Error Response
    ├─→ REQUIRE_APPROVAL → Approval Workflow
    └─→ ALLOW → Continue
        ↓
    Database Operation
        ↓
    Audit Logging
        ↓
    Response
```

### 3. Cross-Domain Workflow

```
Trigger Event (e.g., Project Created)
    ↓
Workflow Engine
    ↓
Step 1: Create Tasks (Tasks Domain)
    ↓
Step 2: Allocate Assets (IT Assets Domain)
    ↓
Step 3: Reserve Infrastructure (Infrastructure Domain)
    ↓
Step 4: Create Budget (Financial Domain)
    ↓
Each Step → Governance Validation
    ↓
Audit Trail Recording
    ↓
Workflow Completion
```

## Security Architecture

### Authentication & Authorization

```
┌─────────────────────────────────────────────────────────────┐
│                    Security Layers                           │
└─────────────────────────────────────────────────────────────┘

1. Authentication
   ↓
   [JWT Token] → Verify Signature → Extract Claims

2. Authorization
   ↓
   [User Role] → Check Permissions → Allow/Deny

3. Governance
   ↓
   [AI Operation] → Validate Rules → Enforce Decision

4. Audit
   ↓
   [All Actions] → Tamper-Evident Log → Compliance
```

**Security Features**:
- JWT-based authentication
- Role-based access control (RBAC)
- Governance-enforced AI operations
- Tamper-evident audit trail
- SSL/TLS encryption in transit
- Database encryption at rest

## Performance Architecture

### Scalability Targets
- **Users**: 50-500 concurrent users
- **Throughput**: 1000+ requests/second
- **Latency**: <100ms for API calls, <500ms for AI operations
- **Database**: 10M+ records across all domains

### Performance Optimizations

1. **Database Level**
   - Strategic indexes on foreign keys and search columns
   - JSONB for flexible schema without ALTER TABLE
   - Connection pooling (asyncpg)
   - Query optimization with EXPLAIN ANALYZE

2. **Application Level**
   - Async/await for non-blocking I/O
   - Response caching for frequently accessed data
   - Batch operations for bulk updates
   - Lazy loading of relationships

3. **Infrastructure Level**
   - Horizontal scaling with multiple app instances
   - Load balancing (Nginx/HAProxy)
   - Database replication for read scaling
   - CDN for static assets

## Deployment Architecture

### Development Environment
```
Developer Machine
├── Python 3.13 (conda/venv)
├── PostgreSQL (local)
├── FastAPI (uvicorn --reload)
└── Vue.js (npm run dev)
```

### Production Environment
```
Load Balancer (Nginx)
    ↓
FastAPI Instances (Gunicorn + Uvicorn workers)
    ↓
PostgreSQL Primary
    ├─→ Replica 1 (Read)
    └─→ Replica 2 (Read)
```

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Vue.js 3 | Reactive UI framework |
| Backend | FastAPI | High-performance async API |
| Database | PostgreSQL 14+ | Relational database with JSONB |
| Governance | ACGS-Lite | Constitutional AI governance |
| ORM | SQLAlchemy 2.0 | Database abstraction |
| Validation | Pydantic 2.0 | Data validation and serialization |
| Auth | JWT (PyJWT), external IdP | Bearer-token verification |
| Server | Uvicorn/Gunicorn | ASGI server |
| Proxy | Nginx | Reverse proxy and load balancer |
| Testing | pytest | Test framework |

## Design Decisions

### Why Modular Monolith?
- **Simplicity**: Single deployment unit, easier operations
- **Integration**: Shared database enables true cross-domain relationships
- **Performance**: No network overhead between domains
- **Governance**: Centralized enforcement point
- **Future-Proof**: Can extract microservices later if needed

### Why PostgreSQL?
- **Relational Integrity**: Foreign keys enforce cross-domain relationships
- **JSONB Support**: Flexible schema for metadata
- **Full-Text Search**: Built-in search capabilities
- **Performance**: Excellent for medium-scale deployments
- **Maturity**: Battle-tested, reliable, well-documented

### Why FastAPI?
- **Performance**: Async/await for high concurrency
- **Developer Experience**: Automatic API docs, type hints
- **Modern**: Built on Python 3.8+ features
- **Ecosystem**: Compatible with SQLAlchemy, Pydantic
- **Standards**: OpenAPI, JSON Schema compliance

### Why ACGS-Lite?
- **Fail-Closed**: Safe by default
- **Tamper-Evident**: Cryptographic audit trail
- **MACI Pattern**: Comprehensive governance lifecycle
- **Flexible**: Rule-based configuration
- **Compliance**: Aligned with EU AI Act, SOC 2, ISO 27001

## Future Architecture Considerations

### Potential Enhancements
1. **Caching Layer**: Redis for session and query caching
2. **Message Queue**: RabbitMQ/Kafka for async workflows
3. **Search Engine**: Elasticsearch for advanced search
4. **Monitoring**: Prometheus + Grafana for observability
5. **Microservices**: Extract high-load domains if needed

### Migration Path to Microservices
If scaling beyond 500 users:
1. Extract AI services first (stateless, compute-heavy)
2. Extract high-traffic domains (Tasks, Projects)
3. Implement API gateway (Kong, Traefik)
4. Add service mesh (Istio) for observability
5. Migrate to event-driven architecture

## References

- [Database Design](database-design.md) - Detailed schema documentation
- [Governance Framework](governance.md) - ACGS-Lite integration
- [API Reference](api-reference.md) - REST API documentation
- [Deployment Guide](deployment.md) - Production deployment
