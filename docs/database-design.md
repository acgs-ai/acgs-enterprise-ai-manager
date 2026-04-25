# ACGS Enterprise Manager - Database Design

## Overview

This document describes the PostgreSQL database schema for the ACGS Enterprise Manager platform. The schema implements a shared data model across six core domains with comprehensive cross-domain relationships, AI operation tracking, and governance integration.

## Design Principles

1. **Shared Data Model**: All domains share a single normalized database with foreign key relationships
2. **Cross-Domain Integration**: Explicit relationship tables enable workflows spanning multiple domains
3. **Governance-First**: All AI operations are logged and checked against governance rules
4. **Audit Trail**: Immutable audit log for compliance and debugging
5. **Performance**: Strategic indexes on relationship columns and search vectors
6. **Extensibility**: JSONB fields for flexible metadata without schema changes

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUPPORTING ENTITIES                       │
├─────────────────────────────────────────────────────────────────┤
│  users                governance_rules      ai_operations        │
│  audit_trail          recommendations       workflows            │
│  search_index         reports                                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CORE DOMAINS                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────┐         ┌──────────┐         ┌──────────┐        │
│  │ projects │◄────────┤  tasks   │────────►│ it_assets│        │
│  └────┬─────┘         └────┬─────┘         └────┬─────┘        │
│       │                    │                     │               │
│       │                    ▼                     │               │
│       │            ┌───────────────┐             │               │
│       ├───────────►│infrastructure │◄────────────┘               │
│       │            └───────────────┘                             │
│       │                                                           │
│       ├───────────►┌──────────────────┐                         │
│       │            │financial_records │                         │
│       │            └──────────────────┘                         │
│       │                                                           │
│       └───────────►┌──────────┐                                 │
│                    │documents │                                 │
│                    └──────────┘                                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Domain Entities

### 1. Projects (Central Hub)
**Purpose**: Central coordination point for all cross-domain activities

**Key Fields**:
- `id`: UUID primary key
- `name`, `description`: Project identification
- `status`: planning | active | on_hold | completed | cancelled
- `start_date`, `end_date`: Timeline
- `budget`, `actual_cost`: Financial tracking
- `team`: JSONB array of team member references
- `owner_id`: Foreign key to users

**Relationships**:
- Has many tasks (1:N)
- Uses many IT assets (1:N)
- Requires infrastructure (M:N via project_infrastructure)
- Has financial records (1:N)
- Has documents (M:N via document_links)

### 2. Tasks
**Purpose**: Task management with cross-domain linking

**Key Fields**:
- `id`: UUID primary key
- `title`, `description`: Task details
- `status`: todo | in_progress | blocked | review | done | cancelled
- `priority`: low | medium | high | urgent
- `assignee_id`: Foreign key to users
- `project_id`: Foreign key to projects
- `due_date`: Deadline
- `estimated_hours`, `actual_hours`: Time tracking

**Relationships**:
- Belongs to project (N:1)
- Assigned to user (N:1)
- Linked to assets (M:N via task_assets)
- Linked to infrastructure (M:N via task_infrastructure)

### 3. IT Assets
**Purpose**: IT asset tracking and lifecycle management

**Key Fields**:
- `id`: UUID primary key
- `name`: Asset name
- `type`: server | workstation | laptop | network_device | storage | software_license | other
- `status`: active | maintenance | retired | disposed
- `owner_id`: Foreign key to users
- `project_id`: Foreign key to projects
- `lifecycle_stage`: new | operational | aging | end_of_life
- `specifications`: JSONB for flexible asset details

**Relationships**:
- Owned by user (N:1)
- Used in project (N:1)
- Linked to tasks (M:N via task_assets)

### 4. Infrastructure
**Purpose**: Infrastructure resources and dependencies

**Key Fields**:
- `id`: UUID primary key
- `name`: Infrastructure component name
- `type`: compute | network | storage | database | security | monitoring
- `status`: operational | degraded | down | maintenance
- `capacity`: JSONB for resource limits
- `dependencies`: JSONB array of dependent infrastructure IDs
- `configuration`: JSONB for infrastructure config

**Relationships**:
- Supports projects (M:N via project_infrastructure)
- Linked to tasks (M:N via task_infrastructure)
- Has dependencies (self-referential via JSONB)

### 5. Financial Records
**Purpose**: Financial transactions and budget tracking

**Key Fields**:
- `id`: UUID primary key
- `type`: expense | revenue | budget_allocation | invoice | payment
- `amount`, `currency`: Financial amount
- `date`: Transaction date
- `category`: Expense/revenue category
- `project_id`: Foreign key to projects
- `approval_status`: pending | approved | rejected
- `approved_by`: Foreign key to users

**Relationships**:
- Belongs to project (N:1)
- Approved by user (N:1)

### 6. Documents
**Purpose**: Document management with entity linking

**Key Fields**:
- `id`: UUID primary key
- `title`, `content`: Document details
- `type`: specification | report | policy | procedure | contract | other
- `tags`: JSONB array for categorization
- `owner_id`: Foreign key to users
- `version`: Document version number
- `file_path`, `file_size`, `mime_type`: File metadata

**Relationships**:
- Owned by user (N:1)
- Linked to any entity (M:N via document_links polymorphic table)

## Supporting Entities

### Users
**Purpose**: System users with roles and permissions

