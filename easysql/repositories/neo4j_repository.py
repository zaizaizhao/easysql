"""
Neo4j Repository - Connection management for Neo4j.

Provides a shared connection layer used by both Neo4jSchemaReader and Neo4jSchemaWriter.
"""

from neo4j import Driver, GraphDatabase

from easysql.utils.logger import get_logger

logger = get_logger(__name__)


class Neo4jRepository:
    """
    Neo4j connection manager.

    Manages the Neo4j driver lifecycle and provides session access
    for both read and write operations.
    """

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver: Driver | None = None

    def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j: {self.uri}")

            if self.database != "neo4j":
                self._ensure_database_exists()

        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise ConnectionError(f"Neo4j connection failed: {e}") from e

    def _ensure_database_exists(self) -> None:
        """Create the database if it doesn't exist (Neo4j Enterprise/AuraDB only)."""
        if self._driver is None:
            return
        try:
            with self._driver.session(database="system") as session:
                result = session.run("SHOW DATABASES WHERE name = $name", name=self.database)
                exists = result.single() is not None

                if not exists:
                    logger.info(f"Creating Neo4j database: {self.database}")
                    session.run(f"CREATE DATABASE {self.database} IF NOT EXISTS")
                    logger.info(f"Database '{self.database}' created successfully")
                else:
                    logger.debug(f"Database '{self.database}' already exists")

        except Exception as e:
            error_msg = str(e).lower()
            if (
                "unsupported" in error_msg
                or "not supported" in error_msg
                or "does not exist" in error_msg
            ):
                logger.warning(
                    "Multi-database not supported (Neo4j Community Edition). "
                    "Falling back to default 'neo4j' database."
                )
                self.database = "neo4j"
            else:
                logger.warning(f"Could not ensure database exists: {e}. Falling back to 'neo4j'.")
                self.database = "neo4j"

    def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.debug("Neo4j connection closed")

    @property
    def driver(self) -> Driver:
        """Get the Neo4j driver, connecting if necessary."""
        if not self._driver:
            self.connect()
        assert self._driver is not None
        return self._driver

    def __enter__(self) -> "Neo4jRepository":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
