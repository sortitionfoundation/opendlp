"""ABOUTME: E2E smoke for the registration auto-reply through the full HTTP + PostgreSQL stack
ABOUTME: Submits the public form and checks a RespondentEmailSendRecord is written"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from babel.dates import format_date
from flask import Flask
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
    page_for_assembly,
    publish_registration_page,
    update_registration_page_html,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token, route_url
from tests.fakes import FakeEmailAdapter


def _page_id(uow, assembly_id):  # type: ignore[no-untyped-def]
    """The id of the assembly's single registration page."""
    page = page_for_assembly(uow, assembly_id)
    assert page is not None
    return page.id


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

AUTO_REPLY_SUBJECT = "Thanks for registering for {{ project.title }}"
AUTO_REPLY_BODY = "<p>Hi {{ respondent.first_name_or_friend }}, we got your registration for {{ assembly.title }}.</p>"


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _build_published_page_with_auto_reply(
    session_factory,
    admin_id,
    *,
    template_reply_to_name: str = "",
    template_reply_to_email: str = "",
    email_question_key: str = "",
    body_html: str = AUTO_REPLY_BODY,
) -> RegistrationPage:
    """Create a published registration page wired to an assigned auto-reply template,
    with a reply-to address and an email field on the page.

    Given an ``email_question_key``, the fixed email field is left off the page and
    the address is asked for in a question of type Email with that key instead."""
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
    form_html = MINIMAL_FORM_HTML
    if email_question_key:
        field_defs[0] = ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.NO)
        field_defs.append((email_question_key, FieldType.EMAIL, False, FieldOnRegistrationPage.YES_REQUIRED))
        form_html = MINIMAL_FORM_HTML.replace("email", email_question_key).replace(
            f'type="{email_question_key}"', 'type="email"'
        )
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

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        update_assembly(
            uow,
            assembly_id,
            admin_id,
            reply_to_name="The Team",
            reply_to_email="team@example.com",
        )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        create_registration_page_with_slugs(uow, admin_id, assembly_id, name="Registration page")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        update_registration_page_html(uow, admin_id, _page_id(uow, assembly_id), form_html)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        template = create_email_template(
            uow,
            admin_id,
            assembly_id,
            name="Auto-reply",
            subject=AUTO_REPLY_SUBJECT,
            body_html=body_html,
            reply_to_name=template_reply_to_name,
            reply_to_email=template_reply_to_email,
        )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assign_auto_reply_template(uow, admin_id, assembly_id, template.id)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        return publish_registration_page(uow, admin_id, _page_id(uow, assembly_id))


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


def _submit(client: FlaskClient, page: RegistrationPage, email: str) -> None:
    form_url = route_url(client, "registration.show_registration_form", url_slug=page.url_slug)
    csrf_token = get_csrf_token(client, form_url)
    response = client.post(form_url, data={"csrf_token": csrf_token, "name": "Ada", "email": email})
    assert response.status_code == 302


def _only_record(session_factory, assembly_id):  # type: ignore[no-untyped-def]
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        respondents = uow.respondents.get_by_assembly_id(assembly_id, status=RespondentStatus.POOL)
        records = uow.respondent_email_send_records.list_by_respondent(respondents[0].id)
        assert len(records) == 1
        return records[0].create_detached_copy()


def test_template_reply_to_is_used_for_the_send(client: FlaskClient, admin_user, postgres_session_factory) -> None:
    """The page's own reply-to wins over the assembly's, and the record keeps the one used."""
    page = _build_published_page_with_auto_reply(
        postgres_session_factory,
        admin_user.id,
        template_reply_to_name="Page Team",
        template_reply_to_email="page-team@example.com",
    )
    adapter = FakeEmailAdapter()
    with patch("opendlp.entrypoints.blueprints.registration.bootstrap.get_email_adapter", return_value=adapter):
        _submit(client, page, "ada-page-reply@example.com")

    assert adapter.sent[0]["reply_to"] == ("Page Team", "page-team@example.com")
    assert adapter.sent[0]["on_behalf_of"] == "Page Team"
    record = _only_record(postgres_session_factory, page.assembly_id)
    assert record.reply_to_email == "page-team@example.com"


def test_assembly_reply_to_is_the_fallback(client: FlaskClient, admin_user, postgres_session_factory) -> None:
    """With no reply-to on the page's template, the assembly's reply-to is used."""
    page = _build_published_page_with_auto_reply(postgres_session_factory, admin_user.id)
    adapter = FakeEmailAdapter()
    with patch("opendlp.entrypoints.blueprints.registration.bootstrap.get_email_adapter", return_value=adapter):
        _submit(client, page, "ada-assembly-reply@example.com")

    assert adapter.sent[0]["reply_to"] == ("The Team", "team@example.com")
    assert adapter.sent[0]["on_behalf_of"] == "The Team"
    record = _only_record(postgres_session_factory, page.assembly_id)
    assert record.reply_to_email == "team@example.com"


def test_a_sole_email_question_receives_the_auto_reply(
    client: FlaskClient, admin_user, postgres_session_factory
) -> None:
    """Without the fixed email field, the page's one question of type Email is where the
    auto-reply goes, and a form asking only for a name greets the respondent by it."""
    page = _build_published_page_with_auto_reply(
        postgres_session_factory, admin_user.id, email_question_key="contact_address"
    )
    form_url = route_url(client, "registration.show_registration_form", url_slug=page.url_slug)
    csrf_token = get_csrf_token(client, form_url)
    adapter = FakeEmailAdapter()
    with patch("opendlp.entrypoints.blueprints.registration.bootstrap.get_email_adapter", return_value=adapter):
        response = client.post(
            form_url,
            data={"csrf_token": csrf_token, "name": "Ada Lovelace", "contact_address": "ada-question@example.com"},
        )
    assert response.status_code == 302

    assert adapter.sent[0]["to"] == ["ada-question@example.com"]
    assert "Hi Ada Lovelace," in adapter.sent[0]["html_body"]
    record = _only_record(postgres_session_factory, page.assembly_id)
    assert record.to_email == "ada-question@example.com"


def test_first_assembly_date_is_written_in_the_respondents_language(
    app: Flask, client: FlaskClient, admin_user, postgres_session_factory
) -> None:
    """The auto-reply is sent while the respondent's request is open, so a date in it
    follows the language they registered in."""
    # The shared app is built before the per-test env scrub, so its LANGUAGES can
    # come from a developer's SUPPORTED_LANGUAGES. The autouse
    # _restore_shared_app_state fixture puts the config back.
    app.config["LANGUAGES"] = ["en", "de"]
    page = _build_published_page_with_auto_reply(
        postgres_session_factory,
        admin_user.id,
        body_html="<p>We start on {{ assembly.first_assembly_date_text }}.</p>",
    )
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        first_date = uow.assemblies.get(page.assembly_id).first_assembly_date
    form_url = route_url(client, "registration.show_registration_form", url_slug=page.url_slug)
    client.get(f"{form_url}?lang=de")
    csrf_token = get_csrf_token(client, form_url)
    adapter = FakeEmailAdapter()
    with patch("opendlp.entrypoints.blueprints.registration.bootstrap.get_email_adapter", return_value=adapter):
        response = client.post(form_url, data={"csrf_token": csrf_token, "name": "Ada", "email": "ada-de@example.com"})
    assert response.status_code == 302

    assert f"We start on {format_date(first_date, 'long', locale='de')}." in adapter.sent[0]["html_body"]
