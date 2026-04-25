# ACGS Enterprise Manager

AI-powered enterprise management platform with constitutional governance.

## Overview

ACGS Enterprise Manager is a full-stack platform that integrates six core business domains (Tasks, IT Assets, Infrastructure, Projects, Financial Operations, Documents) with AI intelligence bounded by the ACGS-Lite governance framework. Built for medium-scale deployments (50-500 concurrent users) with integration as the core value proposition.

## Key Features

### Core Domains
- **Task Management** - Cross-domain task tracking and assignment
- **IT Assets** - Asset lifecycle management and tracking
- **Infrastructure** - Infrastructure resources and dependencies
- **Projects** - Central coordination hub for all activities
- **Financial Operations** - Budget tracking and financial transactions
- **Documents** - Document management with entity linking

### AI Capabilities
- **Recommendations** - AI-generated suggestions across all domains
- **Learning** - Continuous improvement from user feedback
- **Autonomous Operations** - Rule-bounded AI actions with governance gates

### Governance Framework
- **MACI Pattern** - Monitor → Approve → Control → Inspect
- **Fail-Closed Enforcement** - Blocks operations by default on rule violations
- **Tamper-Evident Audit** - Cryptographic chaining of all AI decisions
- **Human-in-the-Loop** - Approval workflow for sensitive operations

## Quick Start

```bash
# Clone repository
git clone <repository-url>
cd acgs-manager

# Setup environment
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Setup database
createdb acgs_manager
psql acgs_manager < database/schema.sql

# Configure
cp .env.example .env
# Edit .env with your settings

# Start server
python -m backend.main

# Visit http://localhost:8000/docs
```

See [Quick Start Guide](docs/quickstart.md) for detailed instructions.

## Documentation

### Getting Started
- [Installation Guide](docs/installation.md) - Setup and installation
- [Quick Start](docs/quickstart.md) - Get running in 5 minutes
- [Configuration](docs/configuration.md) - Environment configuration

### Architecture & Design
- [System Architecture](docs/architecture.md) - High-level design
- [Database Design](docs/database-design.md) - Schema and relationships
- [API Reference](docs/api-reference.md) - REST API documentation

### Governance & AI
- [Governance Framework](docs/governance.md) - ACGS-Lite integration
- [AI Operations](docs/ai-operations.md) - AI capabilities
- [Audit Trail](docs/audit-trail.md) - Compliance and auditing

### Deployment
- [Deployment Guide](docs/deployment.md) - Production deployment
- [Docker Setup](docs/docker.md) - Containerized deployment
- [Monitoring](docs/monitoring.md) - System monitoring

### Development
- [Development Guide](docs/development.md) - Developer setup
- [Testing Guide](docs/testing.md) - Test suite
- [Contributing](docs/contributing.md) - Contribution guidelines

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (Python 3.13) |
| Database | PostgreSQL 14+ |
| Governance | ACGS-Lite Framework |
| Frontend | Vue.js 3 (planned) |
| ORM | SQLAlchemy 2.0 |
| Testing | pytest |
| Server | Uvicorn/Gunicorn |

## Project Status

**Current Phase**: Foundation Implementation

### Completed ✅
- Database schema with cross-domain relationships
- ACGS-Lite governance framework integration
- Backend API foundation with FastAPI
- Governance rules engine and audit trail
- Comprehensive documentation

### In Progress 🔄
- Domain-specific CRUD APIs
- AI recommendation engine
- Frontend application
- Comprehensive test suite

### Planned ⏳
- AI autonomous operations with governance gates
- Cross-domain automated workflows
- Unified search and reporting
- Performance optimization for 50-500 users

## Architecture Highlights

### Integration-First Design
- Shared PostgreSQL database with foreign key relationships
- Cross-domain workflows spanning multiple domains
- Unified search and reporting across all data

### Governance-Bounded AI
- All AI operations validated against constitutional rules
- Fail-closed enforcement prevents unauthorized actions
- Tamper-evident audit trail for compliance
- Human approval workflow for sensitive operations

### Modular Monolith
- Single deployment unit for operational simplicity
- Clear domain boundaries for maintainability
- Shared infrastructure (database, auth, governance)
- Future-proof architecture (can evolve to microservices)

## Development

### Prerequisites
- Python 3.8+
- PostgreSQL 14+
- Git

### Setup Development Environment

```bash
# Install dependencies
pip install -r backend/requirements.txt
pip install -r requirements-test.txt

# Setup database
createdb acgs_manager
psql acgs_manager < database/schema.sql

# Run tests
pytest tests/

# Run governance tests
PYTHONPATH=$(pwd) python backend/governance/test_governance.py

# Start development server
uvicorn backend.main:app --reload
```

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/unit/test_rules_engine.py

# With coverage
pytest --cov=backend tests/

# Governance tests
PYTHONPATH=$(pwd) python backend/governance/test_governance.py
```

## Deployment

### Docker Deployment

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production Deployment

See [Deployment Guide](docs/deployment.md) for detailed production deployment instructions including:
- Server setup and configuration
- Database optimization
- Nginx reverse proxy
- SSL/TLS certificates
- Monitoring and logging
- Backup and recovery

## API Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

See [API Reference](docs/api-reference.md) for complete API documentation.

## Governance

The system uses ACGS-Lite for constitutional AI governance:

```python
from backend.governance import get_governance

governance = get_governance()

# Validate operation
result = governance.validate_operation(
    operation="Update user profile",
    context={"domain": "users", "action": "update"},
    agent_id="ai_agent_1"
)

if result['valid']:
    # Operation allowed
    proceed_with_operation()
else:
    # Operation blocked
    handle_governance_violation(result['violations'])
```

See [Governance Framework](docs/governance.md) for detailed documentation.

## Security

- JWT-based authentication
- Role-based access control (RBAC)
- Governance-enforced AI operations
- Tamper-evident audit trail
- SSL/TLS encryption
- Database encryption at rest

## Compliance

The governance framework supports:
- **EU AI Act** - High-risk AI system requirements
- **SOC 2** - Security and availability controls
- **ISO 27001** - Information security management

## Contributing

Contributions are welcome! Please see [Contributing Guide](docs/contributing.md) for details.

## License

[License information to be added]

## Support

- **Documentation**: [docs/](docs/)
- **API Docs**: http://localhost:8000/docs
- **Issues**: [GitHub Issues]
- **Audit Logs**: `backend/governance/audit_logs/`

## Acknowledgments

- [ACGS-Lite Framework](https://github.com/dislovelhl/acgs-lite) - Constitutional AI governance
- FastAPI - Modern Python web framework
- PostgreSQL - Reliable relational database
- Vue.js - Progressive JavaScript framework

---

**Built with ❤️ for enterprise AI governance**
