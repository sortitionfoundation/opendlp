"""ABOUTME: Tests that the test database engine fails fast on lock contention
ABOUTME: A leaked session holding locks must not be able to hang the whole pytest run"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


class TestTestDatabaseLockTimeout:
    """The test engine must never wait indefinitely for a lock.

    A session leaked by the code under test sits ``idle in transaction`` holding
    locks. Teardown then runs ``DROP TABLE``, which needs a conflicting lock, and
    without a timeout pytest hangs forever with no output and no failing test.
    """

    def test_engine_configures_a_lock_timeout(self, postgres_engine):
        with postgres_engine.connect() as conn:
            lock_timeout = conn.execute(text("SHOW lock_timeout")).scalar()

        # "0" is PostgreSQL's "wait forever", which is what caused the hang.
        assert lock_timeout != "0"

    @pytest.mark.usefixtures("_postgres_tables")
    def test_conflicting_lock_raises_instead_of_waiting(self, postgres_engine):
        with postgres_engine.connect() as holder, postgres_engine.connect() as waiter:
            # Leaves an open transaction holding AccessShareLock on users,
            # exactly as a session leaked by a route does.
            holder.execute(text("SELECT 1 FROM users LIMIT 1"))

            # Shortened so the test does not sit out the real timeout.
            waiter.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(OperationalError):
                waiter.execute(text("LOCK TABLE users IN ACCESS EXCLUSIVE MODE"))
