"""
EasySql - Enterprise Text2SQL Metadata Pipeline

A pipeline for extracting database schema metadata and storing it in
Neo4j (graph relationships) and Milvus (vector embeddings) for
Text2SQL applications.
"""

__version__ = "0.1.0"
__author__ = "EasySql Team"

from easysql.config import Settings, get_settings

__all__ = ["Settings", "get_settings", "__version__"]
