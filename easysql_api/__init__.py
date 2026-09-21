"""
EasySQL API Module.

FastAPI-based REST API for Text2SQL operations.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_app() -> "FastAPI":
    """Load the HTTP application only when requested, not when importing shared storage."""
    from easysql_api.app import create_app as factory

    return factory()

__all__ = ["create_app"]
