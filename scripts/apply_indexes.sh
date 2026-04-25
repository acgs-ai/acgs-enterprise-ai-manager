#!/bin/bash
# Apply database indexes for performance optimization

set -e

echo "Applying database indexes for ACGS Enterprise Manager..."

# Database connection parameters
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-acgs_manager}"
DB_USER="${DB_USER:-postgres}"

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "Error: psql command not found. Please install PostgreSQL client."
    exit 1
fi

# Apply indexes
echo "Connecting to database: $DB_NAME on $DB_HOST:$DB_PORT"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f database/indexes.sql

if [ $? -eq 0 ]; then
    echo "✅ Database indexes applied successfully!"
    echo ""
    echo "Verifying indexes..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\di" | grep "idx_"
    echo ""
    echo "Performance optimization complete!"
else
    echo "❌ Failed to apply database indexes"
    exit 1
fi
