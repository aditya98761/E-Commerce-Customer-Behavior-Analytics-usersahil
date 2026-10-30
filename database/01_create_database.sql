-- Run this in pgAdmin's Query Tool while connected to the default `postgres` database.
-- Change the password here and in backend/.env if you do not want the default.
-- CREATE DATABASE must run as a top-level statement (not inside a transaction/DO block).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bda_user') THEN
        EXECUTE 'CREATE ROLE bda_user LOGIN PASSWORD ''change_me''';
    ELSE
        EXECUTE 'ALTER ROLE bda_user WITH LOGIN PASSWORD ''change_me''';
    END IF;
END
$$;

CREATE DATABASE ecommerce-cba OWNER bda_user;
