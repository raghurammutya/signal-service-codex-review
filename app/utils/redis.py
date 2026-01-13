"""
Minimal Redis helper used in tests/dev.

Provides an in-memory async stub that implements the small subset of Redis
commands relied on by the service.
"""

from typing import Any, Dict, List, Optional
import asyncio
import json


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
    """Lightweight async in-memory Redis replacement."""

    def __init__(self):
        self.store: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}

    def pipeline(self):
        return _Pipeline(self)

    async def ping(self):
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: Any, ex: Optional[int] = None):
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
        return True

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
        for f in fields:
            current.pop(f, None)
        self.store[key] = current
        return True

    async def lpush(self, key: str, value: Any):
        lst = self.store.setdefault(key, [])
        lst.insert(0, value)
        return True

    async def ltrim(self, key: str, start: int, end: int):
        lst = self.store.get(key, [])
        self.store[key] = lst[start : end + 1]
        return True

    async def xadd(self, name, fields, **_kwargs):
        stream = self.store.setdefault(name, [])
        msg_id = str(len(stream))
        stream.append((msg_id, {k.encode(): str(v).encode() for k, v in fields.items()}))
        return msg_id

    async def xgroup_create(self, *_args, **_kwargs):
        return True

    async def xreadgroup(self, *_args, **_kwargs):
        return []

    async def xack(self, *_args, **_kwargs):
        return True

    async def xread(self, streams: dict, count: int = 1):
        result = []
        for name, start_id in streams.items():
            stream = self.store.get(name, [])
            if stream:
                result.append((name, [(mid, data) for mid, data in stream[:count]]))
        return result

    async def xreadgroup(self, group, consumer, streams: dict, count: int = 1, **_kwargs):
        return await self.xread(streams, count=count)

    async def scan(self, *_args, **_kwargs):
        return (0, [])

    async def keys(self, pattern: str):
        return [k for k in self.store if k.startswith(pattern.replace("*", ""))]

    def pubsub(self):
        return self

    async def publish(self, *_args, **_kwargs):
        return True

    async def close(self):
        return True

    async def info(self, section: str = None):
        """Return lightweight memory stats."""
        return {"used_memory": len(self.store), "keys": len(self.store)}


_client: Optional[FakeRedis] = None


async def get_redis_client(_url: str = None):
    """Return a singleton fake redis client for tests/dev."""
    global _client
    if _client is None:
        _client = FakeRedis()
    return _client
