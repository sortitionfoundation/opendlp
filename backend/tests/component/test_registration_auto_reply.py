# ABOUTME: Component tests for the registration auto-reply wiring over a FakeUnitOfWork
# ABOUTME: POSTs the public form and asserts a RespondentEmailSendRecord is written to the fake store

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.email_send_record import EmailSendOutcome
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.entrypoints.flask_app import create_app
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly, update_assembly
from opendlp.service_layer.email_template_service import assign_auto_reply_template, create_email_template
from opendlp.service_layer.registration_page_service import (
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork

MINIMAL_FORM_HTML = """
<form method="post" action="{{ form_action }}">
    {{ csrf_form_element }}
    <label for="name">Name</label>
    <input id="name" name="name" type="text" value="{{ value('name') }}">
    <label for="email">Email</label>
    <input id="email" name="email" type="email" value="{{ value('email') }}">
    <button type="submit">Submit</button>
</form>
"""

AUTO_REPLY_SUBJECT = "Thanks for registering for {{ assembly.title }}"
AUTO_REPLY_BODY = "<p>Hi {{ respondent.first_name_or_friend }}, we got your registration for {{ assembly.title }}.</p>"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FF_"):
            monkeypatch.delenv(key, raising=False)
    reload_flags()
    yield
    reload_flags()


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin_user(fake_store):
    with FakeUnitOfWork(store=fake_store) as uow:
        admin, _ = create_user(
            uow=uow,
            email="admin@example.com",
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
        return user.create_detached_copy()


@pytest.fixture
def app(fake_store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def client(app):
    return app.test_client()


def _build_page_with_auto_reply(
    fake_store, admin_id: uuid.UUID, *, publish: bool, capture_email: bool = True, with_template: bool = True
) -> RegistrationPage:
    """Seed an assembly with a reply-to, a registration page wired to an assigned
    auto-reply template, and (optionally) an email field on the page.

    ``publish=True`` makes submissions live (POOL); ``publish=False`` leaves the page
    in TEST mode. ``capture_email=False`` omits the email field so submitted
    respondents have no address. ``with_template=False`` configures no auto-reply.
    """
    with FakeUnitOfWork(store=fake_store) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Auto Reply Assembly",
            created_by_user_id=admin_id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    field_defs = [("name", FieldType.TEXT, False, FieldOnRegistrationPage.YES_OPTIONAL)]
    if capture_email:
        field_defs.insert(0, ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.YES_REQUIRED))
    with FakeUnitOfWork(store=fake_store) as uow:
        for sort, (key, ftype, is_fixed, on_page) in enumerate(field_defs):
            uow.respondent_field_definitions.add(
                RespondentFieldDefinition(
                    assembly_id=assembly_id,
                    field_key=key,
                    label=key.capitalize(),
                    group=RespondentFieldGroup.OTHER,
                    sort_order=(sort + 1) * 10,
                    field_type=ftype,
                    is_fixed=is_fixed,
                    on_registration_page=on_page,
                )
            )
        uow.commit()

    update_assembly(
        FakeUnitOfWork(store=fake_store),
        assembly_id,
        admin_id,
        reply_to_name="The Team",
        reply_to_email="team@example.com",
    )

    with FakeUnitOfWork(store=fake_store) as uow:
        create_registration_page_with_slugs(uow, admin_id, assembly_id)
    with FakeUnitOfWork(store=fake_store) as uow:
        update_registration_page_html(uow, admin_id, assembly_id, MINIMAL_FORM_HTML)

    if with_template:
        template = create_email_template(
            FakeUnitOfWork(store=fake_store),
            admin_id,
            assembly_id,
            name="Auto-reply",
            subject=AUTO_REPLY_SUBJECT,
            body_html=AUTO_REPLY_BODY,
        )
        assign_auto_reply_template(FakeUnitOfWork(store=fake_store), admin_id, assembly_id, template.id)

    if publish:
        with FakeUnitOfWork(store=fake_store) as uow:
            return publish_registration_page(uow, admin_id, assembly_id)
    with FakeUnitOfWork(store=fake_store) as uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        return page.create_detached_copy()


def _records_for_latest_respondent(fake_store, assembly_id, status):
    """Return send records (detached) for the most recent respondent of the given
    status, asserting at least one respondent exists."""
    with FakeUnitOfWork(store=fake_store) as uow:
        respondents = uow.respondents.get_by_assembly_id(assembly_id, status=status)
        assert respondents, "expected a respondent to have been created"
        respondent = respondents[0]
        return [r.create_detached_copy() for r in uow.respondent_email_send_records.list_by_respondent(respondent.id)]


def test_live_submission_writes_sent_record(client: FlaskClient, fake_store, admin_user: User) -> None:
    page = _build_page_with_auto_reply(fake_store, admin_user.id, publish=True)

    response = client.post(
        f"/register/{page.url_slug}",
        data={"name": "Ada", "email": "ada-autoreply@example.com"},
    )
    assert response.status_code == 302

    records = _records_for_latest_respondent(fake_store, page.assembly_id, RespondentStatus.POOL)
    assert len(records) == 1
    assert records[0].outcome is EmailSendOutcome.SENT
    assert records[0].to_email == "ada-autoreply@example.com"


def test_submission_without_captured_email_writes_no_record(client: FlaskClient, fake_store, admin_user: User) -> None:
    page = _build_page_with_auto_reply(fake_store, admin_user.id, publish=True, capture_email=False)

    response = client.post(f"/register/{page.url_slug}", data={"name": "Ada"})
    assert response.status_code == 302

    records = _records_for_latest_respondent(fake_store, page.assembly_id, RespondentStatus.POOL)
    assert records == []


def test_test_mode_submission_writes_sent_record(client: FlaskClient, fake_store, admin_user: User) -> None:
    page = _build_page_with_auto_reply(fake_store, admin_user.id, publish=False)

    response = client.post(
        f"/register/{page.url_slug}",
        data={"name": "Ada", "email": "ada-testmode@example.com"},
    )
    assert response.status_code == 302

    records = _records_for_latest_respondent(fake_store, page.assembly_id, RespondentStatus.TEST_SUBMISSION)
    assert len(records) == 1
    assert records[0].outcome is EmailSendOutcome.SENT
    assert records[0].to_email == "ada-testmode@example.com"


def test_no_auto_reply_configured_writes_no_record(client: FlaskClient, fake_store, admin_user: User) -> None:
    page = _build_page_with_auto_reply(fake_store, admin_user.id, publish=True, with_template=False)

    response = client.post(
        f"/register/{page.url_slug}",
        data={"name": "Ada", "email": "ada-noreply@example.com"},
    )
    assert response.status_code == 302

    records = _records_for_latest_respondent(fake_store, page.assembly_id, RespondentStatus.POOL)
    assert records == []
