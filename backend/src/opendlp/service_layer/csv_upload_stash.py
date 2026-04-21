"""ABOUTME: Redis-backed temporary stash for pending respondent CSV uploads.
ABOUTME: Holds the raw CSV between the upload-begin and upload-confirm-diff steps."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass

from redis import Redis

from opendlp.config import RedisCfg

_KEY_PREFIX = "csv_import_pending:"
# TTL for a stashed upload — generous enough that an organiser can read the
# diff page, take a coffee break, and still confirm; short enough that
# abandoned uploads don't accumulate.
_DEFAULT_TTL_SECONDS = 30 * 60


@dataclass
class StashedUpload:
    """A CSV blob plus the metadata needed to resume the upload after a diff page."""

    csv_content: str
    filename: str
    id_column: str | None
    replace_existing: bool


def _get_redis() -> Redis:
    cfg = RedisCfg.from_env()
    # decode_responses=False because csv_content is opaque text we round-trip via JSON.
    return Redis(host=cfg.host, port=cfg.port, db=cfg.db)


def _key(user_id: uuid.UUID, assembly_id: uuid.UUID) -> str:
    return f"{_KEY_PREFIX}{user_id}:{assembly_id}"


def stash(
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    upload: StashedUpload,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    redis_client: Redis | None = None,
) -> None:
    """Stash a pending upload under (user_id, assembly_id) with a TTL."""
    r = redis_client or _get_redis()
    payload = json.dumps(asdict(upload))
    r.set(_key(user_id, assembly_id), payload, ex=ttl_seconds)


def fetch(
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    redis_client: Redis | None = None,
) -> StashedUpload | None:
    """Read a stashed upload, or None if expired / missing."""
    r = redis_client or _get_redis()
    raw: bytes | str | None = r.get(_key(user_id, assembly_id))  # type: ignore[assignment]
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    return StashedUpload(**data)


def clear(
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    redis_client: Redis | None = None,
) -> None:
    """Delete any stashed upload. No-op if nothing was stashed."""
    r = redis_client or _get_redis()
    r.delete(_key(user_id, assembly_id))
