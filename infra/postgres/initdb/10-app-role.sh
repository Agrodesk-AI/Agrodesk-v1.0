#!/usr/bin/env bash
# Creates the least-privileged application role and grants it DML on every
# Agrodesk database.
#
# Why: the owner role (POSTGRES_USER, `agrodesk`) is a superuser, and superusers
# bypass row-level security even with FORCE ROW LEVEL SECURITY. Tenant isolation
# relies entirely on RLS, so the API, workers and tests must connect as a role
# that is NOSUPERUSER NOBYPASSRLS. The owner role is kept for alembic only.
#
# Runs automatically on first init via /docker-entrypoint-initdb.d. It is
# idempotent, so it can be re-applied to an existing volume:
#   make db-roles
set -euo pipefail

OWNER="${POSTGRES_USER:-agrodesk}"
APP_ROLE="${APP_DB_USER:-agrodesk_app}"
APP_PASSWORD="${APP_DB_PASSWORD:-agrodesk_app}"
DATABASES="${APP_DATABASES:-${POSTGRES_DB:-agrodesk} agrodesk_test}"

psql_owner() {
  psql -v ON_ERROR_STOP=1 --username "$OWNER" --no-password "$@"
}

# Cluster-level: the role itself (and the test database).
psql_owner --dbname postgres \
  -v app_role="$APP_ROLE" -v app_password="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') \gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
  :'app_role', :'app_password') \gexec
SQL

for db in $DATABASES; do
  psql_owner --dbname postgres -v db="$db" <<'SQL'
SELECT format('CREATE DATABASE %I', :'db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
SQL

  psql_owner --dbname "$db" \
    -v db="$db" -v app_role="$APP_ROLE" -v owner="$OWNER" <<'SQL'
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', :'db', :'app_role') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_role') \gexec
-- Existing objects (re-runs against a migrated database).
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO %I', :'app_role') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_role') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO %I', :'app_role') \gexec
-- Future objects created by the owner (i.e. by alembic migrations).
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO %I', :'owner', :'app_role') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'owner', :'app_role') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO %I', :'owner', :'app_role') \gexec
SQL
done

echo "app role '$APP_ROLE' ready on: $DATABASES"
