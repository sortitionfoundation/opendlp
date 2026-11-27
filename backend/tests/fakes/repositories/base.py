"""ABOUTME: Base in-memory repository that the other repository fakes extend
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid
from collections.abc import Iterable
from typing import Any

from opendlp.service_layer.repositories import (
    AbstractRepository,
)


class FakeRepository(AbstractRepository):
    """Base fake repository with in-memory storage."""

    def __init__(self, items: list[Any] | None = None):
        self._items = list(items) if items else []

    def add(self, item: Any) -> None:
        """Add an item to the repository. Adding one it already holds does nothing, as on a SQLAlchemy session."""
        if any(existing is item for existing in self._items):
            return
        self._items.append(item)

    def get(self, item_id: uuid.UUID) -> Any | None:
        """Get an item by its ID."""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def all(self) -> Iterable[Any]:
        """Get all items in the repository."""
        return list(self._items)
