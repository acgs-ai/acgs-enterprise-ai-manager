-- ACGS Enterprise Manager - PostgreSQL Database Schema
-- Generated: 2026-04-25
-- Description: Shared database schema for 6 core domains with cross-domain relationships

-- Enable UUID extension for primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable full-text search extension
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- SUPPORTING ENTITIES
-- ============================================================================

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'manager', 'user', 'viewer')),
    permissions JSONB DEFAULT '[]'::jsonb,
    team VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- Governance Rules table (acgs-lite integration)
CREATE TABLE governance_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    condition JSONB NOT NULL,
    action VARCHAR(100) NOT NULL,
    domain VARCHAR(50) NOT NULL CHECK (domain IN ('tasks', 'assets', 'infrastructure', 'projects', 'financial', 'documents', 'global')),
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    approval_required BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI Operations table (tracks all AI actions)
CREATE TABLE ai_operations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(100) NOT NULL CHECK (type IN ('recommendation', 'autonomous_action', 'learning', 'analysis')),
    domain VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    input JSONB NOT NULL,
    output JSONB,
    rule_check_result JSONB,
    approval_status VARCHAR(20) DEFAULT 'pending' CHECK (approval_status IN ('pending', 'approved', 'rejected', 'auto_approved')),
    approved_by UUID REFERENCES users(id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INTEGER,
    confidence_score DECIMAL(3,2)
);

-- Audit Trail table (immutable log)
CREATE TABLE audit_trail (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation_id UUID REFERENCES ai_operations(id),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('user', 'ai', 'system')),
    actor_id UUID,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    result VARCHAR(20) CHECK (result IN ('success', 'failure', 'blocked')),
    governance_decision JSONB,
    metadata JSONB
);

-- ============================================================================
-- CORE DOMAIN ENTITIES
-- ============================================================================

-- Projects table (central hub for cross-domain relationships)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'planning' CHECK (status IN ('planning', 'active', 'on_hold', 'completed', 'cancelled')),
    start_date DATE,
    end_date DATE,
    budget DECIMAL(15,2),
    actual_cost DECIMAL(15,2) DEFAULT 0,
    team JSONB DEFAULT '[]'::jsonb,
    owner_id UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'blocked', 'review', 'done', 'cancelled')),
    priority VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    assignee_id UUID REFERENCES users(id),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    due_date TIMESTAMP WITH TIME ZONE,
    estimated_hours DECIMAL(5,2),
    actual_hours DECIMAL(5,2),
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- IT Assets table
CREATE TABLE it_assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('server', 'workstation', 'laptop', 'network_device', 'storage', 'software_license', 'other')),
    status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'maintenance', 'retired', 'disposed')),
    location VARCHAR(255),
    owner_id UUID REFERENCES users(id),
    project_id UUID REFERENCES projects(id),
    purchase_date DATE,
    purchase_cost DECIMAL(12,2),
    lifecycle_stage VARCHAR(50) CHECK (lifecycle_stage IN ('new', 'operational', 'aging', 'end_of_life')),
    warranty_expiry DATE,
    specifications JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Infrastructure table
CREATE TABLE infrastructure (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('compute', 'network', 'storage', 'database', 'security', 'monitoring')),
    status VARCHAR(50) NOT NULL DEFAULT 'operational' CHECK (status IN ('operational', 'degraded', 'down', 'maintenance')),
    capacity JSONB,
    location VARCHAR(255),
    dependencies JSONB DEFAULT '[]'::jsonb,
    configuration JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Financial Records table
CREATE TABLE financial_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(50) NOT NULL CHECK (type IN ('expense', 'revenue', 'budget_allocation', 'invoice', 'payment')),
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    date DATE NOT NULL,
    category VARCHAR(100) NOT NULL,
    project_id UUID REFERENCES projects(id),
    approval_status VARCHAR(20) DEFAULT 'pending' CHECK (approval_status IN ('pending', 'approved', 'rejected')),
    approved_by UUID REFERENCES users(id),
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    content TEXT,
    type VARCHAR(50) NOT NULL CHECK (type IN ('specification', 'report', 'policy', 'procedure', 'contract', 'other')),
    tags JSONB DEFAULT '[]'::jsonb,
    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    owner_id UUID REFERENCES users(id),
    version INTEGER DEFAULT 1,
    file_path VARCHAR(500),
    file_size INTEGER,
    mime_type VARCHAR(100)
);

-- ============================================================================
-- CROSS-DOMAIN RELATIONSHIP TABLES
-- ============================================================================

-- Task-Asset relationships (many-to-many)
CREATE TABLE task_assets (
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES it_assets(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) CHECK (relationship_type IN ('uses', 'requires', 'configures', 'maintains')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id, asset_id)
);

