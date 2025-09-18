"""ABOUTME: Form definitions using Flask-WTF with CSRF protection
ABOUTME: Uses GOV.UK Design System components for consistent government service design"""

from typing import Any

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    PasswordField,
    RadioField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, Length, Optional, ValidationError

from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import validate_email as domain_validate_email
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.translations import gettext as _
from opendlp.translations import lazy_gettext as _l


class DomainEmailValidator:
    """WTForms validator that uses our domain email validation."""

    def __init__(self, message: str | None = None) -> None:
        self.message = message

    def __call__(self, form: Any, field: Any) -> None:
        if not field.data:
            raise ValidationError(_("Empty email address"))
        try:
            domain_validate_email(field.data)
        except ValueError as error:
            message = self.message or _("Invalid email address")
            raise ValidationError(message) from error


class LoginForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Login form with email and password."""

    email = EmailField(
        _l("Email address"), validators=[DataRequired(), DomainEmailValidator()], render_kw={"autocomplete": "email"}
    )

    password = PasswordField(
        _l("Password"), validators=[DataRequired()], render_kw={"autocomplete": "current-password"}
    )

    remember_me = BooleanField(_l("Remember me"))


class RegistrationForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Registration form with invite code, names, email and password."""

    invite_code = StringField(
        _l("Invite Code"),
        validators=[DataRequired(), Length(min=5, max=50)],
        description=_l("Enter your invitation code to register"),
    )

    first_name = StringField(
        _l("First Name"),
        validators=[Length(max=100)],
        description=_l("Optional - your first name"),
        render_kw={"autocomplete": "given-name"},
    )

    last_name = StringField(
        _l("Last Name"),
        validators=[Length(max=100)],
        description=_l("Optional - your last name"),
        render_kw={"autocomplete": "family-name"},
    )

    email = EmailField(
        _l("Email address"),
        validators=[DataRequired(), DomainEmailValidator(), Length(max=255)],
        render_kw={"autocomplete": "email"},
    )

    password = PasswordField(
        _l("Password"), validators=[DataRequired(), Length(min=8)], render_kw={"autocomplete": "new-password"}
    )

    password_confirm = PasswordField(
        _l("Confirm Password"),
        validators=[DataRequired(), EqualTo("password", message=_l("Passwords must match"))],
        render_kw={"autocomplete": "new-password"},
    )

    accept_data_agreement = BooleanField(
        _l("Accept Data Agreement"),
        validators=[DataRequired(message=_l("You must accept the data agreement to register"))],
        description=_l("I agree to the data agreement"),
    )

    def validate_email(self, email: EmailField) -> None:
        """Validate that email is not already registered."""
        if not email.data:
            return
        try:
            with SqlAlchemyUnitOfWork() as uow:
                existing_user = uow.users.get_by_email(email.data)
                if existing_user:
                    raise ValidationError(_("This email address is already registered."))
        except Exception:  # noqa: S110
            # If we can't check (e.g., database error), allow form to continue
            # The service layer will handle this case properly
            pass

    def validate_invite_code(self, invite_code: StringField) -> None:
        """Validate that invite code exists and is valid."""
        if not invite_code.data:
            return
        try:
            with SqlAlchemyUnitOfWork() as uow:
                invite = uow.user_invites.get_by_code(invite_code.data)
                if not invite or not invite.is_valid():
                    raise ValidationError(_("Invalid or expired invite code."))
        except Exception:  # noqa: S110
            # If we can't check (e.g., database error), allow form to continue
            # The service layer will handle this case properly
            pass


class PasswordResetRequestForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Password reset request form."""

    email = EmailField(
        _l("Email address"),
        validators=[DataRequired(), DomainEmailValidator()],
        description=_l("Enter your email address to receive a password reset link"),
        render_kw={"autocomplete": "email"},
    )


class PasswordResetForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Password reset form with new password."""

    password = PasswordField(
        _l("New Password"), validators=[DataRequired(), Length(min=8)], render_kw={"autocomplete": "new-password"}
    )

    password_confirm = PasswordField(
        _l("Confirm New Password"),
        validators=[DataRequired(), EqualTo("password", message=_l("Passwords must match"))],
        render_kw={"autocomplete": "new-password"},
    )


class AssemblyForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Assembly creation and editing form."""

    title = StringField(
        _l("Assembly Title"),
        validators=[DataRequired(), Length(min=3, max=200)],
        description=_l("Enter the title for this assembly"),
    )

    question = TextAreaField(
        _l("Assembly Question"),
        validators=[Optional(), Length(max=1000)],
        description=_l("Optional - the key question this assembly will address"),
        render_kw={"rows": 3},
    )

    first_assembly_date = DateField(
        _l("First Assembly Date"),
        validators=[Optional()],
        description=_l("Optional - when the first assembly meeting will take place"),
    )


class CreateAssemblyForm(AssemblyForm):
    """Form specifically for creating assemblies."""


class EditAssemblyForm(AssemblyForm):
    """Form specifically for editing assemblies."""


class AssemblyGSheetForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for configuring Google Spreadsheet settings for an assembly."""

    url = StringField(
        _l("Google Spreadsheet URL"),
        validators=[DataRequired(), GoogleSpreadsheetURLValidator()],
        description=_l("Full URL of the Google Spreadsheet containing respondent data"),
        render_kw={"placeholder": "https://docs.google.com/spreadsheets/d/..."},
    )

    select_registrants_tab = StringField(
        _l("Selection Registrants Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing registrant data in the Google Spreadsheet - for initial Selection"),
        default="Respondents",
    )

    select_targets_tab = StringField(
        _l("Selection Targets Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing categories, category values and targets - for initial Selection"),
        default="Categories",
    )

    replace_registrants_tab = StringField(
        _l("Replacement Registrants Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing registrant data in the Google Spreadsheet - for Replacements"),
        default="Remaining",
    )

    replace_targets_tab = StringField(
        _l("Replacement Targets Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing categories, category values and targets - for Replacements"),
        default="Replacement Categories",
    )

    check_same_address = BooleanField(
        _l("Check Same Address"),
        description=_l("Enable checking for participants with the same address"),
        default=True,
    )

    generate_remaining_tab = BooleanField(
        _l("Generate Remaining Tab"),
        description=_l("Create a tab with remaining participants after selection"),
        default=True,
    )

    team = RadioField(
        _l("Team Configuration"),
        choices=[
            ("uk", _l("UK Team")),
            ("eu", _l("EU Team")),
            ("aus", _l("Australia Team")),
            ("other", _l("Custom configuration")),
        ],
        default="other",
        validators=[DataRequired()],
        description=_l(
            "Select the team configuration to use for default settings for ID Column, columns to keep and address columns."
        ),
    )

    id_column = StringField(
        _l("ID Column"),
        validators=[DataRequired(), Length(min=1, max=100)],
        default="nationbuilder_id",
        description=_l("Column name containing unique identifiers for respondents"),
    )

    check_same_address_cols_string = StringField(
        _l("Address Columns"),
        validators=[Optional(), Length(max=500)],
        description=_l(
            "Comma-separated list of column names used for checking same address (e.g., primary_address1, zip_royal_mail)"
        ),
    )

    columns_to_keep_string = StringField(
        _l("Columns to Keep"),
        validators=[Optional(), Length(max=1000)],
        description=_l("Comma-separated list of column names to keep in output (e.g., first_name, last_name, email)"),
    )


class CreateAssemblyGSheetForm(AssemblyGSheetForm):
    """Form specifically for creating assembly Google Spreadsheet configuration."""


class EditAssemblyGSheetForm(AssemblyGSheetForm):
    """Form specifically for editing assembly Google Spreadsheet configuration."""
