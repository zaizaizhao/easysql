from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from unittest.mock import patch

import psycopg2
import pytest
from alembic.config import Config

from alembic import command
from easysql.config import get_settings


@pytest.fixture(scope="session")
def postgres_uri(tmp_path_factory):
    """An isolated temporary PostgreSQL cluster; never uses application .env credentials."""
    if os.getenv("EASYSQL_AGENTIC_TEST_POSTGRES") != "1":
        pytest.skip(
            "Set EASYSQL_AGENTIC_TEST_POSTGRES=1 for temporary local PostgreSQL integration"
        )
    preferred = Path("/opt/homebrew/opt/postgresql@16/bin")
    initdb = (
        preferred / "initdb"
        if (preferred / "initdb").exists()
        else Path(shutil.which("initdb") or "")
    )
    if not initdb.is_file():
        pytest.fail("PostgreSQL initdb is required for the requested integration suite")
    root = tmp_path_factory.mktemp("agentic-postgres")
    data = root / "data"
    password = root / "password"
    password.write_text("agentic_test_password\n")
    password.chmod(0o600)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(
        [
            str(initdb),
            "-D",
            str(data),
            "-U",
            "agentic_test_admin",
            "--pwfile",
            str(password),
            "--auth-local=trust",
            "--auth-host=scram-sha-256",
            "--encoding=UTF8",
            "--locale=C",
        ],
        check=True,
        capture_output=True,
    )
    pg_ctl = str(initdb.parent / "pg_ctl")
    subprocess.run(
        [
            pg_ctl,
            "-D",
            str(data),
            "-l",
            str(root / "postgres.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -k /tmp",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
    )
    uri = f"postgresql://agentic_test_admin:agentic_test_password@127.0.0.1:{port}/postgres"
    try:
        with psycopg2.connect(uri) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        with patch.dict(os.environ, {"POSTGRES_URI": uri}):
            get_settings.cache_clear()
            command.upgrade(
                Config(str(Path(__file__).resolve().parents[2] / "alembic.ini")), "head"
            )
        get_settings.cache_clear()
        yield uri
    finally:
        subprocess.run(
            [pg_ctl, "-D", str(data), "-m", "immediate", "-w", "stop"],
            check=False,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def federated_settings(postgres_uri):
    from urllib.parse import urlsplit

    from easysql.config import DatabaseConfig, Settings

    parsed = urlsplit(postgres_uri)
    connection = psycopg2.connect(postgres_uri)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE ROLE agentic_reader LOGIN PASSWORD 'agentic_reader_test' NOSUPERUSER"
        )
        for name in ("emr", "pms", "rvs"):
            cursor.execute(f"CREATE DATABASE {name}")
    connection.close()
    for name in ("emr", "pms", "rvs"):
        with psycopg2.connect(postgres_uri.rsplit("/", 1)[0] + "/" + name) as db:
            with db.cursor() as cursor:
                cursor.execute("CREATE EXTENSION dblink")
                cursor.execute(
                    "CREATE TABLE patient (id bigint PRIMARY KEY, mpi_id text NOT NULL, amount integer)"
                )
                cursor.execute("INSERT INTO patient VALUES (1,'MPI-001',10),(2,'MPI-002',20)")
                cursor.execute("GRANT USAGE ON SCHEMA public TO agentic_reader")
                cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO agentic_reader")
    return Settings(
        _env_file=None,
        postgres_uri=postgres_uri,
        databases={
            name: DatabaseConfig(
                name=name,
                db_type="postgresql",
                host="127.0.0.1",
                port=parsed.port,
                user="agentic_reader",
                password="agentic_reader_test",
                database=name,
                schema="public",
            )
            for name in ("emr", "pms", "rvs")
        },
    )
