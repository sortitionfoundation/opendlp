"""ABOUTME: In-memory stand-in for the Redis client
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""


class FakeRedis:
    """The slice of redis-py the services use, backed by a dict.

    A MagicMock won't do: the CSV upload stash writes on one request and reads
    on the next, and the auto-export debounce relies on ``SET NX`` answering
    truthfully. Values are stored as bytes, as a client built without
    ``decode_responses`` returns them. TTLs are ignored - nothing expires
    within a test.
    """

    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}

    def set(self, key: str, value: str | bytes, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self._values:
            return None
        self._values[key] = value.encode("utf-8") if isinstance(value, str) else value
        return True

    def get(self, key: str) -> bytes | None:
        return self._values.get(key)

    def delete(self, key: str) -> int:
        return 1 if self._values.pop(key, None) is not None else 0
