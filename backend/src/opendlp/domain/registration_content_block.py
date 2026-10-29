"""ABOUTME: Headings and text that an organiser places among the registration questions.
ABOUTME: Also the single ordered list of questions and blocks that the questions step arranges."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from opendlp.domain.html_to_text import html_to_text
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition
from opendlp.translations import gettext as _

# An image has no text, but it is something to show.
_IMAGE_TAG = re.compile(r"<img\b", re.IGNORECASE)


def _body_is_blank(body_html: str) -> bool:
    return not html_to_text(body_html).strip() and not _IMAGE_TAG.search(body_html)


class RegistrationContentBlock:
    """A heading, some text, or both, shown between two registration questions.

    ``sort_order`` is on the same per-assembly scale as the questions'
    ``sort_order``, so the two merge into one list. The heading is plain text;
    the body is HTML from the rich-text editor.
    """

    def __init__(
        self,
        assembly_id: uuid.UUID,
        sort_order: int,
        heading: str = "",
        body_html: str = "",
        block_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if sort_order < 0:
            raise ValueError("sort_order cannot be negative")
        heading = heading.strip()
        _check_not_empty(heading, body_html)
        self.id = block_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.sort_order = sort_order
        self.heading = heading
        self.body_html = body_html
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def update(self, heading: str, body_html: str) -> None:
        heading = heading.strip()
        _check_not_empty(heading, body_html)
        self.heading = heading
        self.body_html = body_html
        self.updated_at = datetime.now(UTC)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RegistrationContentBlock):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "RegistrationContentBlock":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RegistrationContentBlock(
            assembly_id=self.assembly_id,
            sort_order=self.sort_order,
            heading=self.heading,
            body_html=self.body_html,
            block_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


def _check_not_empty(heading: str, body_html: str) -> None:
    if not heading and _body_is_blank(body_html):
        raise ValueError(_("Add a heading, some text, or both"))


class FormItemKind(Enum):
    QUESTION = "question"
    BLOCK = "block"


@dataclass(frozen=True)
class FormItemRef:
    """Names one item on the questions list, whichever table it lives in."""

    kind: FormItemKind
    item_id: uuid.UUID

    @property
    def form_value(self) -> str:
        """How the item is written in a form field, read back by ``parse``."""
        return f"{self.kind.value}:{self.item_id}"

    @classmethod
    def parse(cls, raw: str) -> "FormItemRef | None":
        kind_value, _sep, id_value = raw.partition(":")
        try:
            return cls(FormItemKind(kind_value), uuid.UUID(id_value))
        except ValueError:
            return None


FormItem = RespondentFieldDefinition | RegistrationContentBlock


def form_item_ref(item: FormItem) -> FormItemRef:
    kind = FormItemKind.QUESTION if isinstance(item, RespondentFieldDefinition) else FormItemKind.BLOCK
    return FormItemRef(kind, item.id)


def _sort_key(item: FormItem) -> tuple[int, int, str]:
    if isinstance(item, RespondentFieldDefinition):
        return item.sort_order, 0, item.field_key
    return item.sort_order, 1, str(item.id)


def form_items(fields: list[RespondentFieldDefinition], blocks: list[RegistrationContentBlock]) -> list[FormItem]:
    """The questions and blocks in the one order the questions step shows them.

    Derived fields are left out: they are computed, never asked, and are
    managed on the targets step. Equal sort orders put the question first.
    """
    items: list[FormItem] = [f for f in fields if not f.is_derived]
    items.extend(blocks)
    return sorted(items, key=_sort_key)
