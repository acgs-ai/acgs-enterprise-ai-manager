# Installation Guide

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+), macOS, or Windows with WSL2
- **Python**: 3.8 or higher (3.13 recommended)
- **PostgreSQL**: 14 or higher
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Disk**: 10GB free space

### Required Software
- Python 3.8+ with pip
- PostgreSQL 14+
- Git
- (Optional) Docker and Docker Compose

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd acgs-manager
```

### 2. Set Up Python Environment

#### Using Conda (Recommended)
```bash
# Create conda environment
conda create -n acgs-manager python=3.13
conda activate acgs-manager
```

#### Using venv
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install backend dependencies
pip install -r backend/requirements.txt

# Install test dependencies (optional)
pip install -r requirements-test.txt
```

### 4. Set Up PostgreSQL Database

#### Install PostgreSQL
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql@14
brew services start postgresql@14

# Verify installation
psql --version
```

#### Create Database
```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database and user
CREATE DATABASE acgs_manager;
CREATE USER acgs_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE acgs_manager TO acgs_user;
\q
```

#### Initialize Schema
```bash
# Run database migrations
psql -U acgs_user -d acgs_manager -f database/schema.sql

# Or use the migration script
psql -U acgs_user -d acgs_manager -f database/migrations/001_initial_schema.sql
```

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cat > .env << 'ENVEOF'
# Database Configuration
DATABASE_URL=postgresql+asyncpg://acgs_user:your_secure_password@localhost:5432/acgs_manager

# Security
SECRET_KEY=your-secret-key-change-in-production-use-openssl-rand-hex-32

# ACGS Governance
GOVERNANCE_RULES_PATH=config/governance_rules.yaml
FAIL_CLOSED=true
AUDIT_ENABLED=true

# Server Configuration
HOST=0.0.0.0
PORT=8000
RELOAD=true

# Environment
ENVIRONMENT=development
ENVEOF
```

**Important**: Replace `your_secure_password` and `your-secret-key-change-in-production-use-openssl-rand-hex-32` with secure values.

Generate a secure secret key:
```bash
openssl rand -hex 32
```

### 6. Verify Installation

#### Run Tests
```bash
# Activate environment if not already active
source ~/miniconda3/etc/profile.d/conda.sh
conda activate acgs-manager

# Run governance tests
PYTHONPATH=/home/pen/projects/acgs-manager python backend/governance/test_governance.py

# Run full test suite
pytest tests/
```

#### Start Development Server
```bash
# Start the FastAPI server
python -m backend.main

# Or use uvicorn directly
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

#### Verify Server is Running
```bash
# Check health endpoint
curl http://localhost:8000/health

# Open API documentation
# Visit: http://localhost:8000/docs
```

## Docker Installation (Alternative)

### Using Docker Compose

```bash
# Build and start services
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Manual Docker Setup

```bash
# Build backend image
docker build -t acgs-manager-backend -f docker/Dockerfile.backend .

# Run PostgreSQL container
docker run -d \
  --name acgs-postgres \
  -e POSTGRES_DB=acgs_manager \
  -e POSTGRES_USER=acgs_user \
  -e POSTGRES_PASSWORD=secure_password \
  -p 5432:5432 \
  postgres:14

# Run backend container
docker run -d \
  --name acgs-backend \
  --link acgs-postgres:postgres \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://acgs_user:secure_password@postgres:5432/acgs_manager \
  acgs-manager-backend
```

## Post-Installation

### 1. Verify Governance Framework
```bash
# Check governance rules are loaded
curl http://localhost:8000/governance/rules

# Verify audit trail is working
curl http://localhost:8000/governance/audit/status
```

### 2. Create Admin User
```bash
# Use the API to create first admin user
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "secure_password",
    "role": "admin"
  }'
```

### 3. Load Sample Data (Optional)
```bash
# Load sample data for testing
python scripts/load_sample_data.py
```

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U acgs_user -d acgs_manager -c "SELECT 1;"

# Check DATABASE_URL in .env matches your setup
```

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process or use a different port
uvicorn backend.main:app --port 8001
```

### Import Errors
```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=/path/to/acgs-manager:$PYTHONPATH

# Or install in development mode
pip install -e .
```

### Governance Tests Failing
```bash
# Check governance rules file exists
ls -la config/governance_rules.yaml

# Verify audit log directory is writable
mkdir -p backend/governance/audit_logs
chmod 755 backend/governance/audit_logs
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get started with basic operations
- [Configuration Guide](configuration.md) - Detailed configuration options
- [Development Guide](development.md) - Set up development environment
- [API Documentation](api-reference.md) - Explore the REST API

## Uninstallation

```bash
# Stop services
docker-compose down  # If using Docker

# Drop database
sudo -u postgres psql -c "DROP DATABASE acgs_manager;"

# Remove virtual environment
conda env remove -n acgs-manager  # If using conda
rm -rf venv  # If using venv

# Remove project directory
cd ..
rm -rf acgs-manager
```
