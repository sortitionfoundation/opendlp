# ABOUTME: Component tests for the backoffice auto-reply email editor route and its context loading
# ABOUTME: Drives the real Flask route + email_template_service over a FakeUnitOfWork via a logged-in client

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageStatus,
)
from opendlp.entrypoints.blueprints import backoffice_registration as be_reg
from opendlp.service_layer.exceptions import EmailTemplateInvalid, EmailTemplateNotFoundError
from tests.fakes import FakeUnitOfWork


def _seed_page(
    fake_store, assembly_id, *, url_slug="my-slug", form_html="<p>form</p>", auto_reply_template_id=None
) -> RegistrationPage:
    page = RegistrationPage(
        assembly_id=assembly_id,
        url_slug=url_slug,
        status=RegistrationPageStatus.TEST,
        auto_reply_email_template_id=auto_reply_template_id,
    )
    html = RegistrationPageHtml(registration_page_id=page.id, form_html=form_html)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(html)
        uow.commit()
    return page


def _seed_template(
    fake_store,
    assembly_id,
    *,
    name="Registration auto-reply",
    subject="Hi {{ respondent.first_name_or_friend }}",
    body_html="<p>Body</p>",
) -> EmailTemplate:
    template = EmailTemplate(assembly_id=assembly_id, name=name, subject=subject, body_html=body_html)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.email_templates.add(template)
        uow.commit()
    return template


def _get_page(fake_store, assembly_id) -> RegistrationPage:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.registration_pages.get_by_assembly_id(assembly_id).create_detached_copy()


def _get_template(fake_store, template_id) -> EmailTemplate | None:
    with FakeUnitOfWork(store=fake_store) as uow:
        template = uow.email_templates.get(template_id)
        return template.create_detached_copy() if template else None


def _list_templates(fake_store, assembly_id) -> list[EmailTemplate]:
    with FakeUnitOfWork(store=fake_store) as uow:
        return [t.create_detached_copy() for t in uow.email_templates.list_by_assembly(assembly_id)]


def _patch_current_user(user_id):
    return patch(
        "opendlp.entrypoints.blueprints.backoffice_registration.current_user",
        SimpleNamespace(id=user_id),
    )


@pytest.fixture
def assembly_id(existing_assembly):
    return existing_assembly.id


class TestCreateAction:
    """action=create seeds a default template, assigns it, and drops the user in edit mode."""

    def test_creates_template_with_default_content_and_assigns_it(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "create"},
        )

        assert response.status_code == 302
        # Lands in edit mode on the email step so the manager can customise straight away.
        assert "section=email" in response.location
        assert "edit=1" in response.location

        templates = _list_templates(fake_store, assembly_id)
        assert len(templates) == 1
        template = templates[0]
        assert template.name  # non-empty default name
        assert "{{ assembly.title }}" in template.subject
        assert "{{ respondent.first_name_or_friend }}" in template.body_html

        page = _get_page(fake_store, assembly_id)
        assert page.auto_reply_email_template_id == template.id


class TestSaveAction:
    """action=save updates fields on the existing template; save_and_next also advances step."""

    def test_save_updates_subject_and_body_without_touching_name(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id, name="Original name")
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={
                "action": "save",
                "template_subject": "New subject",
                "template_body_html": "<p>New body</p>",
            },
        )

        assert response.status_code == 302
        assert "section=email" in response.location
        assert "edit=1" not in response.location

        saved = _get_template(fake_store, template.id)
        assert saved.subject == "New subject"
        assert saved.body_html == "<p>New body</p>"
        # Name is deliberately NOT overwritten from the form — the UI doesn't expose it.
        assert saved.name == "Original name"

    def test_save_and_next_redirects_to_preview(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={
                "action": "save_and_next",
                "template_subject": "Updated subject",
                "template_body_html": "<p>Updated body</p>",
            },
        )

        assert response.status_code == 302
        assert "section=preview" in response.location
        # save_and_next still saves the data.
        saved = _get_template(fake_store, template.id)
        assert saved.subject == "Updated subject"

    def test_save_uses_posted_template_id_when_none_assigned(self, logged_in_admin, fake_store, assembly_id):
        # Template exists for the assembly but auto-reply is off. The editor form
        # posts template_id so save/enable work on the currently-displayed template.
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=None)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={
                "action": "save",
                "template_id": str(template.id),
                "template_subject": "Subject via form-supplied id",
                "template_body_html": "<p>Body via form-supplied id</p>",
            },
        )

        assert response.status_code == 302
        saved = _get_template(fake_store, template.id)
        assert saved.subject == "Subject via form-supplied id"

    def test_save_with_no_template_flashes_warning(self, logged_in_admin, fake_store, assembly_id):
        # Page exists but no email template exists yet — save is a no-op with a hint.
        _seed_page(fake_store, assembly_id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={
                "action": "save",
                "template_subject": "Nope",
                "template_body_html": "<p>Nope</p>",
            },
        )

        assert response.status_code == 302
        assert "section=email" in response.location
        assert _list_templates(fake_store, assembly_id) == []


class TestEnableDisableActions:
    """The switch above the editor posts action=enable/disable to flip the assignment FK."""

    def test_enable_assigns_the_posted_template(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=None)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "enable", "template_id": str(template.id)},
        )

        assert response.status_code == 302
        assert "section=email" in response.location
        page = _get_page(fake_store, assembly_id)
        assert page.auto_reply_email_template_id == template.id

    def test_enable_without_template_id_or_assignment_flashes_warning(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, auto_reply_template_id=None)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "enable"},
        )

        assert response.status_code == 302
        page = _get_page(fake_store, assembly_id)
        # Nothing to enable, nothing gets assigned.
        assert page.auto_reply_email_template_id is None

    def test_disable_unassigns_current_template(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "disable"},
        )

        assert response.status_code == 302
        page = _get_page(fake_store, assembly_id)
        assert page.auto_reply_email_template_id is None
        # The template itself is kept so re-enabling later is one click.
        assert _get_template(fake_store, template.id) is not None


