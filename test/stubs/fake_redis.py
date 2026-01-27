"""
Fake Redis implementation for tests.

Provides an in-memory async stub that implements the subset of Redis
commands relied on by the service.
"""

import asyncio
import json
from typing import Any


class _Pipeline:
    def __init__(self, client: "FakeRedis"):
        self.client = client
        self._ops = []

    def incr(self, key: str, amount: int = 1):
        self._ops.append(("incr", key, amount))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for op in self._ops:
            name = op[0]
            if name == "incr":
                _, key, amount = op
                results.append(await self.client.incr(key, amount))
            elif name == "expire":
                _, key, ttl = op
                results.append(await self.client.expire(key, ttl))
        self._ops = []
        return results


class FakeRedis:
    """Lightweight async in-memory Redis replacement for development."""

    def __init__(self):
        self.store: dict[str, Any] = {}
        self.expiry: dict[str, float] = {}

    def pipeline(self):
        return _Pipeline(self)

    async def ping(self):
        return True

    async def exists(self, key: str):
        return key in self.store

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None):
        self.store[key] = value
        if ex:
            await self.expire(key, ex)
        return True

    async def setex(self, key: str, ttl: int, value: Any):
        self.store[key] = value
        await self.expire(key, ttl)
        return True

    async def expire(self, key: str, ttl: int):
        if key in self.store:
            self.expiry[key] = asyncio.get_event_loop().time() + ttl
            return True
        return False

    async def ttl(self, key: str):
        if key not in self.expiry:
            return -1
        return max(0, int(self.expiry[key] - asyncio.get_event_loop().time()))

    async def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
            self.expiry.pop(key, None)
        return len(keys)

    async def flushall(self):
        self.store.clear()
        self.expiry.clear()
        return True

    async def incr(self, key: str, amount: int = 1):
        current = int(self.store.get(key, 0) or 0)
        current += amount
        self.store[key] = current
        return current

    async def hgetall(self, key: str):
        value = self.store.get(key, {})
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {}
        return value or {}

    async def hset(self, key: str, field: str, value: Any):
        current = self.store.get(key, {}) or {}
        current[field] = value
        self.store[key] = current
        return True

    async def hdel(self, key: str, *fields: str):
        current = self.store.get(key, {}) or {}
        deleted_count = 0
        for f in fields:
            if f in current:
                current.pop(f)
                deleted_count += 1
        self.store[key] = current
        return deleted_count

    async def lpush(self, key: str, value: Any):
        lst = self.store.setdefault(key, [])
        lst.insert(0, value)
        return len(lst)

    async def ltrim(self, key: str, start: int, end: int):
        lst = self.store.get(key, [])
        self.store[key] = lst[start : end + 1]
        return True

    async def xadd(self, name, fields, maxlen=None, **_kwargs):
        stream = self.store.setdefault(name, [])
        msg_id = str(len(stream))
        stream.append((msg_id, {k: str(v) for k, v in fields.items()}))

        # Apply maxlen if specified
        if maxlen and len(stream) > maxlen:
            self.store[name] = stream[-maxlen:]

        return msg_id

    async def xgroup_create(self, *_args, **_kwargs):
        return True

    async def xreadgroup(self, group, consumer, streams: dict, count: int = 1, block=None, **_kwargs):
        # Simple mock implementation
        return []

    async def xack(self, *_args, **_kwargs):
        return True

    async def xread(self, streams: dict, count: int = 1, block=None):
        result = []
        for name, _start_id in streams.items():
            stream = self.store.get(name, [])
            if stream:
                result.append((name, list(stream[:count])))
        return result

    async def scan(self, cursor=0, match=None, count=None):
        keys = list(self.store.keys())
        if match:
            pattern = match.replace('*', '')
            keys = [k for k in keys if pattern in k]
        return (0, keys)

    async def keys(self, pattern: str):
        pattern_str = pattern.replace("*", "")
        return [k for k in self.store if pattern_str in k]

    def pubsub(self):
        return self

    async def subscribe(self, *channels):
        """Mock subscribe for pubsub."""

    async def unsubscribe(self, *channels):
        """Mock unsubscribe for pubsub."""

    async def get_message(self, ignore_subscribe_messages=True, timeout=None):
        """Mock get_message for pubsub."""
        return

    async def publish(self, channel, message):
        """Mock publish."""
        return 1

    async def close(self):
        return True

    async def info(self, section: str = None):
        """Return lightweight memory stats."""
        return {"used_memory": len(self.store), "keys": len(self.store), "connected_clients": 1, "uptime_in_seconds": 3600, "redis_version": "fake", "role": "master"}


_fake_client: FakeRedis | None = None


async def get_redis_client(redis_url: str = None):
    """
    Get fake Redis client for tests.
    """
    global _fake_client
    if _fake_client is None:
        _fake_client = FakeRedis()
    return _fake_client
