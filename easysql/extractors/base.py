"""
Base schema extractor interface for EasySql.

Defines the abstract base class and factory for database schema extractors.
Uses the Adapter pattern to support multiple database types with a unified interface.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from easysql.models.schema import DatabaseMeta, DatabaseType, ForeignKeyMeta, TableMeta
from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.config import DatabaseConfig

logger = get_logger(__name__)


class BaseSchemaExtractor(ABC):
    """
    Abstract base class for database schema extractors.

    Implementations should extract schema metadata from specific
    database types (MySQL, PostgreSQL, etc.) and convert them
    to the unified metadata model.

    Usage:
        extractor = MySQLSchemaExtractor(config)
        metadata = extractor.extract_all()
    """

    def __init__(self, config: "DatabaseConfig"):
        """
        Initialize the extractor with database configuration.

        Args:
            config: Database connection configuration
        """
        self.config = config
        self._connection = None

    @property
    @abstractmethod
    def db_type(self) -> DatabaseType:
        """Get the database type handled by this extractor."""
        ...

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the database.

        Raises:
            ConnectionError: If connection fails
        """
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""
        ...

    @abstractmethod
    def extract_tables(self) -> list[TableMeta]:
        """
        Extract all table metadata from the database.

        Returns:
            List of TableMeta objects with columns and indexes
        """
        ...

    @abstractmethod
    def extract_foreign_keys(self) -> list[ForeignKeyMeta]:
        """
        Extract all foreign key relationships.

        Returns:
            List of ForeignKeyMeta objects
        """
        ...

    def extract_all(self) -> DatabaseMeta:
        """
        Extract complete database metadata.

        This is the main entry point that orchestrates the extraction
        of tables, columns, indexes, and foreign keys.

        Returns:
            DatabaseMeta object with complete schema information
        """
        logger.info(f"Starting schema extraction for {self.config.database}")

        try:
            self.connect()

            # Extract tables with columns and indexes
            tables = self.extract_tables()
            logger.info(f"Extracted {len(tables)} tables")

            # Extract foreign key relationships
            foreign_keys = self.extract_foreign_keys()
            logger.info(f"Extracted {len(foreign_keys)} foreign keys")

            # Mark FK columns based on foreign key definitions
            self._mark_fk_columns(tables, foreign_keys)

            # Build the complete database metadata
            db_meta = DatabaseMeta(
                name=self.config.database,
                db_type=self.db_type,
                host=self.config.host,
                port=self.config.port,
                system_type=self.config.system_type,
                description=self.config.description,
                tables=tables,
                foreign_keys=foreign_keys,
            )

            stats = db_meta.get_statistics()
            logger.info(
                f"Extraction complete: {stats['tables']} tables, "
                f"{stats['columns']} columns, {stats['foreign_keys']} FKs"
            )

            return db_meta

        finally:
            self.disconnect()

    def _mark_fk_columns(
        self, tables: list[TableMeta], foreign_keys: list[ForeignKeyMeta]
    ) -> None:
        """Mark columns that are foreign keys based on FK definitions."""
        fk_columns = {(fk.from_table, fk.from_column) for fk in foreign_keys}

        for table in tables:
            for column in table.columns:
                if (table.name, column.name) in fk_columns:
                    column.is_fk = True

    def __enter__(self) -> "BaseSchemaExtractor":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


class ExtractorFactory:
    """
    Factory for creating database schema extractors.

    Uses the Factory pattern to instantiate the appropriate
    extractor based on database type.

    Usage:
        extractor = ExtractorFactory.create(config)
        metadata = extractor.extract_all()
    """

    _extractors: dict[str, type[BaseSchemaExtractor]] = {}

    @classmethod
    def register(cls, db_type: str, extractor_class: type[BaseSchemaExtractor]) -> None:
        """
        Register an extractor class for a database type.

        Args:
            db_type: Database type identifier (e.g., 'mysql', 'postgresql')
            extractor_class: Extractor class to register
        """
        cls._extractors[db_type.lower()] = extractor_class
        logger.debug(f"Registered extractor for {db_type}: {extractor_class.__name__}")

    @classmethod
    def create(cls, config: "DatabaseConfig") -> BaseSchemaExtractor:
        """
        Create an extractor instance for the given configuration.

        Args:
            config: Database connection configuration

        Returns:
            Appropriate extractor instance

        Raises:
            ValueError: If no extractor is registered for the database type
        """
        db_type = config.db_type.lower()

        if db_type not in cls._extractors:
            available = ", ".join(cls._extractors.keys())
            raise ValueError(
                f"No extractor registered for database type '{db_type}'. "
                f"Available types: {available}"
            )

        extractor_class = cls._extractors[db_type]
        logger.info(f"Creating {extractor_class.__name__} for {config.database}")
        return extractor_class(config)

    @classmethod
    def get_supported_types(cls) -> list[str]:
        """Get list of supported database types."""
        return list(cls._extractors.keys())
