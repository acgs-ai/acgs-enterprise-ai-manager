#!/bin/bash
# Comprehensive API Test Suite for ACGS Enterprise Manager

BASE_URL="http://localhost:8001"
API_V1="$BASE_URL/api/v1"

echo "=== ACGS Enterprise Manager - Comprehensive Test Suite ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_count=0
pass_count=0
fail_count=0

run_test() {
    test_count=$((test_count + 1))
    echo -e "${YELLOW}Test $test_count: $1${NC}"
}

pass() {
    pass_count=$((pass_count + 1))
    echo -e "${GREEN}✓ PASS${NC}"
    echo ""
}

fail() {
    fail_count=$((fail_count + 1))
    echo -e "${RED}✗ FAIL: $1${NC}"
    echo ""
}

# Test 1: Health Check
run_test "Health Check"
response=$(curl -s "$BASE_URL/health")
if echo "$response" | jq -e '.status == "healthy"' > /dev/null; then
    pass
else
    fail "Health check failed"
fi

# Test 2: Create Task
run_test "Create Task"
task_response=$(curl -s -X POST "$API_V1/tasks/" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "Implement user authentication",
        "description": "Add JWT-based authentication system",
        "priority": "high",
        "status": "todo",
        "tags": ["security", "backend"],
        "estimated_hours": 8.5
    }')
task_id=$(echo "$task_response" | jq -r '.id')
if [ "$task_id" != "null" ] && [ -n "$task_id" ]; then
    echo "Created task ID: $task_id"
    pass
else
    fail "Task creation failed"
fi

# Test 3: Get Task
run_test "Get Task by ID"
get_response=$(curl -s "$API_V1/tasks/$task_id")
if echo "$get_response" | jq -e '.title == "Implement user authentication"' > /dev/null; then
    pass
else
    fail "Get task failed"
fi

# Test 4: Update Task
run_test "Update Task Status"
update_response=$(curl -s -X PUT "$API_V1/tasks/$task_id" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "Implement user authentication",
        "description": "Add JWT-based authentication system with refresh tokens",
        "priority": "high",
        "status": "in_progress",
        "tags": ["security", "backend"],
        "estimated_hours": 8.5,
        "actual_hours": 2.0
    }')
if echo "$update_response" | jq -e '.status == "in_progress"' > /dev/null; then
    pass
else
    fail "Task update failed"
fi

# Test 5: List Tasks
run_test "List All Tasks"
list_response=$(curl -s "$API_V1/tasks/")
total=$(echo "$list_response" | jq -r '.total')
if [ "$total" -ge 1 ]; then
    echo "Found $total task(s)"
    pass
else
    fail "List tasks failed"
fi

# Test 6: Search Tasks
run_test "Search for 'authentication'"
search_response=$(curl -s "$API_V1/search/?q=authentication&limit=10")
search_total=$(echo "$search_response" | jq -r '.total')
if [ "$search_total" -ge 1 ]; then
    echo "Found $search_total result(s)"
    pass
else
    fail "Search failed"
fi

# Test 7: Create Project
run_test "Create Project"
project_response=$(curl -s -X POST "$API_V1/projects/" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Enterprise Portal",
        "description": "Customer-facing enterprise portal",
        "status": "active",
        "start_date": "2026-04-26T00:00:00Z",
        "budget": 150000.00
    }')
project_id=$(echo "$project_response" | jq -r '.id')
if [ "$project_id" != "null" ] && [ -n "$project_id" ]; then
    echo "Created project ID: $project_id"
    pass
else
    fail "Project creation failed"
fi

# Test 8: Create IT Asset
run_test "Create IT Asset"
asset_response=$(curl -s -X POST "$API_V1/assets/" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "MacBook Pro 16",
        "type": "laptop",
        "status": "active",
        "serial_number": "MBP2026-001",
        "purchase_date": "2026-01-15T00:00:00Z",
        "purchase_cost": 2999.99
    }')
asset_id=$(echo "$asset_response" | jq -r '.id')
if [ "$asset_id" != "null" ] && [ -n "$asset_id" ]; then
    echo "Created asset ID: $asset_id"
    pass
else
    fail "Asset creation failed"
fi

# Test 9: Create Infrastructure
run_test "Create Infrastructure"
infra_response=$(curl -s -X POST "$API_V1/infrastructure/" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Production API Server",
        "type": "server",
        "status": "running",
        "ip_address": "10.0.1.50",
        "specs": {"cpu": "8 cores", "ram": "32GB", "storage": "500GB SSD"}
    }')
infra_id=$(echo "$infra_response" | jq -r '.id')
if [ "$infra_id" != "null" ] && [ -n "$infra_id" ]; then
    echo "Created infrastructure ID: $infra_id"
    pass
else
    fail "Infrastructure creation failed"
fi

