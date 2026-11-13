-- Operon AI database roles (local development / CI).
-- Production roles are provisioned by infrastructure-as-code with secrets from the secret manager.
--   operon_owner : owns the schema, runs Alembic migrations
--   operon_app   : runtime role for API and workers; DML only, no BYPASSRLS
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'operon_owner') THEN
    CREATE ROLE operon_owner LOGIN PASSWORD 'operon_owner_dev' NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'operon_app') THEN
    CREATE ROLE operon_app LOGIN PASSWORD 'operon_app_dev' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

SELECT 'CREATE DATABASE operon OWNER operon_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'operon')\gexec
SELECT 'CREATE DATABASE operon_test OWNER operon_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'operon_test')\gexec

\connect operon
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
GRANT CONNECT ON DATABASE operon TO operon_app;
GRANT USAGE ON SCHEMA public TO operon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE operon_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO operon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE operon_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO operon_app;

\connect operon_test
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
GRANT CONNECT ON DATABASE operon_test TO operon_app;
GRANT USAGE ON SCHEMA public TO operon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE operon_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO operon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE operon_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO operon_app;
