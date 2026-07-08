# 726 — Export respondents (CSV + Google Sheets)

Status: **REVISED after Doctor Chewie's second review.** All review decisions
(D1–D16) and follow-up sub-questions (S1–S4) are folded into the body; §11
summarises them. The export UI is now specified in §3.3. Still nothing
implemented yet.

## 1. Goal & scope

Give organisers a way to **export** the respondents of an assembly.

- **Stage 1 (CSV, definite):** export to a CSV download — the rough reverse of
  the existing "import from CSV" (`import_respondents_from_csv`), but richer: it
  also includes internal fields we hold and never import, most importantly
  `selection_status`.
- **Filtering:** export
  1. all respondents, or
  2. all respondents with one given `selection_status`, or
  3. all respondents that are `SELECTED` **or** `CONFIRMED`.

  No other arbitrary status combinations are required.
- **Stage 2 (Google Sheets export, in scope this round):** export to Google
  Sheets via `gspread`, sharing the tabular-data machinery with the CSV path
  behind an abstract type.
- **Out of scope:** Google Sheets **import** (design-sketched only, built
  later); xlsx files; Microsoft Office Online.

## 2. Where this sits in the current code

Key facts gathered from reading the code (so reviewers can sanity-check my
assumptions):

- **`Respondent`** (`domain/respondents.py`) top-level fields: `external_id`,
  `selection_status`, `selection_run_id`, `consent`, `stay_on_db`, `eligible`,
  `can_attend`, `email`, `source_type`, `attributes` (the flexible JSON dict),
  `created_at`, `updated_at`, `comments`, plus the internal `id` (UUID).
- **`external_id` is always populated.** It is required in `__init__`
  (blank raises `ValueError`). Registration generates `reg-<12 hex>`
  (`registration_submission_service._generate_external_id`); CSV import takes it
  from the id column; manual entry supplies it. So the export id column is never
  blank. (Answers the review question on §4.1.)
- **CSV import** maps the id column → `external_id`, pops `consent`, `eligible`,
  `can_attend`, `email` out of the row (normalised names) and drops everything
  else into `attributes`. It does **not** currently handle `stay_on_db` or
  `source_type`, and it **skips** rows whose `external_id` already exists (no
  update path today). (See §6.)
- **Per-assembly field schema** (`respondent_field_schema_service.get_schema`)
  gives us a **canonical, ordered** list of columns: fixed fields (`email`,
  `eligible`, `can_attend`, `consent`, `stay_on_db`) plus every attribute key,
  ordered by group then `sort_order`. `external_id` / the id column is *not* in
  the schema. Field rows carry `is_fixed`, `is_derived` (+ `derived_from`,
  `derivation_kind`). This is the natural source of export column order.
- **Existing "build rows from respondents" code** lives in
  `adapters/sortition_data_adapter.py` (`OpenDLPDataAdapter.read_people_data`)
  and `service_layer/sortition.py` (`_table_to_csv`, which prefixes a BOM so
  Excel reads UTF-8 correctly). We reuse the BOM idiom.
- **Existing CSV download idiom**: `db_selection_backoffice.py` builds a CSV
  string in memory and returns it with `mimetype="text/csv"` and a
  `Content-Disposition: attachment` header. No file is written to disk — the
  GDPR-safe pattern we follow (§10).
- **gspread today**: only used indirectly through the `sortition-algorithms`
  `GSheetDataSource`, authenticated with a service-account JSON at
  `config.get_google_auth_json_path()`. The service-account email is surfaced to
  users (`context_processors.get_service_account_email`) so they can share a
  sheet with it. Per the brief we do **not** extend `GSheetDataSource`; we add
  our own thin gspread adapter in `src/opendlp/adapters/`.
- **Repository**: `RespondentRepository.get_by_assembly_id(assembly_id, status=,
  eligible_only=, include_deleted=)` filters by a **single** status. We compose
  the SELECTED-or-CONFIRMED set from two such calls (§5).

