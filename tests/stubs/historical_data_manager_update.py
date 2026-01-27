"""Updated historical data manager methods to use continuous aggregates (stub)."""



async def get_async_db():
    """Fallback async context manager used in tests."""

    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            class _Result:
                def fetchall(self):
                    return []

            return _Result()

    return _DummySession()


