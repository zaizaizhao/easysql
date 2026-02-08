-- ============================================================================
-- 00_init.sql
-- Product demo database initialization (PostgreSQL)
-- ============================================================================

-- IMPORTANT:
-- If you are currently connected to database "product", DROP DATABASE will fail.
-- Connect to the default "postgres" database first.

DROP DATABASE IF EXISTS product;
CREATE DATABASE product WITH ENCODING 'UTF8';

-- Then connect to product and run:
--   1) 01_schema.sql
--   2) 02_test_data.sql
