"""ABOUTME: Service for handling public registration form submissions.
ABOUTME: Creates respondents from validated form data with appropriate status."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from opendlp.domain.registration_page import RegistrationPageStatus
from opendlp.domain.respondent_field_schema import FieldType, RespondentFieldDefinition
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentAction, RespondentSourceType, RespondentStatus
from opendlp.service_layer.registration_page_service import (
    find_registration_page_by_url_slug,
    resolve_visibility,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


@dataclass(frozen=True)
class RegistrationSubmissionResult:
    """Result of a registration form submission.

    On success: respondent is set, errors are empty.
    On validation failure: respondent is None, errors contain per-field messages.
    """

    respondent: Respondent | None
    values: dict[str, Any] = field(default_factory=dict)
    field_errors: dict[str, list[str]] = field(default_factory=dict)
    form_errors: list[str] = field(default_factory=list)
    is_test: bool = False

    @property
    def is_valid(self) -> bool:
        """True if submission succeeded (no errors)."""
        return self.respondent is not None and not self.field_errors and not self.form_errors


class RegistrationClosedError(Exception):
    """Raised when submitting to a closed registration page."""

    pass


class RegistrationNotFoundError(Exception):
    """Raised when the registration page doesn't exist or has no slug."""

    pass


def _generate_external_id() -> str:
    """Generate a unique external ID for a form submission."""
    return f"reg-{uuid.uuid4().hex[:12]}"


def _validate_bool(str_value: str, allow_none: bool) -> tuple[bool | None, str | None]:
    """Validate boolean from radio button. Accepts "yes"/"no"/"true"/"false"/"1"/"0"."""
    lower = str_value.lower()
    if lower in ("yes", "true", "1"):
        return True, None
    if lower in ("no", "false", "0"):
        return False, None
    if allow_none:
        return None, None
    return None, "Please select Yes or No"


def _validate_email(str_value: str) -> tuple[str | None, str | None]:
    """Validate email field - required and must contain @."""
    if not str_value:
        return None, "This field is required"
    if "@" not in str_value:
        return None, "Please enter a valid email address"
    return str_value, None


def _validate_choice(str_value: str, valid_values: set[str] | None) -> tuple[str | None, str | None]:
    """Validate choice field - required and must be a valid option."""
    if not str_value:
        return None, "Please select an option"
    if valid_values and str_value not in valid_values:
        return None, "Please select a valid option"
    return str_value, None


def _validate_integer(str_value: str) -> tuple[int | None, str | None]:
    """Validate integer field - required and must be a valid number."""
    if not str_value:
        return None, "This field is required"
    try:
        return int(str_value), None
    except ValueError:
        return None, "Please enter a valid number"


def _validate_field_value(
    fd: RespondentFieldDefinition,
    value: Any,
) -> tuple[Any, str | None]:
    """Validate a single field value. Returns (cleaned_value, error_message or None).

    All fields are required except BOOL_OR_NONE (which explicitly allows None).
    """
    str_value = str(value).strip() if value is not None else ""

    if fd.effective_field_type == FieldType.EMAIL:
        return _validate_email(str_value)

    if fd.effective_field_type in (FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN):
        valid_values = {opt.value for opt in fd.options} if fd.options else None
        return _validate_choice(str_value, valid_values)

    if fd.effective_field_type in (FieldType.BOOL, FieldType.BOOL_OR_NONE):
        return _validate_bool(str_value, allow_none=fd.effective_field_type == FieldType.BOOL_OR_NONE)

    if fd.effective_field_type == FieldType.INTEGER:
        return _validate_integer(str_value)

    # TEXT, LONGTEXT, PHONE, DATE, etc. - require non-empty
    if not str_value:
        return None, "This field is required"
    return str_value, None


