"""ABOUTME: Checks what the service account can do with a Google Sheet, and caches the answer briefly
ABOUTME: Reports access (ok, read-only, not shared, not found...), the title, and configured tabs that are missing"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import gspread
import redis
import structlog
from sortition_algorithms import open_gsheet
from sortition_algorithms.errors import (
    NotNativeGoogleSheetError,
    SpreadsheetNotFoundError,
    SpreadsheetNotSharedError,
    SpreadsheetReadOnlyError,
)

from opendlp.config import RedisCfg

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable, Sequence

    from redis import Redis

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "gsheet_access_check:"
CACHE_TTL_SECONDS = 10 * 60
_HTTP_TOO_MANY_REQUESTS = 429


class GSheetAccessStatus(Enum):
    OK = "ok"
    READ_ONLY = "read_only"
    NOT_SHARED = "not_shared"
    NOT_FOUND = "not_found"
    NOT_NATIVE = "not_native"
    GOOGLE_BUSY = "google_busy"
    UNAVAILABLE = "unavailable"


# Results about Google right now rather than about the sheet. They are never
# cached, so a later page view shows the last real answer instead.
_TRANSIENT_STATUSES = frozenset({GSheetAccessStatus.GOOGLE_BUSY, GSheetAccessStatus.UNAVAILABLE})


@dataclass(frozen=True)
class GSheetAccessResult:
    """The outcome of one access check.

    A failure keeps the library error's code and parameters rather than its
    message, so the panel is translated into the language of whoever views it.
    """

    status: GSheetAccessStatus
    url: str
    checked_at: datetime
    title: str = ""
    error_code: str = ""
    error_params: dict[str, str | int] = field(default_factory=dict)
    missing_selection_tabs: tuple[str, ...] = ()
    missing_replacement_tabs: tuple[str, ...] = ()
    tab_suggestions: dict[str, str] = field(default_factory=dict)

    @property
    def is_transient(self) -> bool:
        return self.status in _TRANSIENT_STATUSES

    def to_json(self) -> str:
        return json.dumps({
            "status": self.status.value,
            "url": self.url,
            "checked_at": self.checked_at.isoformat(),
            "title": self.title,
            "error_code": self.error_code,
            "error_params": self.error_params,
            "missing_selection_tabs": list(self.missing_selection_tabs),
            "missing_replacement_tabs": list(self.missing_replacement_tabs),
            "tab_suggestions": self.tab_suggestions,
        })

    @classmethod
    def from_json(cls, raw: str | bytes) -> GSheetAccessResult:
        data: dict[str, Any] = json.loads(raw)
        return cls(
            status=GSheetAccessStatus(data["status"]),
            url=data["url"],
            checked_at=datetime.fromisoformat(data["checked_at"]),
            title=data["title"],
            error_code=data["error_code"],
            error_params=data["error_params"],
            missing_selection_tabs=tuple(data["missing_selection_tabs"]),
            missing_replacement_tabs=tuple(data["missing_replacement_tabs"]),
            tab_suggestions=data["tab_suggestions"],
        )


def check_gsheet_access(
    client: gspread.client.Client,
    url: str,
    selection_tabs: Sequence[str],
    replacement_tabs: Sequence[str],
    now: datetime,
) -> GSheetAccessResult:
    """Ask Google what the service account can do with the sheet at `url`.

    Tabs are only compared when the sheet opens. An empty tab name is skipped:
    it means that tab is not used. Exceptions other than the ones Google
    access is known to raise propagate, because they are bugs.
    """
    try:
        info = open_gsheet(client, url)
        tab_titles = [worksheet.title for worksheet in info.spreadsheet.worksheets()]
    except (SpreadsheetNotSharedError, SpreadsheetNotFoundError, NotNativeGoogleSheetError) as error:
        return GSheetAccessResult(
            status=_STATUS_FOR_ERROR[type(error)],
            url=url,
            checked_at=now,
            error_code=error.error_code,
            error_params=error.error_params,
        )
    except gspread.exceptions.APIError as error:
        busy = error.code == _HTTP_TOO_MANY_REQUESTS
        status = GSheetAccessStatus.GOOGLE_BUSY if busy else GSheetAccessStatus.UNAVAILABLE
        return GSheetAccessResult(status=status, url=url, checked_at=now)
    except OSError:
        # requests raises its timeout and connection errors as OSError subclasses
        return GSheetAccessResult(status=GSheetAccessStatus.UNAVAILABLE, url=url, checked_at=now)

    missing_selection = _missing_tabs(selection_tabs, tab_titles)
    missing_replacement = _missing_tabs(replacement_tabs, tab_titles)
    suggestions = _near_misses([*missing_selection, *missing_replacement], tab_titles)
    if info.can_edit:
        return GSheetAccessResult(
            status=GSheetAccessStatus.OK,
            url=url,
            checked_at=now,
            title=info.title,
            missing_selection_tabs=missing_selection,
            missing_replacement_tabs=missing_replacement,
            tab_suggestions=suggestions,
        )
    read_only = SpreadsheetReadOnlyError(
        spreadsheet_name=url, title=info.title, service_account_email=info.service_account_email
    )
    return GSheetAccessResult(
        status=GSheetAccessStatus.READ_ONLY,
        url=url,
        checked_at=now,
        title=info.title,
        error_code=read_only.error_code,
        error_params=read_only.error_params,
        missing_selection_tabs=missing_selection,
        missing_replacement_tabs=missing_replacement,
        tab_suggestions=suggestions,
    )


_STATUS_FOR_ERROR: dict[type[Exception], GSheetAccessStatus] = {
    SpreadsheetNotSharedError: GSheetAccessStatus.NOT_SHARED,
    SpreadsheetNotFoundError: GSheetAccessStatus.NOT_FOUND,
    NotNativeGoogleSheetError: GSheetAccessStatus.NOT_NATIVE,
}


def _missing_tabs(configured: Iterable[str], tab_titles: list[str]) -> tuple[str, ...]:
    return tuple(name for name in configured if name and name not in tab_titles)


def _near_misses(missing: Iterable[str], tab_titles: list[str]) -> dict[str, str]:
    """Map each missing name to a real tab that differs only in case or surrounding spaces."""
    suggestions: dict[str, str] = {}
    for name in missing:
        for title in tab_titles:
            if title.strip().casefold() == name.strip().casefold():
                suggestions[name] = title
                break
    return suggestions


def _get_redis() -> Redis:
    return RedisCfg.from_env().create_client()


def _key(assembly_id: uuid.UUID) -> str:
    return f"{_KEY_PREFIX}{assembly_id}"


def store_cached_result(assembly_id: uuid.UUID, result: GSheetAccessResult, redis_client: Redis | None = None) -> None:
    """Remember a result for passing page views. Transient results are not stored."""
    if result.is_transient:
        return
    try:
        r = redis_client or _get_redis()
        r.set(_key(assembly_id), result.to_json(), ex=CACHE_TTL_SECONDS)
    except redis.exceptions.RedisError as error:
        logger.warning("Could not cache Google Sheets access check", assembly_id=str(assembly_id), error=str(error))


def fetch_cached_result(
    assembly_id: uuid.UUID, url: str, redis_client: Redis | None = None
) -> GSheetAccessResult | None:
    """The cached result for this assembly, or None if there is none for `url`."""
    try:
        r = redis_client or _get_redis()
        raw: bytes | str | None = r.get(_key(assembly_id))
    except redis.exceptions.RedisError as error:
        logger.warning(
            "Could not read cached Google Sheets access check", assembly_id=str(assembly_id), error=str(error)
        )
        return None
    if raw is None:
        return None
    result = GSheetAccessResult.from_json(raw)
    return result if result.url == url else None


def forget_cached_result(assembly_id: uuid.UUID, redis_client: Redis | None = None) -> None:
    """Drop the cached result, so a stale answer for an old URL is never shown."""
    try:
        r = redis_client or _get_redis()
        r.delete(_key(assembly_id))
    except redis.exceptions.RedisError as error:
        logger.warning(
            "Could not drop cached Google Sheets access check", assembly_id=str(assembly_id), error=str(error)
        )
