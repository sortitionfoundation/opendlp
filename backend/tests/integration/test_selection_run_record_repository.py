"""ABOUTME: Integration tests for the per-assembly advisory lock behind the writing guard.
ABOUTME: Checks against Postgres that the lock excludes a second session until commit or rollback."""

import uuid

from sqlalchemy import text

from opendlp.bootstrap import bootstrap


def _other_session_can_lock(session_factory, assembly_id: uuid.UUID) -> bool:
    """Whether a fresh session can take the assembly lock right now, without waiting.

    Uses the non-blocking form of the same advisory lock, and rolls the probe
    back so it leaves nothing held.
    """
    session = session_factory()
    try:
        taken = session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": str(assembly_id)}
        ).scalar_one()
        session.rollback()
        return bool(taken)
    finally:
        session.close()


class TestLockAssemblyForWrite:
    def test_lock_excludes_another_session_until_commit(self, postgres_session_factory):
        """While one unit of work holds the lock a second session cannot take it; after commit it can."""
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            assert not _other_session_can_lock(postgres_session_factory, assembly_id)
            uow.commit()
            assert _other_session_can_lock(postgres_session_factory, assembly_id)

    def test_lock_is_released_at_rollback(self, postgres_session_factory):
        """A refused start rolls back, and that must release the lock too."""
        assembly_id = uuid.uuid4()
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(assembly_id)
            assert not _other_session_can_lock(postgres_session_factory, assembly_id)
            uow.rollback()
            assert _other_session_can_lock(postgres_session_factory, assembly_id)

    def test_lock_is_per_assembly(self, postgres_session_factory):
        """Holding one assembly's lock does not stop a task on another assembly."""
        with bootstrap(session_factory=postgres_session_factory) as uow:
            uow.lock_assembly_for_write(uuid.uuid4())
            assert _other_session_can_lock(postgres_session_factory, uuid.uuid4())
            uow.commit()
