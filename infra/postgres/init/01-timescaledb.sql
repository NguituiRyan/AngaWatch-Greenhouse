-- Runs once on first DB init (docker-entrypoint-initdb.d).
-- Enables TimescaleDB + helpful extensions. The `readings` hypertable itself is
-- created by the Alembic migration (so schema lives with the app), but the
-- extension must exist first.
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
