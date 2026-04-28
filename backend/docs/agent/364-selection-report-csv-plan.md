# 364 — Selection summary CSV report

Doctor Chewie — questions resolved, plan tightened. Phases below are
red → green → refactor.

## What I confirmed from the code

- `SelectionRunRecord` lives in `src/opendlp/domain/assembly.py:235`. It already
  has a `# TODO` (line 254) saying "save the targets used for the selection".
  Our story is to do that.
- `SelectionRunRecord` already stores `selected_ids` (list of panels — first
  panel is the chosen one), `remaining_ids`, and `settings_used` (a JSON dict).
- `target_categories` are loaded fresh from the DB by `OpenDLPDataAdapter`
  (`src/opendlp/adapters/sortition_data_adapter.py:46`). They are *mutable* —
  edits to a category after a selection runs would corrupt a historical report.
  This is the reason we have to snapshot.
- Existing CSV downloads live in
  `src/opendlp/service_layer/sortition.py:542` (`generate_selection_csvs`) and
  in two route blueprints (`db_selection_backoffice.py` and the legacy
  `db_selection_legacy.py`). Same pattern: route → service → `Response(...)`.
- The "successful selection" modal is
  `templates/backoffice/components/db_selection_progress_modal.html` — the
  Selected / Remaining download buttons sit at lines 52–59. We add the new
  link there.
- Respondents store their stratification fields in `Respondent.attributes`
  (a free-form dict), keyed by the category name as it appeared in the
  upload. `TargetCategory.name` matches the same key.

## Decisions (confirmed with you)

1. **Scope: DB selection only.** Gsheet selections produce their report in a
   worksheet inside the spreadsheet itself — out of scope here.
2. **No respondent-attribute snapshot.** Report is computed live from current
   respondent data. CSV header notes that caveat.
3. **DELETED respondents** get a separate "Deleted" count column on the
   per-category section so the totals add up.
4. **Modern blueprint only** (`db_selection_backoffice`); legacy blueprint
   left untouched.
5. **CSV encoding: UTF-8 with BOM** for Excel compatibility. We also add the
   BOM to the existing Selected and Remaining CSV downloads while we're in
   there.
6. **Targets snapshot shape** — list of category dicts, 1:1 capture of
   `TargetCategory` + `TargetValue` minus IDs/timestamps:

   ```json
   [
     {
       "name": "Gender",
       "description": "...",
       "sort_order": 0,
       "values": [
         {"value": "Man", "min": 29, "max": 31, "min_flex": 0, "max_flex": -1,
          "percentage_target": 48.5, "description": ""},
         ...
       ]
     },
     ...
   ]
   ```

7. **Percentages**, one decimal place:
   - Target %  = `(min + max) / 2 / number_to_select * 100`
   - Pool %    = `count / pool_total * 100`
   - Selected % = `count / number_selected * 100`
8. **Selection URL** in the CSV header uses
   `gsheets.view_assembly_selection_with_run(assembly_id, run_id)` rendered
   with `_external=True`.
9. **Unknown attribute values** (a respondent has a category-attribute value
   not in the snapshotted targets) shouldn't happen in a live system — the
   selection run would have failed at start. If we encounter one while
   building the report, raise an exception rather than inventing a
   "LOOKUP FAILED" row.
10. **No backfill** for existing `SelectionRunRecord`s — old runs have
    `targets_used = []` and the report endpoint returns a friendly
    "no target snapshot recorded for this run" error.
11. **Derive, don't store**, the run-time pool size and number selected:
    `pool_size = len(selected_ids[0]) + len(remaining_ids)`,
    `number_selected = len(selected_ids[0])`.
12. **Out of scope:** gsheet support, PDF/XLSX export, "compare two
    selections" view.

## Files I expect to touch

New code:
- `src/opendlp/service_layer/selection_report.py` (new module — keep
  `sortition.py` from growing further)
- New route in `src/opendlp/entrypoints/blueprints/db_selection_backoffice.py`
- New Alembic migration under `migrations/versions/`

Edits:
- `src/opendlp/domain/assembly.py` — add `targets_used` field to
  `SelectionRunRecord`; add a `target_categories_to_snapshot()` helper near
  `TargetCategory` (probably in `domain/targets.py`).
