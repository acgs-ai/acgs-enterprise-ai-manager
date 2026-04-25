-- Performance Optimization Indexes
-- Generated: 2026-04-25
-- Purpose: Add indexes to improve query performance for common operations

-- ============================================================================
-- CORE ENTITY INDEXES
-- ============================================================================

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_team ON users(team);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Tasks table indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_id ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority);

-- IT Assets table indexes
CREATE INDEX IF NOT EXISTS idx_assets_type ON it_assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_status ON it_assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_owner_id ON it_assets(owner_id);
CREATE INDEX IF NOT EXISTS idx_assets_project_id ON it_assets(project_id);
CREATE INDEX IF NOT EXISTS idx_assets_lifecycle_stage ON it_assets(lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_assets_warranty_expiry ON it_assets(warranty_expiry);

-- Projects table indexes
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_start_date ON projects(start_date);
CREATE INDEX IF NOT EXISTS idx_projects_end_date ON projects(end_date);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC);

-- Infrastructure table indexes
CREATE INDEX IF NOT EXISTS idx_infrastructure_type ON infrastructure(type);
CREATE INDEX IF NOT EXISTS idx_infrastructure_status ON infrastructure(status);
CREATE INDEX IF NOT EXISTS idx_infrastructure_location ON infrastructure(location);

-- Financial Records table indexes
CREATE INDEX IF NOT EXISTS idx_financial_type ON financial_records(type);
CREATE INDEX IF NOT EXISTS idx_financial_date ON financial_records(date DESC);
CREATE INDEX IF NOT EXISTS idx_financial_project_id ON financial_records(project_id);
CREATE INDEX IF NOT EXISTS idx_financial_approval_status ON financial_records(approval_status);
CREATE INDEX IF NOT EXISTS idx_financial_category ON financial_records(category);

-- Documents table indexes
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type);
CREATE INDEX IF NOT EXISTS idx_documents_owner_id ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_created_date ON documents(created_date DESC);

-- ============================================================================
-- GOVERNANCE & AI INDEXES
-- ============================================================================

-- Governance Rules indexes
CREATE INDEX IF NOT EXISTS idx_governance_domain ON governance_rules(domain);
CREATE INDEX IF NOT EXISTS idx_governance_risk_level ON governance_rules(risk_level);
CREATE INDEX IF NOT EXISTS idx_governance_is_active ON governance_rules(is_active);

-- AI Operations indexes
CREATE INDEX IF NOT EXISTS idx_ai_ops_type ON ai_operations(type);
CREATE INDEX IF NOT EXISTS idx_ai_ops_domain ON ai_operations(domain);
CREATE INDEX IF NOT EXISTS idx_ai_ops_timestamp ON ai_operations(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ai_ops_approval_status ON ai_operations(approval_status);
CREATE INDEX IF NOT EXISTS idx_ai_ops_entity ON ai_operations(entity_type, entity_id);

-- Audit Trail indexes
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_trail(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_trail(actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_trail(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_operation_id ON audit_trail(operation_id);

-- Recommendations indexes
CREATE INDEX IF NOT EXISTS idx_recommendations_domain ON recommendations(domain);
CREATE INDEX IF NOT EXISTS idx_recommendations_status ON recommendations(status);
CREATE INDEX IF NOT EXISTS idx_recommendations_entity ON recommendations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_created_at ON recommendations(created_at DESC);

-- ============================================================================
-- RELATIONSHIP TABLE INDEXES
-- ============================================================================

-- Task-Asset relationships
CREATE INDEX IF NOT EXISTS idx_task_assets_task_id ON task_assets(task_id);
CREATE INDEX IF NOT EXISTS idx_task_assets_asset_id ON task_assets(asset_id);

-- Task-Infrastructure relationships
CREATE INDEX IF NOT EXISTS idx_task_infra_task_id ON task_infrastructure(task_id);
CREATE INDEX IF NOT EXISTS idx_task_infra_infra_id ON task_infrastructure(infrastructure_id);

-- Project-Infrastructure relationships
CREATE INDEX IF NOT EXISTS idx_project_infra_project_id ON project_infrastructure(project_id);
CREATE INDEX IF NOT EXISTS idx_project_infra_infra_id ON project_infrastructure(infrastructure_id);

-- Document Links
CREATE INDEX IF NOT EXISTS idx_doc_links_document_id ON document_links(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_links_entity ON document_links(entity_type, entity_id);

-- ============================================================================
-- FULL-TEXT SEARCH INDEXES (using pg_trgm)
-- ============================================================================

-- Tasks full-text search
CREATE INDEX IF NOT EXISTS idx_tasks_title_trgm ON tasks USING gin(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tasks_description_trgm ON tasks USING gin(description gin_trgm_ops);

-- Projects full-text search
CREATE INDEX IF NOT EXISTS idx_projects_name_trgm ON projects USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_projects_description_trgm ON projects USING gin(description gin_trgm_ops);

-- Documents full-text search
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm ON documents USING gin(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_documents_content_trgm ON documents USING gin(content gin_trgm_ops);

-- IT Assets full-text search
CREATE INDEX IF NOT EXISTS idx_assets_name_trgm ON it_assets USING gin(name gin_trgm_ops);

-- ============================================================================
-- JSONB INDEXES (for efficient JSONB queries)
-- ============================================================================

-- JSONB GIN indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_tasks_tags_gin ON tasks USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_projects_team_gin ON projects USING gin(team);
CREATE INDEX IF NOT EXISTS idx_users_permissions_gin ON users USING gin(permissions);
CREATE INDEX IF NOT EXISTS idx_documents_tags_gin ON documents USING gin(tags);

-- ============================================================================
-- COMPOSITE INDEXES (for common query patterns)
-- ============================================================================

-- Common task queries
CREATE INDEX IF NOT EXISTS idx_tasks_assignee_status ON tasks(assignee_id, status) WHERE status != 'done';
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);

-- Common financial queries
CREATE INDEX IF NOT EXISTS idx_financial_project_date ON financial_records(project_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_financial_type_date ON financial_records(type, date DESC);

-- Common AI operation queries
CREATE INDEX IF NOT EXISTS idx_ai_ops_domain_timestamp ON ai_operations(domain, timestamp DESC);

-- ============================================================================
-- PARTIAL INDEXES (for specific conditions)
-- ============================================================================

-- Active entities only
CREATE INDEX IF NOT EXISTS idx_users_active ON users(id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_governance_active ON governance_rules(id) WHERE is_active = true;

-- Pending approvals
CREATE INDEX IF NOT EXISTS idx_ai_ops_pending ON ai_operations(id, timestamp DESC) WHERE approval_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_financial_pending ON financial_records(id, date DESC) WHERE approval_status = 'pending';

-- Active tasks
CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(id, due_date) WHERE status IN ('todo', 'in_progress', 'blocked');
