"""ABOUTME: Dynamic Flask-WTF form builder for the edit-respondent page.
ABOUTME: Fields are constructed per-request from the per-assembly field schema."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask_wtf import FlaskForm
from wtforms import IntegerField, RadioField, SelectField, StringField, TextAreaField
from wtforms.utils import unset_value
from wtforms.validators import DataRequired, InputRequired, Optional, ValidationError

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    CHOICE_TYPES,
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
)
from opendlp.domain.validators import parse_date_text, validate_date_field
from opendlp.entrypoints.forms import DomainEmailValidator
from opendlp.translations import gettext as _
from opendlp.translations import lazy_gettext as _l

if TYPE_CHECKING:
    from opendlp.domain.respondents import Respondent

ATTR_FIELD_PREFIX = "attr_"
FIXED_FIELD_NAMES = {"email", "eligible", "can_attend", "consent", "stay_on_db"}


class _HelpTextRadioField(RadioField):
    def __init__(self, *args: Any, option_help_text: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.option_help_text: dict[str, str] = option_help_text or {}


class _HelpTextSelectField(SelectField):
    def __init__(self, *args: Any, option_help_text: dict[str, str] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.option_help_text: dict[str, str] = option_help_text or {}


class _DatePartsField(StringField):
    """A DATE attribute entered as three day/month/year inputs.

    The parts post as ``{name}-day``, ``{name}-month`` and ``{name}-year``, the
    same shape as the registration form. ``data`` is the ISO date the parts
    describe, or "" when all three are blank; ``day``/``month``/``year`` hold
    the text to show in each input.
    """

    PARTS = ("day", "month", "year")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.day = ""
        self.month = ""
        self.year = ""

    def process(self, formdata: Any, data: Any = unset_value, extra_filters: Any = None) -> None:
        super().process(formdata, data, extra_filters)
        parsed = parse_date_text(str(self.data or "").strip())
        if parsed is not None:
            self.day, self.month, self.year = str(parsed.day), str(parsed.month), str(parsed.year)
        if formdata is not None and any(f"{self.name}-{part}" in formdata for part in self.PARTS):
            self.day, self.month, self.year = (
                str(formdata.get(f"{self.name}-{part}", "")).strip() for part in self.PARTS
            )
            self.data = ""

    def pre_validate(self, form: Any) -> None:
        if not (self.day or self.month or self.year):
            self.data = ""
            return
        value, error = validate_date_field(f"{self.day}/{self.month}/{self.year}")
        if error:
            raise ValidationError(error)
        self.data = value


def _bool_choices() -> list[tuple[str, str]]:
    return [("true", _("Yes")), ("false", _("No"))]


def _bool_or_none_choices() -> list[tuple[str, str]]:
    return [("true", _("Yes")), ("false", _("No")), ("", _("Not set"))]


def _bool_value_to_radio(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _ensure_current_value_in_options(
    options: list[ChoiceOption], current_value: str
) -> tuple[list[ChoiceOption], bool]:
    """If `current_value` isn't in `options`, append it. Returns new list + whether it was drifted."""
    if not current_value:
        return options, False
    if any(o.value == current_value for o in options):
        return options, False
    return [*options, ChoiceOption(value=current_value)], True


def _build_choice_field(
    field_def: RespondentFieldDefinition,
    current_value: str,
    warnings: list[str],
) -> tuple[Any, Any]:
    options = list(field_def.options or [])
    options, drifted = _ensure_current_value_in_options(options, current_value)
    if drifted:
        warnings.append(
            str(
                _(
                    "The current value for '%(label)s' is not in the options list: %(value)s.",
                    label=field_def.label,
                    value=current_value,
                )
            )
        )

    choices: list[tuple[str, str]] = [("", _("— none —"))]
    choices.extend([(o.value, o.value) for o in options])
    option_help = {o.value: o.help_text for o in options}

    field: _HelpTextSelectField | _HelpTextRadioField
    if field_def.effective_field_type == FieldType.CHOICE_DROPDOWN:
        field = _HelpTextSelectField(
            field_def.label,
            choices=choices,
            validators=[Optional()],
            option_help_text=option_help,
        )
    else:
        field = _HelpTextRadioField(
            field_def.label,
            choices=choices,
            validators=[Optional()],
            option_help_text=option_help,
        )
    return field, current_value


def _build_date_field(
    field_def: RespondentFieldDefinition,
    current_value: str,
    warnings: list[str],
) -> _DatePartsField:
    if current_value and parse_date_text(current_value.strip()) is None:
        warnings.append(
            _(
                "The current value for '%(label)s' is not a date: %(value)s. "
                "Enter a date, or it will be cleared when you save.",
                label=field_def.label,
                value=current_value,
            )
        )
    return _DatePartsField(field_def.label)


