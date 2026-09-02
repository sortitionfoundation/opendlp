# Ticket 886 — Results dashboard: service-layer specification (MOCK stage)

Status: **mock services in place, real business logic pending Hamish.**

The dashboard front-end is being built against three mock service functions so
that work can proceed while the back-end developer is away. This document is the
contract the two halves share. When the real logic lands, only the bodies in
`src/opendlp/service_layer/dashboard_stats.py` change — the dataclass shapes,
the dev-console wiring, and the front-end bindings stay put.

## Where things live

| Piece | Path |
| --- | --- |
| Mock services + dataclasses | `src/opendlp/service_layer/dashboard_stats.py` |
| Dev-console handlers + dispatch | `src/opendlp/entrypoints/blueprints/dev.py` (search `dashboard`) |
| Dev-console tab (Try It) | `/backoffice/dev/service-docs?tab=dashboard` |
| JS slice | `src/js/components/service-docs/dashboard.js` |
| Template partial | `templates/backoffice/service_docs/_dashboard.html` |

## The three services

### 1. `get_assembly_dashboard_summary(uow, assembly_id) -> DashboardSummary`

Headline numbers for the stat-tile row.

```
DashboardSummary(
    assembly_id, assembly_title, number_to_select,
    target_category_count, total_respondents,
    status_counts: [StatusCount(status, count), ...],   # one per RespondentStatus
    mock,
)
```

- **Real:** `assembly_title` and `number_to_select` are read from the Assembly aggregate (existing columns).
- **Mocked:** every count. Real version counts respondents grouped by `RespondentStatus`.

### 2. `get_assembly_dashboard_report(uow, assembly_id) -> DashboardReport`

The full results table plus the derived unmet-targets list. The `rows` are also
the pie-chart series (value → `pool_count`).

```
DashboardReport(
    assembly_id, assembly_title, number_to_select, pool_size,
    categories: [DashboardCategory(name, rows: [CategoryValueRow(
        value, target_min, target_max, pool_count, shortfall, meetable), ...])],
    unmet_targets: [UnmetTarget(category, value, target_min, pool_count, shortfall), ...],
    mock,
)
```

- **Mocked:** all counts. `shortfall = max(0, target_min - pool_count)`; `unmet_targets` is the projection of rows where `shortfall > 0`.

### 3. `export_assembly_dashboard(uow, assembly_id, export_format) -> DashboardExport`

`export_format` ∈ `{csv, xlsx, gsheet}`.

```
DashboardExport(assembly_id, export_format, filename, note, download_ready, mock)
```

- **csv / gsheet:** reuse the existing targets in `adapters/tabular_export.py`.
- **xlsx:** **no backend exists.** `tabular_export.py` has CSV and GSheet targets only. A new xlsx target is needed behind `AbstractTabularExportTarget.write_sheet()`. The mock returns `download_ready=false` for xlsx to keep this visible.

## Decisions the mock made that need Hamish to ratify

1. **Pool-vs-run scope.** The mock treats the dashboard as a **live view of the current pool** (matches the ticket's "only 8 have signed up so far"), *not* the post-selection `SelectionReport` in `selection_report.py`. Selected/confirmed columns are omitted until a selection run exists. Confirm this is the intended source.
2. **Headline total.** `total_respondents` currently sums the live-pool statuses (POOL + WITHDRAWN in the fixture). Confirm which `RespondentStatus` values belong in the headline.
3. **Feasibility semantics.** The mock uses a simple per-value `pool_count < target_min`. The richer joint-quota check already exists as `InfeasibleQuotasError` in `service_layer/target_checking.py` — decide whether the dashboard should use it.
4. **Permissions.** Handlers assume the entrypoint checks `can_view_assembly()`; the mock does not enforce it (the dev console is admin-only).

## Related existing code worth reusing

- `service_layer/selection_report.py` — `SelectionReport`/`CategoryReport`/`CategoryReportRow` already compute per-category target/pool/selected breakdowns for a *completed run*. Much of `get_assembly_dashboard_report` can be a live-pool variant of this.
- `service_layer/target_checking.py` — feasibility / infeasible-quota detection.
- `adapters/tabular_export.py`, `adapters/gsheet_export.py`, `service_layer/respondent_export_service.py` — export plumbing.
