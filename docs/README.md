# ACGS Enterprise Manager - Documentation

## Overview

ACGS Enterprise Manager is a full-stack AI-powered enterprise management platform that integrates six core domains with AI intelligence bounded by the acgs-lite governance framework. The system targets medium-scale deployments (50-500 concurrent users) with full integration as the core value proposition.

## Core Domains

1. **Task Management** - Task tracking with cross-domain linking
2. **IT Assets** - Asset lifecycle management and tracking
3. **Infrastructure** - Infrastructure resources and dependencies
4. **Projects** - Central coordination hub for all activities
5. **Financial Operations** - Budget tracking and financial transactions
6. **Documents** - Document management with entity linking

## AI Capabilities

- **Recommendations** - AI-generated suggestions across domains
- **Learning** - Continuous improvement from user feedback
- **Autonomous Operations** - Rule-bounded AI actions with governance gates

## Technology Stack

- **Backend**: FastAPI (Python 3.13)
- **Database**: PostgreSQL with cross-domain relationships
- **Governance**: acgs-lite framework (MACI pattern)
- **Frontend**: Vue 3 + Vite (scaffold; views: Login, Dashboard, Projects, Tasks, Assets, Documents, Financial, Infrastructure)
- **Testing**: pytest with async support

## Documentation Structure

### Getting Started
- [Installation Guide](installation.md) - Setup and installation instructions
- [Quick Start](quickstart.md) - Get up and running in 5 minutes

### Architecture
- [System Architecture](architecture.md) - High-level system design
- [Database Design](database-design.md) - Schema and relationships
- [API Documentation](api-reference.md) - REST API endpoints

### Governance
- [Governance Framework](governance.md) - ACGS-Lite integration and rules

### Deployment
- [Deployment Guide](deployment.md) - Production deployment instructions
- [Docker Setup](docker.md) - Containerized deployment

### Development
- [Testing Guide](TESTING.md) - Test suite and quality assurance

## Quick Links

- [Installation Guide](installation.md) - Start here for new installations
- [Deployment Guide](deployment.md) - Production deployment
- [API Reference](api-reference.md) - REST API documentation
- [Governance Framework](governance.md) - AI governance and compliance

## Project Status

**Current Phase**: Foundation Implementation

### Completed
- ✅ Database schema design with cross-domain relationships
- ✅ ACGS-Lite governance framework integration
- ✅ Backend API foundation with FastAPI
- ✅ Governance rules engine and audit trail

### In Progress
- 🔄 Domain-specific CRUD APIs
- 🔄 AI recommendation engine
- 🔄 Frontend application
- 🔄 Comprehensive test suite

### Planned
- ⏳ AI autonomous operations with governance gates
- ⏳ Cross-domain automated workflows
- ⏳ Unified search and reporting
- ⏳ Performance optimization

## Support

For questions or issues:
1. Check the relevant documentation section
2. Check audit logs for governance-related issues
3. Review test suite for usage examples

## License

[License information to be added]
