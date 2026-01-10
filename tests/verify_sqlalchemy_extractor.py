
from easysql.config import DatabaseConfig
from easysql.extractors.metadata_providers import (
    MetadataProviderFactory,
    MySQLMetadataProvider,
    PostgreSQLMetadataProvider,
)
from easysql.extractors.sqlalchemy_extractor import SQLAlchemySchemaExtractor


def test_sqlalchemy_extractor_instantiation():
    """Test that SQLAlchemySchemaExtractor can be instantiated and provider created."""
    print("Testing SQLAlchemySchemaExtractor initialization with MySQL config...")

    config = DatabaseConfig(
        name="test_db",
        db_type="mysql",
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="test"
    )

    extractor = SQLAlchemySchemaExtractor(config)
    print(f"Extractor created: {extractor}")

    # We can't easily test connection without a real DB, but we can check if classes import and factories work
    try:
        provider_class = MetadataProviderFactory._providers.get("mysql")
        print(f"MySQL Provider registered: {provider_class == MySQLMetadataProvider}")

        provider_class = MetadataProviderFactory._providers.get("postgresql")
        print(f"PostgreSQL Provider registered: {provider_class == PostgreSQLMetadataProvider}")

    except Exception as e:
        print(f"Factory test failed: {e}")

    print("Verification script finished.")

if __name__ == "__main__":
    test_sqlalchemy_extractor_instantiation()
