# ABOUTME: Component tests for _handle_registration_action over a FakeUnitOfWork
# ABOUTME: Drives real registration-page services and asserts on the page's real stored status

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.registration_page import RegistrationPageStatus
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.blueprints.backoffice_registration import _handle_registration_action
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page,
    get_registration_page,
    publish_registration_page,
    update_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeUnitOfWork

_READY_HTML = (
    '<form action="{{ form_action }}" method="post">{{ csrf_form_element }}'
    '<button type="submit">Register</button></form>'
)


@pytest.fixture
def admin_id(fake_store) -> uuid.UUID:
    with FakeUnitOfWork(store=fake_store) as uow:
        admin, _ = create_user(
            uow=uow,
            email=f"admin-{uuid.uuid4()}@example.com",
            password="adminpass123",  # pragma: allowlist secret
            first_name="Test",
            last_name="Admin",
            global_role=GlobalRole.ADMIN,
            accept_data_agreement=True,
        )
    with FakeUnitOfWork(store=fake_store) as uow:
        user = uow.users.get(admin.id)
        user.confirm_email()
        uow.commit()
        return user.id


@pytest.fixture
def assembly_id(fake_store, admin_id) -> uuid.UUID:
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Component Assembly",
            created_by_user_id=admin_id,
            question="What should we do?",
        )
        return assembly.id


def _seed_page(fake_store, admin_id, assembly_id, *, target_status: RegistrationPageStatus):
    create_registration_page(FakeUnitOfWork(store=fake_store), admin_id, assembly_id)
    update_registration_page(FakeUnitOfWork(store=fake_store), admin_id, assembly_id, url_slug="component-page")
    update_registration_page_html(FakeUnitOfWork(store=fake_store), admin_id, assembly_id, _READY_HTML)
    if target_status == RegistrationPageStatus.TEST:
        return
    publish_registration_page(FakeUnitOfWork(store=fake_store), admin_id, assembly_id)
    if target_status == RegistrationPageStatus.PUBLISHED:
        return
    if target_status == RegistrationPageStatus.CLOSED:
        close_registration_page(FakeUnitOfWork(store=fake_store), admin_id, assembly_id)


def _stored_status(fake_store, admin_id, assembly_id) -> RegistrationPageStatus:
    page = get_registration_page(FakeUnitOfWork(store=fake_store), admin_id, assembly_id)
    return page.status


@pytest.fixture
def as_admin(app, admin_id):
    with (
        app.test_request_context(),
        patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.current_user",
            SimpleNamespace(id=admin_id),
        ),
    ):
        yield


class TestHandleRegistrationAction:
    def test_publish_action_publishes_test_page(self, fake_store, admin_id, assembly_id, as_admin):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.TEST)

        message = _handle_registration_action("publish", admin_id, assembly_id)

        assert "published successfully" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.PUBLISHED

    def test_publish_action_on_already_published_page_does_not_republish(
        self, fake_store, admin_id, assembly_id, as_admin
    ):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.PUBLISHED)

        message = _handle_registration_action("publish", admin_id, assembly_id)

        assert "html updated" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.PUBLISHED

    def test_unpublish_action_returns_page_to_test(self, fake_store, admin_id, assembly_id, as_admin):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.PUBLISHED)

        message = _handle_registration_action("unpublish", admin_id, assembly_id)

        assert "unpublished" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.TEST

    def test_close_action_closes_published_page(self, fake_store, admin_id, assembly_id, as_admin):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.PUBLISHED)

        message = _handle_registration_action("close", admin_id, assembly_id)

        assert "closed" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.CLOSED

    def test_reopen_action_republishes_closed_page(self, fake_store, admin_id, assembly_id, as_admin):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.CLOSED)

        message = _handle_registration_action("reopen", admin_id, assembly_id)

        assert "reopened" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.PUBLISHED

    def test_save_action_uses_saved_message_for_test_pages(self, fake_store, admin_id, assembly_id, as_admin):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.TEST)

        message = _handle_registration_action("save", admin_id, assembly_id)

        assert "saved" in message.lower()
        assert "republished" not in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.TEST

    def test_save_action_uses_republished_message_when_page_published(
        self, fake_store, admin_id, assembly_id, as_admin
    ):
        _seed_page(fake_store, admin_id, assembly_id, target_status=RegistrationPageStatus.PUBLISHED)

        message = _handle_registration_action("save", admin_id, assembly_id)

        assert "republished" in message.lower()
        assert _stored_status(fake_store, admin_id, assembly_id) == RegistrationPageStatus.PUBLISHED
