"""ABOUTME: Unit tests for Assembly domain model
ABOUTME: Tests assembly creation, validation, status changes, and updates"""

import uuid
from datetime import date, datetime, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyStatus


class TestAssembly:
    def test_create_assembly(self):
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Climate Assembly",
            question="How should we address climate change?",
            gsheet="https://docs.google.com/spreadsheets/d/abc123",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Climate Assembly"
        assert assembly.question == "How should we address climate change?"
        assert assembly.gsheet == "https://docs.google.com/spreadsheets/d/abc123"
        assert assembly.first_assembly_date == future_date
        assert assembly.status == AssemblyStatus.ACTIVE
        assert isinstance(assembly.id, uuid.UUID)
        assert isinstance(assembly.created_at, datetime)
        assert isinstance(assembly.updated_at, datetime)

    def test_create_assembly_with_only_title(self):
        """Test creating assembly with only required title field."""
        assembly = Assembly(title="Minimal Assembly")

        assert assembly.title == "Minimal Assembly"
        assert assembly.question == ""
        assert assembly.gsheet == ""
        assert assembly.first_assembly_date is None
        assert assembly.status == AssemblyStatus.ACTIVE
        assert isinstance(assembly.id, uuid.UUID)
        assert isinstance(assembly.created_at, datetime)
        assert isinstance(assembly.updated_at, datetime)

    def test_create_assembly_with_custom_values(self):
        future_date = date.today() + timedelta(days=30)
        assembly_id = uuid.uuid4()
        created_time = datetime(2023, 1, 1, 10, 0, 0)

        assembly = Assembly(
            assembly_id=assembly_id,
            title="Custom Assembly",
            question="Custom question?",
            gsheet="custom-sheet",
            first_assembly_date=future_date,
            status=AssemblyStatus.ARCHIVED,
            created_at=created_time,
            updated_at=created_time,
        )

        assert assembly.id == assembly_id
        assert assembly.status == AssemblyStatus.ARCHIVED
        assert assembly.created_at == created_time
        assert assembly.updated_at == created_time

    def test_create_assembly_strips_whitespace(self):
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="  Spaced Title  ",
            question="  Spaced Question?  ",
            gsheet="  spaced-sheet  ",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Spaced Title"
        assert assembly.question == "Spaced Question?"
        assert assembly.gsheet == "spaced-sheet"

    def test_validate_required_fields(self):
        # Only title is required, empty title should fail
        with pytest.raises(ValueError, match="Assembly title is required"):
            Assembly(title="")

        with pytest.raises(ValueError, match="Assembly title is required"):
            Assembly(title="   ")

        # Empty question and gsheet should be allowed now
        assembly = Assembly(title="Valid Title", question="", gsheet="")
        assert assembly.title == "Valid Title"
        assert assembly.question == ""
        assert assembly.gsheet == ""

    def test_validate_future_date(self):
        past_date = date.today() - timedelta(days=1)
        today = date.today()
        future_date = date.today() + timedelta(days=1)

        # Past date should fail
        with pytest.raises(ValueError, match="First assembly date must be in the future"):
            Assembly(title="Title", first_assembly_date=past_date)

        # Today should fail
        with pytest.raises(ValueError, match="First assembly date must be in the future"):
            Assembly(title="Title", first_assembly_date=today)

        # Future date should work
        assembly = Assembly(title="Title", first_assembly_date=future_date)
        assert assembly.first_assembly_date == future_date

        # None date should work
        assembly_no_date = Assembly(title="Title", first_assembly_date=None)
        assert assembly_no_date.first_assembly_date is None

    def test_archive(self):
        assembly = Assembly(title="Title")

        original_updated_at = assembly.updated_at

        # Small delay to ensure updated_at changes
        import time

        time.sleep(0.01)

        assembly.archive()

        assert assembly.status == AssemblyStatus.ARCHIVED
        assert assembly.updated_at > original_updated_at

    def test_reactivate(self):
        assembly = Assembly(
            title="Title",
            status=AssemblyStatus.ARCHIVED,
        )

        original_updated_at = assembly.updated_at

        # Small delay to ensure updated_at changes
        import time

        time.sleep(0.01)

        assembly.reactivate()

        assert assembly.status == AssemblyStatus.ACTIVE
        assert assembly.updated_at > original_updated_at

    def test_is_active(self):
        active_assembly = Assembly(
            title="Active",
            status=AssemblyStatus.ACTIVE,
        )

        archived_assembly = Assembly(
            title="Archived",
            status=AssemblyStatus.ARCHIVED,
        )

        assert active_assembly.is_active() is True
        assert archived_assembly.is_active() is False

    def test_update_details(self):
        future_date = date.today() + timedelta(days=30)
        new_future_date = date.today() + timedelta(days=60)

        assembly = Assembly(
            title="Original Title",
            question="Original question?",
            gsheet="original-sheet",
            first_assembly_date=future_date,
        )

        original_updated_at = assembly.updated_at

        # Small delay to ensure updated_at changes
        import time

        time.sleep(0.01)

        assembly.update_details(
            title="Updated Title",
            question="Updated question?",
            gsheet="updated-sheet",
            first_assembly_date=new_future_date,
        )

        assert assembly.title == "Updated Title"
        assert assembly.question == "Updated question?"
        assert assembly.gsheet == "updated-sheet"
        assert assembly.first_assembly_date == new_future_date
        assert assembly.updated_at > original_updated_at

    def test_update_details_partial(self):
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Original Title",
            question="Original question?",
            gsheet="original-sheet",
            first_assembly_date=future_date,
        )

        # Update only title
        assembly.update_details(title="New Title")

        assert assembly.title == "New Title"
        assert assembly.question == "Original question?"  # Unchanged
        assert assembly.gsheet == "original-sheet"  # Unchanged
        assert assembly.first_assembly_date == future_date  # Unchanged

    def test_update_details_strips_whitespace(self):
        assembly = Assembly(title="Original", question="Original?", gsheet="original")

        assembly.update_details(title="  New Title  ", question="  New question?  ", gsheet="  new-sheet  ")

        assert assembly.title == "New Title"
        assert assembly.question == "New question?"
        assert assembly.gsheet == "new-sheet"

    def test_update_details_validation(self):
        past_date = date.today() - timedelta(days=1)

        assembly = Assembly(title="Title")

        # Empty title should still fail
        with pytest.raises(ValueError, match="Assembly title cannot be empty"):
            assembly.update_details(title="")

        # Empty question and gsheet should be allowed now
        assembly.update_details(question="", gsheet="")
        assert assembly.question == ""
        assert assembly.gsheet == ""

        # Past date should still fail
        with pytest.raises(ValueError, match="First assembly date must be in the future"):
            assembly.update_details(first_assembly_date=past_date)

    def test_assembly_equality_and_hash(self):
        assembly_id = uuid.uuid4()
        future_date = date.today() + timedelta(days=30)

        assembly1 = Assembly(
            assembly_id=assembly_id,
            title="Assembly 1",
            question="Question 1?",
            gsheet="sheet1",
            first_assembly_date=future_date,
        )

        assembly2 = Assembly(
            assembly_id=assembly_id,
            title="Assembly 2",  # Different title but same ID
            question="Question 2?",
            gsheet="sheet2",
            first_assembly_date=future_date,
        )

        assembly3 = Assembly(title="Assembly 3")

        assert assembly1 == assembly2  # Same ID
        assert assembly1 != assembly3  # Different ID
        assert hash(assembly1) == hash(assembly2)
        assert hash(assembly1) != hash(assembly3)
