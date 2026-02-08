"""Initialize the product demo database for EasySQL examples."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_HOST = os.getenv("PGHOST", "localhost")
DB_PORT = os.getenv("PGPORT", "5432")
DB_USER = os.getenv("PGUSER", "postgres")
DB_PASS = os.getenv("PGPASSWORD", "postgres")
TARGET_DB = os.getenv("TARGET_DB", "product")


def get_connection(dbname: str = "postgres"):
    """Create a PostgreSQL connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=dbname,
    )


def init_database() -> None:
    """Create target database, dropping existing one if needed."""
    print(f"Connecting to Postgres to create database '{TARGET_DB}'...")
    try:
        conn = get_connection("postgres")
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TARGET_DB,))
        if cur.fetchone():
            print(f"Database '{TARGET_DB}' already exists. Dropping...")
            cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(TARGET_DB)))

        print(f"Creating database '{TARGET_DB}'...")
        cur.execute(
            sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(
                sql.Identifier(TARGET_DB)
            )
        )

        cur.close()
        conn.close()
        print("Database created successfully.")
    except Exception as exc:
        print(f"Error creating database: {exc}")
        sys.exit(1)


def run_sql_file(path: Path) -> None:
    """Execute an SQL file against the target database."""
    print(f"Executing {path.name}...")
    try:
        conn = get_connection(TARGET_DB)
        cur = conn.cursor()

        sql_text = path.read_text(encoding="utf-8")
        cur.execute(sql_text)

        conn.commit()
        cur.close()
        conn.close()
        print(f"Successfully executed {path.name}")
    except Exception as exc:
        print(f"Error executing {path.name}: {exc}")
        sys.exit(1)


def main() -> None:
    """Initialize product demo schema and test data."""
    base_dir = Path(__file__).resolve().parent

    init_database()
    run_sql_file(base_dir / "01_schema.sql")
    run_sql_file(base_dir / "02_test_data.sql")

    print("\nInitialization complete")
    print(f"Database: {TARGET_DB}")
    print(f"Host: {DB_HOST}:{DB_PORT}")


if __name__ == "__main__":
    main()
