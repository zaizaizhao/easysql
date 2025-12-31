"""Extractors package for EasySql."""

from easysql.extractors.base import BaseSchemaExtractor, ExtractorFactory
from easysql.extractors.sqlalchemy_extractor import SQLAlchemySchemaExtractor
from easysql.extractors.metadata_providers import (
    DBMetadataProvider,
    MetadataProviderFactory,
)
# 模块导入时自动注册    注册表模式 (Registry Pattern)
# Register uniform extractor for all supported types
# This replaces the legacy specific classes
ExtractorFactory.register("mysql", SQLAlchemySchemaExtractor)
ExtractorFactory.register("postgresql", SQLAlchemySchemaExtractor)
ExtractorFactory.register("oracle", SQLAlchemySchemaExtractor)
ExtractorFactory.register("sqlserver", SQLAlchemySchemaExtractor)

__all__ = [
    "BaseSchemaExtractor",
    "ExtractorFactory",
    "SQLAlchemySchemaExtractor",
    "DBMetadataProvider",
    "MetadataProviderFactory",
]
