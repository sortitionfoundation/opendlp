"""ABOUTME: Form definitions using Flask-WTF with CSRF protection
ABOUTME: Uses GOV.UK Design System components for consistent government service design"""

from collections.abc import Callable
from enum import Enum
from typing import Any

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    IntegerField,
    PasswordField,
    RadioField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, EqualTo, InputRequired, Length, Optional, ValidationError

from opendlp.domain.users import User
from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, assembly_role_options, global_role_options
from opendlp.domain.value_objects import validate_email as domain_validate_email
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.translations import gettext as _
from opendlp.translations import lazy_gettext as _l


def coerce_for_enum(enum: type[Enum]) -> Callable:
    def coerce(name: str | Enum) -> Enum:
        if isinstance(name, enum):
            return name
        try:
            assert isinstance(name, str)
            return enum[name]
        except KeyError:
            raise ValueError(name) from None

    return coerce


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


class EmailDoesNotExistValidator:
    """WTForms validator that checks the email address is not already associated with a user."""

    def __init__(self, message: str = "") -> None:
        self.message = message or _l("This email address is already registered.")

    def __call__(self, form: Any, field: Any) -> None:
        existing_user: User | None = None
        if not field.data:
            return
        try:
            with SqlAlchemyUnitOfWork() as uow:
                existing_user = uow.users.get_by_email(field.data)
        except Exception:  # noqa: S110
            # If we can't check (e.g., database error), allow form to continue
            # The service layer will handle this case properly
            pass
        if existing_user:
            raise ValidationError(str(self.message))


class NonNegativeValidator:
    """WTForms validator that ensures a number field is not negative."""

    def __init__(self, message: str | None = None) -> None:
        self.message = message or _l("Number cannot be negative")

    def __call__(self, form: Any, field: Any) -> None:
        if field.data is not None and field.data < 0:
            raise ValidationError(str(self.message))


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
        validators=[DataRequired(), DomainEmailValidator(), EmailDoesNotExistValidator(), Length(max=255)],
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

    number_to_select = IntegerField(
        _l("Number to Select"),
        validators=[InputRequired(), NonNegativeValidator()],
        description=_l("The number of participants to select for this assembly"),
        default=0,
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
        # Note this name is a duplicate - fieldsets are used to distinguish the duplicates
        _l("Respondents Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing respondents data in the Google Spreadsheet - for initial Selection"),
        default="Respondents",
    )

    select_targets_tab = StringField(
        # Note this name is a duplicate - fieldsets are used to distinguish the duplicates
        _l("Targets Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing categories, category values and targets - for initial Selection"),
        default="Categories",
    )

    replace_registrants_tab = StringField(
        # Note this name is a duplicate - fieldsets are used to distinguish the duplicates
        _l("Respondents Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing respondents data in the Google Spreadsheet - for Replacements"),
        default="Remaining",
    )

    replace_targets_tab = StringField(
        # Note this name is a duplicate - fieldsets are used to distinguish the duplicates
        _l("Targets Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing categories, category values and targets - for Replacements"),
        default="Replacement Categories",
    )

    already_selected_tab = StringField(
        _l("Already Selected Tab Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        description=_l("Name of the tab containing already selected people (used for Replacements)"),
        default="Selected",
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
            "Select the team configuration to use for default settings for ID Column, Address Columns and Columns To Keep."
        ),
    )

    id_column = StringField(
        _l("ID Column"),
        validators=[DataRequired(), Length(min=1, max=100)],
        default="nationbuilder_id",
        description=_l(
            "Column name containing unique identifiers for respondents. Note will be overridden if the Team Configuration is not 'Custom'."
        ),
    )

    check_same_address_cols_string = StringField(
        _l("Address Columns"),
        validators=[Optional(), Length(max=500)],
        description=_l(
            "Comma-separated list of column names used for checking same address (e.g., primary_address1, zip_royal_mail). "
            "Note will be overridden if the Team Configuration is not 'Custom'."
        ),
    )

    columns_to_keep_string = StringField(
        _l("Columns to Keep"),
        validators=[Optional(), Length(max=1000)],
        description=_l(
            "Comma-separated list of column names to keep in output (e.g., first_name, last_name, email). "
            "Note will be overridden if the Team Configuration is not 'Custom'."
        ),
    )


