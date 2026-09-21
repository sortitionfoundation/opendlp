"""ABOUTME: Backoffice routes for the target data sources checklist (registration step 1)
ABOUTME: One row per target; a set-up modal wires each to its field via the four methods"""

import contextlib
import uuid
from typing import Any

import structlog
from flask import Blueprint, flash, redirect, render_template, render_template_string, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.respondent_derivation import DEFAULT_FALLBACK, LargeMappingRule
from opendlp.domain.respondent_field_schema import (
    DERIVATION_TYPE_LABELS,
    DerivationType,
    DerivedFieldError,
    FieldType,
    FixedFieldError,
    RespondentFieldDefinition,
    TargetLinkedFieldError,
    humanise_field_key,
)
from opendlp.entrypoints.derivation_form_parser import (
    age_prefill_from_target,
    parse_age_rule,
    parse_small_mapping_rule,
)
from opendlp.entrypoints.registration_hub import registration_hub_context
from opendlp.service_layer.assembly_service import (
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_tab_enabled_states,
)
from opendlp.service_layer.derivation_service import (
    UNMATCHED_SAMPLE_SIZE,
    MappingUploadReport,
    RecomputeReport,
    recompute_derived_field,
    upload_large_mapping,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
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
    reusable_source_fields,
    target_setup_data,
    target_source_status,
    unlink,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _
from opendlp.translations import ngettext

target_sources_bp = Blueprint("target_sources", __name__)

logger = structlog.get_logger(__name__)

_METHOD_EXACT = "exact"

_SOURCE_TYPE_FOR_AGE = {"date": FieldType.DATE, "year": FieldType.INTEGER}


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _method_options() -> list[dict[str, str]]:
    return [
        {"value": _METHOD_EXACT, "label": _("Exact copy")},
        *({"value": method.value, "label": str(label)} for method, label in DERIVATION_TYPE_LABELS.items()),
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


def _default_new_field_key(method: str, age_source_type: str) -> str:
    """The name a created source question gets when the organiser isn't asked for one."""
    if method == DerivationType.LARGE_MAPPING.value:
        return "Postcode"
    if method == DerivationType.AGE_BRACKET.value:
        return "year_of_birth" if age_source_type == "year" else "date_of_birth"
    return ""


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
    """Initial modal state: seeded from the linked field when editing, no method chosen otherwise."""
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


def _page_context(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, with_hub: bool | None = None) -> dict[str, Any]:
    """Everything view.html and _checklist.html need, read through the route's open ``uow``.

    Called after a route's writes, inside the same block, so the page it
    describes is the one the request leaves behind.

    ``with_hub`` adds the registration hub that view.html paints, inert, behind
    the step's takeover dialog; fragments leave it out. Left unset, it follows
    the request: a full page gets the hub, an HTMX fragment does not.
    """
    if with_hub is None:
        with_hub = not _is_htmx()
    gsheet = None
    csv_status = None
    hub_context: dict[str, Any] = {}
    assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
    statuses = target_source_status(uow, current_user.id, assembly_id)
    with contextlib.suppress(ServiceLayerError):
        gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)
    with contextlib.suppress(ServiceLayerError):
        csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)
    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    if with_hub:
        hub_context = {**registration_hub_context(uow, assembly_id, data_source, gsheet), "page_takeover": True}

    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)
    return {
        **hub_context,
        "assembly": assembly,
        "statuses": statuses,
        "TargetSourceState": TargetSourceState,
        "default_fallback": DEFAULT_FALLBACK,
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


def _status_for(statuses: list[TargetSourceStatus], category_id: uuid.UUID) -> TargetSourceStatus | None:
    return next((s for s in statuses if s.category.id == category_id), None)


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
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    values: dict[str, Any],
    error: str = "",
) -> dict[str, Any]:
    """Everything the set-up modal needs for the chosen method and source."""
    setup = target_setup_data(uow, current_user.id, assembly_id, category_id)
    target: dict[str, Any] = {"id": setup.target_id, "name": setup.target_name, "values": setup.target_values}
    first_date = setup.first_assembly_date
    is_linked = setup.is_linked
    # Until a method is chosen the modal asks only how the data is collected.
    method = values["method"] if values["method"] in _method_labels() else ""
    values["method"] = method

    candidates: list[RespondentFieldDefinition] = []
    if method:
        derivation_type = None if method == _METHOD_EXACT else DerivationType(method)
        candidates = reusable_source_fields(setup.fields, derivation_type, setup.target_values)
    selected_source = _resolve_source_selection(values, candidates, target["name"])

    if not values["new_field_key"]:
        values["new_field_key"] = _default_new_field_key(method, values["age_source_type"])

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
        "is_linked": is_linked,
        "mapping_row_count": setup.mapping_row_count,
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


