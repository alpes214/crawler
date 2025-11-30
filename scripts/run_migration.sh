#!/bin/bash
# Helper script to run Alembic migrations in Docker container

set -e  # Exit on error

echo "Starting migration process..."

# Check if we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "Error: docker-compose.yml not found. Run this script from the project root."
    exit 1
fi

# Start required services
echo "Starting PostgreSQL and FastAPI containers..."
docker compose up -d postgres fastapi

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 10

# Check if PostgreSQL is healthy
if ! docker compose exec postgres pg_isready -U crawler -d crawler > /dev/null 2>&1; then
    echo "PostgreSQL is not ready. Please check logs: docker compose logs postgres"
    exit 1
fi

echo "PostgreSQL is ready"

# Check if migration message was provided
MIGRATION_MSG="${1:-Initial migration - create all tables}"

# Generate migration
echo "🔨 Generating migration: $MIGRATION_MSG"
docker compose exec fastapi alembic revision --autogenerate -m "$MIGRATION_MSG"

# Apply migration
echo "Applying migration..."
docker compose exec fastapi alembic upgrade head

# Verify tables
echo "Verifying tables..."
docker compose exec postgres psql -U crawler -d crawler -c "\dt"

echo "Migration completed successfully!"
echo ""
echo "To view migration history:"
echo "   docker compose exec fastapi alembic history"
echo ""
echo "To connect to database:"
echo "   docker compose exec postgres psql -U crawler -d crawler"
