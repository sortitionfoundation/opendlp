"""ABOUTME: Integration tests for cloning a project against a real Postgres
ABOUTME: Clones a fully populated source with each option on and off and checks the copy stands alone"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from opendlp.domain.assembly import AssemblyGSheet, SelectionRunRecord
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_content_block import RegistrationContentBlock
from opendlp.domain.registration_document import RegistrationDocument
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageAction,
    RegistrationPageHtml,
    RegistrationPageStatus,
)
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    RespondentFieldMappingEntry,
)
from opendlp.domain.respondents import Respondent, RespondentComment
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import (
    AssemblyRole,
    GlobalRole,
    GSheetExportKind,
    RespondentStatus,
    SelectionRunStatus,
    SelectionTaskType,
)
from opendlp.service_layer.assembly_clone_service import CloneOptions, clone_assembly, count_respondents_to_clone
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.exceptions import (
    AssemblyTitleTaken,
    CannotCloneGSheetAssembly,
    InsufficientPermissions,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import assign_assembly_role
from tests.data import VALID_GSHEET_URL

SHA_IMAGE = "a" * 64
SHA_DOC = "b" * 64
QUESTIONS_UPDATED = datetime(2026, 1, 1, tzinfo=UTC)
FORM_UPDATED = datetime(2026, 1, 2, tzinfo=UTC)
DEFAULT = CloneOptions()
FULL = CloneOptions(respondents=True, team=True, confirm_no_personal_data=True)


@pytest.fixture
def people(postgres_session_factory):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        organiser = User(email="organiser@example.com", global_role=GlobalRole.ORGANISER, password_hash="hash")
        caller = User(email="caller@example.com", global_role=GlobalRole.USER, password_hash="hash")
        for user in (admin, organiser, caller):
            uow.users.add(user)
        uow.commit()
        return {"admin": admin.id, "organiser": organiser.id, "caller": caller.id}


@pytest.fixture
def source(postgres_session_factory, people):
    """A project with something in every table a clone reads, and in those it must not copy."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        created = create_assembly(
            uow,
            title="Climate Assembly",
            created_by_user_id=people["organiser"],
            question="What should we do?",
            first_assembly_date=date(2027, 3, 1),
            number_to_select=30,
        )
        assembly = uow.assemblies.get(created.id)
        assembly.set_reply_to("Organiser", "organiser@example.org")
        assembly.questions_updated_at = QUESTIONS_UPDATED
        assembly.selection_settings = SelectionSettings(
            assembly_id=assembly.id, check_same_address=True, check_same_address_cols=["postcode"]
        )
        assembly.csv = AssemblyCSV(
            assembly_id=assembly.id, csv_id_column="ref", settings_confirmed=True, last_import_filename="real.csv"
        )
        assign_assembly_role(uow, people["caller"], assembly.id, AssemblyRole.CONFIRMATION_CALLER)

        gender = TargetCategory(
            assembly_id=assembly.id,
            name="Gender",
            sort_order=0,
            values=[TargetValue(value="Female", min=10, max=20), TargetValue(value="Male", min=10, max=20)],
        )
        region = TargetCategory(
            assembly_id=assembly.id, name="Region", values=[TargetValue(value="North", min=1, max=30)], sort_order=1
        )
        uow.target_categories.add(gender)
        uow.target_categories.add(region)
        uow.flush()

        postcode_field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="postcode",
            label="Postcode",
            group=RespondentFieldGroup.ADDRESS,
            sort_order=1,
        )
        gender_field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="gender",
            label="Gender",
            group=RespondentFieldGroup.ABOUT_YOU,
            sort_order=2,
            field_type=FieldType.CHOICE_RADIO,
            options=[ChoiceOption("Female"), ChoiceOption("Male")],
            target_category_id=gender.id,
        )
        region_field = RespondentFieldDefinition(
            assembly_id=assembly.id,
            field_key="region",
            label="Region",
            group=RespondentFieldGroup.ADDRESS,
            sort_order=3,
            is_derived=True,
            derived_from=["postcode"],
            derivation_type=DerivationType.LARGE_MAPPING,
            derivation_config={"fallback": "Unknown"},
            target_category_id=region.id,
        )
        uow.respondent_field_definitions.bulk_add([postcode_field, gender_field, region_field])
        uow.flush()
        uow.respondent_field_mapping_entries.bulk_add([
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="AB12CD", output_value="North"),
            RespondentFieldMappingEntry(field_id=region_field.id, lookup_key="EF34GH", output_value="North"),
        ])
        uow.registration_content_blocks.add(
            RegistrationContentBlock(assembly_id=assembly.id, sort_order=2, heading="About you")
        )

        image = RegistrationImage(
            assembly_id=assembly.id, byte_size=4, width=1, height=1, sha256=SHA_IMAGE, data=b"\x89PNG", alt="Logo"
        )
        uow.registration_images.add(image)
        uow.registration_documents.add(
            RegistrationDocument(assembly_id=assembly.id, byte_size=4, sha256=SHA_DOC, data=b"%PDF", label="Info")
        )
        template = EmailTemplate(
            assembly_id=assembly.id,
            name="Thanks",
            subject="Thanks",
            body_html=f'<img src="/register-assets/images/{image.id}.png">',
            reply_to_name="Organiser",
            reply_to_email="organiser@example.org",
        )
        uow.email_templates.add(template)
        uow.flush()

        english = RegistrationPage(
            assembly_id=assembly.id,
            name="English",
            language="en",
            url_slug="climate-en",
            short_url_slug="111111",
            status=RegistrationPageStatus.PUBLISHED,
            thank_you_html="<p>Thanks</p>",
            thank_you_use_default=False,
            auto_reply_email_template_id=template.id,
        )
        english.record_create(people["organiser"])
        welsh = RegistrationPage(
            assembly_id=assembly.id, name="Cymraeg", language="cy", url_slug="climate-cy", short_url_slug="222222"
        )
        uow.registration_pages.add(english)
        uow.registration_pages.add(welsh)
        uow.flush()
        for page in (english, welsh):
            uow.registration_page_html_sources.add(
                RegistrationPageHtml(
                    registration_page_id=page.id,
                    intro_html=(
                        f'<img src="/register-assets/images/{image.id}.png">'
                        f'<a href="/register/{page.url_slug}/documents/{SHA_DOC}.pdf">Info</a>'
                    ),
                    form_html="<form>{{ csrf_form_element }}</form>",
                    form_updated_at=FORM_UPDATED,
                )
            )

        run = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status=SelectionRunStatus.COMPLETED,
            task_type=SelectionTaskType.SELECT_FROM_DB,
        )
        uow.selection_run_records.add(run)
        uow.assembly_export_gsheets.add(
            AssemblyExportGSheet(
                assembly_id=assembly.id,
                export_kind=GSheetExportKind.RESPONDENTS,
                url=VALID_GSHEET_URL,
                auto_export=True,
            )
        )
        uow.flush()

        comment = RespondentComment(text="Called", author_id=people["organiser"], created_at=datetime.now(UTC))
        attributes = {"postcode": "AB1 2CD", "gender": "Female", "region": "North"}
        for external_id, status in [
            ("pool", RespondentStatus.POOL),
            ("selected", RespondentStatus.SELECTED),
            ("confirmed", RespondentStatus.CONFIRMED),
            ("withdrawn", RespondentStatus.WITHDRAWN),
            ("test", RespondentStatus.TEST_SUBMISSION),
            ("deleted", RespondentStatus.DELETED),
        ]:
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly.id,
                    external_id=external_id,
                    selection_status=status,
                    selection_run_id=run.task_id if status == RespondentStatus.SELECTED else None,
                    email=f"{external_id}@example.com",
                    registration_page_id=english.id,
                    attributes=dict(attributes),
                    comments=[comment],
                )
            )
        uow.commit()
        return {
            "id": assembly.id,
            "image": image.id,
            "template": template.id,
            "english": english.id,
            "gender": gender.id,
            "region": region.id,
        }