def _attr_field_name(field_key: str) -> str:
    return f"{ATTR_FIELD_PREFIX}{field_key}"


def _build_fixed_field(field_def: RespondentFieldDefinition, respondent: Respondent) -> tuple[str, Any, Any]:
    form_name = field_def.field_key
    label = field_def.label
    if field_def.field_key == "email":
        email_field: Any = StringField(label, validators=[Optional(), DomainEmailValidator()])
        return form_name, email_field, respondent.email
    # fixed booleans (eligible/can_attend/consent/stay_on_db) are always BOOL_OR_NONE
    bool_field: Any = _HelpTextRadioField(label, choices=_bool_or_none_choices(), validators=[Optional()])
    return form_name, bool_field, _bool_value_to_radio(getattr(respondent, field_def.field_key))


def _build_field_for_definition(
    field_def: RespondentFieldDefinition,
    respondent: Respondent,
    warnings: list[str],
) -> tuple[str, Any, Any] | None:
    """Return (form_field_name, wtforms_field_instance, initial_data) or None to skip."""
    if field_def.is_derived:
        return None

    effective = field_def.effective_field_type
    label = field_def.label

    if field_def.field_key in FIXED_FIELD_NAMES:
        return _build_fixed_field(field_def, respondent)

    form_name = _attr_field_name(field_def.field_key)
    current_value = str(respondent.attributes.get(field_def.field_key, "") or "")

    if effective == FieldType.LONGTEXT:
        return form_name, TextAreaField(label, validators=[Optional()]), current_value
    if effective == FieldType.DATE:
        return form_name, _build_date_field(field_def, current_value, warnings), current_value
    if effective == FieldType.INTEGER:
        return form_name, IntegerField(label, validators=[Optional()]), current_value or None
    if effective == FieldType.EMAIL:
        return form_name, StringField(label, validators=[Optional(), DomainEmailValidator()]), current_value
    if effective == FieldType.BOOL:
        strict_bool_field: Any = _HelpTextRadioField(label, choices=_bool_choices(), validators=[InputRequired()])
        return (
            form_name,
            strict_bool_field,
            current_value if current_value in {"true", "false"} else "",
        )
    if effective == FieldType.BOOL_OR_NONE:
        nullable_bool_field: Any = _HelpTextRadioField(label, choices=_bool_or_none_choices(), validators=[Optional()])
        return (
            form_name,
            nullable_bool_field,
            current_value if current_value in {"true", "false"} else "",
        )
    if effective in CHOICE_TYPES:
        field, data = _build_choice_field(field_def, current_value, warnings)
        return form_name, field, data
    return form_name, StringField(label, validators=[Optional()]), current_value


def build_edit_respondent_form(  # type: ignore[no-any-unimported]
    schema: list[RespondentFieldDefinition],
    respondent: Respondent,
) -> tuple[FlaskForm, list[str]]:
    """Return (form_instance, drift_warnings).

    Each non-derived schema field becomes a form field. Fixed-field keys use
    their plain name (e.g. `email`); attribute fields are prefixed with
    `attr_` so they can't shadow WTForms attributes or each other.
    """
    warnings: list[str] = []
    fields: dict[str, Any] = {
        "comment": TextAreaField(_l("Change note"), validators=[DataRequired()]),
    }
    initial: dict[str, Any] = {}
    for field_def in schema:
        built = _build_field_for_definition(field_def, respondent, warnings)
        if built is None:
            continue
        name, field_inst, data = built
        fields[name] = field_inst
        initial[name] = data

    form_cls = type("EditRespondentForm", (FlaskForm,), fields)
    form = form_cls(data=initial)
    return form, warnings


def radio_or_none_to_bool(raw: str | None) -> bool | None:
    """Coerce a bool-or-none radio submission to True/False/None."""
    if raw == "true":
        return True
    if raw == "false":
        return False
    return None


def radio_to_bool(raw: str | None) -> bool:
    """Coerce a strict-bool radio submission to True/False.

    Raises ValueError for missing/blank input so the form can reject it.
    """
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError("Yes/No value required")


__all__ = [
    "ATTR_FIELD_PREFIX",
    "BOOL_TYPES",
    "CHOICE_TYPES",
    "FIXED_FIELD_NAMES",
    "build_edit_respondent_form",
    "radio_or_none_to_bool",
    "radio_to_bool",
]
