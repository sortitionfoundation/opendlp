"""ABOUTME: Backoffice routes for the target data sources checklist (registration step 1)
ABOUTME: One row per target; a set-up modal wires each to its field via the four methods"""

import contextlib
import uuid
from typing import Any

import structlog
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_derivation import DEFAULT_FALLBACK, LargeMappingRule
from opendlp.domain.respondent_field_schema import (
    CHOICE_TYPES,
    DerivationType,
    FieldType,
    RespondentFieldDefinition,
    humanise_field_key,
)
from opendlp.entrypoints.blueprints.respondent_field_schema import (
    age_prefill_from_target,
    parse_age_rule,
    parse_small_mapping_rule,
)
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.derivation_service import (
    MappingUploadReport,
    RecomputeReport,
    compatible_source_fields,
    recompute_derived_field,
    upload_large_mapping,
)
from opendlp.service_layer.exceptions import (
    FieldDefinitionConflictError,
    FieldDefinitionNotFoundError,
    InsufficientPermissions,
    NotFoundError,
    ServiceLayerError,
)
from opendlp.service_layer.target_source_service import (
    AgeBracketSpec,
    ExactCopySpec,
    LargeMappingSpec,
    SmallMappingSpec,
    SourceFieldSpec,
    TargetSourceSpec,
    TargetSourceState,
    TargetSourceStatus,
    adopt_field,
    configure_target_source,
    resync_from_target,
    target_source_status,
    unlink,
)
from opendlp.translations import gettext as _

target_sources_bp = Blueprint("target_sources", __name__)

logger = structlog.get_logger(__name__)

_METHOD_EXACT = "exact"

_SOURCE_TYPE_FOR_AGE = {"date": FieldType.DATE, "year": FieldType.INTEGER}


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _method_options() -> list[dict[str, str]]:
    return [
        {"value": _METHOD_EXACT, "label": _("Exact copy")},
        {"value": DerivationType.AGE_BRACKET.value, "label": _("Age ranges")},
        {"value": DerivationType.SMALL_MAPPING.value, "label": _("Map from more options")},
        {"value": DerivationType.LARGE_MAPPING.value, "label": _("Map postcode to value")},
    ]


def _method_help() -> dict[str, str]:
    return {
        _METHOD_EXACT: _("Ask the question with exactly the target's values as the answers"),
        DerivationType.AGE_BRACKET.value: _("Ask for a date or year of birth and compute the age range"),
        DerivationType.SMALL_MAPPING.value: _("Ask with more detailed answers and map each one to a target value"),
        DerivationType.LARGE_MAPPING.value: _("Ask for a value like a postcode and look each answer up in a table"),
    }


def _method_labels() -> dict[str, str]:
    return {option["value"]: option["label"] for option in _method_options()}


# ---------------------------------------------------------------------------
# Form values.
# ---------------------------------------------------------------------------


def _setup_values_from_request(source: Any) -> dict[str, Any]:
    """Read the set-up modal's submitted state, echoing it back on re-render."""
    values = {
        key: (source.get(key) or "").strip()
        for key in (
            "method",
            "source_mode",
            "reuse_field_id",
            "new_field_key",
            "new_field_label",
            "age_source_type",
            "as_of_day",
            "as_of_month",
            "as_of_year",
            "min_age",
            "max_age",
            "boundaries",
        )
    }
    values["map_source"] = source.getlist("map_source")
    values["map_target"] = source.getlist("map_target")
    return values


class _EmptySource:
    """A request-args stand-in with no submitted values."""

    def get(self, _key: str) -> str:
        return ""

    def getlist(self, _key: str) -> list[str]:
        return []


def _default_setup_values(status: TargetSourceStatus) -> dict[str, Any]:
    """Initial modal state: seeded from the linked field when editing, sensible defaults otherwise."""
    values = _setup_values_from_request(_EmptySource())
    field = status.field
    if field is not None and status.state in (TargetSourceState.LINKED_EXACT, TargetSourceState.MATCHED_NOT_LINKED):
        values["method"] = _METHOD_EXACT
        values["source_mode"] = "reuse"
        values["reuse_field_id"] = str(field.id)
    elif field is not None and status.state == TargetSourceState.LINKED_DERIVED:
        values["method"] = (field.derivation_type or DerivationType.LARGE_MAPPING).value
        values["source_mode"] = "reuse"
        if status.source_field is not None:
            values["reuse_field_id"] = str(status.source_field.id)
        _seed_from_derivation(values, field)
    else:
        values["method"] = _METHOD_EXACT
        values["source_mode"] = "create"
    return values


