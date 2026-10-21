"""ABOUTME: Tests the data migration that moves pages seeded with the old thank-you HTML to the standard page.
ABOUTME: Seeds pages through the repositories, sets their raw column values, then runs the migration's SQL."""

import importlib
import uuid

import pytest
import sqlalchemy as sa

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

migration = importlib.import_module("migrations.versions.a78dcf4c5649_add_thank_you_use_default_to_")


@pytest.fixture
def pages(postgres_session_factory):
    """Three pages, as they stood before the migration: the old default, their own HTML, and blank."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = Assembly(title="Thanks", question="?", number_to_select=10)
        uow.assemblies.add(assembly)
        seeded = {
            "old_default": RegistrationPage(assembly_id=assembly.id, name="a"),
            "own": RegistrationPage(assembly_id=assembly.id, name="b"),
            "blank": RegistrationPage(assembly_id=assembly.id, name="c"),
        }
        for page in seeded.values():
            uow.registration_pages.add(page)
        ids = {key: page.id for key, page in seeded.items()}
        uow.commit()
    _set_raw(postgres_session_factory, ids["old_default"], migration.OLD_DEFAULT_THANK_YOU_HTML)
    _set_raw(postgres_session_factory, ids["own"], "<p>Our own thanks</p>")
    _set_raw(postgres_session_factory, ids["blank"], "  ")
    return ids


def _set_raw(session_factory, page_id: uuid.UUID, html: str) -> None:
    """The column's server default, true, is what every row gets when the column is added."""
    session = session_factory()
    try:
        session.execute(
            sa.text(
                "UPDATE registration_pages SET thank_you_html = :html, thank_you_use_default = true WHERE id = :id"
            ),
            {"html": html, "id": page_id},
        )
        session.commit()
    finally:
        session.close()


def _run(session_factory, *statements) -> None:
    session = session_factory()
    try:
        for statement in statements:
            session.execute(statement)
        session.commit()
    finally:
        session.close()


def _upgrade(session_factory) -> None:
    _run(session_factory, migration.KEEP_OWN_THANK_YOU, migration.BLANK_OLD_DEFAULT)


def _page(session_factory, page_id: uuid.UUID) -> RegistrationPage:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        return uow.registration_pages.get(page_id).create_detached_copy()


class TestThankYouUseDefaultMigration:
    def test_the_old_default_moves_to_the_standard_page_and_is_blanked(self, postgres_session_factory, pages):
        _upgrade(postgres_session_factory)

        page = _page(postgres_session_factory, pages["old_default"])
        assert page.thank_you_use_default is True
        assert page.thank_you_html == ""

    def test_html_of_its_own_is_kept_and_shown(self, postgres_session_factory, pages):
        _upgrade(postgres_session_factory)

        page = _page(postgres_session_factory, pages["own"])
        assert page.thank_you_use_default is False
        assert page.thank_you_html == "<p>Our own thanks</p>"

    def test_blank_html_uses_the_standard_page(self, postgres_session_factory, pages):
        _upgrade(postgres_session_factory)

        assert _page(postgres_session_factory, pages["blank"]).thank_you_use_default is True

    def test_running_it_twice_changes_nothing_more(self, postgres_session_factory, pages):
        _upgrade(postgres_session_factory)
        _upgrade(postgres_session_factory)

        assert _page(postgres_session_factory, pages["own"]).thank_you_use_default is False
        assert _page(postgres_session_factory, pages["old_default"]).thank_you_html == ""

    def test_downgrade_restores_the_old_default_where_the_standard_page_was_used(self, postgres_session_factory, pages):
        _upgrade(postgres_session_factory)
        _run(postgres_session_factory, migration.RESTORE_OLD_DEFAULT)

        assert _page(postgres_session_factory, pages["old_default"]).thank_you_html == (
            migration.OLD_DEFAULT_THANK_YOU_HTML
        )
        assert _page(postgres_session_factory, pages["own"]).thank_you_html == "<p>Our own thanks</p>"
