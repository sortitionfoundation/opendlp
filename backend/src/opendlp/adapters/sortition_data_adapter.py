"""ABOUTME: Data adapter for sortition-algorithms library using OpenDLP database
ABOUTME: Implements AbstractDataSource to load features/people from database instead of CSV/GSheet"""

import uuid
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager

from sortition_algorithms.adapters import AbstractDataSource
from sortition_algorithms.errors import ParseTableMultiError, SelectionMultilineError
from sortition_algorithms.features import MAX_FLEX_UNSET
from sortition_algorithms.utils import RunReport

from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


class OpenDLPDataAdapter(AbstractDataSource):
    """Data adapter that reads from OpenDLP database via UnitOfWork."""

    def __init__(self, uow: AbstractUnitOfWork, assembly_id: uuid.UUID):
        self.uow = uow
        self.assembly_id = assembly_id

    @property
    def people_data_container(self) -> str:
        return "OpenDLP respondents database"

    @property
    def already_selected_data_container(self) -> str:
        return "OpenDLP already selected respondents"

    @contextmanager
    def read_feature_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load target categories from database as feature data."""
        # Note: We don't add a message here as custom codes aren't supported

        categories = self.uow.target_categories.get_by_assembly_id(self.assembly_id)

        # Convert to CSV-like format expected by sortition-algorithms
        # Check if any category uses flex values
        has_flex = any(
            value.min_flex != 0 or value.max_flex != MAX_FLEX_UNSET
            for category in categories
            for value in category.values
        )

        if has_flex:
            headers = ["feature", "value", "min", "max", "min_flex", "max_flex"]
        else:
            headers = ["feature", "value", "min", "max"]

        rows = []
        for category in categories:
            for value in category.values:
                row = {
                    "feature": category.name,
                    "value": value.value,
                    "min": str(value.min),
                    "max": str(value.max),
                }
                if has_flex:
                    row["min_flex"] = str(value.min_flex)
                    # If max_flex is unset, use empty string to let library calculate default
                    row["max_flex"] = str(value.max_flex) if value.max_flex != MAX_FLEX_UNSET else ""
                rows.append(row)

        yield headers, rows

    @contextmanager
    def read_people_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load respondents from database as people data."""
        # Note: We don't add a message here as custom codes aren't supported

        respondents = self.uow.respondents.get_by_assembly_id(
            self.assembly_id,
            eligible_only=True,
        )

        if not respondents:
            yield [], []
            return

        # Build headers from first respondent's attributes + external_id
        first = respondents[0]
        headers = ["external_id", *first.attributes.keys()]

        # Convert to CSV-like format
        rows = []
        for resp in respondents:
            row = {"external_id": resp.external_id}
            row.update({k: str(v) for k, v in resp.attributes.items()})
            rows.append(row)

        yield headers, rows

    @contextmanager
    def read_already_selected_data(
        self, report: RunReport
    ) -> Generator[tuple[Iterable[str], Iterable[dict[str, str]]], None, None]:
        """Load already selected respondents - stub for now."""
        # Note: We don't add a message here as custom codes aren't supported
        yield [], []

    def write_selected(self, selected: list[list[str]], report: RunReport) -> None:
        """Write selected people - stub for now (will update respondent status in future)."""
        # Note: We don't add a message here as custom codes aren't supported
        pass

    def write_remaining(self, remaining: list[list[str]], report: RunReport) -> None:
        """Write remaining people - stub for now."""
        # Note: We don't add a message here as custom codes aren't supported
        pass

    def highlight_dupes(self, dupes: list[int]) -> None:
        """Highlight duplicates - not applicable for database."""
        pass

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