**Key Fields**:
- `role`: admin | manager | user | viewer
- `permissions`: JSONB array of permission strings
- `team`: Team identifier

### Governance Rules
**Purpose**: acgs-lite governance rules for AI operations

**Key Fields**:
- `condition`: JSONB rule condition
- `action`: Action to take when rule matches
- `domain`: Which domain the rule applies to
- `risk_level`: low | medium | high | critical
- `approval_required`: Boolean flag for human approval

### AI Operations
**Purpose**: Log of all AI operations with governance checks

**Key Fields**:
- `type`: recommendation | autonomous_action | learning | analysis
- `input`, `output`: JSONB operation data
- `rule_check_result`: JSONB governance check results
- `approval_status`: pending | approved | rejected | auto_approved
- `confidence_score`: AI confidence (0-1)

### Audit Trail
**Purpose**: Immutable audit log for compliance

**Key Fields**:
- `operation_id`: Foreign key to ai_operations
- `actor_type`: user | ai | system
- `action`: Action performed
- `result`: success | failure | blocked
- `governance_decision`: JSONB governance decision details

### Recommendations
**Purpose**: AI-generated recommendations with feedback loop

**Key Fields**:
- `domain`: Which domain the recommendation applies to
- `entity_type`, `entity_id`: Target entity
- `suggestion`: Recommendation text
- `confidence`: Confidence score (0-1)
- `status`: pending | accepted | rejected | implemented
- `feedback`: User feedback for learning

### Workflows
**Purpose**: Cross-domain automated workflows

**Key Fields**:
- `trigger_domain`: Domain that triggers the workflow
- `trigger_event`: Event that starts the workflow
- `action_domains`: JSONB array of domains affected
- `steps`: JSONB workflow step definitions
- `automation_level`: manual | semi_automated | fully_automated

### Search Index
**Purpose**: Unified search across all domains

**Key Fields**:
- `entity_type`, `entity_id`: Reference to indexed entity
- `domain`: Domain classification
- `search_vector`: PostgreSQL tsvector for full-text search
- `tags`: JSONB array for tag-based filtering

### Reports
**Purpose**: Saved report configurations for multi-domain analytics

**Key Fields**:
- `domains`: JSONB array of included domains
- `metrics`: JSONB metric definitions
- `filters`: JSONB filter configuration
- `schedule`: manual | daily | weekly | monthly

## Cross-Domain Relationship Tables

### task_assets
Links tasks to IT assets with relationship type (uses, requires, configures, maintains)

### task_infrastructure
Links tasks to infrastructure with relationship type (deploys_to, monitors, configures, maintains)

### project_infrastructure
Links projects to infrastructure with allocation percentage

### document_links
Polymorphic links from documents to any entity type (project, task, asset, infrastructure, financial_record)

## Indexes

Strategic indexes are created on:
- All foreign key columns for join performance
- Status and type columns for filtering
- Timestamp columns for sorting
- JSONB tags using GIN indexes
- Full-text search vectors using GIN indexes

## Triggers

### Automatic Timestamp Updates
All tables with `updated_at` columns have triggers to automatically update the timestamp on row modification.

### Search Index Synchronization
Core domain tables (tasks, projects, it_assets, infrastructure, documents) have triggers that automatically update the search_index table when entities are created or modified.

## Performance Considerations

1. **UUID Primary Keys**: Enable distributed ID generation and avoid sequence contention
2. **JSONB Fields**: Flexible schema without ALTER TABLE operations
3. **GIN Indexes**: Fast JSONB and full-text search queries
4. **Composite Indexes**: Multi-column indexes on common query patterns
5. **Cascade Deletes**: Automatic cleanup of dependent records

## Scalability

The schema is designed for medium-scale deployments (50-500 concurrent users):
- Normalized structure reduces data duplication
- Strategic denormalization in search_index for read performance
- JSONB fields avoid excessive JOIN operations
- Indexes on all relationship columns

## Security

1. **Foreign Key Constraints**: Enforce referential integrity
2. **CHECK Constraints**: Validate enum values at database level
3. **Audit Trail**: Immutable log of all AI operations
4. **Governance Integration**: All AI operations checked against rules

## Migration Strategy

The initial migration (`001_initial_schema.sql`) creates:
1. Extensions (uuid-ossp, pg_trgm)
2. All tables in dependency order
3. All indexes
4. All triggers
5. Table comments for documentation

Future migrations should:
- Use sequential numbering (002_, 003_, etc.)
- Include both UP and DOWN migrations
- Test on staging before production
- Document breaking changes

## Acceptance Criteria Verification

✅ All 14 entities from ontology implemented:
- 6 core domains: tasks, it_assets, infrastructure, projects, financial_records, documents
- 8 supporting entities: users, governance_rules, ai_operations, audit_trail, recommendations, workflows, search_index, reports

✅ Foreign key relationships enforced:
- All relationships use proper FOREIGN KEY constraints
- Cascade deletes configured where appropriate
- Referential integrity guaranteed by database

✅ Indexes on relationship columns:
- All foreign key columns indexed
- Composite indexes on common query patterns
- GIN indexes for JSONB and full-text search

✅ Cross-domain relationships:
- task_assets, task_infrastructure, project_infrastructure relationship tables
- document_links polymorphic relationship table
- Projects as central hub connecting all domains
