-- Database initialization script
-- This script runs automatically when PostgreSQL container starts for the first time

-- The database 'crawler' is created automatically by the POSTGRES_DB environment variable
-- This script just ensures it exists and adds any additional setup

-- Ensure database exists (redundant but safe)
SELECT 'CREATE DATABASE crawler'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crawler')\gexec

-- Connect to crawler database
\c crawler

-- Enable extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For faster text search

-- Note: Actual table creation happens via Alembic migrations
-- This script only handles database-level setup
