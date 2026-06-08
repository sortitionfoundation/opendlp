"""ABOUTME: Integration tests for the URL-slug registration submission path.
ABOUTME: Exercises submit_registration end-to-end with a mixed on_registration_page schema."""

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.respondent_field_schema import (
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.value_objects import AssemblyStatus, RespondentStatus
from opendlp.service_layer.registration_submission_service import submit_registration
from tests.fakes import FakeUnitOfWork


def _build(status: RegistrationPageStatus) -> tuple[FakeUnitOfWork, str]:
    uow = FakeUnitOfWork()
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    uow.registration_pages.add(RegistrationPage(assembly_id=assembly.id, url_slug="join-us", status=status))

    fields = [
        ("email", FieldType.EMAIL, True, FieldOnRegistrationPage.YES_REQUIRED, None),
        ("consent", FieldType.BOOL_OR_NONE, True, FieldOnRegistrationPage.YES_REQUIRED, None),
        ("stay_on_db", FieldType.BOOL_OR_NONE, True, FieldOnRegistrationPage.YES_OPTIONAL, None),
        ("first_name", FieldType.TEXT, False, FieldOnRegistrationPage.YES_REQUIRED, None),
        ("nickname", FieldType.TEXT, False, FieldOnRegistrationPage.YES_OPTIONAL, None),
        ("internal_note", FieldType.TEXT, False, FieldOnRegistrationPage.NO, None),
    ]
    for sort, (key, ftype, is_fixed, on_page, options) in enumerate(fields):
        uow.respondent_field_definitions.add(
            RespondentFieldDefinition(
                assembly_id=assembly.id,
                field_key=key,
                label=key.replace("_", " ").capitalize(),
                group=RespondentFieldGroup.OTHER,
                sort_order=(sort + 1) * 10,
                field_type=ftype,
                is_fixed=is_fixed,
                options=options,
                on_registration_page=on_page,
            )
        )
    return uow, "join-us"


def test_published_submission_lands_in_pool_with_mixed_schema() -> None:
    uow, slug = _build(RegistrationPageStatus.PUBLISHED)

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={
            "email": "ada@example.com",
            "consent": "yes",
            "first_name": "Ada",
            "internal_note": "should be dropped",
        },
    )

    assert result.is_valid
    assert result.respondent is not None
    assert result.is_test is False
    assert result.respondent.selection_status == RespondentStatus.POOL
    assert result.respondent.email == "ada@example.com"
    assert result.respondent.consent is True
    # optional checkbox unchecked -> False, never None
    assert result.respondent.stay_on_db is False
    assert result.respondent.attributes["first_name"] == "Ada"
    # optional non-bool left blank is not stored
    assert "nickname" not in result.respondent.attributes
    # a NO field posted anyway is ignored
    assert "internal_note" not in result.respondent.attributes


def test_test_page_submission_is_test_submission() -> None:
    uow, slug = _build(RegistrationPageStatus.TEST)

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={
            "email": "ada@example.com",
            "consent": "yes",
            "first_name": "Ada",
        },
    )

    assert result.is_valid
    assert result.respondent is not None
    assert result.is_test is True
    assert result.respondent.selection_status == RespondentStatus.TEST_SUBMISSION


def test_missing_required_consent_checkbox_rejects() -> None:
    uow, slug = _build(RegistrationPageStatus.PUBLISHED)

    result = submit_registration(
        uow,
        url_slug=slug,
        form_data={"email": "ada@example.com", "first_name": "Ada"},
    )

    assert not result.is_valid
    assert result.respondent is None
    assert "consent" in result.field_errors
