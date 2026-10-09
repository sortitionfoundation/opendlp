"""ABOUTME: Integration tests for the per-assembly advisory lock behind the writing guard.
ABOUTME: Checks against Postgres that the lock is released when the unit of work commits."""

import uuid

from opendlp.bootstrap import bootstrap


class TestLockAssemblyForWrite:
    def test_lock_is_released_at_commit(self, postgres_session_factory):
        """A second unit of work can take the lock once the first has committed."""
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            uow.commit()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            uow.commit()
