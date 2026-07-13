"""ABOUTME: E2E smoke test for the Registration stepper's happy-path journey
ABOUTME: Walks admin through: create page → seed template → save form → save email → publish, over PostgreSQL"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.registration_page import RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly, update_assembly
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture(autouse=True)
def enable_registration_feature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()


def _seed_assembly_with_required_email(postgres_session_factory, admin_id):
    """Assembly with reply-to configured and an email field required on the form,
    so the auto-reply readiness check reports no problems."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Stepper Journey Assembly",
            created_by_user_id=admin_id,
            question="Does the journey work?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly_id,
                field_key="email",
                label="Email",
                group=RespondentFieldGroup.OTHER,
                sort_order=10,
                field_type=FieldType.EMAIL,
                is_fixed=True,
                on_registration_page=FieldOnRegistrationPage.YES_REQUIRED,
            )
        )
        uow.commit()

    update_assembly(
        SqlAlchemyUnitOfWork(postgres_session_factory),
        assembly_id,
        admin_id,
        reply_to_name="The Team",
        reply_to_email="team@example.com",
    )
    return assembly_id


READY_FORM_HTML = (
    '<form action="{{ form_action }}" method="post">{{ csrf_form_element }}'
    '<label for="email">Email</label><input id="email" name="email" type="email">'
    '<button type="submit">Register</button></form>'
)


def test_admin_walks_form_email_preview_and_publishes(logged_in_admin, admin_user, postgres_session_factory):
    """A single happy-path smoke: admin creates a registration page (which auto-seeds a
    default email template), saves the form HTML on step 1, updates the email template on
    step 2, then hits Publish from step 3. The page ends up PUBLISHED with the manager's
    edits persisted."""
    assembly_id = _seed_assembly_with_required_email(postgres_session_factory, admin_user.id)

    # Step 0: create the registration page. Route seeds a default email template
    # as a side effect (unassigned — the switch defaults to OFF).
    response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        assert page is not None, "page should have been created"
        assert page.auto_reply_email_template_id is None, "seeded template starts unassigned"
        seeded = uow.email_templates.list_by_assembly(assembly_id)
        assert len(seeded) == 1, "creation should seed exactly one default template"

    # Step 1: save the form HTML with save_and_next. Redirects to the email section.
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/save",
        data={"action": "save_and_next", "html_content": READY_FORM_HTML},
    )
    assert response.status_code == 302
    assert "section=email" in response.location

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        html = uow.registration_page_html_sources.get_by_page_id(page.id).create_detached_copy()
    assert "Email" in html.form_html

    # Step 2: enable the auto-reply and save updated copy with save_and_next.
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        template = uow.email_templates.list_by_assembly(assembly_id)[0].create_detached_copy()
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/email/save",
        data={"action": "enable", "template_id": str(template.id)},
    )
    assert response.status_code == 302

    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/email/save",
        data={
            "action": "save_and_next",
            "template_subject": "Thanks {{ respondent.first_name_or_friend }}!",
            "template_body_html": "<p>See you at {{ assembly.title }}.</p>",
        },
    )
    assert response.status_code == 302
    assert "section=preview" in response.location

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id).create_detached_copy()
        template = uow.email_templates.get(page.auto_reply_email_template_id).create_detached_copy()
    assert page.auto_reply_email_template_id == template.id
    assert "Thanks" in template.subject
    assert "assembly.title" in template.body_html

    # Step 3: publish. Same save endpoint, no html_content payload (guard skips update).
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/save",
        data={"action": "publish"},
    )
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id).create_detached_copy()
    assert page.status == RegistrationPageStatus.PUBLISHED
