"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the backoffice registration-page routes
ABOUTME: Covers creating a registration page, filling its empty form and fetching the starter HTML skeleton"""

from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.service_layer.registration_page_service import page_for_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


def _registration_url(assembly_id, suffix=""):
    return f"/backoffice/project/{assembly_id}/registration{suffix}"


def test_create_assembly_registration_page_success(
    logged_in_admin: FlaskClient, existing_assembly, postgres_session_factory
):
    """Creating a registration page generates slugs and persists the page."""
    response = logged_in_admin.post(
        _registration_url(existing_assembly.id, "/create"),
        data={"csrf_token": get_csrf_token(logged_in_admin, _registration_url(existing_assembly.id))},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/backoffice/project/{existing_assembly.id}" in response.location
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, existing_assembly.id)
        assert page is not None
        assert page.url_slug


def test_create_seeds_the_intro_and_a_fill_starts_the_form(
    logged_in_admin: FlaskClient, existing_assembly, postgres_session_factory
):
    """A new page's intro carries the assembly title; the empty form's fill button saves starter HTML."""
    logged_in_admin.post(
        _registration_url(existing_assembly.id, "/create"),
        data={"csrf_token": get_csrf_token(logged_in_admin, _registration_url(existing_assembly.id))},
    )
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, existing_assembly.id)
        assert page is not None
        source = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert source is not None
        assert f"<h1>{existing_assembly.title}</h1>" in source.intro_html
        assert source.form_html == ""
        url_slug, page_id = page.url_slug, page.id

    response = logged_in_admin.post(
        _registration_url(existing_assembly.id, f"/{url_slug}/save"),
        data={
            "csrf_token": get_csrf_token(logged_in_admin, _registration_url(existing_assembly.id)),
            "action": "save",
            "step": "form",
            "html_content": "",
            "fill_form": "govuk",
        },
    )

    assert response.status_code == 302
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        source = uow.registration_page_html_sources.get_by_page_id(page_id)
        assert source is not None
        assert "{{ form_action }}" in source.form_html
        assert "govuk-button" in source.form_html


def test_delete_assembly_registration_page_success(
    logged_in_admin: FlaskClient, existing_assembly, postgres_session_factory
):
    """Deleting a never-published page removes it and its HTML source from the database."""
    logged_in_admin.post(
        _registration_url(existing_assembly.id, "/create"),
        data={"csrf_token": get_csrf_token(logged_in_admin, _registration_url(existing_assembly.id))},
    )
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, existing_assembly.id)
        assert page is not None
        url_slug = page.url_slug
        page_id = page.id

    delete_url = _registration_url(existing_assembly.id, f"/{url_slug}/delete")
    response = logged_in_admin.post(
        delete_url,
        data={"csrf_token": get_csrf_token(logged_in_admin, _registration_url(existing_assembly.id))},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assert uow.registration_pages.get(page_id) is None
        assert uow.registration_page_html_sources.get_by_page_id(page_id) is None


def test_get_registration_skeleton_success(logged_in_admin: FlaskClient, existing_assembly, admin_user: User):
    """The skeleton endpoint returns generated starter HTML as JSON."""
    response = logged_in_admin.get(_registration_url(existing_assembly.id, "/skeleton"))

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"html", "html_govuk"}
    assert isinstance(payload["html"], str)
    assert "{{ assembly_title }}" not in payload["html"]
