#!/bin/bash
echo "=== ACGS Enterprise Manager API Test ==="
BASE_URL="http://localhost:8001"

echo -e "\n1. Health Check"
curl -s $BASE_URL/health | jq .

echo -e "\n2. Create a Task"
TASK_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Task",
    "description": "Testing the API",
    "status": "todo",
    "priority": "high"
  }')
echo "$TASK_RESPONSE" | jq .
TASK_ID=$(echo "$TASK_RESPONSE" | jq -r '.id')
echo "Created task ID: $TASK_ID"

echo -e "\n3. Get All Tasks"
curl -s "$BASE_URL/api/v1/tasks/?limit=10" | jq '{total: .total, count: (.items | length)}'

echo -e "\n4. Get Task by ID"
if [ "$TASK_ID" != "null" ] && [ -n "$TASK_ID" ]; then
  curl -s "$BASE_URL/api/v1/tasks/$TASK_ID/" | jq '{id: .id, title: .title, status: .status}'
fi

echo -e "\n5. Update Task Status"
if [ "$TASK_ID" != "null" ] && [ -n "$TASK_ID" ]; then
  curl -s -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/" \
    -H "Content-Type: application/json" \
    -d '{
      "title": "Updated Test Task",
      "status": "in_progress"
    }' | jq '{title: .title, status: .status}'
fi

echo -e "\n6. Get Recommendations"
curl -s "$BASE_URL/api/v1/recommendations/?domain=tasks&limit=5" | jq '{total: .total}'

echo -e "\n7. Search"
curl -s "$BASE_URL/api/v1/search/?q=test&limit=5" | jq '{total: .total, results: (.results | length)}'

echo -e "\n=== Tests completed ==="
