-- ============================================================================
-- 医疗信息系统 - 数据库初始化
-- Database Initialization: medical
-- ============================================================================

-- 1. 创建数据库
-- 注意: 如果正在连接 medical 数据库，此命令会失败。需要先连接 postgres 数据库执行。
DROP DATABASE IF EXISTS medical;
CREATE DATABASE medical WITH ENCODING 'UTF8';

-- 2. 连接到新数据库 (在 psql 中执行)
-- \c medical

-- 3. 创建 Schema
-- DROP SCHEMA IF EXISTS medical CASCADE; -- 如果有名字冲突
-- CREATE SCHEMA medical;

-- 4. 设置搜索路径 (默认使用 public 即可，或者自定义 schema)
-- ALTER DATABASE medical SET search_path TO public;

-- 5. 提示
-- 数据库 'medical' 创建完成。接下来请执行 01_schema.sql 和 02_test_data.sql
