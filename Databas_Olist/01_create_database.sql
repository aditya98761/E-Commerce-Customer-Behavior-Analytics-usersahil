-- Optional: run in pgAdmin Query Tool connected to the default `postgres` database.
-- If you already created the database and login manually, skip this file.
-- Change the password here and in backend/.env if you use a different password.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_user') THEN
        EXECUTE 'CREATE ROLE olist_user LOGIN PASSWORD ''change_me''';
    ELSE
        EXECUTE 'ALTER ROLE olist_user WITH LOGIN PASSWORD ''change_me''';
    END IF;
END
$$;

-- CREATE DATABASE must run outside a transaction. If pgAdmin reports that it
-- is inside a transaction, execute this statement separately with Auto-commit on.
CREATE DATABASE olist_ecommerce OWNER olist_user;
