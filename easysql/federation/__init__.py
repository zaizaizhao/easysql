"""PostgreSQL multi-database query support."""

from easysql.federation.executor import (
    FederatedExecutionResult,
    FederatedSqlExecutor,
    FederatedSqlRequest,
)
from easysql.federation.scope import DatabaseScope, DatabaseTarget
from easysql.federation.status import (
    DatabaseDblinkStatus,
    DblinkRouteStatus,
    FederationStatus,
    FederationStatusProbe,
)

__all__ = [
    "DatabaseScope",
    "DatabaseTarget",
    "FederatedSqlExecutor",
    "FederatedSqlRequest",
    "FederatedExecutionResult",
    "DatabaseDblinkStatus",
    "DblinkRouteStatus",
    "FederationStatus",
    "FederationStatusProbe",
]
