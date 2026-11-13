"""ABOUTME: Creating a project together with the first thing that is written into it
ABOUTME: A Google Sheet's settings or an imported CSV, in the caller's one unit of work so a refusal leaves nothing"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import DataSource, RespondentsSource, TargetsSource

from .assembly_service import add_assembly_gsheet, create_assembly, update_csv_config
from .respondent_service import import_respondents_from_csv
from .target_csv_import import TargetImportResult, import_targets_from_csv
from .unit_of_work import AbstractUnitOfWork


@dataclass(frozen=True, kw_only=True)
class ProjectDetails:
    """What the first step of the create dialog collects."""

    title: str
    question: str = ""
    number_to_select: int = 0


def create_project(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    details: ProjectDetails,
    data_source: DataSource = DataSource.UNDECIDED,
    targets_source: TargetsSource = TargetsSource.UNDECIDED,
    respondents_source: RespondentsSource = RespondentsSource.UNDECIDED,
) -> Assembly:
    """Create a project with its data source choices.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    return create_assembly(
        uow=uow,
        title=details.title,
        created_by_user_id=user_id,
        question=details.question,
        number_to_select=details.number_to_select,
        data_source=data_source,
        targets_source=targets_source,
        respondents_source=respondents_source,
    )


def create_project_with_gsheet(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    details: ProjectDetails,
    gsheet_settings: dict[str, Any],
) -> Assembly:
    """Create a project managed in Google Sheets, with the sheet's settings.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = create_project(uow, user_id, details, data_source=DataSource.GSHEET)
    add_assembly_gsheet(uow=uow, assembly_id=assembly.id, user_id=user_id, **gsheet_settings)
    return assembly


def create_project_with_targets_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    details: ProjectDetails,
    csv_content: str,
    respondents_source: RespondentsSource = RespondentsSource.UNDECIDED,
) -> tuple[Assembly, TargetImportResult]:
    """Create a project held in OpenDLP and import its targets from a CSV.

    A file that is refused raises, and the caller's unit of work then rolls the
    project back with it: there is never a project left behind by a bad file.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = create_project(
        uow,
        user_id,
        details,
        data_source=DataSource.OPENDLP,
        targets_source=TargetsSource.CSV,
        respondents_source=respondents_source,
    )
    result = import_targets_from_csv(
        uow=uow, user_id=user_id, assembly_id=assembly.id, csv_content=csv_content, replace_existing=True
    )
    return assembly, result


def create_project_with_respondents_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    details: ProjectDetails,
    csv_content: str,
    id_column: str | None = None,
    filename: str = "",
    targets_source: TargetsSource = TargetsSource.UNDECIDED,
) -> tuple[Assembly, list[Respondent], list[str]]:
    """Create a project held in OpenDLP and import its respondents from a CSV.

    Returns the project, the respondents imported, and the rows that were
    skipped. A file that is refused outright raises, and the caller's unit of
    work then rolls the project back with it.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = create_project(
        uow,
        user_id,
        details,
        data_source=DataSource.OPENDLP,
        targets_source=targets_source,
        respondents_source=RespondentsSource.CSV,
    )
    respondents, errors, resolved_id_column = import_respondents_from_csv(
        uow=uow,
        user_id=user_id,
        assembly_id=assembly.id,
        csv_content=csv_content,
        replace_existing=True,
        id_column=id_column,
        filename=filename,
    )
    update_csv_config(
        uow=uow,
        user_id=user_id,
        assembly_id=assembly.id,
        last_import_filename=filename,
        last_import_timestamp=datetime.now(UTC),
        csv_id_column=resolved_id_column,
    )
    return assembly, respondents, errors