- `src/opendlp/adapters/orm.py` — add `targets_used` JSON column.
- `src/opendlp/service_layer/sortition.py` — `start_db_select_task` populates
  `targets_used`; `generate_selection_csvs` (or its caller) gains the BOM.
- `src/opendlp/entrypoints/blueprints/db_selection_backoffice.py` — both
  existing download routes now emit BOM (charset header + leading `﻿`).
- `templates/backoffice/components/db_selection_progress_modal.html` — add
  the third download button.
- Existing tests that construct `SelectionRunRecord` (~15 files) will
  generally be fine because the new field has a default; spot-check anything
  that pins exact field counts.

Tests:
- `tests/unit/test_sortition_service.py` — start-task behaviour
- `tests/contract/test_selection_run_record_repo.py` — round-trip new field
- `tests/integration/test_orm.py` — column persists
- New `tests/unit/test_selection_report.py` — the report builder + CSV
- E2E coverage in `tests/e2e/test_db_selection_backoffice.py` — new route
  plus BOM assertion on existing routes
- BDD: skip unless you say otherwise

## Phases (red → green → refactor each phase)

### Phase 1 — Persist `targets_used` on `SelectionRunRecord`

**Red:**
- Domain test: `SelectionRunRecord(targets_used=[...])` round-trips through
  `create_detached_copy` correctly.
- Contract repo test: save a record with non-empty `targets_used`, read it
  back identically.
- Service test: `start_db_select_task` populates `targets_used` from the
  assembly's current target categories using the snapshot dict shape.

**Green:**
- Add `targets_used: list[dict[str, Any]] = field(default_factory=list)` to
  `SelectionRunRecord` (line 235).
- Add `targets_used` JSON column to `orm.selection_run_records` (line 351),
  nullable `False`, default `list`.
- Generate Alembic migration:
  `uv run alembic revision --autogenerate -m "add targets_used to selection_run_records"`.
  Default existing rows to `[]`.
- Add `target_categories_to_snapshot(categories) -> list[dict[str, Any]]`
  helper (in `domain/targets.py`).
- Update `start_db_select_task` (`sortition.py:484`) to call the helper and
  pass the result into the new field.

**Refactor:**
- Verify no fixture in `tests/conftest.py` or `tests/bdd/conftest.py` needs
  the new column seeded — JSON default of `[]` should suffice.

### Phase 2 — Build the selection report data structure

The report builder consumes a `SelectionRunRecord`, the assembly, and the
live respondents, and returns a structured object:

```python
@dataclass
class CategoryReportRow:
    value: str
    target_min: int
    target_max: int
    target_pct: float        # midpoint / number_to_select
    pool_count: int
    pool_pct: float
    selected_count: int
    selected_pct: float
    deleted_count: int       # respondents in pool whose attributes are blanked

@dataclass
class CategoryReport:
    name: str
    rows: list[CategoryReportRow]

@dataclass
class SelectionReport:
    assembly_title: str
    selection_url: str
    number_selected: int
    pool_size: int
    categories: list[CategoryReport]
```

**Red:** unit tests with hand-crafted `SelectionRunRecord`, target snapshot,
and fake respondents to assert exact counts / percentages, including:
- happy path: one category, two values
- multi-category
- DELETED respondents end up in the per-category `deleted_count` and are
  excluded from `pool_count` (so pool % is over live respondents)
- 0-respondent edge case (empty pool)
- a respondent with an attribute value not in the targets snapshot raises
  an exception (per decision 9)
- empty `targets_used` raises a clear "no target snapshot recorded" error

**Green:** implement
`build_selection_report(uow, assembly_id, task_id) -> SelectionReport` in
`service_layer/selection_report.py`.

**Refactor:**
- Match attribute keys to category names using `normalise_field_name`
  (`respondents.py:42`) so case / punctuation drift doesn't trip the
  unknown-value check.

### Phase 3 — CSV serialisation (with BOM)

**Red:**
- Unit tests assert exact CSV content for a small fixture: header section
  (assembly title, URL, number selected, pool size, caveat note) plus
  per-category sections in the layout from `scratchpad/report-tables2.csv`
  with the agreed changes (no "orig", no "confirmed"/"dropped out"; min/max
  columns added; "Deleted" column added).
- Test asserts the output bytes start with the UTF-8 BOM (`﻿`).

**Green:**
- Add `selection_report_to_csv(report: SelectionReport) -> str` using the
  stdlib `csv` module. Prepend `﻿` to the resulting string. Translate
  column headers via `_()`.

