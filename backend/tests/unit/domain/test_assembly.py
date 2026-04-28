"""ABOUTME: Unit tests for Assembly domain model
ABOUTME: Tests assembly creation, validation, status changes, and updates"""

import time
import uuid
from datetime import date, datetime, timedelta

import pytest

from opendlp.domain.assembly import Assembly, SelectionRunRecord
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import AssemblyStatus, SelectionRunStatus, SelectionTaskType


class TestAssembly:
    def test_create_assembly(self):
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Climate Assembly",
            question="How should we address climate change?",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Climate Assembly"
        assert assembly.question == "How should we address climate change?"
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
        assert assembly.first_assembly_date is None
        assert assembly.number_to_select == 0
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
            first_assembly_date=future_date,
        )

        assert assembly.title == "Spaced Title"
        assert assembly.question == "Spaced Question?"

    def test_validate_required_fields(self):
        # Only title is required, empty title should fail
        with pytest.raises(ValueError, match="Assembly title is required"):
            Assembly(title="")

        with pytest.raises(ValueError, match="Assembly title is required"):
            Assembly(title="   ")

        # Empty question should be allowed now
        assembly = Assembly(title="Valid Title", question="")
        assert assembly.title == "Valid Title"
        assert assembly.question == ""

    def test_archive(self):
        assembly = Assembly(title="Title")

        original_updated_at = assembly.updated_at

        # Small delay to ensure updated_at changes
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
            first_assembly_date=future_date,
            number_to_select=50,
        )

        original_updated_at = assembly.updated_at

        # Small delay to ensure updated_at changes
        time.sleep(0.01)

        assembly.update_details(
            title="Updated Title",
            question="Updated question?",
            first_assembly_date=new_future_date,
            number_to_select=100,
        )

        assert assembly.title == "Updated Title"
        assert assembly.question == "Updated question?"
        assert assembly.first_assembly_date == new_future_date
        assert assembly.number_to_select == 100
        assert assembly.updated_at > original_updated_at

    def test_update_details_partial(self):
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Original Title",
            question="Original question?",
            first_assembly_date=future_date,
        )

        # Update only title
        assembly.update_details(title="New Title")

        assert assembly.title == "New Title"
        assert assembly.question == "Original question?"  # Unchanged
        assert assembly.first_assembly_date == future_date  # Unchanged

    def test_update_details_strips_whitespace(self):
        assembly = Assembly(title="Original", question="Original?")

        assembly.update_details(
            title="  New Title  ",
            question="  New question?  ",
        )

        assert assembly.title == "New Title"
        assert assembly.question == "New question?"

    def test_update_details_validation(self):
        assembly = Assembly(title="Title")

        # Empty title should still fail
        with pytest.raises(ValueError, match="Assembly title cannot be empty"):
            assembly.update_details(title="")

        # Empty question should be allowed now
        assembly.update_details(question="")
        assert assembly.question == ""

        # Negative number_to_select should fail
        with pytest.raises(ValueError, match="Number to select cannot be negative"):
            assembly.update_details(number_to_select=-1)

    def test_assembly_equality_and_hash(self):
        assembly_id = uuid.uuid4()
        future_date = date.today() + timedelta(days=30)

        assembly1 = Assembly(
            assembly_id=assembly_id,
            title="Assembly 1",
            question="Question 1?",
            first_assembly_date=future_date,
        )

        assembly2 = Assembly(
            assembly_id=assembly_id,
            title="Assembly 2",  # Different title but same ID
            question="Question 2?",
            first_assembly_date=future_date,
        )

        assembly3 = Assembly(title="Assembly 3")

        assert assembly1 == assembly2  # Same ID
        assert assembly1 != assembly3  # Different ID
        assert hash(assembly1) == hash(assembly2)
        assert hash(assembly1) != hash(assembly3)


