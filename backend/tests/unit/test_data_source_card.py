"""ABOUTME: Unit tests for what the Data source card says about a project's targets and respondents.
ABOUTME: One test for each row of the table in the 1024 project details plan."""

import pytest
from flask import Flask

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import DataSource, RespondentsSource, TargetsSource
from opendlp.entrypoints.data_source_card import SourceRow, respondents_row, targets_row


@pytest.fixture(autouse=True)
def request_context():
    """The count tags are plural-aware translations, which need a request to pick a locale from."""
    app = Flask(__name__)
    with app.test_request_context("/"):
        yield


def _assembly(targets: TargetsSource = TargetsSource.UNDECIDED, respondents=RespondentsSource.UNDECIDED) -> Assembly:
    return Assembly(
        title="Card", data_source=DataSource.OPENDLP, targets_source=targets, respondents_source=respondents
    )


class TestTargetsRow:
    def test_imported_targets_say_uploaded(self):
        assert targets_row(_assembly(TargetsSource.CSV), 4) == SourceRow("Import from CSV", "4 targets uploaded")

    def test_one_imported_target_is_singular(self):
        assert targets_row(_assembly(TargetsSource.CSV), 1).count_tag == "1 target uploaded"

    def test_targets_made_in_opendlp_are_counted_but_not_uploaded(self):
        assert targets_row(_assembly(TargetsSource.MANUAL), 4) == SourceRow("Create inside OpenDLP", "4 targets")

    def test_a_choice_with_no_targets_yet_has_no_tag(self):
        assert targets_row(_assembly(TargetsSource.CSV), 0) == SourceRow("Import from CSV", "")

    def test_no_choice_and_no_targets_reads_decide_later(self):
        assert targets_row(_assembly(), 0) == SourceRow("Decide later", "")

    def test_targets_with_no_stored_choice_show_the_count_alone(self):
        """Every project older than the stored choice: "Decide later" beside 4 targets would contradict itself."""
        assert targets_row(_assembly(), 4) == SourceRow("", "4 targets")


class TestRespondentsRow:
    def test_imported_respondents_say_uploaded(self):
        row = respondents_row(_assembly(respondents=RespondentsSource.CSV), 100)

        assert row == SourceRow("Import from CSV", "100 respondents uploaded")

    def test_one_imported_respondent_is_singular(self):
        assert respondents_row(_assembly(respondents=RespondentsSource.CSV), 1).count_tag == "1 respondent uploaded"

    def test_registered_respondents_are_counted_but_not_uploaded(self):
        row = respondents_row(_assembly(respondents=RespondentsSource.REGISTRATION), 12)

        assert row == SourceRow("Through OpenDLP registration", "12 respondents")

    def test_a_choice_with_no_respondents_yet_has_no_tag(self):
        row = respondents_row(_assembly(respondents=RespondentsSource.REGISTRATION), 0)

        assert row == SourceRow("Through OpenDLP registration", "")

    def test_no_choice_and_no_respondents_reads_decide_later(self):
        assert respondents_row(_assembly(), 0) == SourceRow("Decide later", "")

    def test_respondents_with_no_stored_choice_show_the_count_alone(self):
        assert respondents_row(_assembly(), 100) == SourceRow("", "100 respondents")