def _clone(postgres_session_factory, user_id, source_id, options=DEFAULT):
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        result = clone_assembly(uow, user_id, source_id, options)
        uow.commit()
    return result


class TestDefaultClone:
    def test_project_details_copied_and_reply_to_blank(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"])

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            clone = uow.assemblies.get(result.assembly.id)
            assert clone.id != source["id"]
            assert clone.title == "Climate Assembly (copy)"
            assert clone.question == "What should we do?"
            assert clone.first_assembly_date == date(2027, 3, 1)
            assert clone.number_to_select == 30
            assert clone.questions_updated_at == QUESTIONS_UPDATED
            assert (clone.reply_to_name, clone.reply_to_email) == ("", "")
            assert clone.created_by_user_id == people["admin"]
            assert clone.selection_settings.check_same_address_cols == ["postcode"]
            assert clone.selection_settings.selection_settings_id != (
                uow.assemblies.get(source["id"]).selection_settings.selection_settings_id
            )
            assert (clone.csv.csv_id_column, clone.csv.settings_confirmed) == ("ref", True)
            assert clone.csv.last_import_filename == ""

    def test_targets_and_questions_copied_with_links_remapped(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"])

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            categories = {c.name: c for c in uow.target_categories.get_by_assembly_id(result.assembly.id)}
            assert set(categories) == {"Gender", "Region"}
            assert {c.id for c in categories.values()}.isdisjoint({source["gender"], source["region"]})
            assert [v.value for v in categories["Gender"].values] == ["Female", "Male"]

            fields = {f.field_key: f for f in uow.respondent_field_definitions.list_by_assembly(result.assembly.id)}
            assert set(fields) == {"postcode", "gender", "region"}
            assert fields["gender"].target_category_id == categories["Gender"].id
            assert fields["region"].target_category_id == categories["Region"].id
            assert uow.respondent_field_mapping_entries.count_for_field(fields["region"].id) == 2
            assert len(uow.registration_content_blocks.list_by_assembly(result.assembly.id)) == 1
        assert result.counts["questions"] == 2
        assert result.counts["derived_fields"] == 1

    def test_registration_pages_are_test_with_new_slugs_and_fresh_activity(
        self, postgres_session_factory, people, source
    ):
        result = _clone(postgres_session_factory, people["admin"], source["id"])

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            pages = {p.name: p for p in uow.registration_pages.list_by_assembly_id(result.assembly.id)}
            assert set(pages) == {"English", "Cymraeg"}
            english = pages["English"]
            assert english.status == RegistrationPageStatus.TEST
            assert english.url_slug not in ("", "climate-en", "climate-cy")
            assert english.short_url_slug not in ("", "111111", "222222")
            assert pages["Cymraeg"].url_slug != english.url_slug
            assert english.thank_you_html == "<p>Thanks</p>"
            assert english.thank_you_use_default is False
            assert [(a.action, a.author_id) for a in english.activity] == [
                (RegistrationPageAction.CREATE, people["admin"])
            ]
            assert "cloned from Climate Assembly" in english.activity[0].text

    def test_page_html_and_templates_point_at_the_clone(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"])

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            [image] = uow.registration_images.list_by_assembly_id(result.assembly.id)
            assert image.id != source["image"]
            assert image.created_by == people["admin"]
            assert len(uow.registration_documents.list_by_assembly_id(result.assembly.id)) == 1

            english = next(
                p for p in uow.registration_pages.list_by_assembly_id(result.assembly.id) if p.language == "en"
            )
            html = uow.registration_page_html_sources.get_by_page_id(english.id)
            assert html.intro_html == (
                f'<img src="/register-assets/images/{image.id}.png">'
                f'<a href="/register/{english.url_slug}/documents/{SHA_DOC}.pdf">Info</a>'
            )
            assert html.form_updated_at == FORM_UPDATED

            [template] = uow.email_templates.list_by_assembly(result.assembly.id)
            assert template.id != source["template"]
            assert english.auto_reply_email_template_id == template.id
            assert template.body_html == f'<img src="/register-assets/images/{image.id}.png">'
            assert (template.reply_to_name, template.reply_to_email) == ("", "")

    def test_never_cloned_parts_are_absent(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"])

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.respondents.count_by_assembly_id(result.assembly.id, include_deleted=True) == 0
            assert list(uow.selection_run_records.get_by_assembly_id(result.assembly.id)) == []
            assert (
                uow.assembly_export_gsheets.get_by_assembly_and_kind(result.assembly.id, GSheetExportKind.RESPONDENTS)
                is None
            )
            roles = list(uow.user_assembly_roles.get_roles_for_assembly(result.assembly.id))
            assert [(r.user_id, r.role) for r in roles] == [(people["admin"], AssemblyRole.ASSEMBLY_MANAGER)]

    def test_source_is_unchanged(self, postgres_session_factory, people, source):
        _clone(postgres_session_factory, people["admin"], source["id"], FULL)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            original = uow.assemblies.get(source["id"])
            assert original.title == "Climate Assembly"
            assert original.reply_to_email == "organiser@example.org"
            english = uow.registration_pages.get(source["english"])
            assert (english.url_slug, english.status) == ("climate-en", RegistrationPageStatus.PUBLISHED)
            assert uow.respondents.count_by_assembly_id(source["id"], include_deleted=True) == 6

    def test_second_clone_takes_the_next_copy_title(self, postgres_session_factory, people, source):
        _clone(postgres_session_factory, people["admin"], source["id"])
        second = _clone(postgres_session_factory, people["admin"], source["id"])

        assert second.assembly.title == "Climate Assembly (copy 2)"


class TestCloneWithRespondentsAndTeam:
    def test_respondents_copied_without_history(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"], FULL)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            english_id = next(
                p.id for p in uow.registration_pages.list_by_assembly_id(result.assembly.id) if p.language == "en"
            )
            respondents = {
                r.external_id: r.create_detached_copy()
                for r in uow.respondents.get_by_assembly_id(result.assembly.id, include_deleted=True)
            }
        assert set(respondents) == {"pool", "selected", "confirmed", "withdrawn", "test"}
        assert {r.external_id: r.selection_status for r in respondents.values()} == {
            "pool": RespondentStatus.POOL,
            "selected": RespondentStatus.POOL,
            "confirmed": RespondentStatus.POOL,
            "withdrawn": RespondentStatus.POOL,
            "test": RespondentStatus.TEST_SUBMISSION,
        }
        selected = respondents["selected"]
        assert selected.selection_run_id is None
        assert selected.comments == []
        assert selected.registration_page_id == english_id
        assert selected.email == "selected@example.com"
        assert selected.attributes == {"postcode": "AB1 2CD", "gender": "Female", "region": "North"}
        assert result.counts["respondents"] == 5

    def test_preserve_respondent_status(self, postgres_session_factory, people, source):
        options = CloneOptions(respondents=True, preserve_respondent_status=True, confirm_no_personal_data=True)
        result = _clone(postgres_session_factory, people["admin"], source["id"], options)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            statuses = {
                r.external_id: r.selection_status for r in uow.respondents.get_by_assembly_id(result.assembly.id)
            }
        assert statuses["selected"] == RespondentStatus.SELECTED
        assert statuses["confirmed"] == RespondentStatus.CONFIRMED
        assert statuses["withdrawn"] == RespondentStatus.WITHDRAWN

    def test_team_roles_copied_with_the_cloner_as_manager(self, postgres_session_factory, people, source):
        result = _clone(postgres_session_factory, people["admin"], source["id"], FULL)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            roles = {r.user_id: r.role for r in uow.user_assembly_roles.get_roles_for_assembly(result.assembly.id)}
        assert roles == {
            people["admin"]: AssemblyRole.ASSEMBLY_MANAGER,
            people["organiser"]: AssemblyRole.ASSEMBLY_MANAGER,
            people["caller"]: AssemblyRole.CONFIRMATION_CALLER,
        }
        assert result.counts["team_members"] == 2

    def test_count_respondents_to_clone_leaves_out_deleted(self, postgres_session_factory, people, source):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert count_respondents_to_clone(uow, people["admin"], source["id"]) == 5


class TestCloneWithPartsLeftOut:
    def test_no_targets_drops_derived_fields_and_their_values(self, postgres_session_factory, people, source):
        options = CloneOptions(targets=False, respondents=True, confirm_no_personal_data=True)
        result = _clone(postgres_session_factory, people["admin"], source["id"], options)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.target_categories.get_by_assembly_id(result.assembly.id) == []
            fields = {
                f.field_key: f.target_category_id
                for f in uow.respondent_field_definitions.list_by_assembly(result.assembly.id)
            }
            respondent = uow.respondents.get_by_assembly_id(result.assembly.id)[0].create_detached_copy()
        assert fields == {"postcode": None, "gender": None}
        assert "region" not in respondent.attributes
        assert respondent.attributes["postcode"] == "AB1 2CD"

    def test_no_registration_leaves_respondents_without_a_page(self, postgres_session_factory, people, source):
        options = CloneOptions(registration=False, respondents=True, confirm_no_personal_data=True)
        result = _clone(postgres_session_factory, people["admin"], source["id"], options)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.registration_pages.list_by_assembly_id(result.assembly.id) == []
            assert uow.registration_images.list_by_assembly_id(result.assembly.id) == []
            assert uow.email_templates.list_by_assembly(result.assembly.id) == []
            page_ids = {r.registration_page_id for r in uow.respondents.get_by_assembly_id(result.assembly.id)}
        assert page_ids == {None}

    def test_targets_without_questions(self, postgres_session_factory, people, source):
        options = CloneOptions(questions=False, registration=False)
        result = _clone(postgres_session_factory, people["admin"], source["id"], options)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert len(uow.target_categories.get_by_assembly_id(result.assembly.id)) == 2
            assert uow.respondent_field_definitions.list_by_assembly(result.assembly.id) == []
            assert uow.registration_content_blocks.list_by_assembly(result.assembly.id) == []


class TestCloneRefused:
    def test_gsheet_project_refused(self, postgres_session_factory, people, source):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            uow.assemblies.get(source["id"]).gsheet = AssemblyGSheet(assembly_id=source["id"], url=VALID_GSHEET_URL)
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow, pytest.raises(CannotCloneGSheetAssembly):
            clone_assembly(uow, people["admin"], source["id"], CloneOptions())

    def test_user_who_cannot_see_the_source_refused(self, postgres_session_factory, source):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            outsider = User(email="outsider@example.com", global_role=GlobalRole.ORGANISER, password_hash="hash")
            uow.users.add(outsider)
            uow.commit()
            outsider_id = outsider.id

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow, pytest.raises(InsufficientPermissions):
            clone_assembly(uow, outsider_id, source["id"], CloneOptions())

    def test_taken_title_refused_and_nothing_written(self, postgres_session_factory, people, source):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow, pytest.raises(AssemblyTitleTaken):
            clone_assembly(uow, people["admin"], source["id"], CloneOptions(title="climate assembly"))

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert len(list(uow.assemblies.all())) == 1

    def test_run_out_of_copy_titles(self, postgres_session_factory, people, source):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            for title in ["Climate Assembly (copy)"] + [f"Climate Assembly (copy {n})" for n in range(2, 10)]:
                create_assembly(uow, title=title, created_by_user_id=people["admin"])
            uow.commit()

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow, pytest.raises(AssemblyTitleTaken):
            clone_assembly(uow, people["admin"], source["id"], CloneOptions())


def test_first_assembly_date_in_the_past_is_copied(postgres_session_factory, people):
    """Cloning an old project for training must not trip over its date having passed."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        old = create_assembly(
            uow, title="Old", created_by_user_id=people["admin"], first_assembly_date=date.today() - timedelta(days=400)
        )
        uow.commit()

    result = _clone(postgres_session_factory, people["admin"], old.id)

    assert result.assembly.first_assembly_date == date.today() - timedelta(days=400)