## 3. Proposed architecture

Three cleanly separated pieces, so CSV and Google Sheets share everything except
the final write:

```
                 ┌─────────────────────────────────────────┐
 route  ───────► │ respondent_export_service               │
 (blueprint)     │   export_respondents(uow, user, asm,     │
                 │        status_filter, target)            │
                 │     1. permission check (can_manage)     │
                 │     2. fetch respondents + schema        │
                 │     3. build_respondent_table(...)  ─────┼──► TabularData
                 │     4. target.write_sheet(title, table)  │      (headers,
                 └───────────────┬──────────────────────────┘       rows)
                                 │ target: AbstractTabularExportTarget
                 ┌───────────────┴───────────────┬───────────────────────┐
          CsvExportTarget              GSheetExportTarget         FakeGSheetExportTarget
        (in-memory string)           (adapters/, gspread)          (tests/fakes.py)
```

### 3.1 New/changed files

| File | What |
| --- | --- |
| `src/opendlp/adapters/tabular_export.py` | `TabularData` dataclass; `AbstractTabularExportTarget` (ABC); `CsvExportTarget` (accumulates rows, `getvalue() -> str` with BOM). No gspread import here, so it stays dependency-light and unit-testable. |
| `src/opendlp/service_layer/respondent_export_service.py` | `build_respondent_table(...)` (pure: respondents + schema → `TabularData`); `resolve_status_filter(...)`; `export_respondents(uow, user_id, assembly_id, *, status_filter, target)` (permission-checked orchestration). |
| `src/opendlp/adapters/gsheet_export.py` | `GSheetExportTarget` — real gspread implementation (isolates the gspread import). |
| `src/opendlp/domain/assembly_respondent_gsheet.py` + ORM + repo | New `AssemblyRespondentGSheet` model storing the export sheet URL + tab name (see §7, decision D12). |
| `tests/fakes.py` | `FakeGSheetExportTarget` recording `(title, table)` writes, for component/unit tests. |
| `src/opendlp/entrypoints/blueprints/respondents.py` | New routes: CSV export download; Google Sheets export. |
| templates + nav | Export menu on the respondents/data page (CSV + Google Sheets). |

### 3.2 The abstract type

```python
# adapters/tabular_export.py
@dataclass(frozen=True)
class TabularData:
    headers: list[str]
    rows: list[list[str]]          # each row already stringified, len == len(headers)

class AbstractTabularExportTarget(ABC):
    @abstractmethod
    def write_sheet(self, title: str, table: TabularData) -> None: ...
```

- `CsvExportTarget.write_sheet` writes header + rows into a `StringIO`; a
  `getvalue()` returns the BOM-prefixed CSV string for the download response.
  It accepts **exactly one** `write_sheet` call and raises if called a second
  time (decision D7) — a CSV download is a single sheet.
- `GSheetExportTarget.write_sheet` opens the target spreadsheet, creates/clears a
  worksheet named `title`, and `worksheet.update([headers, *rows])`. Exposes the
  resulting sheet/tab URL via an attribute for the route to flash back.
- `write_sheet` returns `None`; the "result" (CSV string, or sheet URL) is read
  off the concrete target (decision D6). This keeps the interface uniform
  despite the two destinations producing different artefacts.

**Why an ABC not a `typing.Protocol`?** Consistency: the repositories and the
email/data-source adapters in this codebase are all ABCs. Open to a `Protocol` if
reviewers prefer structural typing.

### 3.3 Export UI (modal)

The organiser drives export from a single modal on the **Respondents page** (the
page that shows the respondent table):

- Add an **"Export" button** to that page.
- Clicking it opens a **modal** built on the established modal patterns
  (`templates/backoffice/patterns.html`, and the accessibility guide), **loaded
  via HTMX** as a server-rendered fragment (consistent with the HTMX-modal
  direction), so the pre-filled Google-Sheet settings come from the server.