def _seed_from_derivation(values: dict[str, Any], field: RespondentFieldDefinition) -> None:
    config = field.derivation_config or {}
    if field.derivation_type == DerivationType.AGE_BRACKET:
        as_of = str(config.get("as_of_date", ""))
        if len(as_of.split("-")) == 3:
            year, month, day = as_of.split("-")
            values.update({"as_of_year": year, "as_of_month": str(int(month)), "as_of_day": str(int(day))})
        values["min_age"] = str(config.get("min_age", ""))
        values["max_age"] = str(config.get("max_age", ""))
        values["boundaries"] = ", ".join(str(b) for b in config.get("boundaries", []))
    if field.derivation_type == DerivationType.SMALL_MAPPING:
        mapping = config.get("mapping", {})
        values["map_source"] = list(mapping.keys())
        values["map_target"] = list(mapping.values())


# ---------------------------------------------------------------------------
# Page and modal context.
# ---------------------------------------------------------------------------


def _page_context(assembly_id: uuid.UUID) -> dict[str, Any]:
    """Everything view.html and _checklist.html need."""
    uow = bootstrap.get_flask_uow()
    gsheet = None
    csv_status = None
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        statuses = target_source_status(uow, current_user.id, assembly_id)
        with contextlib.suppress(ServiceLayerError):
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
        with contextlib.suppress(ServiceLayerError):
            csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)
    return {
        "assembly": assembly,
        "statuses": statuses,
        "TargetSourceState": TargetSourceState,
        "method_labels": _method_labels(),
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


def _status_for(statuses: list[TargetSourceStatus], category_id: uuid.UUID) -> TargetSourceStatus | None:
    return next((s for s in statuses if s.category.id == category_id), None)


def _exact_reuse_candidates(
    fields: list[RespondentFieldDefinition], target_values: list[str]
) -> list[RespondentFieldDefinition]:
    """Non-derived choice fields whose options cover every target value."""
    candidates = []
    for field in fields:
        if field.is_derived or field.effective_field_type not in CHOICE_TYPES:
            continue
        option_values = {option.value for option in field.options or []}
        if all(value in option_values for value in target_values):
            candidates.append(field)
    return candidates


def _apply_age_prefills(values: dict[str, Any], target_values: list[str], first_date: Any) -> None:
    """Pre-fill blank age inputs: the as-of date from the assembly, brackets from the target."""
    if not (values["as_of_day"] or values["as_of_month"] or values["as_of_year"]) and first_date is not None:
        values["as_of_day"] = str(first_date.day)
        values["as_of_month"] = str(first_date.month)
        values["as_of_year"] = str(first_date.year)
    if not values["boundaries"]:
        prefill = age_prefill_from_target(target_values)
        if prefill:
            values.update(prefill)
    values["min_age"] = values["min_age"] or "16"
    values["max_age"] = values["max_age"] or "100"


def _candidates_for_method(
    fields: list[RespondentFieldDefinition], method: str, target_values: list[str]
) -> list[RespondentFieldDefinition]:
    """The existing fields the chosen method could reuse as its source."""
    if method == _METHOD_EXACT:
        candidates = _exact_reuse_candidates(fields, target_values)
    else:
        candidates = compatible_source_fields(fields, DerivationType(method))
    return sorted(candidates, key=lambda f: f.field_key.casefold())


def _resolve_source_selection(
    values: dict[str, Any], candidates: list[RespondentFieldDefinition], target_name: str
) -> RespondentFieldDefinition | None:
    """Default the source mode and pre-select a name-matching candidate; return the selected field."""
    if values["source_mode"] not in ("reuse", "create"):
        values["source_mode"] = "reuse" if candidates else "create"
    if values["source_mode"] == "reuse" and not values["reuse_field_id"]:
        name_match = next((f for f in candidates if f.field_key.casefold() == target_name.casefold()), None)
        if name_match is not None:
            values["reuse_field_id"] = str(name_match.id)
    return next((f for f in candidates if str(f.id) == values["reuse_field_id"]), None)


def _setup_modal_ctx(
    assembly_id: uuid.UUID, category_id: uuid.UUID, values: dict[str, Any], error: str = ""
) -> dict[str, Any]:
    """Everything the set-up modal needs for the chosen method and source."""
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = uow.assemblies.get(assembly_id)
        first_date = assembly.first_assembly_date if assembly else None
        category = uow.target_categories.get(category_id)
        if category is None or category.assembly_id != assembly_id:
            raise NotFoundError(f"Target category {category_id} not found")
        target = {"id": category.id, "name": category.name, "values": [v.value for v in category.values]}
        fields = [f.create_detached_copy() for f in uow.respondent_field_definitions.list_by_assembly(assembly_id)]

    method = values["method"] if values["method"] in _method_labels() else _METHOD_EXACT
    values["method"] = method

    candidates = _candidates_for_method(fields, method, target["values"])
    selected_source = _resolve_source_selection(values, candidates, target["name"])

    if method == DerivationType.LARGE_MAPPING.value and not values["new_field_key"]:
        values["new_field_key"] = "Postcode"
    if method == DerivationType.AGE_BRACKET.value and not values["new_field_key"]:
        values["new_field_key"] = "date_of_birth"

    preview_labels: list[str] = []
    mismatch_labels: list[str] = []
    if method == DerivationType.AGE_BRACKET.value:
        _apply_age_prefills(values, target["values"], first_date)
        with contextlib.suppress(ValueError):  # incomplete config — no preview yet
            rule = parse_age_rule(values)
            preview_labels = [*rule.bracket_labels(), rule.fallback]
            mismatch_labels = [label for label in rule.bracket_labels() if label not in set(target["values"])]

    map_rows: list[dict[str, str]] = []
    if method == DerivationType.SMALL_MAPPING.value and selected_source is not None and selected_source.options:
        submitted = dict(zip(values["map_source"], values["map_target"], strict=False))
        map_rows = [
            {"source_value": option.value, "target_value": submitted.get(option.value, "")}
            for option in selected_source.options
        ]

    new_field_name = target["name"] if method == _METHOD_EXACT else values["new_field_key"]
    return {
        "target": target,
        "values": values,
        "error": error,
        "method_options": _method_options(),
        "method_help": _method_help(),
        "candidates": candidates,
        "selected_source": selected_source,
        "source_is_integer": selected_source is not None and selected_source.effective_field_type == FieldType.INTEGER,
        "preview_labels": preview_labels,
        "mismatch_labels": mismatch_labels,
        "map_rows": map_rows,
        "fallback": DEFAULT_FALLBACK,
        "new_field_name": new_field_name,
        "refresh_url": url_for("target_sources.setup_modal", assembly_id=assembly_id, category_id=category_id),
        "configure_url": url_for("target_sources.configure_view", assembly_id=assembly_id, category_id=category_id),
    }


# ---------------------------------------------------------------------------
# Rendering helpers.
# ---------------------------------------------------------------------------


def _sources_url(assembly_id: uuid.UUID) -> str:
    return url_for("target_sources.view_sources", assembly_id=assembly_id)


def _render_page(
    assembly_id: uuid.UUID, modal_ctx: dict[str, Any] | None = None, status: int = 200
) -> ResponseReturnValue:
    return render_template(
        "backoffice/target_sources/view.html", modal_ctx=modal_ctx, **_page_context(assembly_id)
    ), status


def _render_checklist_fragment(assembly_id: uuid.UUID, oob: bool = False) -> str:
    return render_template("backoffice/target_sources/_checklist.html", oob=oob, **_page_context(assembly_id))


def _render_setup_modal(assembly_id: uuid.UUID, modal_ctx: dict[str, Any], status: int = 200) -> ResponseReturnValue:
    if _is_htmx():
        return render_template(
            "backoffice/target_sources/_setup_modal.html", modal_ctx=modal_ctx, **_page_context(assembly_id)
        ), status
    return _render_page(assembly_id, modal_ctx={"mode": "setup", "setup_ctx": modal_ctx}, status=status)


def _report_response(
    assembly_id: uuid.UUID,
    report: RecomputeReport,
    title: str,
    upload_report: MappingUploadReport | None = None,
) -> ResponseReturnValue:
    """Show the recompute report in the modal and refresh the checklist behind it."""
    page_ctx = _page_context(assembly_id)
    report_ctx = {
        "report": report,
        "title": title,
        "upload_report": upload_report,
        "close_url": _sources_url(assembly_id),
    }
    if _is_htmx():
        report_html = render_template(
            "backoffice/respondent_field_schema/_derivation_report_modal.html", report_ctx=report_ctx, **page_ctx
        )
        checklist_html = render_template("backoffice/target_sources/_checklist.html", oob=True, **page_ctx)
        return report_html + checklist_html, 200
    return render_template(
        "backoffice/target_sources/view.html", modal_ctx={"mode": "report", "report_ctx": report_ctx}, **page_ctx
    ), 200


def _close_modal_response(assembly_id: uuid.UUID, message: str) -> ResponseReturnValue:
    """Success without a report: refresh the checklist, close the modal."""
    if _is_htmx():
        return _render_checklist_fragment(assembly_id, oob=True), 200
    flash(message, "success")
    return redirect(_sources_url(assembly_id))


def _dashboard_redirect(message: str) -> ResponseReturnValue:
    flash(message, "error")
    return redirect(url_for("backoffice.dashboard"))


# ---------------------------------------------------------------------------
# Spec building.
# ---------------------------------------------------------------------------


def _parse_source_spec(values: dict[str, Any], method: str) -> SourceFieldSpec:
    """The create-or-reuse source the form describes. Raises ValueError with a user message."""
    if values["source_mode"] == "reuse":
        if not values["reuse_field_id"]:
            raise ValueError(_("Choose the field to use"))
        return SourceFieldSpec(reuse_field_id=uuid.UUID(values["reuse_field_id"]))
    if method == _METHOD_EXACT:
        return SourceFieldSpec()
    field_key = values["new_field_key"].strip()
    if not field_key:
        raise ValueError(_("Enter a name for the new registration field"))
    if method == DerivationType.AGE_BRACKET.value:
        field_type = _SOURCE_TYPE_FOR_AGE.get(values["age_source_type"], FieldType.DATE)
    else:
        field_type = FieldType.TEXT
    return SourceFieldSpec(
        field_key=field_key,
        label=values["new_field_label"].strip() or humanise_field_key(field_key),
        field_type=field_type,
    )


def _parse_setup_spec(values: dict[str, Any]) -> TargetSourceSpec:
    """The TargetSourceSpec the modal's values describe. Raises ValueError with a user message."""
    method = values["method"]
    source = _parse_source_spec(values, method)
    if method == _METHOD_EXACT:
        return ExactCopySpec(source=source)
    if method == DerivationType.AGE_BRACKET.value:
        return AgeBracketSpec(rule=parse_age_rule(values), source=source)
    if method == DerivationType.SMALL_MAPPING.value:
        if values["source_mode"] != "reuse":
            raise ValueError(_("Choose the choice field to map from — add it on the registration fields step first"))
        return SmallMappingSpec(rule=parse_small_mapping_rule(values), source=source)
    if method == DerivationType.LARGE_MAPPING.value:
        return LargeMappingSpec(rule=LargeMappingRule(), source=source)
    raise ValueError(_("Choose how the data should be collected"))


def _linked_field_id(assembly_id: uuid.UUID, category_id: uuid.UUID) -> uuid.UUID | None:
    uow = bootstrap.get_flask_uow()
    with uow:
        statuses = target_source_status(uow, current_user.id, assembly_id)
    status = _status_for(statuses, category_id)
    if (
        status is None
        or status.field is None
        or status.state
        not in (
            TargetSourceState.LINKED_EXACT,
            TargetSourceState.LINKED_DERIVED,
        )
    ):
        return None
    return status.field.id


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources")
@login_required
def view_sources(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """The per-target data sources checklist."""
    try:
        return _render_page(assembly_id)
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/setup-modal")
@login_required
def setup_modal(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the set-up modal — fragment for HTMX, full page with the modal open otherwise."""
    try:
        if "modal" in request.args:
            values = _setup_values_from_request(request.args)
        else:
            uow = bootstrap.get_flask_uow()
            with uow:
                statuses = target_source_status(uow, current_user.id, assembly_id)
            status = _status_for(statuses, category_id)
            if status is None:
                return _dashboard_redirect(_("Target not found"))
            values = _default_setup_values(status)
        return _render_setup_modal(assembly_id, _setup_modal_ctx(assembly_id, category_id, values))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/configure", methods=["POST"])
@login_required
def configure_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Save the set-up modal: wire the target to its source in one transaction."""
    values = _setup_values_from_request(request.form)
    try:
        spec = _parse_setup_spec(values)
        uow = bootstrap.get_flask_uow()
        with uow:
            fields, report = configure_target_source(uow, current_user.id, assembly_id, category_id, spec)
    except (ValueError, FieldDefinitionConflictError, FieldDefinitionNotFoundError) as e:
        return _render_setup_modal(assembly_id, _setup_modal_ctx(assembly_id, category_id, values, error=str(e)), 422)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))

    if report is not None:
        return _report_response(
            assembly_id, report, _("Data source saved — %(key)s recomputed", key=fields[-1].field_key)
        )
    return _close_modal_response(assembly_id, _("Data source saved"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/adopt", methods=["POST"])
@login_required
def adopt_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Link the name-matched existing field the row offered."""
    raw_field_id = request.form.get("field_id", "")
    try:
        field_id = uuid.UUID(raw_field_id)
        uow = bootstrap.get_flask_uow()
        with uow:
            adopt_field(uow, current_user.id, assembly_id, category_id, field_id)
    except (ValueError, FieldDefinitionConflictError, FieldDefinitionNotFoundError) as e:
        flash(str(e) if not isinstance(e, ValueError) else _("Field not found"), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    return _close_modal_response(assembly_id, _("Field linked to its target"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/resync", methods=["POST"])
@login_required
def resync_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Regenerate the linked field's options from the target's current values."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            field, report = resync_from_target(uow, current_user.id, assembly_id, category_id)
    except (FieldDefinitionConflictError, FieldDefinitionNotFoundError) as e:
        flash(str(e), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    if report is not None:
        return _report_response(assembly_id, report, _("Re-synced — %(key)s recomputed", key=field.field_key))
    return _close_modal_response(assembly_id, _("Options re-synced from the target"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/recompute", methods=["POST"])
@login_required
def recompute_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Recompute the linked derived field across the pool."""
    field_id = _linked_field_id(assembly_id, category_id)
    if field_id is None:
        flash(_("No field is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
    except (FieldDefinitionConflictError, FieldDefinitionNotFoundError) as e:
        flash(str(e), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    return _report_response(assembly_id, report, _("Recompute finished"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/upload-modal")
@login_required
def upload_modal(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the lookup-table upload dialog for the target's linked mapping field."""
    return _upload_modal_response(assembly_id, category_id)


def _upload_modal_response(
    assembly_id: uuid.UUID, category_id: uuid.UUID, error: str = "", status: int = 200
) -> ResponseReturnValue:
    uow = bootstrap.get_flask_uow()
    try:
        with uow:
            statuses = target_source_status(uow, current_user.id, assembly_id)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    source_status = _status_for(statuses, category_id)
    if source_status is None or source_status.field is None or not source_status.field.is_derived:
        flash(_("No lookup-table field is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    modal_ctx = {
        "mode": "upload",
        "field": source_status.field,
        "category_id": category_id,
        "error": error,
        "allow_new_outputs": request.form.get("allow_new_outputs") == "1",
    }
    if _is_htmx():
        return render_template(
            "backoffice/target_sources/_upload_modal.html", modal_ctx=modal_ctx, **_page_context(assembly_id)
        ), status
    return _render_page(assembly_id, modal_ctx=modal_ctx, status=status)


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/upload", methods=["POST"])
@login_required
def upload_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Replace the linked mapping field's lookup table from an uploaded CSV, then recompute."""
    field_id = _linked_field_id(assembly_id, category_id)
    if field_id is None:
        flash(_("No field is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    uploaded = request.files.get("mapping_file")
    if uploaded is None or not uploaded.filename:
        return _upload_modal_response(assembly_id, category_id, error=_("Choose a CSV file to upload"), status=422)
    try:
        csv_content = uploaded.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _upload_modal_response(
            assembly_id, category_id, error=_("The file could not be read as UTF-8 text"), status=422
        )
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            upload_report = upload_large_mapping(
                uow,
                current_user.id,
                assembly_id,
                field_id,
                csv_content,
                allow_new_outputs=request.form.get("allow_new_outputs") == "1",
            )
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
    except (FieldDefinitionConflictError, FieldDefinitionNotFoundError) as e:
        return _upload_modal_response(assembly_id, category_id, error=str(e), status=422)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    return _report_response(assembly_id, report, _("Lookup table uploaded"), upload_report=upload_report)


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/unlink", methods=["POST"])
@login_required
def unlink_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Break the link; the field stays behind as a free editable field."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            unlink(uow, current_user.id, assembly_id, category_id)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        flash(_("Target not found"), "error")
        return redirect(_sources_url(assembly_id))
    return _close_modal_response(assembly_id, _("Field unlinked from its target"))
