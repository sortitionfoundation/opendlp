"""ABOUTME: Unit tests for addressing registration pages by page id rather than assembly
ABOUTME: Covers listing, creation of several pages, duplication, deletion and bulk status changes"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import (
    RegistrationPageAction,
    RegistrationPageStatus,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import registration_page_service as service
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    RegistrationPageNotFoundError,
)
from tests.fakes import FakeUnitOfWork

READY_HTML = "<form>{{ csrf_form_element }} {{ form_action }}</form>"


def _admin(uow: FakeUnitOfWork) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def _assembly(uow: FakeUnitOfWork, title: str = "Climate Assembly") -> Assembly:
    assembly = Assembly(title=title, question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    return assembly


def _viewer(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"viewer-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


def _stranger(uow: FakeUnitOfWork) -> User:
    user = User(email=f"stranger-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    uow.users.add(user)
    return user


def _ready_page(uow: FakeUnitOfWork, user: User, assembly: Assembly, name: str, slug: str):  # type: ignore[no-untyped-def]
    """A page with valid HTML and a slug, so it is publishable."""
    page = service.create_registration_page(uow, user.id, assembly.id, name=name)
    service.update_registration_page_html(uow, user.id, page.id, READY_HTML)
    return service.update_registration_page(uow, user.id, page.id, url_slug=slug)


class TestListRegistrationPages:
    def test_empty_when_assembly_has_no_pages(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        assert service.list_registration_pages(uow, admin.id, assembly.id) == []

    def test_lists_every_page_of_the_assembly(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        english = service.create_registration_page(uow, admin.id, assembly.id, name="English")
        spanish = service.create_registration_page(uow, admin.id, assembly.id, name="Español")

        pages = service.list_registration_pages(uow, admin.id, assembly.id)
        assert [p.id for p in pages] == [english.id, spanish.id]

    def test_viewer_can_list(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id, name="English")
        viewer = _viewer(uow, assembly)

        assert len(service.list_registration_pages(uow, viewer.id, assembly.id)) == 1

    def test_stranger_cannot_list(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id, name="English")

        with pytest.raises(InsufficientPermissions):
            service.list_registration_pages(uow, _stranger(uow).id, assembly.id)


class TestCreateSeveralPages:
    def test_an_assembly_may_have_many_pages(self, uow):
        """The constraint this whole change exists to remove."""
        admin, assembly = _admin(uow), _assembly(uow)

        service.create_registration_page(uow, admin.id, assembly.id, name="Variant A")
        service.create_registration_page(uow, admin.id, assembly.id, name="Variant B")

        assert len(service.list_registration_pages(uow, admin.id, assembly.id)) == 2

    def test_create_records_name_and_language(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        page = service.create_registration_page(uow, admin.id, assembly.id, name="Español", language="es")

        assert page.name == "Español"
        assert page.language == "es"

    def test_create_rejects_an_empty_name(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(ValueError, match="name"):
            service.create_registration_page(uow, admin.id, assembly.id, name="   ")

    def test_create_rejects_a_duplicate_name_within_the_assembly(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id, name="English")

        with pytest.raises(ValueError, match="already"):
            service.create_registration_page(uow, admin.id, assembly.id, name="English")

    def test_the_same_name_is_fine_in_a_different_assembly(self, uow):
        admin = _admin(uow)
        first, second = _assembly(uow, "First"), _assembly(uow, "Second")
        service.create_registration_page(uow, admin.id, first.id, name="English")

        page = service.create_registration_page(uow, admin.id, second.id, name="English")
        assert page.assembly_id == second.id


class TestSlugGeneration:
    def test_slug_uses_the_language_code_as_suffix(self, uow):
        """Non-ASCII page names mangle badly, so a language code is preferred."""
        admin, assembly = _admin(uow), _assembly(uow, "Climate Assembly")

        page = service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="Čeština", language="cs")

        assert page.url_slug == "climate-assembly-cs"

    def test_a_lone_page_without_a_language_keeps_a_clean_slug(self, uow):
        admin, assembly = _admin(uow), _assembly(uow, "Climate Assembly")

        page = service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="Variant A")

        assert page.url_slug == "climate-assembly"

    def test_a_later_page_without_a_language_falls_back_to_its_name(self, uow):
        """Reads better than the numeric fallback once the base slug is taken."""
        admin, assembly = _admin(uow), _assembly(uow, "Climate Assembly")
        service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="Variant A")

        second = service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="Variant B")

        assert second.url_slug == "climate-assembly-variant-b"

    def test_slugs_stay_unique_across_pages(self, uow):
        admin, assembly = _admin(uow), _assembly(uow, "Climate Assembly")

        first = service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="A", language="en")
        second = service.create_registration_page_with_slugs(uow, admin.id, assembly.id, name="B", language="en")

        assert first.url_slug != second.url_slug
        assert first.short_url_slug != second.short_url_slug


class TestPageIdAddressing:
    def test_get_by_page_id(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        created = service.create_registration_page(uow, admin.id, assembly.id, name="English")

        page = service.get_registration_page(uow, admin.id, created.id)
        assert page is not None
        assert page.id == created.id

    def test_get_with_source_by_page_id(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        created = service.create_registration_page(uow, admin.id, assembly.id, name="English")
        service.update_registration_page_html(uow, admin.id, created.id, READY_HTML)

        result = service.get_registration_page_with_source(uow, admin.id, created.id)
        assert result is not None
        page, source = result
        assert page.id == created.id
        assert source.readiness_problems() == []

    def test_edits_reach_only_the_addressed_page(self, uow):
        """Sibling variants must not be disturbed by an edit to one of them."""
        admin, assembly = _admin(uow), _assembly(uow)
        english = service.create_registration_page(uow, admin.id, assembly.id, name="English")
        spanish = service.create_registration_page(uow, admin.id, assembly.id, name="Español")

        service.update_registration_page_html(uow, admin.id, spanish.id, "<p>hola</p>")

        english_result = service.get_registration_page_with_source(uow, admin.id, english.id)
        assert english_result is not None
        assert english_result[1].form_html == ""

    def test_publishing_one_page_leaves_its_sibling_alone(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        english = _ready_page(uow, admin, assembly, "English", "climate-en")
        spanish = _ready_page(uow, admin, assembly, "Español", "climate-es")

        service.publish_registration_page(uow, admin.id, english.id)

        sibling = service.get_registration_page(uow, admin.id, spanish.id)
        assert sibling is not None
        assert sibling.status is RegistrationPageStatus.TEST

    def test_unknown_page_id_raises_not_found(self, uow):
        admin = _admin(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.get_registration_page(uow, admin.id, uuid.uuid4())

    def test_a_page_in_an_unmanageable_assembly_looks_missing(self, uow):
        """Existence must not leak across assemblies the user cannot see."""
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="English")

        with pytest.raises(RegistrationPageNotFoundError):
            service.get_registration_page(uow, _stranger(uow).id, page.id)


class TestDuplicateRegistrationPage:
    def test_copies_the_html_and_thank_you_content(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        source = service.create_registration_page(uow, admin.id, assembly.id, name="English")
        service.update_registration_page_html(uow, admin.id, source.id, READY_HTML)
        service.update_thank_you_html(uow, admin.id, source.id, "<p>thanks</p>")

        copy = service.duplicate_registration_page(uow, admin.id, source.id, name="Español", language="es")

        result = service.get_registration_page_with_source(uow, admin.id, copy.id)
        assert result is not None
        assert result[1].form_html == READY_HTML
        assert result[0].thank_you_html == "<p>thanks</p>"

    def test_copy_starts_in_test_with_its_own_slugs(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        source = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, source.id)

        copy = service.duplicate_registration_page(uow, admin.id, source.id, name="Español", language="es")

        assert copy.status is RegistrationPageStatus.TEST
        assert copy.url_slug != "climate-en"
        assert copy.name == "Español"
        assert copy.language == "es"

    def test_copy_records_where_it_came_from(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        source = service.create_registration_page(uow, admin.id, assembly.id, name="English")

        copy = service.duplicate_registration_page(uow, admin.id, source.id, name="Español")

        create_entries = [a for a in copy.activity if a.action is RegistrationPageAction.CREATE]
        assert len(create_entries) == 1
        assert "English" in create_entries[0].text

    def test_copy_gets_its_own_auto_reply_template(self, uow):
        """Editing the copy's auto-reply must never rewrite the original's."""
        admin, assembly = _admin(uow), _assembly(uow)
        template = EmailTemplate(
            assembly_id=assembly.id,
            name="Auto-reply",
            subject="Thanks",
            body_html="Hello in English",
        )
        uow.email_templates.add(template)
        source = service.create_registration_page(uow, admin.id, assembly.id, name="English")
        service.set_auto_reply_template(uow, admin.id, source.id, template.id)

        copy = service.duplicate_registration_page(uow, admin.id, source.id, name="Español", language="es")

        assert copy.auto_reply_email_template_id is not None
        assert copy.auto_reply_email_template_id != template.id
        copied_template = uow.email_templates.get(copy.auto_reply_email_template_id)
        assert copied_template is not None
        assert copied_template.body_html == "Hello in English"

    def test_duplicating_a_page_without_an_auto_reply_leaves_it_unset(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        source = service.create_registration_page(uow, admin.id, assembly.id, name="English")

        copy = service.duplicate_registration_page(uow, admin.id, source.id, name="Español")

        assert copy.auto_reply_email_template_id is None

    def test_stranger_cannot_duplicate(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        source = service.create_registration_page(uow, admin.id, assembly.id, name="English")

        with pytest.raises(RegistrationPageNotFoundError):
            service.duplicate_registration_page(uow, _stranger(uow).id, source.id, name="Español")


class TestDeleteRegistrationPage:
    def test_deletes_a_never_published_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        service.delete_registration_page(uow, admin.id, page.id)

        assert service.list_registration_pages(uow, admin.id, assembly.id) == []

    def test_deletes_the_html_source_too(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        service.delete_registration_page(uow, admin.id, page.id)

        assert uow.registration_page_html_sources.get_by_page_id(page.id) is None

    def test_refuses_a_published_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, page.id)

        with pytest.raises(ValueError, match="published"):
            service.delete_registration_page(uow, admin.id, page.id)

    def test_refuses_a_page_that_was_published_then_unpublished(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, page.id)
        service.unpublish_registration_page(uow, admin.id, page.id)

        with pytest.raises(ValueError, match="published"):
            service.delete_registration_page(uow, admin.id, page.id)

    def test_leaves_sibling_pages_alone(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        keep = service.create_registration_page(uow, admin.id, assembly.id, name="Keep")
        drop = service.create_registration_page(uow, admin.id, assembly.id, name="Drop")

        service.delete_registration_page(uow, admin.id, drop.id)

        assert [p.id for p in service.list_registration_pages(uow, admin.id, assembly.id)] == [keep.id]

    def test_stranger_cannot_delete(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        with pytest.raises(RegistrationPageNotFoundError):
            service.delete_registration_page(uow, _stranger(uow).id, page.id)


class TestDeletableRegistrationPageIds:
    """The list view asks which pages it may offer a delete for."""

    def test_a_never_published_page_is_deletable(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        assert service.deletable_registration_page_ids(uow, admin.id, assembly.id) == {page.id}

    def test_a_published_page_is_not_deletable(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, page.id)

        assert service.deletable_registration_page_ids(uow, admin.id, assembly.id) == set()

    def test_a_page_with_registrations_is_not_deletable(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")
        uow.respondents.add(
            Respondent(
                assembly_id=assembly.id,
                external_id="reg-abc",
                email="ada@example.com",
                registration_page_id=page.id,
            )
        )

        assert service.deletable_registration_page_ids(uow, admin.id, assembly.id) == set()

    def test_only_the_deletable_siblings_come_back(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        live = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, live.id)
        draft = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        assert service.deletable_registration_page_ids(uow, admin.id, assembly.id) == {draft.id}

    def test_a_viewer_is_offered_no_deletions(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id, name="Draft")
        viewer = _viewer(uow, assembly)

        assert service.deletable_registration_page_ids(uow, viewer.id, assembly.id) == set()

    def test_every_id_it_returns_can_actually_be_deleted(self, uow):
        """The contract the list view relies on: offered means it will succeed."""
        admin, assembly = _admin(uow), _assembly(uow)
        live = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, live.id)
        service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        for page_id in service.deletable_registration_page_ids(uow, admin.id, assembly.id):
            service.delete_registration_page(uow, admin.id, page_id)

        assert [p.id for p in service.list_registration_pages(uow, admin.id, assembly.id)] == [live.id]


class TestBulkStatusChanges:
    def test_publish_all_moves_every_ready_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        _ready_page(uow, admin, assembly, "English", "climate-en")
        _ready_page(uow, admin, assembly, "Español", "climate-es")

        results = service.publish_all_registration_pages(uow, admin.id, assembly.id)

        assert [r.outcome for r in results] == [service.BulkStatusOutcome.MOVED] * 2
        pages = service.list_registration_pages(uow, admin.id, assembly.id)
        assert all(p.status is RegistrationPageStatus.PUBLISHED for p in pages)

    def test_publish_all_is_best_effort_over_a_mixed_set(self, uow):
        """One unfinished draft must not stop its siblings going live."""
        admin, assembly = _admin(uow), _assembly(uow)
        ready = _ready_page(uow, admin, assembly, "English", "climate-en")
        already = _ready_page(uow, admin, assembly, "Español", "climate-es")
        service.publish_registration_page(uow, admin.id, already.id)
        slugless = service.create_registration_page(uow, admin.id, assembly.id, name="Cymraeg")

        results = service.publish_all_registration_pages(uow, admin.id, assembly.id)

        by_id = {r.page_id: r for r in results}
        assert by_id[ready.id].outcome is service.BulkStatusOutcome.MOVED
        assert by_id[already.id].outcome is service.BulkStatusOutcome.SKIPPED
        assert by_id[slugless.id].outcome is service.BulkStatusOutcome.FAILED
        assert by_id[slugless.id].problems

        # The commit is the point: the ready page is live despite a sibling failing.
        moved = service.get_registration_page(uow, admin.id, ready.id)
        assert moved is not None
        assert moved.status is RegistrationPageStatus.PUBLISHED

    def test_results_name_each_page(self, uow):
        """The flash message must be able to say which page did not move."""
        admin, assembly = _admin(uow), _assembly(uow)
        service.create_registration_page(uow, admin.id, assembly.id, name="Cymraeg")

        results = service.publish_all_registration_pages(uow, admin.id, assembly.id)

        assert [r.page_name for r in results] == ["Cymraeg"]

    def test_publish_all_reopens_a_closed_page(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, page.id)
        service.close_registration_page(uow, admin.id, page.id)

        results = service.publish_all_registration_pages(uow, admin.id, assembly.id)

        assert results[0].outcome is service.BulkStatusOutcome.MOVED
        reopened = service.get_registration_page(uow, admin.id, page.id)
        assert reopened is not None
        assert reopened.status is RegistrationPageStatus.PUBLISHED

    def test_close_all_closes_only_published_pages(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        live = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, live.id)
        draft = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")

        results = service.close_all_registration_pages(uow, admin.id, assembly.id)

        by_id = {r.page_id: r for r in results}
        assert by_id[live.id].outcome is service.BulkStatusOutcome.MOVED
        assert by_id[draft.id].outcome is service.BulkStatusOutcome.SKIPPED

    def test_unpublish_all_returns_pages_to_test(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")
        service.publish_registration_page(uow, admin.id, page.id)

        service.unpublish_all_registration_pages(uow, admin.id, assembly.id)

        back = service.get_registration_page(uow, admin.id, page.id)
        assert back is not None
        assert back.status is RegistrationPageStatus.TEST

    def test_each_moved_page_records_its_own_activity(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        page = _ready_page(uow, admin, assembly, "English", "climate-en")

        service.publish_all_registration_pages(uow, admin.id, assembly.id)

        published = service.get_registration_page(uow, admin.id, page.id)
        assert published is not None
        entry = published.activity[-1]
        assert entry.action is RegistrationPageAction.PUBLISH
        assert entry.author_id == admin.id

    def test_viewer_cannot_bulk_change_status(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        _ready_page(uow, admin, assembly, "English", "climate-en")
        viewer = _viewer(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.publish_all_registration_pages(uow, viewer.id, assembly.id)

    def test_refuses_a_page_that_has_registrations(self, uow):
        """Test submissions land against a TEST page, so even an unpublished page can have them."""
        admin, assembly = _admin(uow), _assembly(uow)
        page = service.create_registration_page(uow, admin.id, assembly.id, name="Draft")
        uow.respondents.add(
            Respondent(
                assembly_id=assembly.id,
                external_id="reg-abc",
                email="ada@example.com",
                registration_page_id=page.id,
            )
        )

        with pytest.raises(ValueError, match="registrations"):
            service.delete_registration_page(uow, admin.id, page.id)

    def test_registrations_on_a_sibling_page_do_not_block_deletion(self, uow):
        admin, assembly = _admin(uow), _assembly(uow)
        keep = service.create_registration_page(uow, admin.id, assembly.id, name="Keep")
        drop = service.create_registration_page(uow, admin.id, assembly.id, name="Drop")
        uow.respondents.add(
            Respondent(
                assembly_id=assembly.id,
                external_id="reg-abc",
                email="ada@example.com",
                registration_page_id=keep.id,
            )
        )

        service.delete_registration_page(uow, admin.id, drop.id)

        assert [p.id for p in service.list_registration_pages(uow, admin.id, assembly.id)] == [keep.id]