class TestAssemblyNameFields:
    def _assembly_with_attrs(self, *attribute_dicts: dict[str, object]) -> Assembly:
        assembly = Assembly(title="Test Assembly")
        assembly.respondents = [
            Respondent(assembly_id=assembly.id, external_id=f"R{i:03d}", attributes=attrs)
            for i, attrs in enumerate(attribute_dicts)
        ]
        return assembly

    def test_no_respondents_returns_empty_list(self):
        assembly = Assembly(title="Empty Assembly")
        assert assembly.name_fields == []

    def test_first_name_and_last_name(self):
        assembly = self._assembly_with_attrs({"first_name": "Sarah", "last_name": "Jones", "age": "30"})
        assert assembly.name_fields == ["first_name", "last_name"]

    def test_firstname_and_surname(self):
        assembly = self._assembly_with_attrs({"firstname": "Sarah", "surname": "Jones"})
        assert assembly.name_fields == ["firstname", "surname"]

    def test_full_name_alone(self):
        assembly = self._assembly_with_attrs({"full_name": "Sarah Jones", "age": "30"})
        assert assembly.name_fields == ["full_name"]

    def test_name_alone(self):
        assembly = self._assembly_with_attrs({"name": "Sarah Jones", "age": "30"})
        assert assembly.name_fields == ["name"]

    def test_first_last_beats_full_name_and_name(self):
        assembly = self._assembly_with_attrs(
            {"first_name": "Sarah", "last_name": "Jones", "full_name": "Sarah Jones", "name": "Sarah"},
        )
        assert assembly.name_fields == ["first_name", "last_name"]

    def test_first_surname_beats_full_name(self):
        assembly = self._assembly_with_attrs(
            {"firstname": "Sarah", "surname": "Jones", "full_name": "Sarah Jones"},
        )
        assert assembly.name_fields == ["firstname", "surname"]

    def test_full_name_beats_name(self):
        assembly = self._assembly_with_attrs({"full_name": "Sarah Jones", "name": "Sarah"})
        assert assembly.name_fields == ["full_name"]

    def test_normalisation_case_and_separators(self):
        # Keys that normalise to firstname/lastname should match and be returned as-is.
        assembly = self._assembly_with_attrs({"First-Name": "Sarah", "LAST_NAME": "Jones"})
        assert assembly.name_fields == ["First-Name", "LAST_NAME"]

    def test_no_match_returns_empty(self):
        assembly = self._assembly_with_attrs({"age": "30", "gender": "F"})
        assert assembly.name_fields == []

    def test_only_uses_first_respondent(self):
        # First respondent has no name fields; later ones do — we only look at the first.
        assembly = self._assembly_with_attrs(
            {"age": "30"},
            {"first_name": "Sarah", "last_name": "Jones"},
        )
        assert assembly.name_fields == []

    def test_result_is_cached(self):
        assembly = self._assembly_with_attrs({"first_name": "Sarah", "last_name": "Jones"})
        first = assembly.name_fields
        second = assembly.name_fields
        assert first is second


class TestSelectionRunRecordTargetsUsed:
    def _record(self, **overrides) -> SelectionRunRecord:
        kwargs = {
            "assembly_id": uuid.uuid4(),
            "task_id": uuid.uuid4(),
            "status": SelectionRunStatus.PENDING,
            "task_type": SelectionTaskType.SELECT_FROM_DB,
        }
        kwargs.update(overrides)
        return SelectionRunRecord(**kwargs)

    def test_default_is_empty_list(self):
        record = self._record()
        assert record.targets_used == []

    def test_round_trip_through_create_detached_copy(self):
        snapshot = [
            {
                "name": "Gender",
                "description": "",
                "sort_order": 0,
                "values": [
                    {
                        "value": "Man",
                        "min": 1,
                        "max": 2,
                        "min_flex": 0,
                        "max_flex": -1,
                        "percentage_target": 50.0,
                        "description": "",
                    },
                ],
            },
        ]
        record = self._record(targets_used=snapshot)

        copy = record.create_detached_copy()

        assert copy.targets_used == snapshot
        assert copy.targets_used is not record.targets_used
