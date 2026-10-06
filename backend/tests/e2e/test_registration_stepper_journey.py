"""ABOUTME: E2E smoke test for the Registration stepper's happy-path journey
ABOUTME: Walks admin through: create page → seed template → save form → save email → publish, over PostgreSQL"""

from datetime import UTC, datetime, timedelta

import pytest

from opendlp import bootstrap
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole
from opendlp.entrypoints.blueprints import backoffice_registration as route_module
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.assembly_service import create_assembly, update_assembly
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.registration_page_service import page_for_assembly
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

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        update_assembly(
            uow,
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
    # as a side effect and assigns it — the auto-reply is always-on.
    response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id)
        assert page is not None, "page should have been created"
        seeded = uow.email_templates.list_by_assembly(assembly_id)
        assert len(seeded) == 1, "creation should seed exactly one default template"
        assert page.auto_reply_email_template_id == seeded[0].id, "seeded template is assigned (always-on)"
        slug = page.url_slug

    # Step 1: save the form HTML with save_and_next. Redirects to the email section.
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/save",
        data={"action": "save_and_next", "html_content": READY_FORM_HTML},
    )
    assert response.status_code == 302
    assert "section=email" in response.location

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id)
        html = uow.registration_page_html_sources.get_by_page_id(page.id).create_detached_copy()
    assert "Email" in html.form_html

    # Step 2: save updated auto-reply copy with save_and_next (it is already
    # assigned and always-on — there is no enable step).
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/save",
        data={
            "action": "save_and_next",
            "template_subject": "Thanks {{ respondent.first_name_or_friend }}!",
            "template_body_html": "<p>See you at {{ assembly.title }}.</p>",
        },
    )
    assert response.status_code == 302
    assert "section=preview" in response.location

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id).create_detached_copy()
        template = uow.email_templates.get(page.auto_reply_email_template_id).create_detached_copy()
    assert page.auto_reply_email_template_id == template.id
    assert "Thanks" in template.subject
    assert "assembly.title" in template.body_html

    # The manager sees the test-send card on the (non-closed) email section.
    page_text = logged_in_admin.get(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}?section=email",
    ).get_data(as_text=True)
    assert "Send a test email" in page_text

    # Step 2b: send a test of the saved auto-reply. The console email adapter is
    # active in tests, so the send itself succeeds and the success flash shows.
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/send-test",
        data={"test_email_to": "manager@example.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Test email sent to manager@example.com" in response.get_data(as_text=True)

    # An invalid recipient is rejected with a flash, not a send.
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/send-test",
        data={"test_email_to": "not-an-email"},
        follow_redirects=True,
    )
    assert "Enter a valid email address" in response.get_data(as_text=True)

    # Step 3: publish. Same save endpoint, no html_content payload (guard skips update).
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/save",
        data={"action": "publish"},
    )
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id).create_detached_copy()
    assert page.status == RegistrationPageStatus.PUBLISHED


def test_send_test_email_error_paths(logged_in_admin, admin_user, postgres_session_factory, monkeypatch):
    """Each failure mode of the test-send route surfaces as the right flash message."""
    assembly_id = _seed_assembly_with_required_email(postgres_session_factory, admin_user.id)
    response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")
    assert response.status_code == 302

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        slug = page_for_assembly(uow, assembly_id).url_slug
    send_test_url = f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/send-test"
    data = {"test_email_to": "manager@example.com"}

    # A template variable with no value is flashed back as a warning beside the success flash.
    response = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/save",
        data={"action": "save", "template_subject": "Hi {{ bogus_name }}", "template_body_html": "<p>Hi</p>"},
    )
    assert response.status_code == 302
    text = logged_in_admin.post(send_test_url, data=data, follow_redirects=True).get_data(as_text=True)
    assert "Test email sent to manager@example.com" in text
    assert "bogus_name" in text

    # The adapter declining the send surfaces as an error flash.
    class RefusingAdapter:
        def send_email(self, **kwargs):
            return False

    monkeypatch.setattr(bootstrap, "get_email_adapter", lambda: RefusingAdapter())
    text = logged_in_admin.post(send_test_url, data=data, follow_redirects=True).get_data(as_text=True)
    assert "The test email could not be sent" in text
    monkeypatch.undo()

    # An unexpected service error lands in the generic handler.
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(route_module, "prepare_test_auto_reply", boom)
    text = logged_in_admin.post(send_test_url, data=data, follow_redirects=True).get_data(as_text=True)
    assert "An error occurred while sending the test email" in text

    # A vanished assembly (NotFoundError family) redirects to the dashboard.
    def gone(*args, **kwargs):
        raise AssemblyNotFoundError("gone")

    monkeypatch.setattr(route_module, "prepare_test_auto_reply", gone)
    text = logged_in_admin.post(send_test_url, data=data, follow_redirects=True).get_data(as_text=True)
    assert "Assembly not found" in text
    monkeypatch.undo()

    # An unknown slug is reported and redirects to the page list.
    text = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/no-such-slug/email/send-test",
        data=data,
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "That registration page could not be found" in text

    # A page whose template assignment vanished reports there is nothing to test.
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = uow.registration_pages.get_by_url_slug(slug)
        page.auto_reply_email_template_id = None
        uow.commit()
    text = logged_in_admin.post(send_test_url, data=data, follow_redirects=True).get_data(as_text=True)
    assert "There is no auto-reply email to test yet" in text


def test_send_test_email_requires_manage_permission(logged_in_user, regular_user, admin_user, postgres_session_factory):
    """A read-only assembly member can see the page but a test send is refused.

    A user with no role at all gets 'page not found' instead (the service hides
    pages from non-viewers), so the view-but-not-manage case is the one that
    exercises the route's permission branch.
    """
    assembly_id = _seed_assembly_with_required_email(postgres_session_factory, admin_user.id)
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.registration_pages.add(RegistrationPage(assembly_id=assembly_id, url_slug="perm-check-test-send"))
        viewer = uow.users.get(regular_user.id)
        viewer.assembly_roles.append(
            UserAssemblyRole(user_id=viewer.id, assembly_id=assembly_id, role=AssemblyRole.READ_ONLY)
        )
        uow.commit()

    text = logged_in_user.post(
        f"/backoffice/assembly/{assembly_id}/registration/perm-check-test-send/email/send-test",
        data={"test_email_to": "someone@example.com"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "permission to modify this assembly" in text

    # The view-only member can still open the page, but the manage-only test-send
    # card is not rendered for them.
    page_text = logged_in_user.get(
        f"/backoffice/assembly/{assembly_id}/registration/perm-check-test-send?section=email",
    ).get_data(as_text=True)
    assert "Send a test email" not in page_text


def test_closed_page_hides_and_refuses_test_send(logged_in_admin, admin_user, postgres_session_factory):
    """A CLOSED page goes read-only everywhere: no test-send card, and a posted send is refused."""
    assembly_id = _seed_assembly_with_required_email(postgres_session_factory, admin_user.id)
    logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        page = page_for_assembly(uow, assembly_id)
        page.status = RegistrationPageStatus.CLOSED
        slug = page.url_slug
        uow.commit()

    # The card is gone from the (read-only) CLOSED page.
    page_text = logged_in_admin.get(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}?section=email",
    ).get_data(as_text=True)
    assert "Send a test email" not in page_text

    # A posted send is refused even though the admin can manage the assembly.
    text = logged_in_admin.post(
        f"/backoffice/assembly/{assembly_id}/registration/{slug}/email/send-test",
        data={"test_email_to": "manager@example.com"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "This registration page is closed" in text
