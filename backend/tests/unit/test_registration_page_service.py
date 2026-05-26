"""ABOUTME: Unit tests for the registration page service layer
ABOUTME: Covers management functions, public lookup and visibility resolution"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import (
    DEFAULT_THANK_YOU_HTML,
    RegistrationPage,
    RegistrationPageAction,
    RegistrationPageSource,
    RegistrationPageStatus,
)
from opendlp.domain.respondent_field_schema import (
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import registration_page_service as service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
    RegistrationPageNotReady,
    SlugError,
    UserNotFoundError,
)
from tests.fakes import FakeUnitOfWork

READY_HTML = "<form>{{ csrf_form_element }} {{ form_action }}</form>"


def _admin(uow: FakeUnitOfWork) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def _assembly(uow: FakeUnitOfWork) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    return assembly


def _viewer(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    """A user who can view the assembly but not manage it."""
    user = User(email=f"viewer-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


def _create_published_page(uow: FakeUnitOfWork, user: User, assembly: Assembly) -> RegistrationPage:
    service.create_registration_page(uow, user.id, assembly.id)
    service.update_registration_page_html(uow, user.id, assembly.id, READY_HTML)
    service.update_registration_page(uow, user.id, assembly.id, url_slug="a-page")
    return service.publish_registration_page(uow, user.id, assembly.id)


class TestRegistrationPageNotReadyExport:
    def test_exception_carries_problem_list(self):
        exc = RegistrationPageNotReady(["a problem", "another"])
        assert exc.problems == ["a problem", "another"]


class TestCreateRegistrationPage:
    def test_create_makes_page_and_html_source(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        page = service.create_registration_page(uow, admin.id, assembly.id)

        assert page.assembly_id == assembly.id
        assert page.source_type is RegistrationPageSource.HTML
        assert uow.registration_pages.get_by_assembly_id(assembly.id) is not None
        assert uow.registration_page_html_sources.get_by_page_id(page.id) is not None
        assert uow.committed

    def test_create_seeds_default_thank_you_html(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        page = service.create_registration_page(uow, admin.id, assembly.id)

        assert page.thank_you_html == DEFAULT_THANK_YOU_HTML
        source = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert source is not None
        assert source.form_html == ""

    def test_create_appends_create_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        page = service.create_registration_page(uow, admin.id, assembly.id)

        assert len(page.activity) == 1
        entry = page.activity[0]
        assert entry.action is RegistrationPageAction.CREATE
        assert entry.author_id == admin.id
        assert entry.text

    def test_create_raises_if_already_exists(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="already has a registration page"):
            service.create_registration_page(uow, admin.id, assembly.id)

    def test_create_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.create_registration_page(uow, viewer.id, assembly.id)

    def test_create_raises_assembly_not_found(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        with pytest.raises(AssemblyNotFoundError):
            service.create_registration_page(uow, admin.id, uuid.uuid4())

    def test_create_raises_user_not_found(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)

        with pytest.raises(UserNotFoundError):
            service.create_registration_page(uow, uuid.uuid4(), assembly.id)


class TestGetRegistrationPage:
    def test_returns_none_when_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        assert service.get_registration_page(uow, admin.id, assembly.id) is None

    def test_returns_page_when_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        created = service.create_registration_page(uow, admin.id, assembly.id)

        page = service.get_registration_page(uow, admin.id, assembly.id)
        assert page is not None
        assert page.id == created.id

    def test_viewer_can_read(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        assert service.get_registration_page(uow, viewer.id, assembly.id) is not None

    def test_stranger_cannot_read(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        stranger = User(email="s@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(stranger)

        with pytest.raises(InsufficientPermissions):
            service.get_registration_page(uow, stranger.id, assembly.id)


class TestGetRegistrationPageWithSource:
    def test_returns_none_when_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        assert service.get_registration_page_with_source(uow, admin.id, assembly.id) is None

    def test_returns_page_and_source(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)

        result = service.get_registration_page_with_source(uow, admin.id, assembly.id)
        assert result is not None
        page, source = result
        assert page.assembly_id == assembly.id
        assert source.readiness_problems() == []


class TestUpdateRegistrationPage:
    def test_update_slugs_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug="my-page", short_url_slug="mp")
        assert page.url_slug == "my-page"
        assert page.short_url_slug == "mp"

    def test_update_slug_rejects_duplicate_url_slug(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)
        assembly_a, assembly_b = _assembly(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly_a.id)
        service.create_registration_page(uow, admin.id, assembly_b.id)
        service.update_registration_page(uow, admin.id, assembly_a.id, url_slug="taken")

        with pytest.raises(SlugError, match="already in use") as exc:
            service.update_registration_page(uow, admin.id, assembly_b.id, url_slug="taken")
        assert exc.value.field == "url_slug"
        assert exc.value.reason == "taken"

    def test_update_slug_rejects_duplicate_short_url_slug(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)
        assembly_a, assembly_b = _assembly(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly_a.id)
        service.create_registration_page(uow, admin.id, assembly_b.id)
        service.update_registration_page(uow, admin.id, assembly_a.id, short_url_slug="tk")

        with pytest.raises(SlugError, match="already in use") as exc:
            service.update_registration_page(uow, admin.id, assembly_b.id, short_url_slug="tk")
        assert exc.value.field == "short_url_slug"
        assert exc.value.reason == "taken"

    def test_update_slug_raises_slug_error_on_reserved_value(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(SlugError) as exc:
            service.update_registration_page(uow, admin.id, assembly.id, url_slug="admin")
        assert exc.value.field == "url_slug"
        assert exc.value.reason == "reserved"

    def test_update_slug_raises_slug_error_on_malformed_value(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(SlugError) as exc:
            service.update_registration_page(uow, admin.id, assembly.id, short_url_slug="Bad Slug")
        assert exc.value.field == "short_url_slug"
        assert exc.value.reason == "malformed"

    def test_update_slug_allows_same_page_keeping_its_own_slug(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, url_slug="keep-me")

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug="keep-me")
        assert page.url_slug == "keep-me"

    def test_update_slug_rejected_after_publish(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        with pytest.raises(ValueError, match="published"):
            service.update_registration_page(uow, admin.id, assembly.id, url_slug="new-slug")

    def test_update_slug_still_rejected_after_unpublish(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)
        service.unpublish_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="published"):
            service.update_registration_page(uow, admin.id, assembly.id, url_slug="new-slug")

    def test_update_slug_appends_edit_with_description(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug="my-page")
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert len(edits) == 1
        assert "url_slug" in edits[0].text
        assert "my-page" in edits[0].text
        assert edits[0].author_id == admin.id

    def test_update_slug_no_op_no_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug=None)
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert edits == []

    def test_update_slug_both_changed_one_combined_entry(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug="my-page", short_url_slug="mp")
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert len(edits) == 1
        assert "url_slug" in edits[0].text
        assert "short_url_slug" in edits[0].text

    def test_update_slug_cleared_logs_old_value(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, url_slug="my-page")

        page = service.update_registration_page(uow, admin.id, assembly.id, url_slug="")
        last_edit = [a for a in page.activity if a.action is RegistrationPageAction.EDIT][-1]
        assert "Cleared url_slug" in last_edit.text
        assert "'my-page'" in last_edit.text

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.update_registration_page(uow, viewer.id, assembly.id, url_slug="my-page")

    def test_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.update_registration_page(uow, admin.id, assembly.id, url_slug="my-page")


class TestUpdateThankYouHtml:
    def test_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_thank_you_html(uow, admin.id, assembly.id, "<p>thanks</p>")
        assert page.thank_you_html == "<p>thanks</p>"

    def test_rejects_oversized_html(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="1024")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="at most 1024 bytes"):
            service.update_thank_you_html(uow, admin.id, assembly.id, "<p>" + "x" * 1100 + "</p>")

    def test_appends_edit_when_changed(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_thank_you_html(uow, admin.id, assembly.id, "<p>different</p>")
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert len(edits) == 1
        assert "thank-you HTML" in edits[0].text

    def test_no_op_no_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        page = service.update_thank_you_html(uow, admin.id, assembly.id, DEFAULT_THANK_YOU_HTML)
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert edits == []

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.update_thank_you_html(uow, viewer.id, assembly.id, "<p>thanks</p>")

    def test_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.update_thank_you_html(uow, admin.id, assembly.id, "<p>thanks</p>")


class TestUpdateRegistrationPageHtml:
    def test_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        source = service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)
        assert source.form_html == READY_HTML

    def test_rejects_oversized_html(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="1024")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="at most 1024 bytes"):
            service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML + "x" * 1100)

    def test_appends_edit_when_changed(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)
        page = uow.registration_pages.get_by_assembly_id(assembly.id)
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert len(edits) == 1
        assert "form HTML" in edits[0].text

    def test_no_op_no_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)

        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)
        page = uow.registration_pages.get_by_assembly_id(assembly.id)
        edits = [a for a in page.activity if a.action is RegistrationPageAction.EDIT]
        assert len(edits) == 1

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.update_registration_page_html(uow, viewer.id, assembly.id, READY_HTML)

    def test_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)


class TestPublishAndUnpublish:
    def test_publish_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _create_published_page(uow, admin, assembly)
        assert page.status is RegistrationPageStatus.PUBLISHED
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.PUBLISH
        assert last.author_id == admin.id

    def test_publish_accepts_optional_text(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)
        service.update_registration_page(uow, admin.id, assembly.id, url_slug="a-page")

        page = service.publish_registration_page(uow, admin.id, assembly.id, text="going live")
        assert page.activity[-1].text == "going live"

    def test_publish_raises_not_ready_with_problems(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(RegistrationPageNotReady) as exc_info:
            service.publish_registration_page(uow, admin.id, assembly.id)
        assert len(exc_info.value.problems) >= 2

    def test_unpublish_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        page = service.unpublish_registration_page(uow, admin.id, assembly.id)
        assert page.status is RegistrationPageStatus.TEST
        assert page.activity[-1].action is RegistrationPageAction.UNPUBLISH

    def test_publish_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.publish_registration_page(uow, viewer.id, assembly.id)

    def test_publish_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.publish_registration_page(uow, admin.id, assembly.id)

    def test_unpublish_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.unpublish_registration_page(uow, admin.id, assembly.id)


class TestCloseAndReopen:
    def test_close_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        page = service.close_registration_page(uow, admin.id, assembly.id, text="sortition done")
        assert page.status is RegistrationPageStatus.CLOSED
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.CLOSE
        assert last.text == "sortition done"
        assert last.author_id == admin.id

    def test_close_raises_from_test(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="TEST"):
            service.close_registration_page(uow, admin.id, assembly.id)

    def test_close_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.close_registration_page(uow, viewer.id, assembly.id)

    def test_close_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.close_registration_page(uow, admin.id, assembly.id)

    def test_reopen_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)
        service.close_registration_page(uow, admin.id, assembly.id)

        page = service.reopen_registration_page(uow, admin.id, assembly.id, text="resuming")
        assert page.status is RegistrationPageStatus.PUBLISHED
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.REOPEN
        assert last.text == "resuming"

    def test_reopen_runs_readiness(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)
        service.close_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page_html(uow, admin.id, assembly.id, "")

        with pytest.raises(RegistrationPageNotReady):
            service.reopen_registration_page(uow, admin.id, assembly.id)

    def test_reopen_raises_from_published(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        with pytest.raises(ValueError, match="PUBLISHED"):
            service.reopen_registration_page(uow, admin.id, assembly.id)

    def test_reopen_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)
        service.close_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.reopen_registration_page(uow, viewer.id, assembly.id)

    def test_reopen_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.reopen_registration_page(uow, admin.id, assembly.id)


class TestPublicLookup:
    def test_find_by_url_slug_hit(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, url_slug="public-page")

        page = service.find_registration_page_by_url_slug(uow, "public-page")
        assert page is not None
        assert page.assembly_id == assembly.id

    def test_find_by_url_slug_miss(self):
        uow = FakeUnitOfWork()
        assert service.find_registration_page_by_url_slug(uow, "nope") is None

    def test_find_by_url_slug_empty_input(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        assert service.find_registration_page_by_url_slug(uow, "") is None

    def test_find_by_short_url_slug_hit(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, short_url_slug="pp")

        page = service.find_registration_page_by_short_url_slug(uow, "pp")
        assert page is not None
        assert page.assembly_id == assembly.id

    def test_find_by_short_url_slug_miss(self):
        uow = FakeUnitOfWork()
        assert service.find_registration_page_by_short_url_slug(uow, "no") is None

    def test_find_by_short_url_slug_empty_input(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        assert service.find_registration_page_by_short_url_slug(uow, "") is None


class TestResolveVisibility:
    def test_none_page_is_not_found(self):
        result = service.resolve_visibility(None)
        assert result.state is service.RegistrationPageVisibilityState.NOT_FOUND
        assert result.is_visible is False
        assert result.is_test is False
        assert result.page is None

    def test_published_is_live(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", status=RegistrationPageStatus.PUBLISHED)
        result = service.resolve_visibility(page)
        assert result.state is service.RegistrationPageVisibilityState.LIVE
        assert result.is_visible is True
        assert result.is_test is False

    def test_test_status_is_test_state(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", status=RegistrationPageStatus.TEST)
        result = service.resolve_visibility(page)
        assert result.state is service.RegistrationPageVisibilityState.TEST
        assert result.is_visible is True
        assert result.is_test is True

    def test_empty_url_slug_is_not_found(self):
        # A freshly created page is TEST with no slug; it must not be visible.
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="", status=RegistrationPageStatus.TEST)
        result = service.resolve_visibility(page)
        assert result.state is service.RegistrationPageVisibilityState.NOT_FOUND
        assert result.is_visible is False

    def test_empty_url_slug_is_not_found_even_when_published(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="", status=RegistrationPageStatus.PUBLISHED)
        result = service.resolve_visibility(page)
        assert result.state is service.RegistrationPageVisibilityState.NOT_FOUND
        assert result.is_visible is False

    def test_closed_is_closed(self):
        page = RegistrationPage(
            assembly_id=uuid.uuid4(),
            url_slug="a-page",
            status=RegistrationPageStatus.CLOSED,
        )
        result = service.resolve_visibility(page)
        assert result.state is service.RegistrationPageVisibilityState.CLOSED
        assert result.is_visible is False
        assert result.is_test is False


class TestGetPageAndSourceForRender:
    def test_returns_source_for_page(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page_html(uow, admin.id, assembly.id, READY_HTML)
        page = uow.registration_pages.get_by_assembly_id(assembly.id)

        source = service.get_page_and_source_for_render(uow, page)
        assert source.readiness_problems() == []


class TestRenderThankYouHtml:
    def test_returns_thank_you_html_verbatim(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), thank_you_html="<p>thanks {{ name }}</p>")
        assert service.render_thank_you_html(page) == "<p>thanks {{ name }}</p>"


def _add_field(uow: FakeUnitOfWork, assembly_id: uuid.UUID, field_key: str, sort_order: int = 0) -> None:
    uow.respondent_field_definitions.add(
        RespondentFieldDefinition(
            assembly_id=assembly_id,
            field_key=field_key,
            label=field_key.replace("_", " ").title(),
            group=RespondentFieldGroup.NAME_AND_CONTACT,
            sort_order=sort_order,
            field_type=FieldType.TEXT,
        )
    )


class TestGenerateStarterFormHtml:
    def test_happy_path_includes_field_names(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _add_field(uow, assembly.id, "first_name", sort_order=0)
        _add_field(uow, assembly.id, "last_name", sort_order=10)

        html = service.generate_starter_form_html(uow, admin.id, assembly.id)

        assert 'name="first_name"' in html
        assert 'name="last_name"' in html
        assert "{{ csrf_form_element }}" in html
        assert "{{ form_action }}" in html

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        _admin(uow)
        assembly = _assembly(uow)
        _add_field(uow, assembly.id, "first_name")
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.generate_starter_form_html(uow, viewer.id, assembly.id)

    def test_assembly_not_found(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        with pytest.raises(AssemblyNotFoundError):
            service.generate_starter_form_html(uow, admin.id, uuid.uuid4())

    def test_user_not_found(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)

        with pytest.raises(UserNotFoundError):
            service.generate_starter_form_html(uow, uuid.uuid4(), assembly.id)

    def test_empty_schema_returns_minimal_form(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        html = service.generate_starter_form_html(uow, admin.id, assembly.id)

        assert "{{ csrf_form_element }}" in html
        assert "{{ form_action }}" in html
        assert '<button type="submit">Register</button>' in html

    def test_only_returns_fields_for_target_assembly(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)
        assembly_a, assembly_b = _assembly(uow), _assembly(uow)
        _add_field(uow, assembly_a.id, "alpha")
        _add_field(uow, assembly_b.id, "beta")

        html = service.generate_starter_form_html(uow, admin.id, assembly_a.id)

        assert 'name="alpha"' in html
        assert 'name="beta"' not in html

    def test_does_not_commit(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _add_field(uow, assembly.id, "first_name")

        service.generate_starter_form_html(uow, admin.id, assembly.id)

        assert uow.committed is False


class TestSlugify:
    def test_simple_text(self):
        assert service._slugify("Hello World") == "hello-world"

    def test_removes_apostrophes(self):
        assert service._slugify("Citizens' Assembly") == "citizens-assembly"

    def test_removes_special_chars(self):
        assert service._slugify("Dublin 2026!") == "dublin-2026"

    def test_collapses_multiple_hyphens(self):
        assert service._slugify("One -- Two --- Three") == "one-two-three"

    def test_strips_leading_trailing_hyphens(self):
        assert service._slugify("---leading-trailing---") == "leading-trailing"

    def test_handles_underscores(self):
        assert service._slugify("with_underscores") == "with-underscores"

    def test_empty_string(self):
        assert service._slugify("") == ""

    def test_only_special_chars(self):
        assert service._slugify("!@#$%") == ""


class TestGenerateUrlSlugFromName:
    def test_simple_name(self):
        assert service.generate_url_slug_from_name("Test Assembly") == "test-assembly"

    def test_truncates_to_max_length(self):
        slug = service.generate_url_slug_from_name("Dublin Citizens Assembly on Housing 2026", max_length=25)
        assert len(slug) <= 25
        assert slug == "dublin-citizens-assembly"

    def test_truncates_long_first_word(self):
        slug = service.generate_url_slug_from_name("supercalifragilisticexpialidocious", max_length=25)
        assert len(slug) == 25
        assert slug == "supercalifragilisticexpial"[:25]

    def test_empty_name(self):
        assert service.generate_url_slug_from_name("") == ""

    def test_special_chars_only_returns_empty(self):
        assert service.generate_url_slug_from_name("!@#$%") == ""

    def test_keeps_full_words_within_limit(self):
        # "dublin-citizens" = 15 chars, adding "-assembly" = 24 chars (OK)
        slug = service.generate_url_slug_from_name("Dublin Citizens Assembly on Housing", max_length=25)
        assert slug == "dublin-citizens-assembly"


class TestGenerateShortUrlSlug:
    def test_returns_6_digit_string(self):
        slug = service.generate_short_url_slug()
        assert len(slug) == 6
        assert slug.isdigit()

    def test_returns_different_values(self):
        slugs = {service.generate_short_url_slug() for _ in range(10)}
        assert len(slugs) > 1  # Very unlikely to get all the same


class TestGenerateUniqueUrlSlug:
    def test_returns_base_slug_when_available(self):
        uow = FakeUnitOfWork()
        slug = service.generate_unique_url_slug(uow, "my-assembly")
        assert slug == "my-assembly"

    def test_appends_suffix_on_collision(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, url_slug="taken-slug")

        slug = service.generate_unique_url_slug(uow, "taken-slug")
        assert slug == "taken-slug-2"

    def test_increments_suffix_on_multiple_collisions(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)
        # Create multiple assemblies with sequential slugs
        for i in range(1, 4):
            assembly = _assembly(uow)
            service.create_registration_page(uow, admin.id, assembly.id)
            slug = "popular-name" if i == 1 else f"popular-name-{i}"
            service.update_registration_page(uow, admin.id, assembly.id, url_slug=slug)

        slug = service.generate_unique_url_slug(uow, "popular-name")
        assert slug == "popular-name-4"

    def test_generates_random_fallback_when_empty(self):
        uow = FakeUnitOfWork()
        slug = service.generate_unique_url_slug(uow, "")
        assert slug.startswith("assembly-")
        assert len(slug) > 10  # assembly- + 6 digits


class TestGenerateUniqueShortUrlSlug:
    def test_returns_unique_6_digit_slug(self):
        uow = FakeUnitOfWork()
        slug = service.generate_unique_short_url_slug(uow)
        assert len(slug) == 6
        assert slug.isdigit()

    def test_retries_on_collision(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        service.update_registration_page(uow, admin.id, assembly.id, short_url_slug="123456")

        # Should still be able to generate a unique one
        slug = service.generate_unique_short_url_slug(uow)
        assert slug != "123456"
        assert len(slug) == 6


class TestCreateRegistrationPageWithSlugs:
    def test_creates_page_with_auto_generated_slugs(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)
        assembly = Assembly(title="Dublin Citizens Assembly", question="?", status=AssemblyStatus.ACTIVE)
        uow.assemblies.add(assembly)

        page = service.create_registration_page_with_slugs(uow, admin.id, assembly.id)

        assert page.url_slug != ""
        assert page.short_url_slug != ""
        assert len(page.short_url_slug) == 6
        assert page.url_slug == "dublin-citizens-assembly"
        assert uow.committed

    def test_generates_unique_slug_on_collision(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        # Create first assembly with same-ish name
        assembly1 = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
        uow.assemblies.add(assembly1)
        page1 = service.create_registration_page_with_slugs(uow, admin.id, assembly1.id)

        # Create second assembly with same name
        assembly2 = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
        uow.assemblies.add(assembly2)
        page2 = service.create_registration_page_with_slugs(uow, admin.id, assembly2.id)

        assert page1.url_slug == "test-assembly"
        assert page2.url_slug == "test-assembly-2"

    def test_raises_if_page_already_exists(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page_with_slugs(uow, admin.id, assembly.id)

        with pytest.raises(ValueError, match="already has a registration page"):
            service.create_registration_page_with_slugs(uow, admin.id, assembly.id)

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.create_registration_page_with_slugs(uow, viewer.id, assembly.id)

    def test_appends_create_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        page = service.create_registration_page_with_slugs(uow, admin.id, assembly.id)

        assert len(page.activity) == 1
        assert page.activity[0].action is RegistrationPageAction.CREATE
