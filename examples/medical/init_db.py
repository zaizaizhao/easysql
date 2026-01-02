import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# 数据库配置
DB_HOST = "localhost"
DB_PORT = "5432"
DB_USER = "postgres"
DB_PASS = "111111"
TARGET_DB = "medical"

def get_connection(dbname=None):
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=dbname if dbname else "postgres"
    )

def init_database():
    print(f"Connecting to Postgres to create database '{TARGET_DB}'...")
    try:
        # 1. 连接到默认postgres库创建新库
        conn = get_connection()
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # 检查是否存在
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{TARGET_DB}'")
        exists = cur.fetchone()
        
        if exists:
            print(f"Database '{TARGET_DB}' already exists. Dropping...")
            cur.execute(f"DROP DATABASE {TARGET_DB}")
            
        print(f"Creating database '{TARGET_DB}'...")
        cur.execute(f"CREATE DATABASE {TARGET_DB}")
        
        cur.close()
        conn.close()
        print("Database created successfully.")
        
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

def run_sql_file(filename):
    print(f"Executing {filename}...")
    try:
        # 2. 连接到新库执行脚本
        conn = get_connection(TARGET_DB)
        cur = conn.cursor()
        
        with open(filename, 'r', encoding='utf-8') as f:
            sql = f.read()
            cur.execute(sql)
            
        conn.commit()
        cur.close()
        conn.close()
        print(f"Successfully executed {filename}")
        
    except Exception as e:
        print(f"Error executing {filename}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # 1. 创建数据库
    init_database()
    
    # 2. 创建表结构
    run_sql_file("01_schema.sql")
    
    # 3. 插入测试数据
    run_sql_file("02_test_data.sql")
    
    print("\n✅ Initialization complete!")
    print(f"   Database: {TARGET_DB}")
    print(f"   Host: {DB_HOST}:{DB_PORT}")
