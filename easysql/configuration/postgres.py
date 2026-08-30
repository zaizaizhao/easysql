"""PostgreSQL DSN helpers used by configuration consumers."""

from __future__ import annotations

import re

from sqlalchemy.engine import make_url

POSTGRES_SCHEME_PATTERN = re.compile(r"^postgres(?:ql)?(?:\+[^:]+)?://", re.IGNORECASE)


def is_postgres_uri(uri: str) -> bool:
    """Return whether a DSN targets PostgreSQL."""
    return bool(POSTGRES_SCHEME_PATTERN.match(uri))


def normalize_postgres_uri_for_sqlalchemy_async(uri: str) -> str:
    """Return an async SQLAlchemy PostgreSQL DSN using asyncpg."""
    return POSTGRES_SCHEME_PATTERN.sub("postgresql+asyncpg://", uri, count=1)


def normalize_postgres_uri_for_psycopg(uri: str) -> str:
    """Return a driver-neutral PostgreSQL DSN suitable for psycopg/langgraph."""
    return POSTGRES_SCHEME_PATTERN.sub("postgresql://", uri, count=1)


def postgres_database_name(uri: str) -> str:
    """Extract the database name from a PostgreSQL DSN."""
    database = make_url(uri).database
    if not database:
        raise ValueError("POSTGRES_URI must include a database name")
    return database


def postgres_uri_with_database(uri: str, database: str) -> str:
    """Return a psycopg-compatible DSN pointing at a different database."""
    normalized_uri = normalize_postgres_uri_for_psycopg(uri)
    return make_url(normalized_uri).set(database=database).render_as_string(hide_password=False)
