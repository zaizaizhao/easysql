from enum import Enum


class QueryStatus(str, Enum):
    """Lifecycle status for a session/query."""

    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_CLARIFY = "awaiting_clarify"
    COMPLETED = "completed"
    FAILED = "failed"
