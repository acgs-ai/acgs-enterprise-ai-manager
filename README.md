# ACGS Enterprise AI Manager

Enterprise-grade AI Agent Management Platform with Constitutional Governance Framework

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)

## Overview

ACGS Enterprise Manager is a comprehensive platform for managing AI agents with built-in constitutional governance, multi-domain data management, and enterprise-grade security features.

### Key Features

- **Constitutional AI Governance** - ACGS-Lite framework with MACI pattern (Monitor-Approve-Control-Inspect)
- **Multi-Domain Management** - Tasks, Projects, IT Assets, Infrastructure, Documents, Financial Records
- **Full-Text Search** - PostgreSQL-powered search with relevance ranking across all domains
- **Audit Trail** - Tamper-evident logging of all AI operations and governance decisions
- **RESTful API** - FastAPI-based async API with OpenAPI/Swagger documentation
- **Enterprise Security** - Fail-closed enforcement, approval workflows, and compliance tracking

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI REST API                          │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │  Tasks   │ Projects │  Assets  │  Infra   │Documents │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              ACGS Governance Framework                       │
│  ┌──────────┬──────────┬──────────┬──────────────────────┐ │
│  │ Monitor  │ Approve  │ Control  │      Inspect         │ │
│  └──────────┴──────────┴──────────┴──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   Data Layer                                 │
│  ┌──────────────────┬──────────────────┬─────────────────┐ │
│  │   PostgreSQL     │  Search Index    │  Audit Logs     │ │
│  │   (AsyncPG)      │  (Full-Text)     │  (JSONL)        │ │
│  └──────────────────┴──────────────────┴─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 6+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/eliptic/acgs-manager.git
cd acgs-manager
```

2. Install dependencies:
```bash
pip install -r backend/requirements.txt
```

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your database credentials and the AUTH_* settings
# (AUTH_JWT_ISSUER, AUTH_JWT_AUDIENCE, and AUTH_JWKS_URL or AUTH_JWT_KEY)
```
All `/api/v1/*` routes require `Authorization: Bearer <token>`, where the
token is issued by your external identity provider. This API only verifies
tokens and has no login endpoint. Without the `AUTH_*` settings, protected
routes return 503. Only `/health`, `/`, `/docs` and `/redoc` are public.

4. Initialize database:
```bash
psql -U postgres -c "CREATE DATABASE acgs_enterprise_manager;"
psql -U postgres -d acgs_enterprise_manager -f database/schema.sql
psql -U postgres -d acgs_enterprise_manager -f database/indexes.sql
```

5. Start the server:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8001
```

6. Access the API documentation:
```
http://localhost:8001/docs
```

## Testing

Run the core functionality test suite:

```bash
./test_core_functionality.sh
```

Expected output:
```
Total Tests: 10
Passed: 10
Failed: 0

All core functionality tests passed! ✓
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Tasks
- `POST /api/v1/tasks/` - Create task
- `GET /api/v1/tasks/{id}` - Get task
- `PUT /api/v1/tasks/{id}` - Update task
- `DELETE /api/v1/tasks/{id}` - Delete task
- `GET /api/v1/tasks/` - List tasks (with filters)

### Projects
- `POST /api/v1/projects/` - Create project
- `GET /api/v1/projects/{id}` - Get project
- `PUT /api/v1/projects/{id}` - Update project
- `DELETE /api/v1/projects/{id}` - Delete project

### IT Assets
- `POST /api/v1/assets/` - Create asset
- `GET /api/v1/assets/{id}` - Get asset
- `PUT /api/v1/assets/{id}` - Update asset
- `DELETE /api/v1/assets/{id}` - Delete asset

### Infrastructure
- `POST /api/v1/infrastructure/` - Create infrastructure
- `GET /api/v1/infrastructure/{id}` - Get infrastructure
- `PUT /api/v1/infrastructure/{id}` - Update infrastructure
- `DELETE /api/v1/infrastructure/{id}` - Delete infrastructure

### Documents
- `POST /api/v1/documents/` - Create document
- `GET /api/v1/documents/{id}` - Get document
- `PUT /api/v1/documents/{id}` - Update document
- `DELETE /api/v1/documents/{id}` - Delete document

### Financial Records
- `POST /api/v1/financial/` - Create financial record
- `GET /api/v1/financial/{id}` - Get financial record
- `PUT /api/v1/financial/{id}` - Update financial record
- `DELETE /api/v1/financial/{id}` - Delete financial record

### Search
- `GET /api/v1/search/?q={query}` - Full-text search across all domains
- `GET /api/v1/search/suggest?q={query}` - Search suggestions
- `GET /api/v1/search/tags` - Popular tags

### AI Recommendations
- `GET /api/v1/recommendations/tasks/{id}` - Get AI recommendations (governed by ACGS)

## ACGS Governance

The ACGS (AI Constitutional Governance System) framework enforces rules on all AI operations:

### MACI Pattern

1. **Monitor** - Validate operations against constitutional rules
2. **Approve** - Request human approval for high-risk operations
3. **Control** - Enforce decisions (allow/block/require-approval)
4. **Inspect** - Audit trail of all governance decisions

### Configuration

Edit `config/governance_rules.yaml` to customize governance rules:

```yaml
rules:
  - id: low-confidence-block
    description: Block AI recommendations with confidence < 0.7
    severity: HIGH
    conditions:
      - field: confidence
        operator: lt
        value: 0.7
    action: BLOCK
```

## Database Schema

### Core Tables
- `tasks` - Task management with priorities and tags
- `projects` - Project tracking with budgets and timelines
- `it_assets` - IT asset inventory with lifecycle tracking
- `infrastructure` - Infrastructure monitoring and management
- `documents` - Document management with versioning
- `financial_records` - Financial transaction tracking

### System Tables
- `search_index` - Full-text search index (auto-updated via triggers)
- `users` - User management and authentication
- `audit_logs` - Governance decision audit trail

## Development

### Project Structure

```
acgs-manager/
├── backend/
│   ├── api/              # FastAPI route handlers
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic layer
│   ├── governance/       # ACGS governance framework
│   ├── search/           # Search engine
│   └── main.py          # Application entry point
├── config/
│   └── governance_rules.yaml  # ACGS rules configuration
├── database/
│   ├── schema.sql       # Database schema
│   └── indexes.sql      # Database indexes
└── tests/
    └── test_core_functionality.sh
```

### Running Tests

```bash
# Core functionality tests
./test_core_functionality.sh

# Comprehensive tests
./test_comprehensive.sh
```

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

See [LICENSE](LICENSE) for details.

### Why AGPL-3.0?

The AGPL-3.0 license ensures that:
- Any modifications to this software must be made available under the same license
- Network use (SaaS) counts as distribution - users accessing the software over a network have the right to receive the source code
- The software remains free and open for the community

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## Support

- **Issues**: https://github.com/eliptic/acgs-manager/issues
- **Documentation**: See `/docs` directory
- **ACGS Framework**: https://github.com/eliptic/acgs-lite

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com)
- Powered by [ACGS-Lite](https://github.com/eliptic/acgs-lite) governance framework
- Database: [PostgreSQL](https://www.postgresql.org)
- ORM: [SQLAlchemy](https://www.sqlalchemy.org)

---

**Status**: Production Ready ✓

All core functionality tests passing (10/10)
