"""ABOUTME: Backoffice routes for managing a per-assembly respondent field schema
ABOUTME: Read-only schema rows plus an HTMX add/edit field modal; move, delete, initialise"""

import contextlib
import uuid
from itertools import zip_longest
from typing import Any

import structlog
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_field_schema import (
    CHOICE_TYPES,
    FIELD_TYPE_LABELS,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    ChoiceOption,
    DerivationType,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    normalise_field_key,
)
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
    ServiceLayerError,
)
from opendlp.service_layer.respondent_field_schema_service import (
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    add_choice_option,
    add_field,
    delete_field,
    get_schema,
    get_schema_grouped,
    guess_field_types,
    initialise_empty_schema,
    remove_choice_option,
    reorder_group,
    update_choice_option,
    update_field,
)
from opendlp.service_layer.respondent_field_spec_service import build_field_spec
from opendlp.translations import gettext as _

respondent_field_schema_bp = Blueprint("respondent_field_schema", __name__)

logger = structlog.get_logger(__name__)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _schema_page_redirect(assembly_id: uuid.UUID) -> ResponseReturnValue:
    # Preserve the submitting form's scroll position so saving a field, moving a
    # row, or editing an option doesn't bounce the user back to the top of the page.
    return redirect_preserving_scroll(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))


def _parse_group(raw: str | None) -> RespondentFieldGroup | None:
    """Parse a submitted group value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return RespondentFieldGroup(raw)
    except ValueError:
        return None


def _parse_field_type(raw: str | None) -> FieldType | None:
    """Parse a submitted field_type value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return FieldType(raw)
    except ValueError:
        return None