-- Task-Infrastructure relationships (many-to-many)
CREATE TABLE task_infrastructure (
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    infrastructure_id UUID REFERENCES infrastructure(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) CHECK (relationship_type IN ('deploys_to', 'monitors', 'configures', 'maintains')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (task_id, infrastructure_id)
);

-- Project-Infrastructure relationships (many-to-many)
CREATE TABLE project_infrastructure (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    infrastructure_id UUID REFERENCES infrastructure(id) ON DELETE CASCADE,
    allocation_percentage INTEGER CHECK (allocation_percentage >= 0 AND allocation_percentage <= 100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, infrastructure_id)
);

-- Document-Entity relationships (polymorphic many-to-many)
CREATE TABLE document_links (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    entity_type VARCHAR(50) NOT NULL CHECK (entity_type IN ('project', 'task', 'asset', 'infrastructure', 'financial_record')),
    entity_id UUID NOT NULL,
    link_type VARCHAR(50) CHECK (link_type IN ('attachment', 'reference', 'specification', 'report')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, entity_type, entity_id)
);

-- ============================================================================
-- AI & AUTOMATION ENTITIES
-- ============================================================================

-- Recommendations table
CREATE TABLE recommendations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    suggestion TEXT NOT NULL,
    confidence DECIMAL(3,2) CHECK (confidence >= 0 AND confidence <= 1),
    rationale TEXT,
    ai_operation_id UUID REFERENCES ai_operations(id),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'implemented')),
    feedback TEXT,
    feedback_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Workflows table (cross-domain automation)
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    trigger_domain VARCHAR(50) NOT NULL,
    trigger_event VARCHAR(100) NOT NULL,
    action_domains JSONB NOT NULL,
    steps JSONB NOT NULL,
    automation_level VARCHAR(20) DEFAULT 'manual' CHECK (automation_level IN ('manual', 'semi_automated', 'fully_automated')),
    is_active BOOLEAN DEFAULT true,
    execution_count INTEGER DEFAULT 0,
    last_executed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Workflow Executions table (tracks workflow runs)
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID REFERENCES workflows(id) ON DELETE CASCADE,
    trigger_entity_type VARCHAR(50),
    trigger_entity_id UUID,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_log JSONB,
    error_message TEXT
);

-- ============================================================================
-- SEARCH & REPORTING ENTITIES
-- ============================================================================

-- Search Index table (unified search across all domains)
CREATE TABLE search_index (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    domain VARCHAR(50) NOT NULL,
    title VARCHAR(255),
    content TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    metadata JSONB,
    search_vector tsvector,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (entity_type, entity_id)
);

-- Reports table (saved report configurations)
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    domains JSONB NOT NULL,
    metrics JSONB NOT NULL,
    filters JSONB,
    schedule VARCHAR(50) CHECK (schedule IN ('manual', 'daily', 'weekly', 'monthly')),
    created_by UUID REFERENCES users(id),
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

-- User indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_team ON users(team);

-- Governance Rules indexes
CREATE INDEX idx_governance_rules_domain ON governance_rules(domain);
CREATE INDEX idx_governance_rules_risk_level ON governance_rules(risk_level);
CREATE INDEX idx_governance_rules_active ON governance_rules(is_active);

-- AI Operations indexes
CREATE INDEX idx_ai_operations_type ON ai_operations(type);
CREATE INDEX idx_ai_operations_domain ON ai_operations(domain);
CREATE INDEX idx_ai_operations_entity ON ai_operations(entity_type, entity_id);
CREATE INDEX idx_ai_operations_timestamp ON ai_operations(timestamp DESC);
CREATE INDEX idx_ai_operations_approval_status ON ai_operations(approval_status);

-- Audit Trail indexes
CREATE INDEX idx_audit_trail_operation_id ON audit_trail(operation_id);
CREATE INDEX idx_audit_trail_timestamp ON audit_trail(timestamp DESC);
CREATE INDEX idx_audit_trail_actor ON audit_trail(actor_type, actor_id);
CREATE INDEX idx_audit_trail_entity ON audit_trail(entity_type, entity_id);

-- Projects indexes
CREATE INDEX idx_projects_status ON projects(status);
CREATE INDEX idx_projects_owner_id ON projects(owner_id);
CREATE INDEX idx_projects_dates ON projects(start_date, end_date);

-- Tasks indexes
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_assignee_id ON tasks(assignee_id);
CREATE INDEX idx_tasks_project_id ON tasks(project_id);
CREATE INDEX idx_tasks_due_date ON tasks(due_date);

-- IT Assets indexes
CREATE INDEX idx_it_assets_type ON it_assets(type);
CREATE INDEX idx_it_assets_status ON it_assets(status);
CREATE INDEX idx_it_assets_owner_id ON it_assets(owner_id);
CREATE INDEX idx_it_assets_project_id ON it_assets(project_id);
CREATE INDEX idx_it_assets_lifecycle_stage ON it_assets(lifecycle_stage);

-- Infrastructure indexes
CREATE INDEX idx_infrastructure_type ON infrastructure(type);
CREATE INDEX idx_infrastructure_status ON infrastructure(status);
CREATE INDEX idx_infrastructure_location ON infrastructure(location);