def _validate_form_data(
    form_data: Mapping[str, Any],
    field_definitions: list[RespondentFieldDefinition],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Validate form data against field definitions.

    Returns (cleaned_data, field_errors).
    Iterates over all field definitions to handle missing fields (e.g. unselected
    radio buttons which don't appear in form_data at all).
    """
    cleaned: dict[str, Any] = {}
    errors: dict[str, list[str]] = {}

    for fd in field_definitions:
        key = fd.field_key
        # Get value from form_data, defaulting to empty string if missing
        # (unselected radio buttons won't be in form_data)
        value = form_data.get(key, "")

        cleaned_value, error = _validate_field_value(fd, value)
        if error:
            errors.setdefault(key, []).append(error)
        else:
            cleaned[key] = cleaned_value

    return cleaned, errors


def submit_registration(
    uow: AbstractUnitOfWork,
    *,
    url_slug: str,
    form_data: Mapping[str, Any],
) -> RegistrationSubmissionResult:
    """Submit a registration form and create a respondent.

    Args:
        uow: Unit of work for database access
        url_slug: The registration page's URL slug
        form_data: Form data as submitted (typically request.form)

    Returns:
        RegistrationSubmissionResult with the created respondent or validation errors.

    Raises:
        RegistrationNotFoundError: If the page doesn't exist or has no slug
        RegistrationClosedError: If the page is closed
    """
    # Convert form_data to a plain dict for storage in result
    submitted_values = dict(form_data)

    with uow:
        # Look up the registration page
        page = find_registration_page_by_url_slug(uow, url_slug)

        if page is None:
            raise RegistrationNotFoundError(f"Registration page not found: {url_slug}")

        visibility = resolve_visibility(page)

        if not visibility.is_visible:
            if page.status == RegistrationPageStatus.CLOSED:
                raise RegistrationClosedError("Registration is closed")
            raise RegistrationNotFoundError(f"Registration page not available: {url_slug}")

        is_test = visibility.is_test

        # Get field definitions for validation
        field_definitions = uow.respondent_field_definitions.list_by_assembly(page.assembly_id)

        # Validate form data
        cleaned_data, field_errors = _validate_form_data(form_data, field_definitions)

        if field_errors:
            return RegistrationSubmissionResult(
                respondent=None,
                values=submitted_values,
                field_errors=field_errors,
                form_errors=[],
                is_test=is_test,
            )

        # Determine respondent status based on page status
        respondent_status = RespondentStatus.TEST_SUBMISSION if is_test else RespondentStatus.POOL

        # Extract top-level Respondent fields from cleaned_data
        # These are reserved field names that go to Respondent constructor, not attributes
        email = str(cleaned_data.pop("email", ""))
        consent = cleaned_data.pop("consent", None)
        eligible = cleaned_data.pop("eligible", None)
        can_attend = cleaned_data.pop("can_attend", None)
        stay_on_db = cleaned_data.pop("stay_on_db", None)

        # Create the respondent
        external_id = _generate_external_id()
        respondent = Respondent(
            assembly_id=page.assembly_id,
            external_id=external_id,
            email=email,
            consent=consent,
            eligible=eligible,
            can_attend=can_attend,
            stay_on_db=stay_on_db,
            attributes=cleaned_data,
            source_type=RespondentSourceType.REGISTRATION_FORM,
            selection_status=respondent_status,
        )

        # Add creation comment
        comment_text = "Submitted via registration form"
        if is_test:
            comment_text += " (test submission)"

        # Use a system UUID for the author since this is a public submission
        system_author_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        respondent.add_comment(
            text=comment_text,
            author_id=system_author_id,
            action=RespondentAction.CREATE,
        )

        uow.respondents.add(respondent)
        uow.commit()

        return RegistrationSubmissionResult(
            respondent=respondent.create_detached_copy(),
            values=submitted_values,
            field_errors={},
            form_errors=[],
            is_test=is_test,
        )


def submit_registration_by_assembly_id(
    uow: AbstractUnitOfWork,
    *,
    assembly_id: uuid.UUID,
    form_data: Mapping[str, Any],
    is_test: bool = False,
) -> RegistrationSubmissionResult:
    """Submit a registration form directly by assembly ID.

    This is a convenience function for testing via service-docs.
    It bypasses the URL slug lookup and page status check.

    Args:
        uow: Unit of work for database access
        assembly_id: The assembly to submit to
        form_data: Form data as submitted
        is_test: If True, creates TEST_SUBMISSION respondent; otherwise POOL

    Returns:
        RegistrationSubmissionResult with the created respondent or validation errors.
    """
    submitted_values = dict(form_data)

    with uow:
        # Verify assembly exists
        assembly = uow.assemblies.get(assembly_id)
        if assembly is None:
            return RegistrationSubmissionResult(
                respondent=None,
                values=submitted_values,
                field_errors={},
                form_errors=["Assembly not found"],
                is_test=is_test,
            )

        # Get field definitions for validation
        field_definitions = uow.respondent_field_definitions.list_by_assembly(assembly_id)

        # Validate form data
        cleaned_data, field_errors = _validate_form_data(form_data, field_definitions)

        if field_errors:
            return RegistrationSubmissionResult(
                respondent=None,
                values=submitted_values,
                field_errors=field_errors,
                form_errors=[],
                is_test=is_test,
            )

        # Determine respondent status
        respondent_status = RespondentStatus.TEST_SUBMISSION if is_test else RespondentStatus.POOL

        # Extract top-level Respondent fields from cleaned_data
        # These are reserved field names that go to Respondent constructor, not attributes
        email = str(cleaned_data.pop("email", ""))
        consent = cleaned_data.pop("consent", None)
        eligible = cleaned_data.pop("eligible", None)
        can_attend = cleaned_data.pop("can_attend", None)
        stay_on_db = cleaned_data.pop("stay_on_db", None)

        # Create the respondent
        external_id = _generate_external_id()
        respondent = Respondent(
            assembly_id=assembly_id,
            external_id=external_id,
            email=email,
            consent=consent,
            eligible=eligible,
            can_attend=can_attend,
            stay_on_db=stay_on_db,
            attributes=cleaned_data,
            source_type=RespondentSourceType.REGISTRATION_FORM,
            selection_status=respondent_status,
        )

        # Add creation comment
        comment_text = "Submitted via registration form"
        if is_test:
            comment_text += " (test submission)"

        system_author_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        respondent.add_comment(
            text=comment_text,
            author_id=system_author_id,
            action=RespondentAction.CREATE,
        )

        uow.respondents.add(respondent)
        uow.commit()

        return RegistrationSubmissionResult(
            respondent=respondent.create_detached_copy(),
            values=submitted_values,
            field_errors={},
            form_errors=[],
            is_test=is_test,
        )
