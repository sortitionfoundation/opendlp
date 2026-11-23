"""ABOUTME: Domain events - facts about something that happened, recorded on the UnitOfWork
ABOUTME: Frozen dataclasses holding ids and small values, never personal data"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    """Something that happened, named in the past tense.

    An event carries ids and small values only. It says which assembly or
    respondent, never what someone's answers are, so it is safe to log and
    anything built from it stays inside the erasure strategy.
    """


@dataclass(frozen=True)
class RespondentsChanged(Event):
    """One or more respondents of an assembly were created, changed or deleted."""

    assembly_id: uuid.UUID


@dataclass(frozen=True)
class RespondentSchemaChanged(Event):
    """The fields that make up a respondent of an assembly changed: added, renamed, reordered or removed."""

    assembly_id: uuid.UUID
