"""ABOUTME: Unit tests for selection run history repository methods
ABOUTME: Tests paginated queries and user joins for SelectionRunRecord"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from opendlp.adapters.sql_repository import SqlAlchemySelectionRunRecordRepository
from opendlp.domain.assembly import SelectionRunRecord
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, SelectionRunStatus, SelectionTaskType


@pytest.fixture
def session(sqlite_session_factory):
    """Create a test database session."""
    session = sqlite_session_factory()
    yield session
    session.close()


def test_get_by_assembly_id_paginated_returns_records_with_users(session):
    """Test that paginated query returns records with user information."""
    # Create users
    user1 = User(
        user_id=uuid4(),
        email="user1@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash1",  # pragma: allowlist secret
        first_name="User",
        last_name="One",
    )
    user2 = User(
        user_id=uuid4(),
        email="user2@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash2",  # pragma: allowlist secret
        first_name="User",
        last_name="Two",
    )
    session.add(user1)
    session.add(user2)
    session.commit()

    # Create assembly
    assembly_id = uuid4()

    # Create run records with different timestamps
    now = datetime.now(UTC)
    records = []
    for i in range(5):
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            celery_task_id=f"celery-{i}",
            user_id=user1.id if i % 2 == 0 else user2.id,
            created_at=now - timedelta(minutes=i),
            completed_at=now - timedelta(minutes=i - 1),
        )
        records.append(record)
        session.add(record)
    session.commit()

    # Test paginated query
    repo = SqlAlchemySelectionRunRecordRepository(session)
    result, total_count = repo.get_by_assembly_id_paginated(assembly_id, page=1, per_page=50)

    # Verify total count
    assert total_count == 5

    # Verify we got all records
    assert len(result) == 5

    # Verify records have users
    for run_record, user in result:
        assert run_record is not None
        assert user is not None
        assert user.id in (user1.id, user2.id)

    # Verify ordering (newest first)
    assert result[0][0].task_id == records[0].task_id
    assert result[4][0].task_id == records[4].task_id


def test_get_by_assembly_id_paginated_pagination_works(session):
    """Test that pagination logic works correctly."""
    user = User(
        user_id=uuid4(),
        email="user@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash",  # pragma: allowlist secret
    )
    session.add(user)
    session.commit()

    assembly_id = uuid4()
    now = datetime.now(UTC)

    # Create 75 run records
    for i in range(75):
        record = SelectionRunRecord(
            assembly_id=assembly_id,
            task_id=uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.LOAD_GSHEET,
            celery_task_id=f"celery-{i}",
            user_id=user.id,
            created_at=now - timedelta(minutes=i),
        )
        session.add(record)
    session.commit()

    repo = SqlAlchemySelectionRunRecordRepository(session)

    # Test page 1
    page1_results, total_count = repo.get_by_assembly_id_paginated(assembly_id, page=1, per_page=50)
    assert total_count == 75
    assert len(page1_results) == 50

    # Test page 2
    page2_results, total_count = repo.get_by_assembly_id_paginated(assembly_id, page=2, per_page=50)
    assert total_count == 75
    assert len(page2_results) == 25

    # Verify no overlap between pages
    page1_ids = {record.task_id for record, _ in page1_results}
    page2_ids = {record.task_id for record, _ in page2_results}
    assert len(page1_ids & page2_ids) == 0


def test_get_by_assembly_id_paginated_handles_null_user_id(session):
    """Test that records with null user_id return None for user."""
    assembly_id = uuid4()

    # Create run record with null user_id
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid4(),
        status=SelectionRunStatus.COMPLETED,
        task_type=SelectionTaskType.SELECT_GSHEET,
        celery_task_id="celery-123",
        user_id=None,  # No user
        created_at=datetime.now(UTC),
    )
    session.add(record)
    session.commit()

    repo = SqlAlchemySelectionRunRecordRepository(session)
    result, total_count = repo.get_by_assembly_id_paginated(assembly_id)

    assert total_count == 1
    assert len(result) == 1

    run_record, user = result[0]
    assert run_record is not None
    assert user is None


def test_get_by_assembly_id_paginated_handles_deleted_user(session):
    """Test that records with deleted users return None for user."""
    # Create user
    user = User(
        user_id=uuid4(),
        email="user@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash",  # pragma: allowlist secret
    )
    session.add(user)
    session.commit()

    assembly_id = uuid4()

    # Create run record
    record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid4(),
        status=SelectionRunStatus.COMPLETED,
        task_type=SelectionTaskType.SELECT_GSHEET,
        celery_task_id="celery-123",
        user_id=user.id,
        created_at=datetime.now(UTC),
    )
    session.add(record)
    session.commit()

    # Delete the user
    session.delete(user)
    session.commit()

    # Query should still work with user as None
    repo = SqlAlchemySelectionRunRecordRepository(session)
    result, total_count = repo.get_by_assembly_id_paginated(assembly_id)

    assert total_count == 1
    assert len(result) == 1

    run_record, user = result[0]
    assert run_record is not None
    assert user is None


def test_get_by_assembly_id_paginated_ordering_newest_first(session):
    """Test that records are ordered by created_at descending (newest first)."""
    user = User(
        user_id=uuid4(),
        email="user@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash",  # pragma: allowlist secret
    )
    session.add(user)
    session.commit()

    assembly_id = uuid4()
    now = datetime.now(UTC)

    # Create records with specific timestamps
    oldest_record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid4(),
        status=SelectionRunStatus.COMPLETED,
        task_type=SelectionTaskType.SELECT_GSHEET,
        celery_task_id="old",
        user_id=user.id,
        created_at=now - timedelta(hours=3),
    )
    middle_record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid4(),
        status=SelectionRunStatus.COMPLETED,
        task_type=SelectionTaskType.LOAD_GSHEET,
        celery_task_id="middle",
        user_id=user.id,
        created_at=now - timedelta(hours=2),
    )
    newest_record = SelectionRunRecord(
        assembly_id=assembly_id,
        task_id=uuid4(),
        status=SelectionRunStatus.RUNNING,
        task_type=SelectionTaskType.SELECT_GSHEET,
        celery_task_id="new",
        user_id=user.id,
        created_at=now - timedelta(hours=1),
    )

    session.add(oldest_record)
    session.add(middle_record)
    session.add(newest_record)
    session.commit()

    repo = SqlAlchemySelectionRunRecordRepository(session)
    result, total_count = repo.get_by_assembly_id_paginated(assembly_id)

    assert total_count == 3
    assert len(result) == 3

    # Verify ordering
    assert result[0][0].task_id == newest_record.task_id
    assert result[1][0].task_id == middle_record.task_id
    assert result[2][0].task_id == oldest_record.task_id


def test_get_by_assembly_id_paginated_filters_by_assembly(session):
    """Test that only records for the specified assembly are returned."""
    user = User(
        user_id=uuid4(),
        email="user@example.com",
        global_role=GlobalRole.USER,
        is_active=True,
        password_hash="hash",  # pragma: allowlist secret
    )
    session.add(user)
    session.commit()

    assembly1_id = uuid4()
    assembly2_id = uuid4()

    # Create records for assembly 1
    for i in range(3):
        record = SelectionRunRecord(
            assembly_id=assembly1_id,
            task_id=uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            celery_task_id=f"a1-{i}",
            user_id=user.id,
            created_at=datetime.now(UTC),
        )
        session.add(record)

    # Create records for assembly 2
    for i in range(2):
        record = SelectionRunRecord(
            assembly_id=assembly2_id,
            task_id=uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_GSHEET,
            celery_task_id=f"a2-{i}",
            user_id=user.id,
            created_at=datetime.now(UTC),
        )
        session.add(record)

    session.commit()

    repo = SqlAlchemySelectionRunRecordRepository(session)

    # Query assembly 1
    result1, total1 = repo.get_by_assembly_id_paginated(assembly1_id)
    assert total1 == 3
    assert len(result1) == 3
    for run_record, _ in result1:
        assert run_record.assembly_id == assembly1_id

    # Query assembly 2
    result2, total2 = repo.get_by_assembly_id_paginated(assembly2_id)
    assert total2 == 2
    assert len(result2) == 2
    for run_record, _ in result2:
        assert run_record.assembly_id == assembly2_id
