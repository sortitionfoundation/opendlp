"""ABOUTME: Unit tests for the registration page service layer
ABOUTME: Covers management functions, public lookup and visibility resolution"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import DEFAULT_THANK_YOU_HTML, RegistrationPage, RegistrationPageSource
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

    def test_update_slug_rejected_when_published(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        with pytest.raises(ValueError, match="published"):
            service.update_registration_page(uow, admin.id, assembly.id, url_slug="new-slug")

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
        assert page.is_published is True

    def test_publish_raises_not_ready_with_problems(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)

        with pytest.raises(RegistrationPageNotReady) as exc_info:
            service.publish_registration_page(uow, admin.id, assembly.id)
        # No url_slug and empty form HTML are both reported.
        assert len(exc_info.value.problems) >= 2

    def test_unpublish_happy_path(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _create_published_page(uow, admin, assembly)

        page = service.unpublish_registration_page(uow, admin.id, assembly.id)
        assert page.is_published is False

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


class TestRegeneratePreviewToken:
    def test_token_changes_and_is_persisted(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        created = service.create_registration_page(uow, admin.id, assembly.id)

        updated = service.regenerate_preview_token(uow, admin.id, assembly.id)
        assert updated.preview_token != created.preview_token
        stored = uow.registration_pages.get_by_assembly_id(assembly.id)
        assert stored.preview_token == updated.preview_token

    def test_requires_manage_permission(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id)
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.regenerate_preview_token(uow, viewer.id, assembly.id)

    def test_raises_when_page_not_created(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.regenerate_preview_token(uow, admin.id, assembly.id)


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
    def test_not_found_is_not_visible(self):
        result = service.resolve_visibility(None)
        assert result.is_visible is False
        assert result.is_preview is False
        assert result.page is None

    def test_published_is_visible(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", is_published=True)
        result = service.resolve_visibility(page)
        assert result.is_visible is True
        assert result.is_preview is False

    def test_unpublished_with_matching_token_is_preview(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), preview_token="secret")
        result = service.resolve_visibility(page, preview_token="secret")
        assert result.is_visible is True
        assert result.is_preview is True

    def test_unpublished_with_wrong_token_is_not_visible(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), preview_token="secret")
        result = service.resolve_visibility(page, preview_token="wrong")
        assert result.is_visible is False

    def test_unpublished_with_empty_token_is_not_visible(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), preview_token="secret")
        result = service.resolve_visibility(page, preview_token="")
        assert result.is_visible is False


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
