"""ABOUTME: Integration tests for the Google Sheets access check cache against a real Redis
ABOUTME: Checks the round trip, the TTL and the URL guard with the client the app builds"""

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.service_layer import gsheet_access_check
from opendlp.service_layer.gsheet_access_check import (
    GSheetAccessResult,
    GSheetAccessStatus,
    fetch_cached_result,
    forget_cached_result,
    store_cached_result,
)

_URL = "https://docs.google.com/spreadsheets/d/abc/edit"


@pytest.fixture
def redis(test_redis_client):
    test_redis_client.flushdb()
    yield test_redis_client
    test_redis_client.flushdb()


def _result() -> GSheetAccessResult:
    return GSheetAccessResult(
        status=GSheetAccessStatus.READ_ONLY,
        url=_URL,
        checked_at=datetime(2026, 10, 16, 14, 2, tzinfo=UTC),
        title="Leeds Assembly",
        error_code="spreadsheet_read_only",
        error_params={"spreadsheet_name": _URL, "title": "Leeds Assembly", "service_account_email": "r@example.com"},
        missing_selection_tabs=("Categories",),
        tab_suggestions={"Categories": "categories"},
    )


class TestGSheetAccessCacheWithRedis:
    def test_round_trip(self, redis) -> None:
        assembly_id = uuid.uuid4()

        store_cached_result(assembly_id, _result(), redis_client=redis)

        assert fetch_cached_result(assembly_id, _URL, redis_client=redis) == _result()

    def test_stored_with_ten_minute_ttl(self, redis) -> None:
        assembly_id = uuid.uuid4()

        store_cached_result(assembly_id, _result(), redis_client=redis)

        ttl = redis.ttl(f"gsheet_access_check:{assembly_id}")
        assert 0 < ttl <= gsheet_access_check.CACHE_TTL_SECONDS

    def test_other_url_is_a_miss_and_forget_removes(self, redis) -> None:
        assembly_id = uuid.uuid4()
        store_cached_result(assembly_id, _result(), redis_client=redis)

        assert fetch_cached_result(assembly_id, "https://docs.google.com/spreadsheets/d/other", redis) is None
        forget_cached_result(assembly_id, redis_client=redis)
        assert fetch_cached_result(assembly_id, _URL, redis_client=redis) is None
