"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the backoffice registration-page routes
ABOUTME: Covers creating a registration page and fetching the starter HTML skeleton"""

from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


def _registration_url(assembly_id, suffix=""):
    return f"/backoffice/assembly/{assembly_id}/registration{suffix}"


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
    assert f"/backoffice/assembly/{existing_assembly.id}" in response.location
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_assembly_id(existing_assembly.id)
        assert page is not None
        assert page.url_slug


def test_get_registration_skeleton_success(logged_in_admin: FlaskClient, existing_assembly, admin_user: User):
    """The skeleton endpoint returns generated starter HTML as JSON."""
    response = logged_in_admin.get(_registration_url(existing_assembly.id, "/skeleton"))

    assert response.status_code == 200
    payload = response.get_json()
    assert "html" in payload
    assert isinstance(payload["html"], str)
