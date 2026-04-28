"""ABOUTME: Service for building the selection summary report from a SelectionRunRecord
ABOUTME: Computes target / pool / selected breakdowns per target category"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from opendlp.adapters.url_generator import URLGenerator
from opendlp.domain.respondents import Respondent, normalise_field_name
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _


class SelectionReportError(Exception):
    """Raised when a selection summary report cannot be built."""


@dataclass
class CategoryReportRow:
    value: str
    target_min: int
    target_max: int
    target_pct: float
    pool_count: int
    pool_pct: float
    selected_count: int
    selected_pct: float
    deleted_count: int


@dataclass
class CategoryReport:
    name: str
    rows: list[CategoryReportRow] = field(default_factory=list)


@dataclass
class SelectionReport:
    assembly_title: str
    selection_url: str
    number_selected: int
    pool_size: int
    categories: list[CategoryReport] = field(default_factory=list)


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _target_pct(target_min: int, target_max: int, number_to_select: int) -> float:
    if number_to_select == 0:
        return 0.0
    midpoint = (target_min + target_max) / 2
    return round(midpoint / number_to_select * 100, 1)


def _attribute_value(respondent: Respondent, category_name: str) -> str:
    target_key = normalise_field_name(category_name)
    for key, value in respondent.attributes.items():
        if normalise_field_name(key) == target_key:
            return str(value) if value is not None else ""
    return ""


def _build_category_report(
    category: dict[str, Any],
    pool_respondents: list[Respondent],
    selected_respondents: list[Respondent],
    number_to_select: int,
) -> CategoryReport:
    name = category["name"]
    known_values = {v["value"] for v in category["values"]}
    pool_counts: dict[str, int] = dict.fromkeys(known_values, 0)
    selected_counts: dict[str, int] = dict.fromkeys(known_values, 0)
    deleted_counts: dict[str, int] = dict.fromkeys(known_values, 0)

    for resp in pool_respondents:
        if resp.selection_status == RespondentStatus.DELETED:
            continue
        value = _attribute_value(resp, name)
        if value not in known_values:
            raise SelectionReportError(
                f"Respondent {resp.external_id} has value '{value}' for "
                f"category '{name}' which is not in the recorded targets",
            )
        pool_counts[value] += 1

    for resp in selected_respondents:
        if resp.selection_status == RespondentStatus.DELETED:
            continue
        value = _attribute_value(resp, name)
        if value not in known_values:
            raise SelectionReportError(
                f"Selected respondent {resp.external_id} has value '{value}' "
                f"for category '{name}' which is not in the recorded targets",
            )
        selected_counts[value] += 1

    pool_total = sum(pool_counts.values())
    selected_total = sum(selected_counts.values())

    rows = [
        CategoryReportRow(
            value=v["value"],
            target_min=v["min"],
            target_max=v["max"],
            target_pct=_target_pct(v["min"], v["max"], number_to_select),
            pool_count=pool_counts[v["value"]],
            pool_pct=_pct(pool_counts[v["value"]], pool_total),
            selected_count=selected_counts[v["value"]],
            selected_pct=_pct(selected_counts[v["value"]], selected_total),
            deleted_count=deleted_counts[v["value"]],
        )
        for v in category["values"]
    ]
    return CategoryReport(name=name, rows=rows)


def build_selection_report(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    task_id: uuid.UUID,
    url_generator: URLGenerator,
) -> SelectionReport:
    record = uow.selection_run_records.get_by_task_id(task_id)
    if record is None:
        raise SelectionReportError(f"Selection run {task_id} not found")
    if not record.targets_used:
        raise SelectionReportError("This run has no target snapshot recorded — cannot build summary report")

    assembly = uow.assemblies.get(assembly_id)
    if assembly is None:
        raise SelectionReportError(f"Assembly {assembly_id} not found")

    selected_ext_ids: list[str] = list(record.selected_ids[0]) if record.selected_ids else []
    remaining_ext_ids: list[str] = list(record.remaining_ids) if record.remaining_ids else []
    pool_ext_ids = selected_ext_ids + remaining_ext_ids

    respondents_by_id: dict[str, Respondent] = {
        r.external_id: r for r in uow.respondents.get_by_assembly_id(assembly_id, include_deleted=True)
    }

    pool_respondents = [respondents_by_id[ext_id] for ext_id in pool_ext_ids if ext_id in respondents_by_id]
    selected_respondents = [respondents_by_id[ext_id] for ext_id in selected_ext_ids if ext_id in respondents_by_id]

    categories = [
        _build_category_report(cat, pool_respondents, selected_respondents, assembly.number_to_select)
        for cat in record.targets_used
    ]

    selection_url = url_generator.generate_url(
        "gsheets.view_assembly_selection_with_run",
        _external=True,
        assembly_id=assembly_id,
        run_id=task_id,
    )

    return SelectionReport(
        assembly_title=assembly.title,
        selection_url=selection_url,
        number_selected=len(selected_ext_ids),
        pool_size=len(pool_ext_ids),
        categories=categories,
    )


_BOM = "﻿"


def _format_pct(value: float) -> str:
    return f"{value:.1f}"


def _format_target_count(target_min: int, target_max: int) -> str:
    midpoint = (target_min + target_max) / 2
    if midpoint.is_integer():
        return str(int(midpoint))
    return f"{midpoint:g}"


def selection_report_to_csv(report: SelectionReport) -> str:
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow([_("Assembly"), report.assembly_title])
    writer.writerow([_("Selection URL"), report.selection_url])
    writer.writerow([_("Number selected"), report.number_selected])
    writer.writerow([_("Pool size at selection time"), report.pool_size])
    writer.writerow(
        [
            _("Note: pool / selected counts are computed live and reflect any later edits to respondent data"),
        ],
    )
    writer.writerow([])

    for category in report.categories:
        writer.writerow(
            [
                category.name,
                _("Target"),
                "",
                "",
                "",
                _("All respondents"),
                "",
                _("Selected"),
                "",
                _("Deleted"),
            ],
        )
        writer.writerow(
            [
                "",
                _("%"),
                _("#"),
                _("Min"),
                _("Max"),
                _("%"),
                _("#"),
                _("%"),
                _("#"),
                _("#"),
            ],
        )
        for row in category.rows:
            writer.writerow(
                [
                    row.value,
                    _format_pct(row.target_pct),
                    _format_target_count(row.target_min, row.target_max),
                    row.target_min,
                    row.target_max,
                    _format_pct(row.pool_pct),
                    row.pool_count,
                    _format_pct(row.selected_pct),
                    row.selected_count,
                    row.deleted_count,
                ],
            )
        writer.writerow([])

    return _BOM + output.getvalue()
