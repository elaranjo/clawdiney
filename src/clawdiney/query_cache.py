"""Redis-backed cache for query results."""

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

import redis

from .config import Config

logger = logging.getLogger(__name__)

# Redis connection timeouts (seconds)
REDIS_SOCKET_CONNECT_TIMEOUT = 5
REDIS_SOCKET_TIMEOUT = 5

# Cache key prefix
CACHE_KEY_PREFIX = "clawdiney:query:"

# Default TTL (hours)
DEFAULT_TTL_HOURS = 24


class QueryCache:
    """Redis-backed cache for query results with TTL support."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int = 0,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        """
        Initialize Redis cache connection.

        Args:
            host: Redis host (default: from Config.REDIS_HOST)
            port: Redis port (default: from Config.REDIS_PORT)
            db: Redis database number (default: 0)
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        self.host = host or Config.REDIS_HOST
        self.port = port or Config.REDIS_PORT
        self.db = db
        self.ttl = timedelta(hours=ttl_hours)
        self._client: redis.Redis | None = None
        self._connected = False

    @property
    def client(self) -> redis.Redis | None:
        """Lazy Redis client initialization with error handling."""
        if self._client is not None:
            return self._client

        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=Config.REDIS_PASSWORD if Config.REDIS_PASSWORD else None,
                decode_responses=True,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
            )
            # Test connection
            self._client.ping()
            self._connected = True
            logger.info(f"Query cache connected to Redis at {self.host}:{self.port}")
            return self._client
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Cache disabled.")
            self._connected = False
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            return None
        except Exception as e:
            logger.warning(f"Redis initialization error: {e}. Cache disabled.")
            self._connected = False
            if self._client:
                try:
                    self._client.close()
                except Exception:
                    pass
            return None

    def _hash_query(self, query: str) -> str:
        """Generate SHA-256 hash of query for cache key."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _build_key(self, query: str) -> str:
        """Build cache key for query."""
        return f"{CACHE_KEY_PREFIX}{self._hash_query(query)}"

    def get(self, query: str) -> dict[str, Any] | None:
        """
        Get cached results for query.

        Args:
            query: The original query string

        Returns:
            Cached results dict or None if not found/expired
        """
        client = self.client
        if not client:
            return None

        try:
            key = self._build_key(query)
            cached = client.get(key)
            if cached:
                # Log apenas o hash para evitar vazar dados sensíveis
                if logger.isEnabledFor(logging.DEBUG):
                    query_hash = self._hash_query(query)[:16]
                    logger.debug("Cache hit for query hash: %s...", query_hash)
                return json.loads(cached)
            if logger.isEnabledFor(logging.DEBUG):
                query_hash = self._hash_query(query)[:16]
                logger.debug("Cache miss for query hash: %s...", query_hash)
            return None
        except redis.RedisError as e:
            logger.warning(f"Redis get error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Cache JSON decode error: {e}")
            return None

    def set(self, query: str, results: dict[str, Any]) -> bool:
        """
        Cache query results with TTL.

        Args:
            query: The original query string
            results: Results dict to cache

        Returns:
            True if successful, False otherwise
        """
        client = self.client
        if not client:
            return False

        try:
            key = self._build_key(query)
            client.setex(key, self.ttl, json.dumps(results))
            # Log apenas o hash para evitar vazar dados sensíveis
            if logger.isEnabledFor(logging.DEBUG):
                query_hash = self._hash_query(query)[:16]
                logger.debug("Cached results for query hash: %s...", query_hash)
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis set error: {e}")
            return False
        except (TypeError, ValueError) as e:
            logger.warning(f"Cache JSON encode error: {e}")
            return False

    def invalidate(self, pattern: str = "*") -> int:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Glob pattern to match keys (default: "*" for all)

        Returns:
            Number of keys deleted
        """
        client = self.client
        if not client:
            return 0

        try:
            keys = client.keys(f"{CACHE_KEY_PREFIX}{pattern}")
            if keys:
                deleted = int(client.delete(*keys))  # type: ignore[misc]
                logger.info(f"Invalidated {deleted} cache entries")
                return deleted
            return 0
        except redis.RedisError as e:
            logger.warning(f"Redis invalidate error: {e}")
            return 0

    def is_available(self) -> bool:
        """Check if Redis cache is available."""
        return self._connected and self.client is not None

    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            finally:
                self._client = None
                self._connected = False