def _parse_on_registration_page(raw: str | None) -> FieldOnRegistrationPage | None:
    """Parse a submitted on_registration_page value; returns None if empty or unrecognised."""
    if not raw:
        return None
    try:
        return FieldOnRegistrationPage(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# The modal's user-facing type taxonomy.
#
# The modal offers a shorter menu than FieldType: LONGTEXT and BOOL_OR_NONE are
# excluded (no current use case outside CSV import), but a field that already
# has one of those types shows it as a selectable entry so editing never forces
# a type change. "free_text" fans out to TEXT/EMAIL/INTEGER via a sub-select
# and "choice" to CHOICE_RADIO/CHOICE_DROPDOWN.
# ---------------------------------------------------------------------------

_STANDARD_TYPE_CHOICES: list[tuple[str, Any]] = [
    ("bool", FIELD_TYPE_LABELS[FieldType.BOOL]),
    ("free_text", FIELD_TYPE_LABELS[FieldType.TEXT]),
    ("choice", FIELD_TYPE_LABELS[FieldType.CHOICE_RADIO]),
    ("date", FIELD_TYPE_LABELS[FieldType.DATE]),
]

_LEGACY_TYPE_CHOICES: dict[FieldType, tuple[str, Any]] = {
    FieldType.LONGTEXT: ("longtext", FIELD_TYPE_LABELS[FieldType.LONGTEXT]),
    FieldType.BOOL_OR_NONE: ("bool_or_none", FIELD_TYPE_LABELS[FieldType.BOOL_OR_NONE]),
}

_FREE_TEXT_SUBTYPES: dict[str, FieldType] = {
    "text": FieldType.TEXT,
    "email": FieldType.EMAIL,
    "integer": FieldType.INTEGER,
}

_CHOICE_STYLES: dict[str, FieldType] = {
    "choice_radio": FieldType.CHOICE_RADIO,
    "choice_dropdown": FieldType.CHOICE_DROPDOWN,
}


def _field_type_from_taxonomy(values: dict[str, Any]) -> FieldType:
    """Map the modal's type_choice/subtype/style values onto a FieldType."""
    type_choice = values["type_choice"]
    if type_choice == "bool":
        return FieldType.BOOL
    if type_choice == "free_text":
        return _FREE_TEXT_SUBTYPES.get(values["free_text_subtype"], FieldType.TEXT)
    if type_choice == "choice":
        return _CHOICE_STYLES.get(values["choice_style"], FieldType.CHOICE_RADIO)
    if type_choice == "date":
        return FieldType.DATE
    if type_choice == "longtext":
        return FieldType.LONGTEXT
    if type_choice == "bool_or_none":
        return FieldType.BOOL_OR_NONE
    return FieldType.TEXT


def _taxonomy_from_field_type(field_type: FieldType) -> dict[str, str]:
    """The modal taxonomy values that would produce ``field_type``."""
    values = {"type_choice": "free_text", "free_text_subtype": "text", "choice_style": "choice_radio"}
    if field_type == FieldType.BOOL:
        values["type_choice"] = "bool"
    elif field_type in (FieldType.TEXT, FieldType.EMAIL, FieldType.INTEGER):
        values["free_text_subtype"] = next(k for k, v in _FREE_TEXT_SUBTYPES.items() if v == field_type)
    elif field_type in CHOICE_TYPES:
        values["type_choice"] = "choice"
        values["choice_style"] = field_type.value
    elif field_type == FieldType.DATE:
        values["type_choice"] = "date"
    elif field_type in _LEGACY_TYPE_CHOICES:
        values["type_choice"] = _LEGACY_TYPE_CHOICES[field_type][0]
    return values


# ---------------------------------------------------------------------------
# Modal context builders — everything _field_modal.html needs to render.
# ---------------------------------------------------------------------------


def _modal_values_from_request(source: Any) -> dict[str, Any]:
    """Rebuild the modal form state from a submitted (or hx-included) form."""
    options = [
        {"value": value, "help_text": help_text}
        for value, help_text in zip_longest(source.getlist("option_value"), source.getlist("option_help"), fillvalue="")
    ]
    return {
        "label": source.get("label", ""),
        "field_key": source.get("field_key", ""),
        "type_choice": source.get("type_choice", "free_text"),
        "free_text_subtype": source.get("free_text_subtype", "text"),
        "choice_style": source.get("choice_style", "choice_radio"),
        "help_text": source.get("help_text", ""),
        "on_registration_page": source.get("on_registration_page", FieldOnRegistrationPage.YES_REQUIRED.value),
        "options": options,
    }


def _modal_values_from_field(field: RespondentFieldDefinition) -> dict[str, Any]:
    """The modal form state for editing an existing field."""
    values: dict[str, Any] = {
        "label": field.label,
        "field_key": field.field_key,
        "help_text": field.help_text,
        "on_registration_page": field.on_registration_page.value,
        "options": [{"value": o.value, "help_text": o.help_text} for o in field.options or []],
    }
    values.update(_taxonomy_from_field_type(field.field_type))
    return values


def _default_modal_values() -> dict[str, Any]:
    return {
        "label": "",
        "field_key": "",
        "type_choice": "free_text",
        "free_text_subtype": "text",
        "choice_style": "choice_radio",
        "help_text": "",
        "on_registration_page": FieldOnRegistrationPage.YES_REQUIRED.value,
        "options": [],
    }


def _normalise_modal_values(values: dict[str, Any]) -> dict[str, Any]:
    """Keep the rendered form coherent: a choice type always shows ≥1 option row."""
    if values["type_choice"] == "choice" and not values["options"]:
        values["options"] = [{"value": "", "help_text": ""}]
    return values


def _new_modal_ctx(assembly_id: uuid.UUID, values: dict[str, Any], error: str = "") -> dict[str, Any]:
    return {
        "mode": "new",
        "field": None,
        "action_url": url_for("respondent_field_schema.add_field_view", assembly_id=assembly_id),
        "refresh_url": url_for("respondent_field_schema.new_field_modal", assembly_id=assembly_id),
        "type_choices": list(_STANDARD_TYPE_CHOICES),
        "type_locked": False,
        "is_derived": False,
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _edit_modal_ctx(
    assembly_id: uuid.UUID, field: RespondentFieldDefinition, values: dict[str, Any], error: str = ""
) -> dict[str, Any]:
    type_choices = list(_STANDARD_TYPE_CHOICES)
    if field.field_type in _LEGACY_TYPE_CHOICES:
        type_choices.append(_LEGACY_TYPE_CHOICES[field.field_type])
    return {
        "mode": "edit",
        "field": field,
        "action_url": url_for("respondent_field_schema.update_field_view", assembly_id=assembly_id, field_id=field.id),
        "refresh_url": url_for("respondent_field_schema.edit_field_modal", assembly_id=assembly_id, field_id=field.id),
        "type_choices": type_choices,
        "type_locked": field.is_fixed,
        "is_derived": field.is_derived,
        "error": error,
        "values": _normalise_modal_values(values),
    }


def _apply_option_action(values: dict[str, Any], form_action: str) -> dict[str, Any]:
    """Apply an options-editor round-trip action (add/remove a row) to the form state."""
    if form_action == "add_option":
        values["options"].append({"value": "", "help_text": ""})
    elif form_action.startswith("remove_option_"):
        try:
            index = int(form_action.removeprefix("remove_option_"))
        except ValueError:
            return values
        if 0 <= index < len(values["options"]):
            values["options"].pop(index)
    return values


def _submitted_options(values: dict[str, Any]) -> list[ChoiceOption]:
    """The non-blank option rows as domain objects; blank rows are dropped."""
    return [
        ChoiceOption(value=row["value"].strip(), help_text=row["help_text"].strip())
        for row in values["options"]
        if row["value"].strip()
    ]


# ---------------------------------------------------------------------------
# Page and fragment rendering.
# ---------------------------------------------------------------------------


def _derivation_type_labels() -> dict[str, str]:
    return {
        DerivationType.AGE_BRACKET.value: _("Age brackets"),
        DerivationType.SMALL_MAPPING.value: _("Map choices"),
        DerivationType.LARGE_MAPPING.value: _("Lookup table"),
    }


def _schema_page_context(assembly_id: uuid.UUID) -> dict[str, Any]:
    """Everything view.html and _editor.html need to render the schema page."""
    uow = bootstrap.get_flask_uow()
    gsheet = None
    csv_status = None
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        grouped = get_schema_grouped(uow, current_user.id, assembly_id)

        # Reuse the assembly-tabs computed state so the tab bar renders correctly.
        # Both lookups are optional — a fresh assembly has neither.
        with contextlib.suppress(ServiceLayerError):
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
        with contextlib.suppress(ServiceLayerError):
            csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    sections = [
        {
            "group": group,
            "label": GROUP_LABELS[group],
            "fields": grouped.get(group, []),
        }
        for group in GROUP_DISPLAY_ORDER
    ]
    schema_has_rows = any(section["fields"] for section in sections)

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    all_fields = [f for group_fields in grouped.values() for f in group_fields]
    has_guessable_text_rows = any(
        not f.is_fixed and not f.is_derived and f.field_type == FieldType.TEXT for f in all_fields
    )
    with uow:
        has_respondents = uow.respondents.count_by_assembly_id(assembly_id) > 0
    show_guess_button = has_guessable_text_rows and has_respondents

    return {
        "assembly": assembly,
        "sections": sections,
        "group_choices": [(group.value, GROUP_LABELS[group]) for group in GROUP_DISPLAY_ORDER],
        "field_type_labels_by_value": {ft.value: FIELD_TYPE_LABELS[ft] for ft in FieldType},
        "derivation_type_labels": _derivation_type_labels(),
        "on_registration_page_choices": [
            (FieldOnRegistrationPage.NO.value, _("Not shown")),
            (FieldOnRegistrationPage.YES_OPTIONAL.value, _("Optional")),
            (FieldOnRegistrationPage.YES_REQUIRED.value, _("Required")),
        ],
        "schema_has_rows": schema_has_rows,
        "show_guess_button": show_guess_button,
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


def _render_schema_page(
    assembly_id: uuid.UUID, modal_ctx: dict[str, Any] | None = None, status: int = 200
) -> ResponseReturnValue:
    """Render the full schema page, optionally with the field modal already open."""
    return render_template(
        "backoffice/respondent_field_schema/view.html",
        modal_ctx=modal_ctx,
        **_schema_page_context(assembly_id),
    ), status


def _render_editor_fragment(assembly_id: uuid.UUID, oob: bool = False) -> ResponseReturnValue:
    """Render just the #schema-editor fragment.

    With ``oob=True`` the fragment swaps out-of-band, so the (otherwise empty)
    response also clears #field-modal-container — closing the modal that
    triggered the mutation.
    """
    return render_template(
        "backoffice/respondent_field_schema/_editor.html",
        oob=oob,
        **_schema_page_context(assembly_id),
    ), 200


def _render_modal_fragment(assembly_id: uuid.UUID, modal_ctx: dict[str, Any], status: int = 200) -> ResponseReturnValue:
    return render_template(
        "backoffice/respondent_field_schema/_field_modal.html",
        modal_ctx=modal_ctx,
        **_schema_page_context(assembly_id),
    ), status


def _load_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> RespondentFieldDefinition | None:
    uow = bootstrap.get_flask_uow()
    with uow:
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            return None
        detached: RespondentFieldDefinition = field.create_detached_copy()
        return detached


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema")
@login_required
def view_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display the respondent field schema for an assembly."""
    try:
        return _render_schema_page(assembly_id)
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema.json")
@login_required
def field_spec_json(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Return the assembly's full respondent field spec as JSON.

    Deliberately not linked from anywhere in the UI. It exists so a script
    outside the app — a test-data generator, for one — can discover an
    assembly's CSV columns and their valid values without scraping the schema
    page. See docs/respondent_field_spec.md for the shape.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            spec = build_field_spec(uow, current_user.id, assembly_id)
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for field spec",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        return jsonify({"error": _("Assembly not found")}), 404
    except InsufficientPermissions as e:
        logger.warning("Insufficient permissions for field spec", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("You don't have permission to view this assembly")}), 403
    return jsonify(spec), 200


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/initialise", methods=["POST"])
@login_required
def initialise_schema(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Seed an empty schema (fixed-field rows only) for registration-first assemblies."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            inserted = initialise_empty_schema(uow, current_user.id, assembly_id)
        if inserted:
            flash(_("Schema initialised with %(count)d fixed fields.", count=inserted), "success")
        else:
            flash(_("Schema already exists."), "info")
    except InsufficientPermissions:
        flash(_("You don't have permission to initialise the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/new-modal")
@login_required
def new_field_modal(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the add-field modal.

    HTMX requests get the modal fragment — both on first open and on the
    type-radio re-renders, which hx-include the form state as query args. A
    plain navigation gets the whole schema page with the modal already open,
    so the flow still works (via full page loads) when JS is unavailable.
    """
    values = _modal_values_from_request(request.args) if "modal" in request.args else _default_modal_values()
    modal_ctx = _new_modal_ctx(assembly_id, values)
    try:
        if _is_htmx():
            return _render_modal_fragment(assembly_id, modal_ctx)
        return _render_schema_page(assembly_id, modal_ctx=modal_ctx)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@respondent_field_schema_bp.route("/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/edit-modal")
@login_required
def edit_field_modal(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the edit-field modal (HTMX fragment / full-page fallback)."""
    try:
        field = _load_field(assembly_id, field_id)
        if field is None:
            flash(_("Field not found."), "error")
            return redirect(url_for("respondent_field_schema.view_schema", assembly_id=assembly_id))
        values = (
            _modal_values_from_request(request.args) if "modal" in request.args else _modal_values_from_field(field)
        )
        modal_ctx = _edit_modal_ctx(assembly_id, field, values)
        if _is_htmx():
            return _render_modal_fragment(assembly_id, modal_ctx)
        return _render_schema_page(assembly_id, modal_ctx=modal_ctx)
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _modal_roundtrip_response(
    assembly_id: uuid.UUID, modal_ctx: dict[str, Any], status: int = 200
) -> ResponseReturnValue:
    """Re-render the modal without saving — HTMX gets the fragment, no-JS the full page."""
    if _is_htmx():
        return _render_modal_fragment(assembly_id, modal_ctx, status=status)
    return _render_schema_page(assembly_id, modal_ctx=modal_ctx, status=status)


def _flash_failure_response(assembly_id: uuid.UUID, message: str) -> ResponseReturnValue:
    flash(message, "error")
    return _schema_page_redirect(assembly_id)


def _try_add_field(assembly_id: uuid.UUID, values: dict[str, Any], is_modal: bool) -> str:
    """Validate and save a new field; returns a user-facing error message, or "" on success."""
    label = values["label"].strip()
    field_key = normalise_field_key(values["field_key"] or label or request.form.get("field_key", ""))
    if not field_key:
        return _("A label or field key is required (letters, numbers and underscores).")
    group = _parse_group(request.form.get("group")) or RespondentFieldGroup.OTHER
    if is_modal:
        field_type = _field_type_from_taxonomy(values)
    else:
        field_type = _parse_field_type(request.form.get("field_type")) or FieldType.TEXT
    on_registration_page = (
        _parse_on_registration_page(values["on_registration_page"]) or FieldOnRegistrationPage.YES_REQUIRED
    )

    options = _submitted_options(values) if field_type in CHOICE_TYPES else None
    if field_type in CHOICE_TYPES and not options:
        return _("A choice field needs at least one option.")

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            add_field(
                uow,
                current_user.id,
                assembly_id,
                field_key,
                label=label or None,
                group=group,
                field_type=field_type,
                options=options,
                on_registration_page=on_registration_page,
                help_text=values["help_text"].strip(),
            )
    except FieldDefinitionConflictError as e:
        return str(e)
    except InsufficientPermissions:
        return _("You don't have permission to edit the schema")
    except NotFoundError:
        return _("Assembly not found")
    return ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/add",
    methods=["POST"],
)
@login_required
def add_field_view(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a new field to the schema — from the modal, or a plain form post.

    Modal submissions carry the type taxonomy (``type_choice`` etc.), a
    wholesale options list, and a ``form_action`` distinguishing Save from the
    options-editor round-trips. A plain post with ``field_key``/``field_type``
    (the pre-modal shape) still works so scripted callers don't break.
    """
    form_action = request.form.get("form_action", "save")
    is_modal = request.form.get("modal") == "1"
    values = _modal_values_from_request(request.form)

    if is_modal and form_action != "save":
        # An options-editor round-trip (add/remove a row) or a no-JS type refresh
        # — re-render the form with the entered values, saving nothing.
        return _modal_roundtrip_response(
            assembly_id, _new_modal_ctx(assembly_id, _apply_option_action(values, form_action))
        )

    error = _try_add_field(assembly_id, values, is_modal)
    if error:
        if is_modal:
            return _modal_roundtrip_response(assembly_id, _new_modal_ctx(assembly_id, values, error=error), status=422)
        return _flash_failure_response(assembly_id, error)

    if _is_htmx():
        return _render_editor_fragment(assembly_id, oob=True)
    flash(_("Field added."), "success")
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/update",
    methods=["POST"],
)
@login_required
def update_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update a field — from the edit modal, or the row's section select.

    Modal submissions carry the type taxonomy and a wholesale options list;
    the row form posts just ``group``. A plain post with ``field_type`` (the
    pre-modal shape) still works so scripted callers don't break.
    """
    form_action = request.form.get("form_action", "save")
    is_modal = request.form.get("modal") == "1"
    values = _modal_values_from_request(request.form)

    field = _load_field(assembly_id, field_id)
    if field is None:
        return _field_missing_response(assembly_id, oob=is_modal)

    if is_modal and form_action != "save":
        return _modal_roundtrip_response(
            assembly_id, _edit_modal_ctx(assembly_id, field, _apply_option_action(values, form_action))
        )

    if is_modal:
        update_kwargs, error = _modal_update_kwargs(field, values)
    else:
        update_kwargs, error = _legacy_update_kwargs()
        if not update_kwargs and not error:
            return _nothing_submitted_response(assembly_id)

    if not error:
        error = _try_update_field(assembly_id, field_id, update_kwargs)

    if error:
        if is_modal:
            return _modal_roundtrip_response(
                assembly_id, _edit_modal_ctx(assembly_id, field, values, error=error), status=422
            )
        return _flash_failure_response(assembly_id, error)

    if _is_htmx():
        # A modal save clears the modal via the out-of-band swap; the row's
        # section select targets #schema-editor directly, so no OOB there.
        return _render_editor_fragment(assembly_id, oob=is_modal)
    flash(_("Field updated."), "success")
    return _schema_page_redirect(assembly_id)


def _field_missing_response(assembly_id: uuid.UUID, oob: bool) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(assembly_id, oob=oob)
    flash(_("Field not found."), "error")
    return _schema_page_redirect(assembly_id)


def _nothing_submitted_response(assembly_id: uuid.UUID) -> ResponseReturnValue:
    if _is_htmx():
        return _render_editor_fragment(assembly_id)
    flash(_("No changes submitted."), "info")
    return _schema_page_redirect(assembly_id)


def _modal_update_kwargs(field: RespondentFieldDefinition, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The update_field kwargs for a modal save, plus a validation error message ("" when valid).

    A fixed field keeps its type and a derived field keeps its type, options and
    registration state — the modal doesn't render those controls, so the save
    doesn't touch them.
    """
    update_kwargs: dict[str, Any] = {
        "label": values["label"].strip() or None,
        "help_text": values["help_text"],
    }
    if not field.is_derived:
        update_kwargs["on_registration_page"] = _parse_on_registration_page(values["on_registration_page"])
    if not field.is_fixed and not field.is_derived:
        field_type = _field_type_from_taxonomy(values)
        update_kwargs["field_type"] = field_type
        if field_type in CHOICE_TYPES:
            options = _submitted_options(values)
            if not options:
                return {}, _("A choice field needs at least one option.")
            update_kwargs["options"] = options
    return update_kwargs, ""


def _legacy_update_kwargs() -> tuple[dict[str, Any], str]:
    """The update_field kwargs for a plain (non-modal) post; empty dict means nothing was submitted."""
    label = request.form.get("label", "").strip() or None
    group = _parse_group(request.form.get("group"))
    field_type = _parse_field_type(request.form.get("field_type"))
    on_registration_page = _parse_on_registration_page(request.form.get("on_registration_page"))
    if label is None and group is None and field_type is None and on_registration_page is None:
        return {}, ""
    return {
        "label": label,
        "group": group,
        "field_type": field_type,
        "on_registration_page": on_registration_page,
    }, ""


def _try_update_field(assembly_id: uuid.UUID, field_id: uuid.UUID, update_kwargs: dict[str, Any]) -> str:
    """Run the update; returns a user-facing error message, or "" on success."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            update_field(uow, current_user.id, assembly_id, field_id, **update_kwargs)
    except FieldDefinitionConflictError as e:
        return str(e)
    except FieldDefinitionNotFoundError:
        # The message may carry internal detail — show a generic one.
        return _("Field not found.")
    except ValueError as e:
        # Domain validation (e.g. a choice type without options) — the message
        # is developer-written and safe to show.
        return str(e)
    except InsufficientPermissions:
        return _("You don't have permission to edit the schema")
    except NotFoundError:
        return _("Assembly not found")
    return ""


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/guess-types",
    methods=["POST"],
)
@login_required
def guess_types_view(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Overwrite TEXT-typed schema rows with guessed types based on respondent data."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            changed = guess_field_types(uow, current_user.id, assembly_id)
        if changed:
            flash(_("Guessed types for %(count)d fields.", count=len(changed)), "success")
        else:
            flash(_("No fields were guessed — no untouched text rows to update."), "info")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/add",
    methods=["POST"],
)
@login_required
def add_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Append a ChoiceOption to a choice field."""
    value = request.form.get("value", "").strip()
    help_text = request.form.get("help_text", "")
    if not value:
        flash(_("Option value is required."), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            add_choice_option(uow, current_user.id, assembly_id, field_id, value, help_text)
        flash(_("Option added."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/update",
    methods=["POST"],
)
@login_required
def update_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Update the value and/or help_text of an existing ChoiceOption."""
    old_value = request.form.get("old_value", "").strip()
    new_value = request.form.get("value", "").strip()
    new_help_text = request.form.get("help_text", "")
    if not old_value:
        flash(_("Original option value is required."), "error")
        return _schema_page_redirect(assembly_id)
    if not new_value:
        flash(_("Option value cannot be blank."), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            update_choice_option(
                uow,
                current_user.id,
                assembly_id,
                field_id,
                old_value=old_value,
                new_value=new_value,
                new_help_text=new_help_text,
            )
        flash(_("Option updated."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Option not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/options/remove",
    methods=["POST"],
)
@login_required
def remove_option_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a ChoiceOption from a choice field."""
    value = request.form.get("value", "").strip()
    if not value:
        flash(_("Option value is required."), "error")
        return _schema_page_redirect(assembly_id)
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            remove_choice_option(uow, current_user.id, assembly_id, field_id, value)
        flash(_("Option removed."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Option not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/move",
    methods=["POST"],
)
@login_required
def move_field(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Shift a field up or down one slot within its group.

    Accepts a ``direction`` form field of ``"up"`` or ``"down"``. Reuses the
    service-layer ``reorder_group`` to re-issue sort_orders atomically.
    """
    direction = request.form.get("direction", "")
    if direction not in {"up", "down"}:
        flash(_("Invalid move direction."), "error")
        return _schema_page_redirect(assembly_id)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            fields = get_schema(uow, current_user.id, assembly_id)
            target = next((f for f in fields if f.id == field_id), None)
            if target is None:
                flash(_("Field not found."), "error")
                return _schema_page_redirect(assembly_id)

            same_group = [f for f in fields if f.group == target.group]
            index = next(i for i, f in enumerate(same_group) if f.id == field_id)
            swap_with = index - 1 if direction == "up" else index + 1
            if swap_with < 0 or swap_with >= len(same_group):
                # Already at the top/bottom — silent no-op rather than a flash.
                return _schema_page_redirect(assembly_id)

            new_order = same_group[:]
            new_order[index], new_order[swap_with] = new_order[swap_with], new_order[index]
            reorder_group(
                uow,
                current_user.id,
                assembly_id,
                target.group,
                [f.id for f in new_order],
            )
    except InsufficientPermissions:
        flash(_("You don't have permission to reorder fields"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)


@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/<uuid:field_id>/delete",
    methods=["POST"],
)
@login_required
def delete_field_view(assembly_id: uuid.UUID, field_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a non-fixed field from the schema. Fixed fields are protected by the service layer."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            delete_field(uow, current_user.id, assembly_id, field_id)
        flash(_("Field removed."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except FieldDefinitionNotFoundError:
        flash(_("Field not found."), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)