-- Financial Records indexes
CREATE INDEX idx_financial_records_type ON financial_records(type);
CREATE INDEX idx_financial_records_project_id ON financial_records(project_id);
CREATE INDEX idx_financial_records_date ON financial_records(date DESC);
CREATE INDEX idx_financial_records_approval_status ON financial_records(approval_status);
CREATE INDEX idx_financial_records_category ON financial_records(category);

-- Documents indexes
CREATE INDEX idx_documents_type ON documents(type);
CREATE INDEX idx_documents_owner_id ON documents(owner_id);
CREATE INDEX idx_documents_created_date ON documents(created_date DESC);

-- Recommendations indexes
CREATE INDEX idx_recommendations_domain ON recommendations(domain);
CREATE INDEX idx_recommendations_entity ON recommendations(entity_type, entity_id);
CREATE INDEX idx_recommendations_status ON recommendations(status);
CREATE INDEX idx_recommendations_ai_operation_id ON recommendations(ai_operation_id);

-- Workflows indexes
CREATE INDEX idx_workflows_trigger_domain ON workflows(trigger_domain);
CREATE INDEX idx_workflows_active ON workflows(is_active);
CREATE INDEX idx_workflow_executions_workflow_id ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);

-- Search Index indexes
CREATE INDEX idx_search_index_entity ON search_index(entity_type, entity_id);
CREATE INDEX idx_search_index_domain ON search_index(domain);
CREATE INDEX idx_search_index_search_vector ON search_index USING gin(search_vector);
CREATE INDEX idx_search_index_tags ON search_index USING gin(tags);

-- Reports indexes
CREATE INDEX idx_reports_created_by ON reports(created_by);
CREATE INDEX idx_reports_public ON reports(is_public);

-- ============================================================================
-- TRIGGERS FOR AUTOMATIC UPDATES
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at trigger to all relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_governance_rules_updated_at BEFORE UPDATE ON governance_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_it_assets_updated_at BEFORE UPDATE ON it_assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_infrastructure_updated_at BEFORE UPDATE ON infrastructure
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_financial_records_updated_at BEFORE UPDATE ON financial_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflows_updated_at BEFORE UPDATE ON workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_search_index_updated_at BEFORE UPDATE ON search_index
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reports_updated_at BEFORE UPDATE ON reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to update search index when entities change
CREATE OR REPLACE FUNCTION update_search_index()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO search_index (entity_type, entity_id, domain, title, content, tags, search_vector)
    VALUES (
        TG_TABLE_NAME,
        NEW.id,
        CASE TG_TABLE_NAME
            WHEN 'tasks' THEN 'tasks'
            WHEN 'it_assets' THEN 'assets'
            WHEN 'infrastructure' THEN 'infrastructure'
            WHEN 'projects' THEN 'projects'
            WHEN 'financial_records' THEN 'financial'
            WHEN 'documents' THEN 'documents'
        END,
        COALESCE(NEW.title, NEW.name, ''),
        COALESCE(NEW.description, NEW.content, ''),
        COALESCE(NEW.tags, '[]'::jsonb),
        to_tsvector('english', COALESCE(NEW.title, NEW.name, '') || ' ' || COALESCE(NEW.description, NEW.content, ''))
    )
    ON CONFLICT (entity_type, entity_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        content = EXCLUDED.content,
        tags = EXCLUDED.tags,
        search_vector = EXCLUDED.search_vector,
        updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply search index triggers to core domain tables
CREATE TRIGGER update_tasks_search_index AFTER INSERT OR UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_search_index();

CREATE TRIGGER update_projects_search_index AFTER INSERT OR UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_search_index();

CREATE TRIGGER update_it_assets_search_index AFTER INSERT OR UPDATE ON it_assets
    FOR EACH ROW EXECUTE FUNCTION update_search_index();

CREATE TRIGGER update_infrastructure_search_index AFTER INSERT OR UPDATE ON infrastructure
    FOR EACH ROW EXECUTE FUNCTION update_search_index();

CREATE TRIGGER update_documents_search_index AFTER INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_search_index();

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE users IS 'System users with roles and permissions';
COMMENT ON TABLE governance_rules IS 'acgs-lite governance rules for AI operations';
COMMENT ON TABLE ai_operations IS 'Log of all AI operations with governance checks';
COMMENT ON TABLE audit_trail IS 'Immutable audit log for compliance';
COMMENT ON TABLE projects IS 'Central hub for cross-domain project management';
COMMENT ON TABLE tasks IS 'Task management with cross-domain links';
COMMENT ON TABLE it_assets IS 'IT asset tracking and lifecycle management';
COMMENT ON TABLE infrastructure IS 'Infrastructure resources and dependencies';
COMMENT ON TABLE financial_records IS 'Financial transactions and budget tracking';
COMMENT ON TABLE documents IS 'Document management with entity linking';
COMMENT ON TABLE recommendations IS 'AI-generated recommendations with feedback';
COMMENT ON TABLE workflows IS 'Cross-domain automated workflows';
COMMENT ON TABLE search_index IS 'Unified search index across all domains';
COMMENT ON TABLE reports IS 'Saved report configurations for multi-domain analytics';
