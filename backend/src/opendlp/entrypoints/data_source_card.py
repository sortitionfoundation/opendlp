"""ABOUTME: What the Data source card on the project details page says about a project held in OpenDLP
ABOUTME: Pairs the stored choice for targets and for respondents with how much of each the project has"""

from dataclasses import dataclass

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import (
    RespondentsSource,
    TargetsSource,
    respondents_source_labels,
    targets_source_labels,
)
from opendlp.translations import ngettext


@dataclass(frozen=True)
class SourceRow:
    """One row of the card: how the data arrives, and a tag counting what is there."""

    source: str
    count_tag: str


def targets_row(assembly: Assembly, count: int) -> SourceRow:
    choice = assembly.targets_source
    if count == 0:
        return SourceRow(str(targets_source_labels[choice]), "")
    if choice == TargetsSource.CSV:
        tag = ngettext("%(num)d target uploaded", "%(num)d targets uploaded", count)
    else:
        tag = ngettext("%(num)d target", "%(num)d targets", count)
    return SourceRow(_source_beside_data(choice != TargetsSource.UNDECIDED, str(targets_source_labels[choice])), tag)


def respondents_row(assembly: Assembly, count: int) -> SourceRow:
    choice = assembly.respondents_source
    if count == 0:
        return SourceRow(str(respondents_source_labels[choice]), "")
    if choice == RespondentsSource.CSV:
        tag = ngettext("%(num)d respondent uploaded", "%(num)d respondents uploaded", count)
    else:
        tag = ngettext("%(num)d respondent", "%(num)d respondents", count)
    return SourceRow(
        _source_beside_data(choice != RespondentsSource.UNDECIDED, str(respondents_source_labels[choice])), tag
    )


def _source_beside_data(decided: bool, label: str) -> str:
    """Nothing, when the project has data and nobody said how it arrived.

    "Decide later" beside "4 targets" reads as a contradiction, and it is what
    every project older than the stored choice would otherwise show.
    """
    return label if decided else ""
