"""ABOUTME: DatabaseProgressReporter persists sortition-algorithms progress events to SelectionRunRecord.
ABOUTME: Throttles writes to once per min_interval_seconds; phase transitions always force-flush."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from opendlp.bootstrap import bootstrap


class DatabaseProgressReporter:
    def __init__(
        self,
        task_id: uuid.UUID,
        *,
        session_factory: sessionmaker | None = None,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self._task_id = task_id
        self._session_factory = session_factory
        self._min_interval = min_interval_seconds
        self._last_write = 0.0
        self._phase_name = ""
        self._phase_total: int | None = None

    def start_phase(self, name: str, total: int | None = None, *, message: str | None = None) -> None:
        self._phase_name = name
        self._phase_total = total
        self._write(current=0, force=True)

    def update(self, current: int, *, message: str | None = None) -> None:
        self._write(current=current, force=False)

    def end_phase(self) -> None:
        pass

    def _write(self, *, current: int, force: bool) -> None:
        now = time.monotonic()
        if not force and (now - self._last_write) < self._min_interval:
            return
        self._last_write = now

        payload: dict[str, Any] = {
            "phase": self._phase_name,
            "current": current,
            "total": self._phase_total,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        with bootstrap(session_factory=self._session_factory) as uow:
            record = uow.selection_run_records.get_by_task_id(self._task_id)
            if record is None:
                return
            record.progress = payload
            if hasattr(record, "_sa_instance_state"):
                flag_modified(record, "progress")
            uow.commit()