**Refactor:**
- If string assembly gets ugly, factor a per-category writer.

### Phase 4 — Route for the report

**Red:**
- E2E: GET the new route returns 200, mimetype
  `text/csv; charset=utf-8`, response body starts with BOM and contains the
  assembly title.
- E2E: redirect with flash when the run isn't completed.
- E2E: redirect with flash for missing run / unknown assembly.
- E2E: permission gate matches existing download routes.
- E2E: friendly error when `targets_used` is empty (old run).

**Green:**
- Add `download_db_selection_report` route in
  `db_selection_backoffice.py`, mirroring `download_db_selected`. Filename:
  `selection-report-<run_id>.csv`. Reuse `get_assembly_with_permissions` and
  the same `NotFoundError` / `InvalidSelection` / `InsufficientPermissions`
  exception handling.

**Refactor:** three near-identical routes is still fine — no helper needed.

### Phase 5 — Add BOM to existing Selected / Remaining downloads

**Red:**
- Update existing E2E tests for `download_db_selected` and
  `download_db_remaining` to assert the response body starts with the BOM
  and the mimetype includes `charset=utf-8`.

**Green:**
- Modify `generate_selection_csvs` (or a thin wrapper) so each returned CSV
  string is BOM-prefixed, and update both routes to set
  `mimetype="text/csv; charset=utf-8"`.

**Refactor:**
- If we end up with the same prefix logic in two places, lift a tiny
  `_bom_prefix(csv: str) -> str` helper.

### Phase 6 — Link the report from the success modal

**Red:**
- Extend `test_progress_modal_wiring.py` (or add a sibling test): when the
  modal renders for a completed real (non-test) selection, the HTML
  contains a link to the new route.

**Green:**
- Add a third button in `db_selection_progress_modal.html` next to
  "Download Selected" / "Download Remaining" — label "Download Summary
  Report" (i18n).

**Refactor:** none expected.

### Phase 7 — i18n + check + commit

- `just translate-regen` after all new gettext strings are in.
- `just check` and `just test` clean.
- Commit per phase or as one squashed commit — your call.

## Anything I'm missing?

I don't think so given your answers. Pool size and number selected stay
derived; old runs surface a clear "no snapshot" error rather than a
fabricated report; gsheet path is left to its in-spreadsheet worksheet.

## Detailed todo list

Strict red → green → refactor inside every phase. Each phase ends with a
green test suite and one commit before the next phase starts.

### Phase 1 — Persist `targets_used` on `SelectionRunRecord` ✅

- [x] **Red 1.1** — Domain test in `tests/unit/domain/test_assembly.py`:
  `targets_used` round-trips through `create_detached_copy`.
- [x] **Red 1.2** — Contract test in
  `tests/contract/test_selection_run_record_repo.py`: persists and reads
  back unchanged; default is `[]`.
- [x] **Red 1.3** — Service test in `tests/unit/test_sortition_service.py`
  for `start_db_select_task`: snapshot matches assembly target categories.
- [x] **Red 1.4** — Domain unit test for `target_categories_to_snapshot`
  in `tests/unit/test_targets.py`.
- [x] Confirmed tests failed for the right reasons.
- [x] **Green 1.5** — Field added to `SelectionRunRecord`.
- [x] **Green 1.6** — Helper added to `domain/targets.py`.
- [x] **Green 1.7** — `targets_used` column added to ORM table.
- [x] **Green 1.8** — Alembic migration `e6b16af27da3` generated, edited
  to use `server_default='[]'` so existing rows backfill cleanly.
- [x] **Green 1.9** — `start_db_select_task` populates the field via the
  helper; categories fetched through `uow.target_categories`.
- [x] **Green 1.10** — Full unit + contract + integration suite passes
  (1542 tests).
- [x] **Refactor 1.11** — Verified conftest data-deletion helpers don't
  need updates (no new tables).
- [x] **Refactor 1.12** — Helper docstring kept minimal.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 2 — Build the selection report data structure ✅

- [x] **Red 2.1–2.7** — `tests/unit/test_selection_report.py` covers happy
  path, multi-category, DELETED handling, empty pool, unknown attribute
  raise, empty targets_used raise, URL generator wiring, normalised
  attribute keys, missing run.
