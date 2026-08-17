"""ABOUTME: Component tests for the dev /service-docs registration-page lifecycle handlers
ABOUTME: Drives the five _handle_* functions over a FakeUnitOfWork and pins down their error responses"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml, RegistrationPageStatus
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.entrypoints.blueprints.dev import (
    _dev_error,
    _handle_close_registration_page,
    _handle_publish_registration_page,
    _handle_reopen_registration_page,
    _handle_submit_registration,
    _handle_unpublish_registration_page,
)
from opendlp.service_layer.exceptions import ImageQuotaExceeded, InsufficientPermissions
from tests.fakes import FakeStore, FakeUnitOfWork

_READY_HTML = (
    '<form action="{{ form_action }}" method="post">'
    "{{ csrf_form_element }}"
    '<input name="email" type="email">'
    '<button type="submit">Send</button>'
    "</form>"
)


def _seed_admin(store: FakeStore) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    with FakeUnitOfWork(store=store) as uow:
        uow.users.add(user)
        uow.commit()
    return user


def _seed_page(
    store: FakeStore,
    *,
    status: RegistrationPageStatus = RegistrationPageStatus.TEST,
    url_slug: str = "my-slug",
    form_html: str = _READY_HTML,
) -> RegistrationPage:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    page = RegistrationPage(assembly_id=assembly.id, url_slug=url_slug, status=status)
    source = RegistrationPageHtml(registration_page_id=page.id, form_html=form_html)
    with FakeUnitOfWork(store=store) as uow:
        uow.assemblies.add(assembly)
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(source)
        uow.commit()
    return page


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin(fake_store):
    return _seed_admin(fake_store)


@pytest.fixture
def app(fake_store):
    from opendlp.entrypoints.flask_app import create_app  # noqa: PLC0415

    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def as_admin(app, admin):
    """Push a request context with current_user set to the seeded admin."""
    with (
        app.test_request_context(),
        patch("opendlp.entrypoints.blueprints.dev.current_user", SimpleNamespace(id=admin.id)),
    ):
        yield


class TestDevError:
    """The dev-only error text: safe message, plus where to find the rest."""

    CONSOLE_HINT = "check the Flask console log"

    def test_uses_the_curated_message_of_a_user_facing_exception(self):
        text = _dev_error(ImageQuotaExceeded(limit=5))

        assert "maximum of 5 images" in text
        assert self.CONSOLE_HINT in text

    def test_falls_back_to_a_generic_message_for_a_plain_exception(self):
        text = _dev_error(ValueError("connection string postgres://user:hunter2@db/x failed"))

        assert "hunter2" not in text
        assert "Something went wrong" in text
        assert self.CONSOLE_HINT in text

    def test_points_at_the_console_even_when_the_message_is_generic(self):
        assert self.CONSOLE_HINT in _dev_error(RuntimeError("boom"))


class TestPublishRegistrationPage:
    def test_publishes_a_ready_page(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store)

        result = _handle_publish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "success"
        assert result["registration_page"]["status"] == RegistrationPageStatus.PUBLISHED.value

    def test_reports_readiness_problems_to_the_developer(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, form_html="")

        result = _handle_publish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "RegistrationPageNotReady"
        # RegistrationPageNotReady carries curated problems, so they survive
        assert "The form HTML is empty" in result["error"]
        assert "check the Flask console log" in result["error"]

    def test_reports_a_missing_page_without_leaking_the_internal_message(self, fake_store, as_admin, shared_uow):
        assembly = Assembly(title="No page", question="?", status=AssemblyStatus.ACTIVE)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.add(assembly)
            uow.commit()

        result = _handle_publish_registration_page(shared_uow, {"assembly_id": str(assembly.id)})

        assert result["status"] == "error"
        assert result["error_type"] == "RegistrationPageNotFoundError"
        # NotFoundError messages embed ids and are not curated for a reader
        assert str(assembly.id) not in result["error"]
        assert "Something went wrong" in result["error"]

    def test_reports_a_wrong_status_as_a_value_error(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.PUBLISHED)

        result = _handle_publish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"

    def test_lets_an_unexpected_error_propagate_to_the_route(self, fake_store, as_admin, shared_uow):
        """Anything not in the narrowed tuple belongs to service_docs_execute's handler."""
        page = _seed_page(fake_store)

        with (
            patch(
                "opendlp.entrypoints.blueprints.dev.publish_registration_page",
                side_effect=RuntimeError("database on fire"),
            ),
            pytest.raises(RuntimeError),
        ):
            _handle_publish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})


class TestUnpublishRegistrationPage:
    def test_returns_a_published_page_to_test(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.PUBLISHED)

        result = _handle_unpublish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "success"
        assert result["registration_page"]["status"] == RegistrationPageStatus.TEST.value

    def test_reports_a_wrong_status_without_raising(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.TEST)

        result = _handle_unpublish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"
        assert "check the Flask console log" in result["error"]


class TestCloseRegistrationPage:
    def test_closes_a_published_page(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.PUBLISHED)

        result = _handle_close_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "success"
        assert result["registration_page"]["status"] == RegistrationPageStatus.CLOSED.value

    def test_reports_a_wrong_status_without_raising(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.TEST)

        result = _handle_close_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "ValueError"


class TestReopenRegistrationPage:
    def test_reopens_a_closed_page(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.CLOSED)

        result = _handle_reopen_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "success"
        assert result["registration_page"]["status"] == RegistrationPageStatus.PUBLISHED.value

    def test_reports_readiness_problems_when_reopening(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store, status=RegistrationPageStatus.CLOSED, form_html="")

        result = _handle_reopen_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "RegistrationPageNotReady"
        assert "The form HTML is empty" in result["error"]


class TestSubmitRegistration:
    def test_reports_a_missing_assembly_as_a_form_error(self, fake_store, as_admin, shared_uow):
        """This service reports problems in its result rather than raising."""
        result = _handle_submit_registration(shared_uow, {"assembly_id": str(uuid.uuid4()), "form_data": {}})

        assert result["status"] == "validation_error"
        assert result["form_errors"] == ["Assembly not found"]

    def test_lets_an_unexpected_error_propagate_to_the_route(self, fake_store, as_admin, shared_uow):
        with (
            patch(
                "opendlp.entrypoints.blueprints.dev.submit_registration_by_assembly_id",
                side_effect=RuntimeError("database on fire"),
            ),
            pytest.raises(RuntimeError),
        ):
            _handle_submit_registration(shared_uow, {"assembly_id": str(uuid.uuid4()), "form_data": {}})


class TestPermissionErrorsStayCurated:
    def test_insufficient_permissions_keeps_its_message(self, fake_store, as_admin, shared_uow):
        page = _seed_page(fake_store)

        with patch(
            "opendlp.entrypoints.blueprints.dev.publish_registration_page",
            side_effect=InsufficientPermissions(action="publish registration page", required_role="organiser"),
        ):
            result = _handle_publish_registration_page(shared_uow, {"assembly_id": str(page.assembly_id)})

        assert result["status"] == "error"
        assert result["error_type"] == "InsufficientPermissions"
        assert "Insufficient permissions" in result["error"]
