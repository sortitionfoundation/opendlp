"""ABOUTME: Unit tests for the data source choices an Assembly records.
ABOUTME: Covers the defaults, the labels, clearing the sub-choices, and the detached copy."""

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import (
    DataSource,
    RespondentsSource,
    TargetsSource,
    data_source_labels,
    respondents_source_labels,
    targets_source_labels,
)


class TestDataSourceChoices:
    def test_a_new_assembly_has_made_no_choice(self):
        """Nothing is assumed for a project nobody has answered for."""
        assembly = Assembly(title="Fresh")

        assert assembly.data_source == DataSource.UNDECIDED
        assert assembly.targets_source == TargetsSource.UNDECIDED
        assert assembly.respondents_source == RespondentsSource.UNDECIDED

    def test_choices_can_be_given_at_creation(self):
        assembly = Assembly(
            title="Chosen",
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.CSV,
            respondents_source=RespondentsSource.REGISTRATION,
        )

        assert assembly.data_source == DataSource.OPENDLP
        assert assembly.targets_source == TargetsSource.CSV
        assert assembly.respondents_source == RespondentsSource.REGISTRATION

    def test_set_data_sources_leaves_unnamed_choices_alone(self):
        """None means "not answering this one", so a lone upload can set just its own choice."""
        assembly = Assembly(title="Partial", data_source=DataSource.OPENDLP, targets_source=TargetsSource.MANUAL)

        assembly.set_data_sources(respondents_source=RespondentsSource.CSV)

        assert assembly.data_source == DataSource.OPENDLP
        assert assembly.targets_source == TargetsSource.MANUAL
        assert assembly.respondents_source == RespondentsSource.CSV

    def test_moving_to_google_sheets_clears_the_sub_choices(self):
        """The targets and respondents choices only mean something inside OpenDLP."""
        assembly = Assembly(
            title="Switching",
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.CSV,
            respondents_source=RespondentsSource.CSV,
        )

        assembly.set_data_sources(data_source=DataSource.GSHEET)

        assert assembly.targets_source == TargetsSource.UNDECIDED
        assert assembly.respondents_source == RespondentsSource.UNDECIDED

    def test_google_sheets_refuses_sub_choices_given_with_it(self):
        assembly = Assembly(title="Sheet", data_source=DataSource.GSHEET, targets_source=TargetsSource.CSV)

        assert assembly.targets_source == TargetsSource.UNDECIDED

    def test_set_data_sources_touches_updated_at(self):
        assembly = Assembly(title="Stamped")
        before = assembly.updated_at

        assembly.set_data_sources(data_source=DataSource.OPENDLP)

        assert assembly.updated_at >= before

    def test_detached_copy_keeps_the_choices(self):
        """create_detached_copy is a hand-written field list, so a new field can be silently dropped."""
        assembly = Assembly(
            title="Copied",
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.MANUAL,
            respondents_source=RespondentsSource.CSV,
        )

        copy = assembly.create_detached_copy()

        assert copy.data_source == DataSource.OPENDLP
        assert copy.targets_source == TargetsSource.MANUAL
        assert copy.respondents_source == RespondentsSource.CSV


class TestDataSourceLabels:
    def test_every_location_that_can_be_chosen_has_a_label(self):
        assert set(data_source_labels) == {DataSource.OPENDLP, DataSource.GSHEET}

    def test_every_targets_choice_has_a_label(self):
        """Including the undecided one, which the dropdown shows as "Decide later"."""
        assert set(targets_source_labels) == set(TargetsSource)

    def test_every_respondents_choice_has_a_label(self):
        assert set(respondents_source_labels) == set(RespondentsSource)