- In the modal the organiser chooses:
  - **Destination** — CSV download **or** Google Sheet.
  - **Filter** — none (all), a single `selection_status`, or SELECTED-or-CONFIRMED
    (§5).
  - **If Google Sheet is chosen**, two extra fields appear: **spreadsheet URL**
    and **tab/worksheet name**. They are blank the first time; on export they are
    saved to `AssemblyRespondentGSheet` and **pre-filled** on subsequent exports,
    editable before each run (S4). Show the service-account email so the
    organiser can share the sheet.
- **Submit:**
  - CSV → streams the file download (§10).
  - Google Sheet → writes the tab, then flashes the resulting sheet/tab URL; on a
    gspread permission error, flash a "share the sheet with `<service-account>`"
    message.

Accessibility / CSP: follow the component-accessibility guide and the
CSP-compatible Alpine/HTMX patterns (flat `x-model`, no string args in `@click`,
`X-CSRFToken` on AJAX) referenced in `CLAUDE.md`.

## 4. Export column specification

Column order, left to right:

1. **id column** — header = the assembly's configured `csv_id_column` if set
   (from `assembly.csv`), else `"external_id"`; value = `respondent.external_id`
   (always populated — see §2). Using the configured name keeps re-import
   aligned with the importer's `id_column` auto-detection.
2. **Schema fields, in schema order** — for each `RespondentFieldDefinition`
   from `get_schema` (which already interleaves the fixed fields `email`,
   `eligible`, `can_attend`, `consent`, `stay_on_db` with attributes by
   group/sort_order):
   - fixed fields read from the top-level attribute (`respondent.email`, etc.);
   - attribute fields read from `respondent.attributes[field_key]`;
   - **derived fields are included** in the export (decision D2). A derived
     field's value comes from `respondent.attributes[field_key]` if present,
     else blank. Export needs no distinction between kinds of derived field;
     how import *writes* derived fields is deferred to the re-import round
     (§4.1).
3. **Any leftover attribute keys** not present in the schema, appended in sorted
   order, so no data is silently dropped if a schema row was deleted (D3).
4. **Internal fields** (the "extra" columns), appended last, **all of them**
   (D4): `selection_status`, `source_type`, `selection_run_id`, `created_at`,
   `updated_at`. Easy to drop one or two later if they prove noisy.

### 4.1 Derived fields: no distinction needed for export (deferred)

Export includes **every** schema field regardless of derived flag, reading its
value from `respondent.attributes[field_key]` (or blank). **Export does not
need any internal/external derived distinction** — that only matters for how
import *writes* derived values, which is deferred to the re-import round
(decision on S1 deferred).

Recorded so the re-import round has the context: "derived" currently conflates
two things that a future re-import will want to keep apart —

- **Internally-derived** — OpenDLP computes the value from other fields; a
  re-import must **not** let a user overwrite a value the system owns.
- **Externally-derived / annotation** — a value that does *not* come from the
  registration form but is produced by an **export → external computation →
  re-import** cycle (the spreadsheet-formula workflow in §6.1). Import is how
  these get their value, so a re-import *should* accept them.

The model today has a single `is_derived` flag. When we build re-import we will
decide how to split it — candidate namings then:
`is_derived_internal` / `is_derived_external`; or keep `is_derived` (internal) +
add `is_external_annotation`; or a `derivation_source` enum. **No model change
is needed for this export round.**

### Value serialisation (chosen for import symmetry)

- Booleans (`eligible`/`can_attend`/`consent`/`stay_on_db`): `True → "true"`,
  `False → "false"`, `None → ""` (empty). Import parses `str.lower() == "true"`,
  so `""`/`"false"` → `None`/`False` respectively; `None → ""` round-trips to
  `None`. ✅ symmetric.
