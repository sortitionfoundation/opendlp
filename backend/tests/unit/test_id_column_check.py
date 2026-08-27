"""ABOUTME: Unit tests for check_id_column_in_headers
ABOUTME: Tests the error naming the CSV's own columns when the id column is missing"""

import pytest

from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.respondent_field_schema_service import (
    MAX_LISTED_HEADERS,
    check_id_column_in_headers,
)


class TestCheckIdColumnInHeaders:
    def test_passes_when_id_column_present(self):
        check_id_column_in_headers("external_id", ["external_id", "first_name"])

    def test_names_the_missing_column(self):
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("nationbuilder_id", ["id", "first_name"])

        assert 'no column called "nationbuilder_id"' in str(exc_info.value)

    def test_lists_the_columns_the_csv_does_have(self):
        """The whole point: the organiser can fix the field without opening the file."""
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("nationbuilder_id", ["id", "first_name", "email"])

        message = str(exc_info.value)
        assert "id, first_name, email" in message

    def test_points_at_the_first_column_as_the_blank_fallback(self):
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("nationbuilder_id", ["person_ref", "first_name"])

        assert 'clear it to use the first column ("person_ref")' in str(exc_info.value)

    def test_caps_the_listed_columns(self):
        """A respondent export can be dozens of columns wide; a flash message can't."""
        headers = [f"col{i}" for i in range(MAX_LISTED_HEADERS + 5)]

        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("missing", headers)

        message = str(exc_info.value)
        assert f"col{MAX_LISTED_HEADERS - 1}" in message
        assert f"col{MAX_LISTED_HEADERS}" not in message
        assert "and 5 more" in message

    def test_no_cap_note_when_exactly_at_the_limit(self):
        headers = [f"col{i}" for i in range(MAX_LISTED_HEADERS)]

        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("missing", headers)

        message = str(exc_info.value)
        assert "more" not in message
        assert f"col{MAX_LISTED_HEADERS - 1}" in message

    def test_explains_the_prefill_when_the_value_is_last_uploads(self):
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers(
                "nationbuilder_id",
                ["id", "first_name"],
                previous_id_column="nationbuilder_id",
            )

        assert "pre-filled from your last upload" in str(exc_info.value)

    def test_no_prefill_note_when_the_value_was_typed(self):
        """A value that differs from last time came from the organiser, not the form."""
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers(
                "typo_id",
                ["id", "first_name"],
                previous_id_column="nationbuilder_id",
            )

        assert "pre-filled" not in str(exc_info.value)

    def test_no_prefill_note_when_there_was_no_previous_upload(self):
        with pytest.raises(InvalidSelection) as exc_info:
            check_id_column_in_headers("nationbuilder_id", ["id", "first_name"])

        assert "pre-filled" not in str(exc_info.value)