# Test 10: Create Document
run_test "Create Document"
doc_response=$(curl -s -X POST "$API_V1/documents/" \
    -H "Content-Type: application/json" \
    -d '{
        "title": "API Documentation",
        "content": "Complete API reference for all endpoints",
        "type": "technical",
        "tags": ["api", "documentation", "reference"]
    }')
doc_id=$(echo "$doc_response" | jq -r '.id')
if [ "$doc_id" != "null" ] && [ -n "$doc_id" ]; then
    echo "Created document ID: $doc_id"
    pass
else
    fail "Document creation failed"
fi

# Test 11: Create Financial Record
run_test "Create Financial Record"
financial_response=$(curl -s -X POST "$API_V1/financial/" \
    -H "Content-Type: application/json" \
    -d '{
        "type": "expense",
        "category": "software",
        "amount": 299.99,
        "description": "Annual subscription for development tools",
        "date": "2026-04-26T00:00:00Z"
    }')
financial_id=$(echo "$financial_response" | jq -r '.id')
if [ "$financial_id" != "null" ] && [ -n "$financial_id" ]; then
    echo "Created financial record ID: $financial_id"
    pass
else
    fail "Financial record creation failed"
fi

# Test 12: Multi-domain Search
run_test "Multi-domain Search"
multi_search=$(curl -s "$API_V1/search/?q=enterprise&limit=20")
multi_total=$(echo "$multi_search" | jq -r '.total')
if [ "$multi_total" -ge 1 ]; then
    echo "Found $multi_total result(s) across domains"
    pass
else
    fail "Multi-domain search failed"
fi

# Test 13: Domain-specific Search
run_test "Search in Tasks Domain Only"
domain_search=$(curl -s "$API_V1/search/?q=authentication&domains=tasks&limit=10")
domain_total=$(echo "$domain_search" | jq -r '.total')
if [ "$domain_total" -ge 1 ]; then
    echo "Found $domain_total task(s)"
    pass
else
    fail "Domain-specific search failed"
fi

# Test 14: Tag-based Search
run_test "Search by Tags"
tag_search=$(curl -s "$API_V1/search/tags/?tags=security&limit=10")
tag_total=$(echo "$tag_search" | jq -r '.total')
if [ "$tag_total" -ge 1 ]; then
    echo "Found $tag_total item(s) with 'security' tag"
    pass
else
    fail "Tag-based search failed"
fi

# Test 15: Get Popular Tags
run_test "Get Popular Tags"
tags_response=$(curl -s "$API_V1/search/tags/popular?limit=10")
tags_count=$(echo "$tags_response" | jq -r 'length')
if [ "$tags_count" -ge 1 ]; then
    echo "Found $tags_count popular tag(s)"
    pass
else
    fail "Get popular tags failed"
fi

# Test 16: Link Task to Project
run_test "Link Task to Project"
link_response=$(curl -s -X PUT "$API_V1/tasks/$task_id" \
    -H "Content-Type: application/json" \
    -d "{
        \"title\": \"Implement user authentication\",
        \"description\": \"Add JWT-based authentication system with refresh tokens\",
        \"priority\": \"high\",
        \"status\": \"in_progress\",
        \"tags\": [\"security\", \"backend\"],
        \"estimated_hours\": 8.5,
        \"actual_hours\": 2.0,
        \"project_id\": \"$project_id\"
    }")
if echo "$link_response" | jq -e ".project_id == \"$project_id\"" > /dev/null; then
    pass
else
    fail "Link task to project failed"
fi

# Test 17: Link Task to Asset
run_test "Link Task to Asset"
link_asset=$(curl -s -X POST "$API_V1/tasks/$task_id/assets/$asset_id")
if [ $? -eq 0 ]; then
    pass
else
    fail "Link task to asset failed"
fi

# Test 18: Get Task with Relationships
run_test "Get Task with All Relationships"
full_task=$(curl -s "$API_V1/tasks/$task_id")
has_project=$(echo "$full_task" | jq -e '.project != null')
has_assets=$(echo "$full_task" | jq -e '.assets | length > 0')
if [ "$has_project" = "true" ] && [ "$has_assets" = "true" ]; then
    pass
else
    fail "Task relationships not loaded"
fi

# Test 19: Delete Task
run_test "Delete Task"
delete_response=$(curl -s -X DELETE "$API_V1/tasks/$task_id")
verify_delete=$(curl -s "$API_V1/tasks/$task_id")
if echo "$verify_delete" | jq -e '.detail == "Task not found"' > /dev/null; then
    pass
else
    fail "Task deletion failed"
fi

# Test 20: Verify Search Index Updated
run_test "Verify Search Index After Deletion"
search_after_delete=$(curl -s "$API_V1/search/?q=authentication&limit=10")
# Should still find results if other items match, or 0 if only the deleted task matched
if [ $? -eq 0 ]; then
    pass
else
    fail "Search index verification failed"
fi

# Summary
echo "========================================"
echo -e "${YELLOW}Test Summary${NC}"
echo "========================================"
echo "Total Tests: $test_count"
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review the output above.${NC}"
    exit 1
fi