- `selection_status` / `source_type`: the enum `.value` (e.g. `"SELECTED"`).
- Timestamps: ISO 8601 (`created_at.isoformat()`).
- `attributes` values: `str(value)` (already strings in practice).
- **Headers are the raw field keys** (decision D8), not human labels, so the
  file re-imports cleanly. Any i18n happens only in the surrounding UI.

## 5. Filtering specification

`resolve_status_filter` maps a UI choice to a set of statuses:

| UI choice | Statuses exported |
| --- | --- |
| All | everything **except `DELETED`** (includes `TEST_SUBMISSION`, `POOL`, `SELECTED`, `CONFIRMED`, `WITHDRAWN`) — decision D9 |
| A single status X | `{X}` |
| Selected or confirmed | `{SELECTED, CONFIRMED}` |

- `DELETED` respondents are **never** exported (D10): their PII is already
  blanked, so rows would be empty.
- **Fetching the SELECTED-or-CONFIRMED set (decision D5 = Option C):** run two
  existing single-status queries (`get_by_assembly_id(status=SELECTED)` and
  `…status=CONFIRMED`) and concatenate in Python. No new repository method, no
  new contract test. The "All" case uses
  `get_by_assembly_id(include_deleted=False)` (which already excludes `DELETED`).

## 6. Round-trip / re-import safety

Export is a **superset** of import, so a naive "export then re-import" would
currently **crash**: `import_respondents_from_csv` drops unknown columns into
`attributes`, and `Respondent.__init__` → `validate_no_field_name_collisions`
**rejects** any attribute key normalising to a reserved field name
(`selection_status`, `selection_run_id`, `source_type`, `created_at`, …). A file
containing our internal columns would raise `ValueError`.

**Chosen approach (decision D11 = Option A): recognise and skip.** Teach the
importer to recognise the reserved/internal columns and **skip** them, so an
exported file re-imports as a plain respondent import (internal fields ignored,
new records get status `POOL` as today). Specifically, on import:

- **Skip** `selection_status`, `selection_run_id`, `source_type`, `created_at`,
  `updated_at` (informational-only in the file).
- Derived-field import handling (internally- vs. externally-derived, §4.1) is
  **deferred to the re-import round** — it is not needed for crash-safety, since
  a derived column's key is not reserved and would simply land in `attributes`
  today.
- **`stay_on_db` handling (special — decision from review):** `stay_on_db` is the
  respondent's own statement of whether we may keep their details beyond this
  event. Overriding it in bulk is a serious act.
  - When **creating a new record** (e.g. importing from an internal system that
    legitimately holds `stay_on_db`), **honour** the column — extract it like the
    other booleans into the fresh record.
  - When an import would **update an existing record** (no such path today, but
    the row-oriented refactor and future GSheet import make it likely),
    **ignore** `stay_on_db` and surface a line in the end-of-import status
    ("stay_on_db left unchanged for N existing records"). Bulk import must never
    silently flip an existing consent flag. Per-individual overrides stay a
    manual, audited edit (the existing `update_respondent` path).
- Result reporting: the importer's returned `errors`/status list gains
  informational messages for skipped columns so the organiser understands what
  was and wasn't applied.

### 6.1 Keep the door open for the derived-via-spreadsheet workflow

