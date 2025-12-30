
import sys

# Ensure extractors package is imported to trigger registration
import easysql.extractors

from easysql.config import DatabaseConfig
from easysql.extractors.base import ExtractorFactory
from easysql.extractors.sqlalchemy_extractor import SQLAlchemySchemaExtractor

def test_factory_registration():
    """Test that factory returns correct extractor for DB types."""
    print("Testing ExtractorFactory registration...")
    
    # Test MySQL
    mysql_config = DatabaseConfig(
        name="test_mysql",
        db_type="mysql",
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="test"
    )
    
    try:
        extractor = ExtractorFactory.create(mysql_config)
        print(f"Created extractor for mysql: {type(extractor).__name__}")
        assert isinstance(extractor, SQLAlchemySchemaExtractor), "MySQL should use SQLAlchemySchemaExtractor"
        print(f"  Schema: {mysql_config.get_default_schema()}")
    except Exception as e:
        print(f"Failed to create MySQL extractor: {e}")
        return False

    # Test PostgreSQL
    pg_config = DatabaseConfig(
        name="test_pg",
        db_type="postgresql",
        host="localhost",
        port=5432,
        user="postgres",
        password="password",
        database="test"
    )
    
    try:
        extractor = ExtractorFactory.create(pg_config)
        print(f"Created extractor for postgresql: {type(extractor).__name__}")
        assert isinstance(extractor, SQLAlchemySchemaExtractor), "PostgreSQL should use SQLAlchemySchemaExtractor"
        print(f"  Schema: {pg_config.get_default_schema()}")
    except Exception as e:
        print(f"Failed to create PostgreSQL extractor: {e}")
        return False

    # Test Oracle
    oracle_config = DatabaseConfig(
        name="test_oracle",
        db_type="oracle",
        host="localhost",
        port=1521,
        user="system",
        password="password",
        database="ORCL"
    )
    
    try:
        extractor = ExtractorFactory.create(oracle_config)
        print(f"Created extractor for oracle: {type(extractor).__name__}")
        print(f"  Schema: {oracle_config.get_default_schema()}")
    except Exception as e:
        print(f"Failed to create Oracle extractor: {e}")
        return False

    # Test SQLServer
    sqlserver_config = DatabaseConfig(
        name="test_sqlserver",
        db_type="sqlserver",
        host="localhost",
        port=1433,
        user="sa",
        password="password",
        database="master"
    )
    
    try:
        extractor = ExtractorFactory.create(sqlserver_config)
        print(f"Created extractor for sqlserver: {type(extractor).__name__}")
        print(f"  Schema: {sqlserver_config.get_default_schema()}")
    except Exception as e:
        print(f"Failed to create SQLServer extractor: {e}")
        return False

    # Test custom schema
    custom_schema_config = DatabaseConfig(
        name="test_custom",
        db_type="postgresql",
        host="localhost",
        port=5432,
        user="postgres",
        password="password",
        database="test",
        schema="my_schema"
    )
    assert custom_schema_config.get_default_schema() == "my_schema", "Custom schema should be used"
    print(f"Custom schema test passed: {custom_schema_config.get_default_schema()}")
        
    print("Factory verification successful!")
    return True

if __name__ == "__main__":
    success = test_factory_registration()
    if not success:
        sys.exit(1)
