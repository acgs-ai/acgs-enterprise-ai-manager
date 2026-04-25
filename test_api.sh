#!/bin/bash
echo "=== ACGS Enterprise Manager API Test ==="
echo ""

BASE_URL="http://localhost:8001"

echo "1. Health Check"
curl -s $BASE_URL/health | jq .
echo ""

echo "2. Create a Task"
TASK_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Task",
    "description": "Testing the API",
    "status": "pending",
    "priority": "high"
  }')
echo "$TASK_RESPONSE" | jq .
TASK_ID=$(echo "$TASK_RESPONSE" | jq -r '.id')
echo "Created task ID: $TASK_ID"
echo ""

echo "3. Get All Tasks"
curl -s "$BASE_URL/api/v1/tasks/?limit=10" | jq '.items | length'
echo ""

echo "4. Get Task by ID"
if [ "$TASK_ID" != "null" ] && [ -n "$TASK_ID" ]; then
  curl -s "$BASE_URL/api/v1/tasks/$TASK_ID/" | jq '.title'
else
  echo "No task ID to fetch"
fi
echo ""

echo "5. Create an Asset"
ASSET_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/assets/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Laptop",
    "type": "hardware",
    "status": "active",
    "location": "Office A"
  }')
echo "$ASSET_RESPONSE" | jq .
echo ""

echo "6. Get All Assets"
curl -s "$BASE_URL/api/v1/assets/?limit=10" | jq '.items | length'
echo ""

echo "7. Search"
curl -s "$BASE_URL/api/v1/search/?q=test&limit=5" | jq '.total'
echo ""

echo "=== All tests completed ==="