# Each takes the page context its route built inside its ``with uow:`` block, and
# renders outside it: a template is the slow part of a request, and a
# transaction held open across it is how a connection pool runs dry.


def _render_page(
    page_ctx: dict[str, Any], modal_ctx: dict[str, Any] | None = None, status: int = 200
) -> ResponseReturnValue:
    return render_template("backoffice/target_sources/view.html", modal_ctx=modal_ctx, **page_ctx), status


def _render_checklist_fragment(page_ctx: dict[str, Any], oob: bool = False) -> str:
    return render_template("backoffice/target_sources/_checklist.html", oob=oob, **page_ctx)


def _render_setup_modal(page_ctx: dict[str, Any], modal_ctx: dict[str, Any], status: int = 200) -> ResponseReturnValue:
    if _is_htmx():
        return render_template("backoffice/target_sources/_setup_modal.html", modal_ctx=modal_ctx, **page_ctx), status
    return _render_page(page_ctx, modal_ctx={"mode": "setup", "setup_ctx": modal_ctx}, status=status)


def _report_response(
    assembly_id: uuid.UUID,
    page_ctx: dict[str, Any],
    report: RecomputeReport,
    title: str,
    upload_report: MappingUploadReport | None = None,
) -> ResponseReturnValue:
    """Show the recompute report in the modal and refresh the checklist behind it."""
    report_ctx = {
        "report": report,
        "title": title,
        "upload_report": upload_report,
        "close_url": _sources_url(assembly_id),
        "sample_size": UNMATCHED_SAMPLE_SIZE,
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


def _recompute_toast(report: RecomputeReport, message: str) -> tuple[str, str]:
    """The toast text and flash category for a recompute: a warning when anything needs a look."""
    lines = [message]
    category = "success"
    if report.fell_back:
        category = "warning"
        lines.append(
            _(
                "%(count)d fell back to %(fallback)s because their answer matched no target value.",
                count=report.fell_back,
                fallback=report.fallback,
            )
        )
        if report.unmatched_sample:
            lines.append(_("Answers that matched nothing: %(values)s", values=", ".join(report.unmatched_sample)))
    if report.completed_selection_runs:
        category = "warning"
        lines.append(
            ngettext(
                "This assembly has %(num)s completed selection run. Recomputing changes the pool underneath it — the numbers that selection was made from no longer match what is stored.",
                "This assembly has %(num)s completed selection runs. Recomputing changes the pool underneath them — the numbers those selections were made from no longer match what is stored.",
                report.completed_selection_runs,
            )
        )
    return "\n".join(lines), category


def _toast_response(
    assembly_id: uuid.UUID, page_ctx: dict[str, Any], message: str, category: str
) -> ResponseReturnValue:
    """Close the modal, refresh the checklist and say what happened in a toast."""
    flash(message, category)
    if _is_htmx():
        toasts = render_template_string(
            '{% from "backoffice/components/floating_alerts.html" import floating_alerts %}'
            "{{ floating_alerts(oob=true) }}"
        )
        return _render_checklist_fragment(page_ctx, oob=True) + toasts, 200
    return redirect(_sources_url(assembly_id))


def _saved_response(
    assembly_id: uuid.UUID, page_ctx: dict[str, Any], report: RecomputeReport | None, saved: str, recomputed: str
) -> ResponseReturnValue:
    """After a save that may have recomputed the pool.

    With no respondents yet - the usual case while an assembly is first being set
    up - a recompute has done nothing worth reporting, so nothing is said about it.
    """
    if report is None or report.total == 0:
        return _close_modal_response(assembly_id, page_ctx, saved)
    return _toast_response(assembly_id, page_ctx, *_recompute_toast(report, recomputed))


def _close_modal_response(assembly_id: uuid.UUID, page_ctx: dict[str, Any], message: str) -> ResponseReturnValue:
    """Success without a report: refresh the checklist, close the modal."""
    if _is_htmx():
        return _render_checklist_fragment(page_ctx, oob=True), 200
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
            raise ValueError(_("Choose the question to use"))
        try:
            return SourceFieldSpec(reuse_field_id=uuid.UUID(values["reuse_field_id"]))
        except ValueError as e:
            # Only a hand-edited form sends something that is not an id.
            raise ValueError(_("Choose the question to use")) from e
    if method == _METHOD_EXACT:
        return SourceFieldSpec()
    # With nothing to reuse the modal names the new question itself rather than asking.
    field_key = values["new_field_key"].strip() or _default_new_field_key(method, values["age_source_type"])
    if not field_key:
        raise ValueError(_("Enter a name for the new registration question"))
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
    if method not in _method_labels():
        raise ValueError(_("Choose how the data should be collected"))
    source = _parse_source_spec(values, method)
    if method == _METHOD_EXACT:
        return ExactCopySpec(source=source)
    if method == DerivationType.AGE_BRACKET.value:
        return AgeBracketSpec(rule=parse_age_rule(values), source=source)
    if method == DerivationType.SMALL_MAPPING.value:
        if values["source_mode"] != "reuse":
            raise ValueError(
                _("Choose the choice question to map from — add it on the registration questions step first")
            )
        return SmallMappingSpec(rule=parse_small_mapping_rule(values), source=source)
    return LargeMappingSpec(rule=LargeMappingRule(), source=source)


def _linked_field_id(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, category_id: uuid.UUID) -> uuid.UUID | None:
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
#
# Each opens one ``with uow:`` block around everything it reads and writes,
# including the page context its response is rendered from, and renders after
# the block has closed. The one exception is a save that fails: its block has
# rolled back, so the dialog it re-opens is read in a block of its own.
# ---------------------------------------------------------------------------


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources")
@login_required
def view_sources(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """The per-target data sources checklist."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _page_context(uow, assembly_id, with_hub=True)
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))
    return _render_page(page_ctx)


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/setup-modal")
@login_required
def setup_modal(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the set-up modal — fragment for HTMX, full page with the modal open otherwise."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _page_context(uow, assembly_id)
            if "modal" in request.args:
                values = _setup_values_from_request(request.args)
            else:
                status = _status_for(page_ctx["statuses"], category_id)
                if status is None:
                    return _dashboard_redirect(_("Target not found"))
                values = _default_setup_values(status)
            modal_ctx = _setup_modal_ctx(uow, assembly_id, category_id, values)
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))
    return _render_setup_modal(page_ctx, modal_ctx)


def _setup_error_response(
    assembly_id: uuid.UUID, category_id: uuid.UUID, values: dict[str, Any], error: str
) -> ResponseReturnValue:
    """Re-open the set-up modal with an error, after a save that did not happen.

    The save's block has rolled back, so the dialog is read in a fresh one.
    Building it loads the assembly and the target, so it can fail in its own
    right — the form is parsed before anything checks who is asking.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _page_context(uow, assembly_id)
            modal_ctx = _setup_modal_ctx(uow, assembly_id, category_id, values, error=error)
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))
    return _render_setup_modal(page_ctx, modal_ctx, 422)


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
            page_ctx = _page_context(uow, assembly_id)
    except (FixedFieldError, DerivedFieldError, TargetLinkedFieldError):
        # Domain guards the form cannot trip; their messages are written for a developer.
        logger.exception("Target source set-up refused by a domain guard", assembly_id=str(assembly_id))
        return _setup_error_response(assembly_id, category_id, values, _("This data source could not be saved"))
    except ValueError as e:
        # Raised by the form parsers and the rule constructors, each with a message written for the organiser.
        return _setup_error_response(assembly_id, category_id, values, str(e))
    except FieldDefinitionConflictError as e:
        return _setup_error_response(assembly_id, category_id, values, e.user_msg())
    except FieldDefinitionNotFoundError:
        # The message names internal ids - show a generic one.
        return _setup_error_response(assembly_id, category_id, values, _("Question not found"))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))

    source_status = _status_for(page_ctx["statuses"], category_id)
    # The row count is None unless the target is fed by a lookup table.
    if source_status is not None and source_status.mapping_row_count == 0:
        # A lookup table with no rows maps everyone to the fallback, so the
        # dialog moves straight on to uploading it rather than closing.
        if _is_htmx():
            return _render_upload_modal(page_ctx, assembly_id, category_id, setup_step=True, refresh_checklist=True)
        return redirect(
            url_for("target_sources.upload_modal", assembly_id=assembly_id, category_id=category_id, step="setup")
        )
    return _saved_response(
        assembly_id,
        page_ctx,
        report,
        saved=_("Data source saved"),
        recomputed=_("Data source saved — %(key)s recomputed for every respondent", key=fields[-1].field_key),
    )


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
            page_ctx = _page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        flash(e.user_msg(), "error")
        return redirect(_sources_url(assembly_id))
    except (ValueError, FieldDefinitionNotFoundError):
        # A malformed id, or one the service does not know; its message names internal ids.
        flash(_("Question not found"), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    return _close_modal_response(assembly_id, page_ctx, _("Question linked to its target"))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/resync", methods=["POST"])
@login_required
def resync_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Regenerate the linked field's options from the target's current values."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            field, report = resync_from_target(uow, current_user.id, assembly_id, category_id)
            page_ctx = _page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        flash(e.user_msg(), "error")
        return redirect(_sources_url(assembly_id))
    except FieldDefinitionNotFoundError:
        # The message names internal ids - show a generic one.
        flash(_("No question is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    except ValueError:
        # The linked field's stored derivation no longer parses, so there is no rule to re-sync.
        flash(_("This data source could not be re-synced — set it up again"), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    return _saved_response(
        assembly_id,
        page_ctx,
        report,
        saved=_("Options re-synced from the target"),
        recomputed=_("Re-synced — %(key)s recomputed for every respondent", key=field.field_key),
    )


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/recompute", methods=["POST"])
@login_required
def recompute_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Recompute the linked derived field across the pool."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            # Found and recomputed in one transaction, so the link cannot change in between.
            field_id = _linked_field_id(uow, assembly_id, category_id)
            if field_id is None:
                flash(_("No question is linked to this target"), "error")
                return redirect(_sources_url(assembly_id))
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
            page_ctx = _page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        flash(e.user_msg(), "error")
        return redirect(_sources_url(assembly_id))
    except FieldDefinitionNotFoundError:
        # The message names internal ids - show a generic one.
        flash(_("No question is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    if report.total == 0:
        return _toast_response(assembly_id, page_ctx, _("There are no respondents to recompute yet"), "info")
    return _toast_response(assembly_id, page_ctx, *_recompute_toast(report, _("Recompute finished")))


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/upload-modal")
@login_required
def upload_modal(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the lookup-table upload dialog for the target's linked mapping field.

    ``?step=setup`` serves it as the second step of the set-up dialog.
    """
    return _upload_modal_response(assembly_id, category_id, setup_step=request.args.get("step") == "setup")


def _upload_modal_response(
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    error: str = "",
    status: int = 200,
    setup_step: bool = False,
) -> ResponseReturnValue:
    """Open the upload dialog in a block of its own: on a GET, or after an upload that did not happen."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _page_context(uow, assembly_id)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to view this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    return _render_upload_modal(page_ctx, assembly_id, category_id, error=error, status=status, setup_step=setup_step)


def _render_upload_modal(
    page_ctx: dict[str, Any],
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    error: str = "",
    status: int = 200,
    setup_step: bool = False,
    refresh_checklist: bool = False,
) -> ResponseReturnValue:
    source_status = _status_for(page_ctx["statuses"], category_id)
    if source_status is None or source_status.field is None or not source_status.field.is_derived:
        flash(_("No question with a lookup table is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    modal_ctx = {
        "mode": "upload",
        "field": source_status.field,
        "category_id": category_id,
        "error": error,
        "allow_new_outputs": request.form.get("allow_new_outputs") == "1",
        "setup_step": setup_step,
        "defer_upload": request.form.get("defer_upload") == "1",
        "fallback": LargeMappingRule.from_config(source_status.field.derivation_config or {}).fallback,
    }
    if _is_htmx():
        dialog_html = render_template("backoffice/target_sources/_upload_modal.html", modal_ctx=modal_ctx, **page_ctx)
        if refresh_checklist:
            dialog_html += _render_checklist_fragment(page_ctx, oob=True)
        return dialog_html, status
    return _render_page(page_ctx, modal_ctx=modal_ctx, status=status)


def _defer_upload_response(assembly_id: uuid.UUID, category_id: uuid.UUID, setup_step: bool) -> ResponseReturnValue:
    """Close the set-up dialog without a lookup table, once the organiser has said so."""
    if request.form.get("defer_upload") != "1":
        return _upload_modal_response(
            assembly_id,
            category_id,
            error=_("Tick the box to upload the lookup table later"),
            status=422,
            setup_step=setup_step,
        )
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page_ctx = _page_context(uow, assembly_id)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    source_status = _status_for(page_ctx["statuses"], category_id)
    if source_status is None or source_status.field is None:
        flash(_("No question is linked to this target"), "error")
        return redirect(_sources_url(assembly_id))
    field = source_status.field
    message = _(
        "Data source saved. Until the lookup table is uploaded, everyone's %(key)s will be %(fallback)s.",
        key=field.field_key,
        fallback=LargeMappingRule.from_config(field.derivation_config or {}).fallback,
    )
    return _toast_response(assembly_id, page_ctx, message, "warning")


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/upload", methods=["POST"])
@login_required
def upload_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Replace the linked mapping field's lookup table from an uploaded CSV, then recompute."""
    setup_step = request.form.get("setup_step") == "1"
    if request.form.get("form_action") == "defer":
        return _defer_upload_response(assembly_id, category_id, setup_step)
    uploaded = request.files.get("mapping_file")
    if uploaded is None or not uploaded.filename:
        return _upload_modal_response(
            assembly_id, category_id, error=_("Choose a CSV file to upload"), status=422, setup_step=setup_step
        )
    try:
        csv_content = uploaded.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _upload_modal_response(
            assembly_id,
            category_id,
            error=_("The file could not be read as UTF-8 text"),
            status=422,
            setup_step=setup_step,
        )
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            # Found, uploaded to and recomputed in one transaction, so the link cannot change in between.
            field_id = _linked_field_id(uow, assembly_id, category_id)
            if field_id is None:
                flash(_("No question is linked to this target"), "error")
                return redirect(_sources_url(assembly_id))
            upload_report = upload_large_mapping(
                uow,
                current_user.id,
                assembly_id,
                field_id,
                csv_content,
                allow_new_outputs=request.form.get("allow_new_outputs") == "1",
            )
            report = recompute_derived_field(uow, current_user.id, assembly_id, field_id)
            page_ctx = _page_context(uow, assembly_id)
    except FieldDefinitionConflictError as e:
        return _upload_modal_response(assembly_id, category_id, error=e.user_msg(), status=422, setup_step=setup_step)
    except FieldDefinitionNotFoundError:
        # The message names internal ids - show a generic one.
        return _upload_modal_response(
            assembly_id, category_id, error=_("Question not found"), status=422, setup_step=setup_step
        )
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except NotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    return _report_response(assembly_id, page_ctx, report, _("Lookup table uploaded"), upload_report=upload_report)


@target_sources_bp.route("/assembly/<uuid:assembly_id>/target-sources/<uuid:category_id>/unlink", methods=["POST"])
@login_required
def unlink_view(assembly_id: uuid.UUID, category_id: uuid.UUID) -> ResponseReturnValue:
    """Break the link: a question stays behind, a computed question is deleted."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            _unlinked, deleted = unlink(uow, current_user.id, assembly_id, category_id)
            page_ctx = _page_context(uow, assembly_id)
    except InsufficientPermissions:
        return _dashboard_redirect(_("You don't have permission to edit this assembly"))
    except AssemblyNotFoundError:
        return _dashboard_redirect(_("Assembly not found"))
    except NotFoundError:
        flash(_("Target not found"), "error")
        return redirect(_sources_url(assembly_id))
    if deleted:
        return _close_modal_response(assembly_id, page_ctx, _("Computed question deleted"))
    return _close_modal_response(assembly_id, page_ctx, _("Question unlinked from its target"))
