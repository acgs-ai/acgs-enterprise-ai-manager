# Quick Start Guide

Get ACGS Enterprise Manager up and running in 5 minutes.

## Prerequisites

- Python 3.8+ installed
- PostgreSQL 14+ installed and running
- Git installed

## Quick Setup

### 1. Clone and Setup Environment

```bash
# Clone repository
git clone <repository-url>
cd acgs-manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt
```

### 2. Setup Database

```bash
# Create database
sudo -u postgres psql -c "CREATE DATABASE acgs_manager;"
sudo -u postgres psql -c "CREATE USER acgs_user WITH PASSWORD 'dev_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE acgs_manager TO acgs_user;"

# Initialize schema
psql -U acgs_user -d acgs_manager -f database/schema.sql
```

### 3. Configure Environment

```bash
# Create .env file
cat > .env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://acgs_user:dev_password@localhost:5432/acgs_manager
SECRET_KEY=dev-secret-key-change-in-production
GOVERNANCE_RULES_PATH=config/governance_rules.yaml
FAIL_CLOSED=true
AUDIT_ENABLED=true
HOST=0.0.0.0
PORT=8000
RELOAD=true
ENVIRONMENT=development
ENVEOF
```

### 4. Start the Server

```bash
# Start FastAPI server
python -m backend.main

# Server will start at http://localhost:8000
```

### 5. Verify Installation

Open your browser and visit:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## First Steps

### Explore the API Documentation

Visit http://localhost:8000/docs to see the interactive API documentation powered by Swagger UI.

### Test Governance Framework

```bash
# Run governance tests
PYTHONPATH=$(pwd) python backend/governance/test_governance.py

# Expected output: All 9 tests passing
```

### Check Database Schema

```bash
# Connect to database
psql -U acgs_user -d acgs_manager

# List tables
\dt

# View projects table
\d projects

# Exit
\q
```

## Common Operations

### Create a Project

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Project",
    "description": "Testing the ACGS Enterprise Manager",
    "status": "planning",
    "budget": 50000
  }'
```

### Create a Task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Setup development environment",
    "description": "Configure local dev environment",
    "status": "todo",
    "priority": "high"
  }'
```

### View Governance Audit Trail

```bash
# Check audit logs
ls -la backend/governance/audit_logs/

# View latest audit entries
tail -f backend/governance/audit_logs/audit_*.jsonl
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/unit/test_rules_engine.py

# Run with coverage
pytest --cov=backend tests/
```

### Database Migrations

```bash
# Create a new migration
alembic revision -m "Add new field to projects"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Formatting

```bash
# Format code with black
black backend/

# Check with flake8
flake8 backend/

# Type checking with mypy
mypy backend/
```

## Troubleshooting

### Port Already in Use

```bash
# Use a different port
uvicorn backend.main:app --port 8001
```

### Database Connection Failed

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U acgs_user -d acgs_manager -c "SELECT 1;"
```

### Import Errors

```bash
# Set PYTHONPATH
export PYTHONPATH=$(pwd):$PYTHONPATH

# Or run from project root
cd /path/to/acgs-manager
python -m backend.main
```

## Next Steps

- [Installation Guide](installation.md) - Detailed installation instructions
- [Architecture](architecture.md) - Understand the system design
- [API Reference](api-reference.md) - Explore all API endpoints
- [Development Guide](development.md) - Set up development environment
- [Governance Framework](governance.md) - Learn about AI governance

## Useful Commands

```bash
# Start server with auto-reload
uvicorn backend.main:app --reload

# Run tests in watch mode
pytest-watch

# View logs
tail -f /var/log/acgs-manager/error.log

# Check governance rules
cat config/governance_rules.yaml

# Backup database
pg_dump -U acgs_user acgs_manager > backup.sql

# Restore database
psql -U acgs_user acgs_manager < backup.sql
```

## Getting Help

- Check the [FAQ](faq.md)
- Review [API Documentation](api-reference.md)
- Inspect audit logs for governance issues
- Run test suite to verify setup
