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

### Phase 2 — Build the selection report data structure

- [ ] **Red 2.1** — Create `tests/unit/test_selection_report.py` with a
  `FakeUnitOfWork` (or reuse `tests/fakes.py`) and a happy-path test: one
  category, two values, three respondents — assert
  `SelectionReport.categories[0].rows` matches expected counts and pcts.
- [ ] **Red 2.2** — Add multi-category test (e.g. Gender + Age) covering
  per-category isolation.
- [ ] **Red 2.3** — Add DELETED respondent test: respondent with status
  DELETED is counted in `deleted_count` and NOT in `pool_count`.
- [ ] **Red 2.4** — Add zero-respondent edge case test: empty pool returns
  zeroed counts and `0.0` pcts (no ZeroDivisionError).
- [ ] **Red 2.5** — Add unknown-attribute-value test: respondent has a
  category attribute value not present in `targets_used` → builder raises
  a domain-defined exception (e.g. `SelectionReportError`).
- [ ] **Red 2.6** — Add empty-`targets_used` test: builder raises
  `SelectionReportError("no target snapshot recorded for this run")`.
- [ ] **Red 2.7** — Add header-fields test: `assembly_title`,
  `selection_url`, `number_selected`, `pool_size` populated correctly. Use a
  Flask test app to exercise `url_for(_external=True)`.
- [ ] Confirm all seven tests fail (module doesn't exist yet).
- [ ] **Green 2.8** — Create
  `src/opendlp/service_layer/selection_report.py` with the dataclasses
  (`CategoryReportRow`, `CategoryReport`, `SelectionReport`) and a
  `SelectionReportError` exception.
- [ ] **Green 2.9** — Implement
  `build_selection_report(uow, assembly_id, task_id) -> SelectionReport`:
  fetch run record, validate `targets_used` non-empty, fetch respondents,
  bucket by `(category_name, value)`, compute pcts, build dataclasses.
- [ ] **Green 2.10** — Use `normalise_field_name` to match category names
  to respondent attribute keys.
- [ ] **Green 2.11** — Run `just test` and confirm the new tests pass.
- [ ] **Refactor 2.12** — If the bucket-and-count logic is gnarly, extract
  a `_count_by_value(respondents, category)` private helper.
- [ ] **Check** — `just check` clean.
- [ ] **Commit** — `feat: build selection summary report data structure`.

### Phase 3 — CSV serialisation (with BOM)

- [ ] **Red 3.1** — In `tests/unit/test_selection_report.py` add
  `test_csv_output_has_bom` asserting the result starts with `'﻿'`.
- [ ] **Red 3.2** — Add a fixture-based test asserting exact CSV content
  for a known small `SelectionReport`: header section (title / URL /
  number selected / pool size / caveat note), then per-category sections
  in the agreed layout (no "orig", no "confirmed/dropped out", min/max
  and Deleted columns).
- [ ] **Red 3.3** — Add a test confirming column header strings go
  through `gettext` (e.g. patch `gettext` in test, assert called).
- [ ] Confirm tests fail.
- [ ] **Green 3.4** — Implement
  `selection_report_to_csv(report: SelectionReport) -> str` in the same
  module using stdlib `csv.writer` with `StringIO`. Prepend `'﻿'`.
- [ ] **Green 3.5** — Make sure header text uses `_()` for translation.
- [ ] **Green 3.6** — Run `just test`.
- [ ] **Refactor 3.7** — If the writer function is long, split into
  `_write_header_section`, `_write_category_section`.
- [ ] **Check** — `just check` clean.
- [ ] **Commit** — `feat: serialise selection summary report to CSV`.

### Phase 4 — Route for the report

- [ ] **Red 4.1** — In `tests/e2e/test_db_selection_backoffice.py` (or a
  new `test_db_selection_report.py`) add an end-to-end happy-path test:
  authenticated organiser, completed real selection, GET the route returns
  200, mimetype `text/csv; charset=utf-8`, body starts with BOM and
  contains the assembly title.
- [ ] **Red 4.2** — Test for `targets_used == []` (old run): GET redirects
  with a flash matching the "no target snapshot" message.
- [ ] **Red 4.3** — Test for run not completed: redirects with flash.
- [ ] **Red 4.4** — Test for unknown `run_id`: redirects with flash.
- [ ] **Red 4.5** — Test for unauthorised user: same behaviour as
  `download_db_selected` (redirect + flash).
- [ ] Confirm tests fail (404 / route not found).
- [ ] **Green 4.6** — Add `download_db_selection_report` route in
  `src/opendlp/entrypoints/blueprints/db_selection_backoffice.py` modelled
  on `download_db_selected` (same decorators, same exception ladder).
- [ ] **Green 4.7** — Wire it through to
  `build_selection_report` + `selection_report_to_csv`. Filename
  `selection-report-<run_id>.csv`.
- [ ] **Green 4.8** — Run `just test`.
- [ ] **Refactor 4.9** — Sanity-check the three near-identical download
  routes; do not extract a helper unless the duplication is painful.
- [ ] **Check** — `just check` clean.
- [ ] **Commit** — `feat: add selection summary report download route`.

### Phase 5 — Add BOM to existing Selected / Remaining downloads

- [ ] **Red 5.1** — Update existing E2E tests for `download_db_selected`
  and `download_db_remaining` (in `tests/e2e/test_db_selection_backoffice.py`
  and any legacy mirror in `tests/e2e/test_db_selection_routes.py` —
  inspect first; modern blueprint is the priority) to assert the response
  body starts with `'﻿'` and mimetype includes `charset=utf-8`.
- [ ] Confirm tests fail.
- [ ] **Green 5.2** — Modify `generate_selection_csvs` (or wrap its
  outputs) in `src/opendlp/service_layer/sortition.py` so both returned
  strings are BOM-prefixed.
- [ ] **Green 5.3** — Update `download_db_selected` and
  `download_db_remaining` in `db_selection_backoffice.py` to set
  `mimetype="text/csv; charset=utf-8"`.
- [ ] **Green 5.4** — Run `just test`.
- [ ] **Refactor 5.5** — If BOM-prefixing happens in two places, extract
  a private `_with_bom(csv: str) -> str` helper.
- [ ] **Check** — `just check` clean.
- [ ] **Commit** — `feat: add UTF-8 BOM to selection CSV downloads`.

### Phase 6 — Link the report from the success modal

- [ ] **Red 6.1** — Extend
  `tests/unit/test_progress_modal_wiring.py` (or add a sibling test): for a
  completed real (non-test) DB selection, rendered modal HTML contains
  a link to the new route via `url_for`.
- [ ] **Red 6.2** — Test that a *test* selection (`task_type =
  TEST_SELECT_FROM_DB`) **also** renders the report link — test selections
  exist precisely to check whether targets can be met and how the
  distribution will look, so the summary report is more useful here than
  for real runs.
- [ ] Confirm tests fail.
- [ ] **Green 6.3** — Add a third button in
  `templates/backoffice/components/db_selection_progress_modal.html`
  next to "Download Selected" / "Download Remaining". Label:
  `_("Download Summary Report")`.
- [ ] **Green 6.4** — Run `just test`.
- [ ] **Refactor 6.5** — None expected; verify modal layout still looks
  sensible (no horizontal overflow with three buttons).
- [ ] **Check** — `just check` clean.
- [ ] **Commit** — `feat: link summary report from selection results modal`.

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
