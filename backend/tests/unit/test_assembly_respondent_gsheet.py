# ABOUTME: Unit tests for the AssemblyRespondentGSheet domain object
# ABOUTME: Covers URL validation in __post_init__, update_values guards, and copying

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.assembly_respondent_gsheet import AssemblyRespondentGSheet

VALID_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
OTHER_VALID_URL = "https://docs.google.com/spreadsheets/d/2CyjNWt1YSB6oGNelLwceCakhVVrqumct85PhWF3vqnt/edit"


class TestPostInit:
    def test_valid_url_is_accepted(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        assert config.url == VALID_URL

    def test_empty_url_is_allowed(self) -> None:
        # The URL is only set later (once the organiser fills the form in), so an
        # empty URL must not fail validation.
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4())
        assert config.url == ""

    def test_whitespace_is_stripped_from_url(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=f"  {VALID_URL}  ")
        assert config.url == VALID_URL

    def test_invalid_url_raises_value_error(self) -> None:
        # The blueprint relies on invalid URLs raising a ValueError (wtforms
        # ValidationError is a ValueError subclass), so lock that contract in.
        with pytest.raises(ValueError):
            AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url="not-a-google-sheet")

    def test_timestamps_default_to_now(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4())
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_result_fields_default_to_empty(self) -> None:
        # spreadsheet_title and worksheet_url are populated after an export; they
        # start blank so the config can be created before any write has happened.
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4())
        assert config.spreadsheet_title == ""
        assert config.worksheet_url == ""


class TestUpdateValues:
    def test_updates_editable_fields(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        config.update_values(url=OTHER_VALID_URL, worksheet_name="New tab")
        assert config.url == OTHER_VALID_URL
        assert config.worksheet_name == "New tab"

    def test_updates_result_fields(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        config.update_values(
            spreadsheet_title="Assembly Data",
            worksheet_url="https://docs.google.com/spreadsheets/d/abc#gid=1",
        )
        assert config.spreadsheet_title == "Assembly Data"
        assert config.worksheet_url == "https://docs.google.com/spreadsheets/d/abc#gid=1"

    def test_bumps_updated_at(self) -> None:
        past = datetime(2020, 1, 1, tzinfo=UTC)
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), created_at=past, updated_at=past)
        config.update_values(worksheet_name="New tab")
        assert config.updated_at is not None
        assert config.updated_at > past
        # created_at is not touched by an update.
        assert config.created_at == past

    def test_validates_new_url(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        with pytest.raises(ValueError):
            config.update_values(url="not-a-google-sheet")

    def test_rejects_non_updatable_field(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        with pytest.raises(ValueError):
            config.update_values(assembly_id=str(uuid.uuid4()))

    def test_rejects_created_at_update(self) -> None:
        config = AssemblyRespondentGSheet(assembly_id=uuid.uuid4(), url=VALID_URL)
        with pytest.raises(ValueError):
            config.update_values(created_at="2020-01-01")


def test_create_detached_copy_is_equal() -> None:
    config = AssemblyRespondentGSheet(
        assembly_id=uuid.uuid4(),
        assembly_respondent_gsheet_id=uuid.uuid4(),
        url=VALID_URL,
        worksheet_name="Export",
    )
    copy = config.create_detached_copy()
    assert copy is not config
    assert copy == config
