"""ABOUTME: Component tests for the public routes with several registration pages per assembly
ABOUTME: Each page renders, submits and thanks independently while feeding one pool"""

import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import RespondentStatus
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
    update_thank_you_html,
)
from tests.fakes import FakeStore, FakeUnitOfWork

MINIMAL_FORM_HTML = "<form method='post' action='{{ form_action }}'>{{ csrf_form_element }}</form>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch):
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _assembly(store: FakeStore, admin: User, title: str = "Climate Assembly"):
    with FakeUnitOfWork(store=store) as uow:
        return create_assembly(uow=uow, title=title, created_by_user_id=admin.id, question="What should we do?").id


def _page(store: FakeStore, admin: User, assembly_id, name: str, language: str = "", *, publish: bool = True):
    with FakeUnitOfWork(store=store) as uow:
        page = create_registration_page_with_slugs(uow, admin.id, assembly_id, name=name, language=language)
    with FakeUnitOfWork(store=store) as uow:
        update_registration_page_html(uow, admin.id, page.id, MINIMAL_FORM_HTML)
    if publish:
        with FakeUnitOfWork(store=store) as uow:
            page = publish_registration_page(uow, admin.id, page.id)
    return page


class TestSeveralLivePages:
    def test_every_variant_renders_at_its_own_slug(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        assembly_id = _assembly(fake_store, admin_user)
        english = _page(fake_store, admin_user, assembly_id, "English", "en")
        spanish = _page(fake_store, admin_user, assembly_id, "Espanol", "es")

        assert english.url_slug != spanish.url_slug
        for page in (english, spanish):
            assert client.get(f"/register/{page.url_slug}").status_code == 200

    def test_each_variant_has_its_own_short_url(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        assembly_id = _assembly(fake_store, admin_user)
        english = _page(fake_store, admin_user, assembly_id, "English", "en")
        spanish = _page(fake_store, admin_user, assembly_id, "Espanol", "es")

        english_redirect = client.get(f"/r/{english.short_url_slug}")
        spanish_redirect = client.get(f"/r/{spanish.short_url_slug}")

        assert english.url_slug in english_redirect.location
        assert spanish.url_slug in spanish_redirect.location

    def test_submissions_from_both_variants_land_in_one_pool(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        assembly_id = _assembly(fake_store, admin_user)
        english = _page(fake_store, admin_user, assembly_id, "English", "en")
        spanish = _page(fake_store, admin_user, assembly_id, "Espanol", "es")

        client.post(f"/register/{english.url_slug}", data={"email": "ada@example.com"})
        client.post(f"/register/{spanish.url_slug}", data={"email": "grace@example.com"})

        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly_id, status=RespondentStatus.POOL)
            by_page = {r.registration_page_id for r in respondents}

        assert len(respondents) == 2
        assert by_page == {english.id, spanish.id}

    def test_each_variant_serves_its_own_thank_you(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        assembly_id = _assembly(fake_store, admin_user)
        english = _page(fake_store, admin_user, assembly_id, "English", "en")
        spanish = _page(fake_store, admin_user, assembly_id, "Espanol", "es")
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, english.id, "<h1>Thank you</h1>")
        with FakeUnitOfWork(store=fake_store) as uow:
            update_thank_you_html(uow, admin_user.id, spanish.id, "<h1>Gracias</h1>")

        english_body = client.get(f"/register/{english.url_slug}/thank-you").get_data(as_text=True)
        spanish_body = client.get(f"/register/{spanish.url_slug}/thank-you").get_data(as_text=True)

        assert "Thank you" in english_body
        assert "Gracias" not in english_body
        assert "Gracias" in spanish_body


class TestMixedStatusesAcrossVariants:
    def test_a_test_variant_records_test_submissions_beside_a_live_one(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        """Statuses are per page, so a draft variant cannot pollute the live pool."""
        assembly_id = _assembly(fake_store, admin_user)
        live = _page(fake_store, admin_user, assembly_id, "English", "en")
        draft = _page(fake_store, admin_user, assembly_id, "Espanol", "es", publish=False)

        client.post(f"/register/{live.url_slug}", data={"email": "ada@example.com"})
        client.post(f"/register/{draft.url_slug}", data={"email": "grace@example.com"})

        with FakeUnitOfWork(store=fake_store) as uow:
            pool = uow.respondents.get_by_assembly_id(assembly_id, status=RespondentStatus.POOL)
            tests = uow.respondents.get_by_assembly_id(assembly_id, status=RespondentStatus.TEST_SUBMISSION)

        assert [r.registration_page_id for r in pool] == [live.id]
        assert [r.registration_page_id for r in tests] == [draft.id]

    def test_closing_one_variant_leaves_its_sibling_live(
        self, client: FlaskClient, fake_store: FakeStore, admin_user: User
    ) -> None:
        assembly_id = _assembly(fake_store, admin_user)
        staying = _page(fake_store, admin_user, assembly_id, "English", "en")
        closing = _page(fake_store, admin_user, assembly_id, "Espanol", "es")
        with FakeUnitOfWork(store=fake_store) as uow:
            close_registration_page(uow, admin_user.id, closing.id)

        assert client.get(f"/register/{staying.url_slug}").status_code == 200
        closed_response = client.get(f"/register/{closing.url_slug}")
        assert closed_response.status_code == 302
        assert "/registration-closed" in closed_response.location
