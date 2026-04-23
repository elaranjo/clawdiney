"""Tests for QueryCache functionality."""

import os
import time
from unittest.mock import patch

import pytest
import redis

from clawdiney.query_cache import QueryCache


@pytest.fixture
def mock_redis():
    """Mock Redis client for unit tests."""
    with patch("clawdiney.query_cache.redis.Redis") as mock:
        mock_instance = mock.return_value
        mock_instance.ping.return_value = True
        mock_instance.get.return_value = None
        mock_instance.setex.return_value = True
        mock_instance.keys.return_value = []
        mock_instance.delete.return_value = 0
        mock_instance.close.return_value = None
        yield mock_instance


class TestQueryCacheInit:
    """Test QueryCache initialization."""

    def test_init_default_config(self, mock_redis):
        """Test initialization with default config values."""
        cache = QueryCache()
        assert cache.host == "localhost"
        assert cache.port == 6379
        assert cache.ttl.total_seconds() == 24 * 60 * 60  # 24 hours

    def test_init_custom_params(self, mock_redis):
        """Test initialization with custom parameters."""
        cache = QueryCache(host="custom-host", port=6380, db=1, ttl_hours=12)
        assert cache.host == "custom-host"
        assert cache.port == 6380
        assert cache.ttl.total_seconds() == 12 * 60 * 60  # 12 hours


class TestQueryCacheHash:
    """Test query hashing functionality."""

    def test_hash_query_consistent(self, mock_redis):
        """Test that same query produces same hash."""
        cache = QueryCache()
        hash1 = cache._hash_query("test query")
        hash2 = cache._hash_query("test query")
        assert hash1 == hash2

    def test_hash_query_different(self, mock_redis):
        """Test that different queries produce different hashes."""
        cache = QueryCache()
        hash1 = cache._hash_query("query one")
        hash2 = cache._hash_query("query two")
        assert hash1 != hash2

    def test_build_key_format(self, mock_redis):
        """Test cache key format."""
        cache = QueryCache()
        key = cache._build_key("test")
        assert key.startswith("clawdiney:query:")


class TestQueryCacheOperations:
    """Test cache operations with mocked Redis."""

    def test_cache_miss(self, mock_redis):
        """Test cache miss returns None."""
        mock_redis.get.return_value = None
        cache = QueryCache()
        result = cache.get("test query")
        assert result is None

    def test_cache_hit(self, mock_redis):
        """Test cache hit returns cached data."""
        import json
        cached_data = {"result": "test data"}
        mock_redis.get.return_value = json.dumps(cached_data)
        cache = QueryCache()
        result = cache.get("test query")
        assert result == cached_data

    def test_cache_set(self, mock_redis):
        """Test setting cache value."""
        cache = QueryCache()
        result = cache.set("test query", {"data": "value"})
        assert result is True
        mock_redis.setex.assert_called_once()

    def test_cache_set_redis_error(self, mock_redis):
        """Test set returns False on Redis error."""
        # Use RedisError which is caught by the handler
        mock_redis.setex.side_effect = redis.RedisError("Redis error")
        cache = QueryCache()
        _ = cache.client  # Trigger client initialization with mock
        result = cache.set("test query", {"data": "value"})
        assert result is False

    def test_cache_invalidate(self, mock_redis):
        """Test cache invalidation."""
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        mock_redis.delete.return_value = 3
        cache = QueryCache()
        result = cache.invalidate("pattern")
        assert result == 3

    def test_is_available_connected(self, mock_redis):
        """Test is_available returns True when connected."""
        cache = QueryCache()
        _ = cache.client  # Trigger client initialization
        assert cache.is_available() is True

    def test_is_available_not_connected(self):
        """Test is_available returns False when not connected."""
        with patch("clawdiney.query_cache.redis.Redis") as mock:
            mock.return_value.ping.side_effect = Exception("Connection failed")
            cache = QueryCache()
            assert cache.is_available() is False


class TestQueryCacheIntegration:
    """Integration tests with real Redis (skipped by default)."""

    @pytest.mark.skipif(
        os.getenv("RUN_CACHE_TESTS") != "1",
        reason="Set RUN_CACHE_TESTS=1 to run Redis integration tests",
    )
    def test_real_redis_roundtrip(self):
        """Test cache set and get with real Redis."""
        cache = QueryCache(ttl_hours=1)
        try:
            # Set value
            test_data = {"query": "test", "results": ["result1", "result2"]}
            assert cache.set("integration_test", test_data) is True

            # Get value
            result = cache.get("integration_test")
            assert result == test_data
        finally:
            cache.close()

    @pytest.mark.skipif(
        os.getenv("RUN_CACHE_TESTS") != "1",
        reason="Set RUN_CACHE_TESTS=1 to run Redis integration tests",
    )
    def test_real_redis_ttl(self):
        """Test cache TTL with real Redis."""
        cache = QueryCache(ttl_hours=1)
        try:
            test_data = {"test": "data"}
            cache.set("ttl_test", test_data)

            # Check TTL exists
            ttl = cache.client.ttl("clawdiney:query:" + cache._hash_query("ttl_test"))
            assert ttl > 0
            assert ttl <= 3600  # 1 hour max
        finally:
            cache.close()
