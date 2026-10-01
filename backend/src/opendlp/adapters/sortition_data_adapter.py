"""ABOUTME: Data adapter for sortition-algorithms library using OpenDLP database
ABOUTME: Implements AbstractDataSource to load features/people from database instead of CSV/GSheet"""

import uuid
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from typing import Any

from sortition_algorithms.adapters import AbstractDataSource
from sortition_algorithms.errors import BadDataError, ParseTableMultiError, SelectionMultilineError
from sortition_algorithms.features import MAX_FLEX_UNSET
from sortition_algorithms.utils import RunReport

from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import SELECTED_RESPONDENT_STATUSES, RespondentStatus
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

# The header this adapter emits for the unique id of each person. Respondents in
# the database are keyed by Respondent.external_id whatever the uploaded CSV
# called its id column, so this is fixed. Anything building a
# sortition_algorithms Settings for this adapter must use it as the id_column -
# see SelectionSettings.to_settings(id_column=...).
DB_ID_COLUMN = "external_id"


class OpenDLPDataAdapter(AbstractDataSource):
    """Data adapter that reads from OpenDLP database via UnitOfWork."""

    def __init__(
        self,
        uow: AbstractUnitOfWork,
        assembly_id: uuid.UUID,
        *,
        eligible_only: bool = True,
        targets_snapshot: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Args:
          uow: The UnitOfWork for accessing data
          assembly_id: The ID of the Assembly to get data for
          eligible_only: Whether to get only eligible people. If False, we get all people.
          targets_snapshot: Feature data to use instead of the assembly's target
            categories, in the shape target_categories_to_snapshot() produces. A
            replacement selection runs on targets derived from the stored ones,
            and this is how the task is handed exactly what the run record holds.
        """
        self.uow = uow
        self.assembly_id = assembly_id
        self.eligible_only = eligible_only
        self.targets_snapshot = targets_snapshot

    @property
    def people_data_container(self) -> str:
        return "OpenDLP respondents database"

    @property
    def already_selected_data_container(self) -> str:
        return "OpenDLP already selected respondents"

    def _feature_rows(self) -> list[tuple[str, str, int, int, int, int]]:
        """(feature, value, min, max, min_flex, max_flex) for every target value."""
        if self.targets_snapshot is not None:
            return [
                (
                    category["name"],
                    value["value"],
                    value["min"],
                    value["max"],
                    value.get("min_flex", 0),
                    value.get("max_flex", MAX_FLEX_UNSET),
                )
                for category in self.targets_snapshot
                for value in category["values"]
            ]
        categories = self.uow.target_categories.get_by_assembly_id(self.assembly_id)
        return [
            (category.name, value.value, value.min, value.max, value.min_flex, value.max_flex)
            for category in categories
            for value in category.values
        ]

    @contextmanager
    def read_feature_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load target categories from database as feature data."""
        # Note: We don't add a message here as custom codes aren't supported

        feature_rows = self._feature_rows()

        # Convert to CSV-like format expected by sortition-algorithms
        # Only include flex columns if ALL values have explicit (non-default) flex set.
        # If any value has MAX_FLEX_UNSET, omit flex columns entirely and let
        # the library calculate safe defaults via set_default_max_flex().
        all_flex_set = bool(feature_rows) and all(
            min_flex != 0 or max_flex != MAX_FLEX_UNSET for _, _, _, _, min_flex, max_flex in feature_rows
        )

        if all_flex_set:
            headers = ["feature", "value", "min", "max", "min_flex", "max_flex"]
        else:
            headers = ["feature", "value", "min", "max"]

        rows = []
        for feature, value, min_val, max_val, min_flex, max_flex in feature_rows:
            row = {
                "feature": feature,
                "value": value,
                "min": str(min_val),
                "max": str(max_val),
            }
            if all_flex_set:
                row["min_flex"] = str(min_flex)
                row["max_flex"] = str(max_flex)
            rows.append(row)

        yield headers, rows

    @contextmanager
    def read_people_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load respondents from database as people data."""
        # Note: We don't add a message here as custom codes aren't supported

        if self.eligible_only:
            respondents = self.uow.respondents.get_by_assembly_id(
                self.assembly_id,
                status=RespondentStatus.POOL,
                eligible_only=True,
            )
            if not respondents:
                raise BadDataError(
                    "No eligible respondents found for selection. "
                    "Check that respondents have been uploaded, have status POOL "
                    "and are not marked as ineligible or unable to attend."
                )
        else:
            # DELETED respondents are omitted from the people feed: the
            # sortition-algorithms validator rejects blanked attribute values.
            # generate_selection_csvs synthesises blanked rows for them after
            # the fact so historical exports still reference their external_id.
            respondents = self.uow.respondents.get_by_assembly_id(self.assembly_id, include_deleted=False)
            if not respondents:
                raise BadDataError(
                    "No eligible respondents found for selection. Check that respondents have been uploaded."
                )

        yield self._respondent_table(respondents)

    @staticmethod
    def _respondent_table(respondents: list[Respondent]) -> tuple[list[str], list[dict[str, str]]]:
        """Headers and rows in the CSV-like shape the library reads, keyed by external_id."""
        # Build headers from first respondent's attributes + external_id
        first = respondents[0]
        headers = [DB_ID_COLUMN, *first.attributes.keys()]

        rows = []
        for resp in respondents:
            row = {DB_ID_COLUMN: resp.external_id}
            row.update({k: str(v) for k, v in resp.attributes.items()})
            rows.append(row)
        return headers, rows

    @contextmanager
    def read_already_selected_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load the respondents who already hold a place: selected or confirmed.

        The library uses them to keep a replacement selection away from the
        household of someone already on the panel. A withdrawn person has given
        their place up, so their household is eligible again and they are not
        in this feed.
        """
        # Note: We don't add a message here as custom codes aren't supported
        respondents = self.uow.respondents.get_by_assembly_id_statuses(
            self.assembly_id, statuses=list(SELECTED_RESPONDENT_STATUSES)
        )
        if not respondents:
            yield [], []
            return
        yield self._respondent_table(respondents)

    def write_selected(self, selected: list[list[str]], report: RunReport) -> None:
        """Write selected people - stub for now (will update respondent status in future)."""
        # Note: We don't add a message here as custom codes aren't supported

    def write_remaining(self, remaining: list[list[str]], report: RunReport) -> None:
        """Write remaining people - stub for now."""
        # Note: We don't add a message here as custom codes aren't supported

    def highlight_dupes(self, dupes: list[int]) -> None:
        """Highlight duplicates - not applicable for database."""

    def customise_features_parse_error(
        self, error: ParseTableMultiError, headers: Sequence[str]
    ) -> SelectionMultilineError:
        return SelectionMultilineError([
            "Parser error(s) while reading target categories from database",
            *[str(e) for e in error.all_errors],
        ])

    def customise_people_parse_error(
        self, error: ParseTableMultiError, headers: Sequence[str]
    ) -> SelectionMultilineError:
        return SelectionMultilineError([
            "Parser error(s) while reading respondents from database",
            *[str(e) for e in error.all_errors],
        ])

    def customise_already_selected_parse_error(
        self, error: ParseTableMultiError, headers: Sequence[str]
    ) -> SelectionMultilineError:
        return SelectionMultilineError([
            "Parser error(s) while reading already selected respondents",
            *[str(e) for e in error.all_errors],
        ])