class CreateAssemblyGSheetForm(AssemblyGSheetForm):
    """Form specifically for creating assembly Google Spreadsheet configuration."""


class EditAssemblyGSheetForm(AssemblyGSheetForm):
    """Form specifically for editing assembly Google Spreadsheet configuration."""


class EditUserForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for editing user details (admin only)."""

    first_name = StringField(
        _l("First Name"),
        validators=[Length(max=100)],
        description=_l("User's first name"),
        render_kw={"autocomplete": "given-name"},
    )

    last_name = StringField(
        _l("Last Name"),
        validators=[Length(max=100)],
        description=_l("User's last name"),
        render_kw={"autocomplete": "family-name"},
    )

    global_role = RadioField(
        _l("Global Role"),
        choices=[(k, v) for k, v in global_role_options.items()],
        coerce=coerce_for_enum(GlobalRole),
        validators=[DataRequired()],
        description=_l("User's global role determines their permissions across the system"),
    )

    is_active = BooleanField(
        _l("Active Account"),
        description=_l("Inactive users cannot log in to the system"),
        default=True,
    )


class CreateInviteForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for creating user invites (admin only)."""

    global_role = RadioField(
        _l("Role for New User"),
        choices=[(k, v) for k, v in global_role_options.items()],
        coerce=coerce_for_enum(GlobalRole),
        validators=[DataRequired()],
        description=_l("The role that will be granted to the user who uses this invite"),
        default="user",
    )

    email = EmailField(
        _l("Email Address (Optional)"),
        validators=[Optional(), DomainEmailValidator(), EmailDoesNotExistValidator()],
        description=_l("Optional - if provided, the invite will be emailed to this address"),
        render_kw={"autocomplete": "email"},
    )

    expires_in_hours = IntegerField(
        _l("Expires In (Hours)"),
        validators=[Optional()],
        description=_l("Optional - number of hours until the invite expires (default: 168 hours / 7 days)"),
        default=168,
    )


class AddUserToAssemblyForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for adding a user to an assembly with a specific role."""

    user_id = StringField(
        _l("User Email"),
        validators=[DataRequired()],
        description=_l("Select a user to add to this assembly"),
    )

    role = RadioField(
        _l("Assembly Role"),
        choices=[(k, v) for k, v in assembly_role_options.items()],
        coerce=coerce_for_enum(AssemblyRole),
        validators=[DataRequired()],
        description=_l("Select the role this user will have on the assembly"),
        default=AssemblyRole.CONFIRMATION_CALLER.name,
    )


class EditOwnProfileForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for users to edit their own profile."""

    first_name = StringField(
        _l("First Name"),
        validators=[Length(max=100)],
        description=_l("Your first name"),
        render_kw={"autocomplete": "given-name"},
    )

    last_name = StringField(
        _l("Last Name"),
        validators=[Length(max=100)],
        description=_l("Your last name"),
        render_kw={"autocomplete": "family-name"},
    )


class ChangeOwnPasswordForm(FlaskForm):  # type: ignore[no-any-unimported]
    """Form for users to change their own password."""

    current_password = PasswordField(
        _l("Current Password"),
        validators=[DataRequired()],
        render_kw={"autocomplete": "current-password"},
    )

    new_password = PasswordField(
        _l("New Password"),
        validators=[DataRequired(), Length(min=8)],
        render_kw={"autocomplete": "new-password"},
    )

    new_password_confirm = PasswordField(
        _l("Confirm New Password"),
        validators=[DataRequired(), EqualTo("new_password", message=_l("Passwords must match"))],
        render_kw={"autocomplete": "new-password"},
    )
