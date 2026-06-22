"""ABOUTME: E2E smoke for the registration auto-reply through the full HTTP + PostgreSQL stack
ABOUTME: Submits the public form and checks a RespondentEmailSendRecord is written"""

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
from opendlp.domain.value_objects import RespondentStatus
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly, update_assembly
from opendlp.service_layer.email_template_service import assign_auto_reply_template, create_email_template
from opendlp.service_layer.registration_page_service import (
    create_registration_page_with_slugs,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token, route_url

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
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _build_published_page_with_auto_reply(session_factory, admin_id) -> RegistrationPage:
    """Create a published registration page wired to an assigned auto-reply template,
    with a reply-to address and an email field on the page."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Auto Reply Assembly",
            created_by_user_id=admin_id,
            question="Test question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    field_defs = [
        ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.YES_REQUIRED),
        ("name", FieldType.TEXT, False, FieldOnRegistrationPage.YES_OPTIONAL),
    ]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
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
        SqlAlchemyUnitOfWork(session_factory),
        assembly_id,
        admin_id,
        reply_to_name="The Team",
        reply_to_email="team@example.com",
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        create_registration_page_with_slugs(uow, admin_id, assembly_id)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        update_registration_page_html(uow, admin_id, assembly_id, MINIMAL_FORM_HTML)

    template = create_email_template(
        SqlAlchemyUnitOfWork(session_factory),
        admin_id,
        assembly_id,
        name="Auto-reply",
        subject=AUTO_REPLY_SUBJECT,
        body_html=AUTO_REPLY_BODY,
    )
    assign_auto_reply_template(SqlAlchemyUnitOfWork(session_factory), admin_id, assembly_id, template.id)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        return publish_registration_page(uow, admin_id, assembly_id)


def test_live_submission_writes_sent_record(client: FlaskClient, admin_user, postgres_session_factory) -> None:
    """A live submission to a page with an auto-reply configured sends the email and
    records a SENT RespondentEmailSendRecord addressed to the respondent (PostgreSQL smoke)."""
    page = _build_published_page_with_auto_reply(postgres_session_factory, admin_user.id)
    form_url = route_url(client, "registration.show_registration_form", url_slug=page.url_slug)
    csrf_token = get_csrf_token(client, form_url)

    response = client.post(
        form_url,
        data={"csrf_token": csrf_token, "name": "Ada", "email": "ada-autoreply@example.com"},
    )
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        respondents = uow.respondents.get_by_assembly_id(page.assembly_id, status=RespondentStatus.POOL)
        assert respondents, "expected a respondent to have been created"
        records = uow.respondent_email_send_records.list_by_respondent(respondents[0].id)
        assert len(records) == 1
        assert records[0].outcome is EmailSendOutcome.SENT
        assert records[0].to_email == "ada-autoreply@example.com"