Recorded for the future (do **not** build now, but don't block it): an organiser
could export respondents to tab A of a spreadsheet, have tab B use formulas that
reference tab A (plus lookup tabs) to compute derived fields — e.g. age from a
date of birth, or region from a postcode — then re-import tab B. Tab B carries
the id column (so rows match) and the derived columns, and import ignores the
rest. An automated loop could export → wait → re-import to populate
externally-derived fields for use in targets.

Implication for this round: the import **skip** rules above should key off the
*field's role* (id column, internal reserved) rather than a blanket "unknown
column → attribute", so that a genuine externally-derived column can later be
recognised and written when we build re-import. The row-oriented import core
(§7.2, done this round per D13) is where that logic will eventually live.

## 7. Google Sheets export (in scope) + import (design sketch)

Reuses everything above; only a new `AbstractTabularExportTarget` implementation
plus (later) an import counterpart.

### 7.1 Export to Google Sheets

- `adapters/gsheet_export.py::GSheetExportTarget(spreadsheet_ref, auth_json_path,
  worksheet_title)`:
  - authenticate with the **same** service-account JSON as `GSheetDataSource`
    (`gspread.service_account(filename=config.get_google_auth_json_path())`);
  - `open_by_url` / `open_by_key` the target spreadsheet;
  - create the worksheet (or clear if it exists), then `update([headers,*rows])`;
  - store the tab URL for the route to display.

- **Where the target sheet is configured (decision D12 = Option D — new model):**
  We do **not** reuse `AssemblyGSheet`. That model is for the workflow where
  targets/selected/registrants all live in a Google Sheet, and configuring it
  prompts for tab names of things we explicitly do **not** want stored in Google
  Sheets for the export case. Instead:
  - Add a new model **`AssemblyRespondentGSheet`** (name confirmed) storing the
    export **spreadsheet URL** + **worksheet/tab name** (and probably the id
    column to write). The organiser sets these the first time they export to a
    sheet; they are saved here and **pre-filled** on future exports, editable
    before each run (decision S4 — see the UI in §3.3).
  - We do **not** rename the existing `AssemblyGSheet` → `AssemblySelectionGSheet`
    in this round — that rename is a large, mechanical diff (ORM table,
    repository, `gsheets*.py`, `domain/assembly.py`, templates, Alembic
    migration) and is scheduled as a **separate follow-up round** (decision S3).
    This round only *adds* `AssemblyRespondentGSheet`.
  - The service account still needs edit access to the target spreadsheet; we
    keep surfacing `get_service_account_email` so organisers can share it.

- **Injection for tests:** mirror the `uow_factory` seam — register a
  `gsheet_export_target_factory` in `app.extensions`, defaulting to the real
  adapter, so component tests inject `FakeGSheetExportTarget`. gspread is an
  external boundary; per the mocking policy we exercise the real adapter only in
  a boundary-mocked or manually-run test, never in CI proper.

### 7.2 Import from Google Sheets (out of scope — sketch only; but do the refactor)

Google Sheets **import** is **not** built this round. But we **do** the enabling
refactor now (decision D13):

- Refactor `import_respondents_from_csv` into a thin CSV wrapper over a new core
  `import_respondents_from_rows(uow, ..., headers, rows)` holding the per-row
  logic (dup detection, bool extraction, column-skip rules from §6, schema
  reconciliation). CSV import calls the core immediately; a future GSheet import
  calls the same core.
- Later (out of scope): a read helper opens a worksheet →
  `get_all_records()` → `(headers, rows)` → feeds the core; same service-account
  auth and sharing story as export.

Doing the row-oriented refactor now is what makes both the skip rules (§6) and
the eventual GSheet import clean, rather than string-munging CSV twice.

## 8. TDD implementation plan

Each step: write the failing test(s) first, then the code. Ordered so each layer
is driven by a test before the layer above it exists.

### Stage 1 — CSV export

1. ✅ **`TabularData` + `CsvExportTarget`** — *unit* (`tests/unit/`, no db/redis):
   header + rows → BOM-prefixed CSV; quoting/commas handled by `csv`; a second
   `write_sheet` call raises (D7).
2. ✅ **`build_respondent_table`** — *unit*, pure over plain `Respondent` objects +
   a schema list: id-column header rule; schema-ordered columns; fixed from
   top-level; attributes from dict; derived **included**; leftover attribute keys
   appended sorted; all internal columns appended; bool/enum/None serialisation
   per §4.
3. ✅ **`resolve_status_filter`** — *unit*: All (everything but DELETED), single
   status, SELECTED-or-CONFIRMED; invalid input handled.
4. ✅ **`export_respondents` service** — *unit* over `FakeUnitOfWork`:
   permission denied → `InsufficientPermissions` (uses `can_manage_assembly`,
   D14); missing user/assembly → correct errors; each filter variant produces
   the expected rows via a `CsvExportTarget`; `DELETED` never appears; the
   SELECTED-or-CONFIRMED path issues the two queries and merges (D5/Option C).
5. ✅ **CSV export route** — *component* (`tests/component/`, Flask over
   `FakeUnitOfWork`): `GET .../respondents/export?status=...` → 200, `text/csv`,
   `Content-Disposition: attachment; filename=...`, correct header row + one row
   per matching respondent; permission failure → flash/redirect; filter variants.
6. ✅ **PostgreSQL smoke** — *e2e*: one happy-path per new route (real DB round-trip).
7. **BDD** (decision D15): a feature — "organiser exports SELECTED-or-CONFIRMED
   respondents to CSV" — asserting the download happens and contains expected
   rows/columns. *(Deferred until after step 13: the BDD scenario drives the
   export modal, which is built with the Google Sheets route.)*

### Row-oriented import refactor + re-import safety (D13, §6)

8. ✅ **Extract `import_respondents_from_rows`** — refactor with existing import
   tests staying green; add *unit* tests for the new core directly.
9. ✅ **Column-skip + `stay_on_db` rules** — *unit* + *integration*: an exported
   file re-imports without crashing; internal reserved columns skipped with a
   status message; `stay_on_db` honoured on **create**; (guard test for the
   future update path — ignored + reported — even if update isn't wired yet).
   Derived-field import handling is out of this round (§4.1/§6).

### Stage 2 — Google Sheets export

10. ✅ **`FakeGSheetExportTarget`** (fakes) + *unit* tests exercising
    `export_respondents` against it (records the single `(title, table)` write).
11. ✅ **`AssemblyRespondentGSheet` model** (+ ORM, repo, Alembic migration,
    `_delete_all_test_data()` / BDD `delete_all_except_standard_users()` updates,
    contract tests for the new repo). No `AssemblyGSheet` rename this round (S3).
12. ✅ **`GSheetExportTarget`** real adapter — *test* with gspread mocked at the
    boundary (or a manually-run integration check); unit-level auth/tab logic.
13. ✅ **Export modal + Google Sheets route** (§3.3) — *component* over
    `FakeUnitOfWork` with the fake target injected: HTMX-loaded modal with
    destination + filter; Google-Sheet fields pre-filled from
    `AssemblyRespondentGSheet` and saved on export; surface the service-account
    email + a confirmation before writing PII externally. (The CSV path of the
    modal reuses the Stage-1 route.)
14. ✅ **e2e** smoke for the GSheet export route (fake target).

### Cross-cutting

15. **i18n**: wrap new UI strings in `_()`/`_l()`; run `just translate-regen`.
16. **Docs**: update `docs/architecture.md` (respondent service/adapters/new
    model rows); short respondent-export doc. (The `AssemblyGSheet` →
    `AssemblySelectionGSheet` rename is a separate follow-up round, S3.) Run
    `just check` + `just test`; regenerate `../.secrets.baseline` if test secret
    line numbers shift.

## 9. Testing strategy summary (per `docs/testing.md`)

| Level | Covers |
| --- | --- |
| **Unit** | `TabularData`/`CsvExportTarget`, `build_respondent_table`, `resolve_status_filter`, `export_respondents` over `FakeUnitOfWork`, the new import core + skip/`stay_on_db` rules, GSheet export against `FakeGSheetExportTarget`. |
| **Contract** | New `AssemblyRespondentGSheet` repository (fake vs SQL parity). No new respondent-repo method (D5/Option C reuses existing ones). |
| **Integration** | Re-import-safety round trip (real DB); `AssemblyRespondentGSheet` persistence/JSON round-trips. |
| **Component** | Export route(s) over `FakeUnitOfWork`: content-type, disposition, body, filters, permissions; GSheet route with `FakeGSheetExportTarget`. |
| **e2e** | One PostgreSQL happy-path smoke per new route. |
| **BDD** | "Organiser exports respondents to CSV" (D15). |

State-based assertions throughout (assert on the CSV bytes / `FakeStore` / the
fake target's recorded writes), never `mock.assert_called_with`. gspread is the
only thing mocked at the boundary.

## 10. GDPR & security

- **No persisted export files.** CSV is generated in memory and streamed as a
  download (the `db_selection_backoffice` pattern). Nothing hits disk or
  long-term DB storage — consistent with the "right to be forgotten" requirement
  in `CLAUDE.md`.
- **`DELETED` respondents excluded** from every export.
- **`stay_on_db` never bulk-overwritten** on existing records (§6) — the consent
  flag is protected.
- **Permission gate:** export uses **`can_manage_assembly`** (D14), matching
  import — an export of contact details is a manage-level action.
- **Google Sheets:** exporting pushes PII to an external Google resource, only
  ever to a spreadsheet the organiser controls and has shared with our
  service-account. Surface the service-account email and a clear confirmation
  before writing.

## 11. Decisions from review + remaining sub-questions

**Resolved (folded into the body above):**

- **D1** id-column header = configured `csv_id_column` else `external_id`;
  `external_id` is always populated.
- **D2** Derived fields **included** in export; no internal/external derived
  distinction needed for export — that split is deferred to the re-import round
  (§4.1).
- **D3** Append non-schema leftover attribute keys, sorted.
- **D4** Include **all** internal columns (`selection_status`, `source_type`,
  `selection_run_id`, `created_at`, `updated_at`).
- **D5** SELECTED-or-CONFIRMED via **two existing queries merged in Python**
  (Option C).
- **D6** `write_sheet` returns `None`; result read off the concrete target.
- **D7** `CsvExportTarget` allows **one** `write_sheet` call only.
- **D8** File headers are **raw field keys**.
- **D9** "All" includes everything **except `DELETED`** (incl. `TEST_SUBMISSION`).
- **D10** `DELETED` always excluded.
- **D11** Re-import safety via **Option A (recognise & skip)**; `stay_on_db`
  honoured on create, ignored+reported on update.
- **D12** New **`AssemblyRespondentGSheet`** model (Option D) storing the export
  sheet URL + tab name, saved/pre-filled per assembly. The `AssemblyGSheet` →
  `AssemblySelectionGSheet` rename is a **separate follow-up round** (S3), not
  this one.
- **D13** Do the row-oriented import refactor **now**.
- **D14** Export permission = **`can_manage_assembly`**.
- **D15** Add a **BDD** scenario for CSV export.
- **D16** Google Sheets **export in scope** this round; Google Sheets **import
  out of scope** (design-sketched).

**Sub-questions from the last round — now resolved:**

- **S1** Derived internal/external split naming — **deferred**. Not needed for
  export; decide when we build re-import (§4.1 records the candidate namings).
- **S2** New model name — **`AssemblyRespondentGSheet`** confirmed.
- **S3** `AssemblyGSheet` → `AssemblySelectionGSheet` rename — **separate
  follow-up round** (big, mechanical diff); this round only adds the new model.
- **S4** Export tab naming — **organiser-chosen**, saved to
  `AssemblyRespondentGSheet`, pre-filled and editable on future exports (§3.3).

**Open for a final check before implementation:**

- The **UI shape** (§3.3): "Export" button on the Respondents page → HTMX modal →
  destination (CSV / Google Sheet) + filter, with the Google-Sheet URL/tab fields
  appearing only for the sheet destination and pre-filled from
  `AssemblyRespondentGSheet`. Flagged here so you can confirm the modal captures
  what you described before I start building.