- [x] Confirmed module not found before implementation.
- [x] **Green 2.8–2.10** — Created `service_layer/selection_report.py`
  with dataclasses, `SelectionReportError`, and `build_selection_report`.
  Uses `URLGenerator` so the route can pass Flask's `url_for`.
- [x] **Green 2.11** — All 9 report tests + 1269 unit/contract tests pass.
- [x] **Refactor 2.12** — Per-category logic factored into
  `_build_category_report` helper.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 3 — CSV serialisation (with BOM) ✅

- [x] **Red 3.1–3.3** — Tests for BOM prefix, header metadata, category
  section layout (10-column table with Target %/#/Min/Max, All respondents
  %/#, Selected %/#, Deleted #), blank line between sections, and CSV
  quoting of values containing commas.
- [x] Confirmed import error before implementation.
- [x] **Green 3.4–3.5** — Implemented `selection_report_to_csv` using
  stdlib `csv.writer` and `StringIO`. Header strings translated via `_()`.
  Midpoint formatted via `_format_target_count` (integer or trimmed
  decimal).
- [x] **Green 3.6** — All 14 report tests pass.
- [x] **Refactor 3.7** — Pulled `_format_pct`, `_format_target_count`,
  and `_BOM` into module-level helpers.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 4 — Route for the report ✅

- [x] **Red 4.1–4.5** — `TestSelectionReportDownload` added to
  `tests/e2e/test_db_selection_backoffice.py`: success, empty
  targets_used, unknown run, unauthenticated.
- [x] Confirmed all 4 tests failed before implementation.
- [x] **Green 4.6–4.7** — Added `download_db_selection_report` route at
  `/backoffice/assembly/<assembly_id>/selection/db/<run_id>/download/report`
  using the same exception ladder as the other download routes plus a
  `SelectionReportError` branch. Wired through `URLGenerator` from
  `bootstrap.get_url_generator(current_app)`.
- [x] **Green 4.8** — All 42 e2e DB selection tests pass.
- [x] **Refactor 4.9** — Three near-identical routes left as-is.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 5 — Add BOM to existing Selected / Remaining downloads ✅

- [x] **Red 5.1** — Existing `TestCsvSelectionDownload` tests now assert
  `response.data.startswith("﻿".encode())`.
- [x] Confirmed both tests failed before implementation.
- [x] **Green 5.2** — `_table_to_csv` in
  `service_layer/sortition.py` BOM-prefixes its output (single helper
  `_CSV_BOM` constant).
- [x] **Green 5.3** — Existing routes already serve `mimetype="text/csv"`
  which Flask renders as `text/csv; charset=utf-8`, no change needed
  there.
- [x] **Green 5.4** — All download tests pass.
- [x] **Refactor 5.5** — Single helper covers both downloads via the
  shared `_table_to_csv` codepath.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 6 — Link the report from the success modal ✅

- [x] **Red 6.1–6.2** — Added `TestDbSelectionModalReportLink` covering
  completed real and test selections. Added a fake URL rule for
  `download_db_selection_report` to the test app.
- [x] Confirmed both tests failed before implementation.
- [x] **Green 6.3** — Added a "Download Summary Report" button next to
  the existing two in `db_selection_progress_modal.html`.
- [x] **Green 6.4** — All 6 progress-modal-wiring tests pass.
- [x] **Refactor 6.5** — Three outline-style buttons in a `.flex.gap-3
  flex-wrap` container — wraps cleanly.
- [x] **Check** — `just check` clean.
- [x] **Commit** — done.

### Phase 7 — i18n + final check + manual smoke test

- [ ] **Translations** — `just translate-regen`; commit the regenerated
  `.po` / `.pot` files.
- [ ] **Full check** — `just check` and `just test` clean.
- [ ] **Manual smoke test** — start the app (`just run`), trigger a real DB
  selection on a small fixture assembly, click "Download Summary Report",
  open the CSV in LibreOffice / Excel, confirm:
  - non-ASCII characters render correctly (BOM doing its job)
  - target / pool / selected percentages match expectations
  - DELETED column shows zero on a clean dataset
  - URL in the header opens back to this selection
- [ ] **Manual smoke test 2** — repeat for an *old* selection that has
  empty `targets_used`; confirm the friendly error redirect.
- [ ] **Commit** — `chore: regenerate translations for selection report`
  (only if `translate-regen` produced changes uncommitted in earlier
  phases).
