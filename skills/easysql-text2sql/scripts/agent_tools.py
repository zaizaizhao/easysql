#!/usr/bin/env python3
"""Standard-library client for EasySQL's read-only agent tool endpoints."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


class ToolApiError(RuntimeError):
    """Normalized API or transport error suitable for an agent client."""


def _request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-selected local URL
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = {"detail": raw or exc.reason}
        raise ToolApiError(f"HTTP {exc.code}: {json.dumps(detail, ensure_ascii=False)}") from None
    except URLError as exc:
        raise ToolApiError(f"Cannot reach EasySQL API at {url}: {exc.reason}") from None
    except json.JSONDecodeError:
        raise ToolApiError(f"EasySQL API returned non-JSON content from {url}") from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EASYSQL_AGENT_TOOLS_URL", DEFAULT_BASE_URL),
        help="EasySQL API base URL including /api/v1",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("databases", help="List credential-free logical databases")

    table_search = subparsers.add_parser("search-tables", help="Milvus table search")
    _add_database(table_search)
    _add_query(table_search)
    table_search.add_argument("--top-k", type=int, default=5)
    table_search.add_argument("--table", action="append", dest="table_names")

    column_search = subparsers.add_parser("search-columns", help="Milvus column search")
    _add_database(column_search)
    _add_query(column_search)
    column_search.add_argument("--top-k", type=int, default=10)
    column_search.add_argument("--table", action="append", dest="table_names")

    describe = subparsers.add_parser("describe-tables", help="Read exact Neo4j schemas")
    _add_database(describe)
    _add_required_tables(describe)

    expand = subparsers.add_parser("expand-tables", help="Expand Neo4j FK neighbors")
    _add_database(expand)
    _add_required_tables(expand)
    expand.add_argument("--max-depth", type=int, default=1)

    paths = subparsers.add_parser("find-join-paths", help="Find Neo4j FK join edges")
    _add_database(paths)
    _add_required_tables(paths)
    paths.add_argument("--max-hops", type=int, default=5)

    check = subparsers.add_parser("check-sql", help="Classify SQL without executing it")
    _add_database(check)
    check.add_argument(
        "--database",
        action="append",
        dest="remote_databases",
        help="Additional selected logical database; may be repeated",
    )
    sql_source = check.add_mutually_exclusive_group(required=True)
    sql_source.add_argument("--sql")
    sql_source.add_argument("--sql-file", type=Path)
    return parser


def _add_database(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True, dest="db_name", help="Logical database name")


def _add_query(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--query", required=True, help="One semantic search goal")


def _add_required_tables(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--table", required=True, action="append", dest="table_names")


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    common = {
        "base_url": args.base_url,
        "timeout": args.timeout,
    }
    if args.command == "databases":
        return _request_json(method="GET", path="agent-tools/databases", payload=None, **common)

    if args.command == "search-tables":
        payload = {
            "db_name": args.db_name,
            "query": args.query,
            "top_k": args.top_k,
            "table_names": args.table_names,
        }
        return _request_json(
            method="POST",
            path="agent-tools/search-tables",
            payload=payload,
            **common,
        )

    if args.command == "search-columns":
        payload = {
            "db_name": args.db_name,
            "query": args.query,
            "top_k": args.top_k,
            "table_names": args.table_names,
        }
        return _request_json(
            method="POST",
            path="agent-tools/search-columns",
            payload=payload,
            **common,
        )

    if args.command == "describe-tables":
        return _request_json(
            method="POST",
            path="agent-tools/table-schema",
            payload={"db_name": args.db_name, "table_names": args.table_names},
            **common,
        )

    if args.command == "expand-tables":
        return _request_json(
            method="POST",
            path="agent-tools/expand-tables",
            payload={
                "db_name": args.db_name,
                "seed_tables": args.table_names,
                "max_depth": args.max_depth,
            },
            **common,
        )

    if args.command == "find-join-paths":
        return _request_json(
            method="POST",
            path="agent-tools/join-paths",
            payload={
                "db_name": args.db_name,
                "table_names": args.table_names,
                "max_hops": args.max_hops,
            },
            **common,
        )

    if args.command == "check-sql":
        sql = args.sql if args.sql is not None else args.sql_file.read_text(encoding="utf-8")
        db_names = list(dict.fromkeys([args.db_name, *(args.remote_databases or [])]))
        result = _request_json(
            method="POST",
            path="execute/check",
            payload={
                "sql": sql,
                "db_name": args.db_name,
                "db_names": db_names,
                "primary_db": args.db_name,
                "allow_mutation": False,
            },
            **common,
        )
        result["read_only"] = bool(
            result.get("safe")
            and not result.get("is_mutation")
            and result.get("statement_type") == "SELECT"
        )
        return result

    raise ToolApiError(f"Unsupported command: {args.command}")


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    try:
        result = run_command(args)
    except (OSError, ToolApiError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=errors)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
