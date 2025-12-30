"""
Database-specific metadata providers for EasySql.

Provides database-specific implementations for retrieving metadata
that SQLAlchemy Inspector doesn't support uniformly across databases,
such as comments, enum values, and row counts.
"""

from easysql.extractors.metadata_providers.base import (
    DBMetadataProvider,
    MetadataProviderFactory,
)
from easysql.extractors.metadata_providers.mysql import MySQLMetadataProvider
from easysql.extractors.metadata_providers.postgresql import PostgreSQLMetadataProvider
from easysql.extractors.metadata_providers.oracle import OracleMetadataProvider
from easysql.extractors.metadata_providers.sqlserver import SQLServerMetadataProvider

__all__ = [
    "DBMetadataProvider",
    "MetadataProviderFactory",
    "MySQLMetadataProvider",
    "PostgreSQLMetadataProvider",
    "OracleMetadataProvider",
    "SQLServerMetadataProvider",
]
