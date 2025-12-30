"""
Base metadata provider interface for EasySql.

Defines the abstract base class for database-specific metadata providers
and the factory for creating appropriate provider instances.
"""

from abc import ABC, abstractmethod
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class DBMetadataProvider(ABC):
    """
    Abstract base class for database-specific metadata providers.

    Handles metadata that SQLAlchemy Inspector doesn't support uniformly
    across different database types, such as:
    - Table/column comments
    - Enum values
    - Row count estimates
    - Chinese name parsing from comments
    """

    def __init__(self, engine: "Engine"):
        """
        Initialize the metadata provider.

        Args:
            engine: SQLAlchemy engine for database connections
        """
        self.engine = engine

    @abstractmethod
    def get_table_comment(self, schema: str, table_name: str) -> str | None:
        """
        Get the comment/description for a table.

        Args:
            schema: Schema/database name
            table_name: Table name

        Returns:
            Table comment or None if not available
        """
        ...

    @abstractmethod
    def get_column_comment(
        self, schema: str, table_name: str, column_name: str
    ) -> str | None:
        """
        Get the comment/description for a column.

        Args:
            schema: Schema/database name
            table_name: Table name
            column_name: Column name

        Returns:
            Column comment or None if not available
        """
        ...

    @abstractmethod
    def get_enum_values(self, column_type: str, udt_name: str | None = None) -> list[str]:
        """
        Extract enum values from a column type definition.

        Args:
            column_type: The column type string (e.g., "enum('a','b','c')")
            udt_name: User-defined type name (for PostgreSQL enums)

        Returns:
            List of enum values, or empty list if not an enum type
        """
        ...

    @abstractmethod
    def get_row_count(self, schema: str, table_name: str) -> int:
        """
        Get the estimated row count for a table.

        Args:
            schema: Schema/database name
            table_name: Table name

        Returns:
            Estimated row count (0 if not available)
        """
        ...

    def parse_comment(self, comment: str | None) -> tuple[str | None, str | None]:
        """
        Parse Chinese name and description from comment.

        Handles formats like:
        - "中文名"
        - "中文名-描述"
        - "中文名: 描述"
        - "中文名（描述）"

        Args:
            comment: Raw comment string

        Returns:
            Tuple of (chinese_name, description)
        """
        if not comment:
            return None, None

        comment = comment.strip()

        # Try to extract Chinese name (first continuous Chinese characters)
        match = re.match(r"^([\u4e00-\u9fa5]+)", comment)
        chinese_name = match.group(1) if match else None

        # If the comment is longer, the rest is description
        if chinese_name and len(comment) > len(chinese_name):
            description = comment
        else:
            description = None

        return chinese_name, description


class MetadataProviderFactory:
    """
    Factory for creating database-specific metadata providers.

    Uses the Factory pattern to instantiate the appropriate
    provider based on database type.
    """

    _providers: dict[str, type[DBMetadataProvider]] = {}

    @classmethod
    def register(cls, db_type: str, provider_class: type[DBMetadataProvider]) -> None:
        """
        Register a metadata provider class for a database type.

        Args:
            db_type: Database type identifier (e.g., 'mysql', 'postgresql')
            provider_class: Provider class to register
        """
        cls._providers[db_type.lower()] = provider_class
        logger.debug(f"Registered metadata provider for {db_type}: {provider_class.__name__}")

    @classmethod
    def create(cls, db_type: str, engine: "Engine") -> DBMetadataProvider:
        """
        Create a metadata provider instance for the given database type.

        Args:
            db_type: Database type identifier
            engine: SQLAlchemy engine

        Returns:
            Appropriate metadata provider instance

        Raises:
            ValueError: If no provider is registered for the database type
        """
        db_type_lower = db_type.lower()

        if db_type_lower not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"No metadata provider registered for database type '{db_type}'. "
                f"Available types: {available}"
            )

        provider_class = cls._providers[db_type_lower]
        logger.debug(f"Creating {provider_class.__name__} for {db_type}")
        return provider_class(engine)

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported database types."""
        return list(cls._providers.keys())