class TestErrorHandling:
    def test_invalid_template_returns_to_edit_mode_with_flash(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.update_email_template",
            side_effect=EmailTemplateInvalid(["subject must not be empty"]),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/email/save",
                data={"action": "save", "template_subject": "", "template_body_html": "<p></p>"},
            )

        assert response.status_code == 302
        # Lands back in edit mode so the manager can fix the problem.
        assert "section=email" in response.location
        assert "edit=1" in response.location

    def test_email_template_not_found_flashes_error_and_redirects(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.update_email_template",
            side_effect=EmailTemplateNotFoundError("gone"),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/email/save",
                data={"action": "save", "template_subject": "x", "template_body_html": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "section=email" in response.location
        assert "edit=1" not in response.location

    def test_no_registration_page_redirects_to_assembly_view(self, logged_in_admin, fake_store, assembly_id):
        # No page seeded — dispatch raises RegistrationPageNotFoundError, caller falls
        # back to the Details tab.
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "create"},
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}" in response.location
        assert "/registration/email" not in response.location

    def test_non_admin_is_redirected_off_the_backoffice(self, logged_in_user, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        response = logged_in_user.post(
            f"/backoffice/assembly/{assembly_id}/registration/email/save",
            data={"action": "save", "template_subject": "x", "template_body_html": "<p>x</p>"},
        )

        assert response.status_code == 302
        # Redirects to the dashboard (via the InsufficientPermissions handler).
        assert "/backoffice/assembly" not in response.location or "/registration" not in response.location

    def test_unexpected_error_lands_on_email_section(self, logged_in_admin, fake_store, assembly_id):
        template = _seed_template(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, auto_reply_template_id=template.id)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.update_email_template",
            side_effect=RuntimeError("boom"),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/email/save",
                data={"action": "save", "template_subject": "x", "template_body_html": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "section=email" in response.location


class TestLoadAutoReplyContext:
    """The view route falls back to list_email_templates()[0] when nothing is assigned."""

    def test_returns_assigned_template_and_enabled_true(self, app, fake_store, admin_user, existing_assembly):
        template = _seed_template(fake_store, existing_assembly.id)
        _seed_page(fake_store, existing_assembly.id, auto_reply_template_id=template.id)
        page = _get_page(fake_store, existing_assembly.id)

        with app.test_request_context(), _patch_current_user(admin_user.id):
            loaded, enabled, problems = be_reg._load_auto_reply_context(page, existing_assembly.id)

        assert loaded.id == template.id
        assert enabled is True
        assert isinstance(problems, list)

    def test_falls_back_to_first_template_when_none_assigned(self, app, fake_store, admin_user, existing_assembly):
        template = _seed_template(fake_store, existing_assembly.id)
        _seed_page(fake_store, existing_assembly.id, auto_reply_template_id=None)
        page = _get_page(fake_store, existing_assembly.id)

        with app.test_request_context(), _patch_current_user(admin_user.id):
            loaded, enabled, problems = be_reg._load_auto_reply_context(page, existing_assembly.id)

        assert loaded.id == template.id
        assert enabled is False
        assert isinstance(problems, list)

    def test_returns_none_when_no_registration_page(self, fake_store, existing_assembly):
        loaded, enabled, problems = be_reg._load_auto_reply_context(None, existing_assembly.id)
        assert loaded is None
        assert enabled is False
        assert problems == []

    def test_falls_back_to_first_template_when_assigned_template_lookup_fails(
        self, app, fake_store, admin_user, existing_assembly
    ):
        # Assigned template id points at nothing (data drift). We still surface the
        # first available template so the manager can edit rather than seeing an empty state.
        stray_id = uuid.uuid4()
        fallback = _seed_template(fake_store, existing_assembly.id, name="Fallback")
        _seed_page(fake_store, existing_assembly.id, auto_reply_template_id=stray_id)
        page = _get_page(fake_store, existing_assembly.id)

        with (
            app.test_request_context(),
            _patch_current_user(admin_user.id),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.get_email_template",
                side_effect=EmailTemplateNotFoundError("gone"),
            ),
        ):
            loaded, enabled, _problems = be_reg._load_auto_reply_context(page, existing_assembly.id)

        assert loaded.id == fallback.id
        assert enabled is False


class TestCreateDefaultAutoReplyTemplate:
    """The best-effort seed on page creation should never propagate exceptions to the caller."""

    def test_seed_failure_is_swallowed_and_page_creation_still_succeeds(self, logged_in_admin, fake_store, assembly_id):
        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.create_email_template",
            side_effect=RuntimeError("db down"),
        ):
            response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")

        assert response.status_code == 302
        # The page still gets created even though seeding the template failed.
        with FakeUnitOfWork(store=fake_store) as uow:
            page = uow.registration_pages.get_by_assembly_id(assembly_id)
        assert page is not None
        # No template got persisted.
        assert _list_templates(fake_store, assembly_id) == []


class TestPageCreationSeedsDefaultTemplate:
    """POST to /registration/create seeds a default email template as a side effect."""

    def test_create_page_route_seeds_default_template(self, logged_in_admin, fake_store, assembly_id):
        response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/create")

        assert response.status_code == 302
        templates = _list_templates(fake_store, assembly_id)
        assert len(templates) == 1
        # Not assigned — the switch starts OFF; the manager can review before enabling.
        page = _get_page(fake_store, assembly_id)
        assert page.auto_reply_email_template_id is None
