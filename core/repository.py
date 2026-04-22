from __future__ import annotations
import abc
import json
import structlog
from core.state import TransferState

logger = structlog.get_logger()

# -------------------------
# Abstract Base (the seam)
# -------------------------
class StateRepository(abc.ABC):
    """
    Interface for session state storage.
    Swap implementations via dependency injection — never in domain code.
    """

    @abc.abstractmethod
    def get(self, session_id: str) -> TransferState:
        """Load state for a session. Returns fresh state if not found."""
        ...

    @abc.abstractmethod
    def save(self, session_id: str, state: TransferState) -> None:
        """Persist state for a session."""
        ...

    @abc.abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete state for a session (cancel/reset flow)."""
        ...


# -------------------------
# In-Memory (dev / tests)
# -------------------------
class InMemoryRepository(StateRepository):
    """
    Stores state in a plain dict.
    Fast, zero dependencies — perfect for dev and unit tests.
    Lost on restart — not for production.
    """

    def __init__(self):
        self._store: dict[str, TransferState] = {}

    def get(self, session_id: str) -> TransferState:
        state = self._store.get(session_id, TransferState())
        logger.info("repo.get", session_id=session_id, status=state.status)
        return state

    def save(self, session_id: str, state: TransferState) -> None:
        self._store[session_id] = state
        logger.info("repo.save", session_id=session_id, status=state.status)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        logger.info("repo.delete", session_id=session_id)


# -------------------------
# Redis (production)
# -------------------------
class RedisRepository(StateRepository):
    """
    Stores state in Redis as JSON.
    Survives server restarts — use in production.
    TTL defaults to 1 hour per session.
    """

    def __init__(self, redis_client, ttl_seconds: int = 3600):
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"transfer:session:{session_id}"

    def get(self, session_id: str) -> TransferState:
        raw = self._redis.get(self._key(session_id))
        if raw is None:
            logger.info("repo.get.miss", session_id=session_id)
            return TransferState()
        state = TransferState(**json.loads(raw))
        logger.info("repo.get.hit", session_id=session_id, status=state.status)
        return state

    def save(self, session_id: str, state: TransferState) -> None:
        self._redis.setex(
            self._key(session_id),
            self._ttl,
            json.dumps(state.model_dump())
        )
        logger.info("repo.save", session_id=session_id, status=state.status)

    def delete(self, session_id: str) -> None:
        self._redis.delete(self._key(session_id))
        logger.info("repo.delete", session_id=session_id)


# -------------------------
# Factory (env-driven)
# -------------------------
def get_repository(backend: str = "memory", **kwargs) -> StateRepository:
    """
    Returns the right repository based on env config.
    Usage:
        repo = get_repository(backend="memory")           # dev
        repo = get_repository(backend="redis", redis_client=r, ttl_seconds=3600)  # prod
    """
    if backend == "redis":
        if "redis_client" not in kwargs:
            raise ValueError("redis_client is required for Redis backend")
        return RedisRepository(**kwargs)
    return InMemoryRepository()