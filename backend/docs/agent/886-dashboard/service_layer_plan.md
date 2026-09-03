# Ticket 886 — Results dashboard: service-layer implementation plan

Status: **in progress.** Phases 0-2 done; Phases 3-5 outstanding. Phase 6 is a
separate ticket. Revision 3 of the plan folds in Doctor Chewie's COMMENT lines
from revisions 1 and 2.

Companion to [service_layer_spec.md](service_layer_spec.md), which described the mock
stage and carries the answers to the mock's own open questions. This document says
what the real implementation should be, what it costs, and what is left to decide.

## 1. What exists today

| Piece                       | Path                                                                                               | State                                       |
| --------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| Mock services + dataclasses | `src/opendlp/service_layer/dashboard_stats.py`                                                     | all counts fabricated                       |
| Real dashboard page         | `backoffice.view_assembly_dashboard`, `templates/backoffice/assembly_dashboard.html`               | live, flag-gated tab, reads the mocks       |
| Report → pie-card mapping   | `backoffice._build_dashboard_sections`                                                             | real, unit-tested                           |
| Dev-console handlers        | `entrypoints/blueprints/dev.py` (search `dashboard`)                                               | real, calls the mocks with **keyword** args |
| Dev-console tab + JS slice  | `templates/backoffice/service_docs/_dashboard.html`, `src/js/components/service-docs/dashboard.js` | real                                        |
| Tests                       | `tests/component/test_assembly_dashboard.py`, `tests/unit/test_dashboard_sections.py`              | assert against mock fixture numbers         |

The page renders four pie cards per category — Target, Respondents, Selected,
Confirmed — and the last two are hard-coded skeletons because `DashboardReport`
carries no selected/confirmed counts. The chart/table toggle, the export button
and the findings banner are not wired.

## 2. Settled decisions

### From the spec

- **Live respondents, never a `SelectionRunRecord`.** Every count comes from the
  `respondents` table as it is now. `selection_report.py` is therefore a reference
  for _shape_, not a thing to call: it reconstructs a pool from a run's recorded
  external IDs, which is exactly what we are not doing. We reuse its ideas
  (`_pct`, the category/row/report nesting) and none of its code path.
- **Headline total** = POOL + SELECTED + CONFIRMED + WITHDRAWN.
- **Simple feasibility check** — no `InfeasibleQuotasError`, no solver, no call
  into `target_checking.py`.
- **Permissions** follow the house pattern (details below).

### From the reviews

- **`mock` goes.** Confirmed with the team that nobody has a plan for it. It
  appears in no JavaScript, no template binding and no test — only the dataclass
  defaults, the `asdict()` output in the dev console, and three lines of
  descriptive prose in `_dashboard.html`. `DashboardExport.note` and
  `download_ready` go with it (see §6).
- **Selected and Confirmed pies get real data** (`selected_count`,
  `confirmed_count` on the row).
- **`target_pct` comes from `TargetValue.percentage_target`**, with a fallback —
  and `selection_report` is changed to use the same formula.
- **Shortfall is measured over an eligible-only `available_count`**, not the
  headline pool count.
- **`unmatched_count`** on the category, and we never raise on an unknown value.
- **One generalised GSheet export table**, renamed properly, keyed by export kind.
- **Category → attribute matching** uses `normalise_field_name`.
- **`target_category_count`** stays, from `len(categories)`, not a `COUNT` query.

### Consequences worth writing down

**The headline exceeds the category totals, on purpose.** `total_respondents`
includes WITHDRAWN; the per-value `pool_count` uses `COUNTED_RESPONDENT_STATUSES`
(POOL + SELECTED + CONFIRMED), which is the constant that exists to answer "who is
the pool a target is measured against", and is what the Targets page already
counts. So the headline will normally exceed the sum of any category's counts, by
the number of withdrawals. Correct, but it will read as a bug to whoever comes
next: it needs a comment in the code, and `status_counts` is what explains it in
the UI.

**Three different denominators now live in one row.** `pool_count` (POOL +
SELECTED + CONFIRMED), `available_count` (POOL and not explicitly ineligible), and
`selected_count` / `confirmed_count`. Each is right for its question and none is
interchangeable. The dataclass field comments are load-bearing.

### Permissions — two traps

The house pattern, as used by `target_checking.check_targets_detailed` and
`respondent_export_service.export_respondents`:

```python
@require_assembly_permission(can_view_assembly)
def get_assembly_dashboard_summary(uow, user_id, assembly_id) -> DashboardSummary:
```

1. **The decorator only fires on positional args.** `require_assembly_permission`
   reads `args[0], args[1], args[2]` and silently does nothing when `len(args) < 3`.
   `dev.py` currently calls these services with keyword arguments
   (`get_assembly_dashboard_summary(uow=uow, assembly_id=...)`), so a decorated
   service called that way would **skip the check entirely**. Every call site must
   pass `uow, user_id, assembly_id` positionally, and a test must assert a
   non-member gets `InsufficientPermissions`.
2. Reads are `can_view_assembly`; the **export** is a manage action
   (`can_manage_assembly`), matching `export_respondents`.

### Scope boundary — what this plan does not touch

**This is a service-layer plan.** Blueprints, templates and JavaScript are out of
scope except for the *minimal* edits that a service-layer change forces: if a field
is renamed or a return type changes, the call site is updated to keep working, and
nothing more. Concretely:

- **In scope:** `dashboard_stats.py`, the repository methods, the domain helper,
  `selection_report.py`, the GSheet export domain/ORM/repository/migration, and the
  tests for all of it. Renames pushed into `respondents.py`, `export_modal.html`,
  `assembly_data.html` and `dev.py` by the Phase 4 rename. The dev-console export
  handler, because its service's signature and return type both change.
- **Out of scope:** lighting up the Selected and Confirmed pie cards; the
  chart/table toggle; the findings banner; an export button or modal on the
  dashboard page; any BDD feature file.

Two knock-on effects to be honest about. `selected_count` and `confirmed_count`
land on the row and **sit unused** until a follow-up front-end ticket deletes the
skeleton branch in `_build_dashboard_sections` — the data is there, the page still
shows placeholders. And the dashboard export is **reachable only from the dev
console** until that same follow-up adds the button. Both are deliberate: the
service layer lands complete and the UI catches up separately.

## 3. Decisions in detail, where the note needs unpacking

### Percentages, unified across both reports (was Q2)

`TargetValue.percentage_target` post-dates the spec, so `target_pct` is copied from
it rather than derived. When it is `None`, fall back to
`(min + max) / sum(min + max)` across the category — **which is exactly what
`TargetCategory.derive_percentages_from_minmax()` already computes**. That method
mutates the domain object, which the dashboard must not do (it would write derived
percentages back into targets the organiser never set).

`selection_report._target_pct` answers the same question a different way: its
fallback is `midpoint / number_to_select`. Both reports now use the newer
within-category formula, so an assembly cannot show two different target
percentages depending on which report you open.

The shared helper has to work on **plain min/max pairs, not on domain objects**:
`selection_report` reads a targets *snapshot* off the run record
(`value_snapshot["min"]`, `["max"]`, `["percentage_target"]`), and never has a
`TargetCategory` to hand. So:

> Add a module-level `percentages_from_minmax(pairs) -> list[float]` to
> `domain/targets.py`, returning `0.0` for every value when the min/max sum is zero.
> `TargetCategory.derive_percentages_from_minmax()` calls it and assigns;
> `selection_report._target_pct` and the dashboard call it and do not.

**This changes a shipped report.** For any run whose snapshot has no
`percentage_target` — every run recorded before percentages existed — the CSV's
target-% column will print different numbers than it did yesterday. That is the
intent of the note, but it is user-visible and belongs in the commit message.
`_target_pct`'s `number_to_select` argument becomes dead and goes, and with it the
same argument on `_build_category_report`, which passes it nowhere else.

Three tests in `tests/unit/test_selection_report.py` change, and their new
expectations are worth writing down now because they are the proof the change did
what we meant:

- `test_a_missing_percentage_falls_back_to_the_midpoint` — a two-value Gender
  snapshot with `min=1, max=1` on each and 4 seats: **25.0 → 50.0**, because the
  denominator is now the category's own `sum(min + max) = 4`, not the seat count.
- `test_an_explicit_none_percentage_falls_back_too` — same, **25.0 → 50.0**.
- `test_no_seats_and_no_percentage_is_zero_rather_than_a_divide_by_zero` — with
  `number_to_select=0` the old formula divided by zero and returned `0.0`; the new
  one does not divide by seats at all and returns **50.0**. The divide-by-zero case
  it was guarding has moved, so the test should be re-pointed at the case that can
  still divide by zero: a category whose every min and max is zero.

**The other percentages are not stored.** `pool_pct`, `selected_pct` and
`confirmed_pct` are derivable from counts the row already carries, so the row does
not gain fields for them — the CSV builder and the template compute them at the
point of use. The denominator is the **category total**, matching
`selection_report`. `_pct` in that module is the shared helper; lift it somewhere
both can import rather than copying it.

### Eligible-only shortfall (was Q3)

`available_count` = respondents in POOL whose `eligible` and `can_attend` are not
explicitly `False` — the same set `OpenDLPDataAdapter` hands the selection
algorithm. `shortfall = max(0, target_min - available_count)` and
`meetable = shortfall == 0`, so the dashboard's "can we meet this" agrees with what
a selection run would actually find, which was the point of the note.

Consequence: `UnmetTarget.pool_count` becomes `UnmetTarget.available_count`. A row
that says "shortfall 3" alongside a count that is not the one the shortfall came
from is a trap, so the field follows the arithmetic. The wider `pool_count` stays
on `CategoryValueRow` for display.

### The GSheet export table (was Q5)

Option (c), generalised and renamed. The notes add two requirements the original
option did not have: a **separate spreadsheet URL per export kind** (respondent
data is personal and access-controlled; dashboard data is aggregate and an
organiser may want it public), and room for **more export kinds later**. So the
table is keyed on `(assembly_id, export_kind)` and each row owns its own URL,
worksheet name, spreadsheet title and worksheet URL.

```python
class GSheetExportKind(Enum):
    RESPONDENTS = "RESPONDENTS"
    DASHBOARD = "DASHBOARD"

@dataclass
class AssemblyExportGSheet:      # was AssemblyRespondentGSheet
    assembly_id: uuid.UUID
    export_kind: GSheetExportKind
    ...                          # url, worksheet_name, spreadsheet_title, worksheet_url unchanged
```

- Module `domain/assembly_respondent_gsheet.py` → `domain/assembly_export_gsheet.py`.
- Table `assembly_respondent_gsheets` → `assembly_export_gsheets`, plus an
  `export_kind` column; `unique(assembly_id)` → `unique(assembly_id, export_kind)`.
- Repository → `AssemblyExportGSheetRepository`;
  `get_by_assembly_id(assembly_id)` → `get_by_assembly_and_kind(assembly_id, kind)`.
- UoW attribute `uow.assembly_respondent_gsheets` → `uow.assembly_export_gsheets`.
- `worksheet_name`'s default of `"Respondents"` becomes per-kind.

**Nothing copies the respondent sheet's URL into the dashboard row.** They are
independent by design; sharing a default would quietly put aggregate data in the
sheet that holds personal data, or worse, the other way round.

**`AssemblyGSheet` stays separate.** It is the selection _input_ source, a
different thing with different fields, and folding it in would merge "where the
data comes from" with "where exports go".

**The migration must be hand-written.** `alembic revision --autogenerate` renders a
table rename as drop + create, which discards every saved export config. The
revision needs `op.rename_table`, then `add_column` with a server default of
`RESPONDENTS`, then drop the default, then swap the unique constraint. Write it,
then check the generated SQL before running it anywhere real.

Cost of the rename: **139 references across 17 live files** (`orm.py`,
`sql_repository.py`, `database.py`, the domain module, `unit_of_work.py`,
`repositories.py`, `respondent_export_service.py`, the `respondents` blueprint,
`fakes.py`, six test modules, and two `conftest.py` delete lists), plus
`templates/backoffice/respondents/export_modal.html` and
`templates/backoffice/assembly_data.html`. The two existing migrations under
`migrations/versions/` keep the old names and must not be touched. This is why it
gets its own phase.

### `target_category_count` (was Q7)

Taken from `len(categories)`. `get_assembly_dashboard_summary` does not otherwise
need the category list, so this trades a cheap `COUNT` for a full
`get_by_assembly_id` load — a handful of rows per assembly, so the difference is
noise, and it drops a repository call from the module. Both public services now
load assembly + categories, so that pair goes in one private
`_load_dashboard_context(uow, assembly_id)` used by both. The route calls both
services and so loads them twice; if that ever matters, the fix is one combined
`get_assembly_dashboard()` with the two public functions as thin wrappers — not
worth doing yet.

## 4. The contract after the change

```python
@dataclass
class StatusCount:
    status: str          # RespondentStatus.value
    count: int

@dataclass
class DashboardSummary:
    assembly_id: str
    assembly_title: str
    number_to_select: int
    target_category_count: int
    total_respondents: int            # POOL + SELECTED + CONFIRMED + WITHDRAWN
    status_counts: list[StatusCount]  # one per RespondentStatus, stable order, zeros included

@dataclass
class CategoryValueRow:
    value: str
    target_min: int
    target_max: int
    target_pct: float     # TargetValue.percentage_target, else normalised (min+max)
    pool_count: int       # COUNTED_RESPONDENT_STATUSES: POOL + SELECTED + CONFIRMED
    available_count: int  # POOL, and not explicitly ineligible / unable to attend
    selected_count: int   # SELECTED + CONFIRMED
    confirmed_count: int  # CONFIRMED only
    shortfall: int        # max(0, target_min - available_count)
    meetable: bool        # shortfall == 0

@dataclass
class DashboardCategory:
    name: str
    rows: list[CategoryValueRow]
    unmatched_count: int = 0   # respondents whose value is not a declared target value

@dataclass
class UnmetTarget:
    category: str
    value: str
    target_min: int
    available_count: int
    shortfall: int

@dataclass
class DashboardReport:
    assembly_id: str
    assembly_title: str
    number_to_select: int
    pool_size: int             # respondents in COUNTED statuses; one count, not a derived average
    categories: list[DashboardCategory]
    unmet_targets: list[UnmetTarget]
```

`DashboardExport` disappears — see §6.

`DashboardStatsError` also disappears. It currently subclasses plain `Exception`,
outside the `OpenDLPError` tree, so it bypasses `user_msg()` and the JSON-body
rules. Its two uses become the existing `AssemblyNotFoundError` (raised by the
permission decorator anyway) and `InvalidSelection` for a bad export format.

## 5. Queries and repository work

Two new methods on `RespondentRepository`:

```python
def count_by_status(self, assembly_id: uuid.UUID) -> dict[RespondentStatus, int]:
    """One entry per status present for the assembly; the caller fills in the zeros."""

def get_attribute_value_counts_by_status(
    self, assembly_id: uuid.UUID, attribute_name: str
) -> dict[str, dict[RespondentStatus, int]]:
    """Counts of each distinct value of one attribute, broken down by selection status."""
```

and one more for the eligible-only figure the shortfall needs:

```python
def get_attribute_value_available_counts(
    self, assembly_id: uuid.UUID, attribute_name: str
) -> dict[str, int]:
    """Counts of each distinct value among respondents available to select:
    POOL, and neither eligible nor can_attend explicitly False."""
```

These last two could be one query with a filtered aggregate
(`count(*) FILTER (WHERE ...)`), saving one round trip per category. Two plain
methods instead, on the house rule that simple and maintainable beats concise and
performant: each has an obvious contract and an obvious contract test, and the cost
is one extra indexed `GROUP BY` per category.

Each method needs: abstract in `service_layer/repositories.py`, SQL in
`adapters/sql_repository.py`, fake in `tests/fakes.py`, contract tests in
`tests/contract/test_respondent_repo.py` running against both backends.

Query count per dashboard load: 1 assembly + 1 status breakdown + 1 target
categories + 2 per category. A five-category assembly is 13 queries, **independent
of respondent count** — no `get_by_assembly_id()` full load, which is what
`selection_report` does and what would hurt at 10k respondents.

## 6. Export — reshaped to the house pattern

The mock's `export_assembly_dashboard(uow, assembly_id, export_format) -> DashboardExport`
returns a filename and a prose note and no bytes. The real thing should look like
`respondent_export_service`, which is the pattern the codebase already proved:

```python
@require_assembly_permission(can_manage_assembly)
def export_dashboard_report(uow, user_id, assembly_id, *, target: AbstractTabularExportTarget,
                            sheet_title: str = DEFAULT_SHEET_TITLE) -> None: ...

@require_assembly_permission(can_manage_assembly)
def export_dashboard_report_to_gsheet(uow, user_id, assembly_id, *, spreadsheet_url: str,
                                      worksheet_name: str, target: AbstractGSheetExportTarget) -> None: ...
```

The caller picks the target (`CsvExportTarget()` inline; the GSheet target via
the `gsheet_export_target_factory` app extension, so tests can fake it) and turns
it into a `Response` or a flash. `export_format`, `filename`, `note` and
`download_ready` all stop existing: the format **is** the target. Writing the route
that does that turning is the follow-up front-end ticket, not this plan — here the
only caller is the dev console.

Building the `TabularData` is a pure function over a `DashboardReport` —
`build_dashboard_table(report) -> TabularData` — so it unit-tests with no `uow`,
the way `build_respondent_table` does. Header layout follows
`selection_report_to_csv`: a preamble block (assembly, number to select, pool
size), then one block per category, with the percentages computed here.

GDPR note: unlike the respondent export, this table is aggregate counts only — no
personal data leaves in it, and nothing is written to disk. That is what makes the
"an organiser may want this sheet public" case in §3 safe.

**Dev console.** The console cannot receive a file download, so its export handler
becomes: build the report, run it into a `CsvExportTarget`, and return the CSV text
plus a row count in the JSON panel. `_dashboard.html` and `dashboard.js` need the
format dropdown reduced to csv/gsheet and the Returns prose updated.

## 7. Phases

Each phase is independently committable and leaves the suite green. Docs and code
commit separately.

**Phase 0 — tidy the contract. ✅ Done.** Drop `mock` from the three dataclasses; replace
`DashboardStatsError` with the standard exceptions; update the three prose lines in
`_dashboard.html`. No behaviour change; the mock data stays. _Tests:_ existing ones
stay green.

**Phase 1 — repository methods. ✅ Done.** The three from §5: abstract, SQL, fake, contract
tests. Nothing calls them yet. _Tests:_ contract tests over both backends —
empty assembly, DELETED excluded, an absent attribute, and the three-way
`eligible` / `can_attend` states (`True` / `False` / `None`, where only explicit
`False` excludes).

**Phase 2 — real `get_assembly_dashboard_summary`. ✅ Done.** Add `user_id`, decorate with
`can_view_assembly`, add `_load_dashboard_context`, count for real. Update both
call sites to pass positionally. _Tests:_ integration over a seeded assembly
(counts per status, zeros present for absent statuses, the
POOL+SELECTED+CONFIRMED+WITHDRAWN total, TEST and DELETED excluded); a permission
test for a non-member; update `tests/component/test_assembly_dashboard.py`, which
currently asserts the mock's `44`.

**Phase 3 — real `get_assembly_dashboard_report`, and the unified percentage.**
Per-category counts, `target_pct` from the new shared
`percentages_from_minmax()`, `available_count`, shortfall, `unmatched_count`,
`unmet_targets`, `pool_size`. Delete `_mock_categories`. Change
`selection_report._target_pct` over to the same helper and drop its now-dead
`number_to_select` argument. `selected_count` and `confirmed_count` land on the row
but nothing renders them yet — the pie-card skeletons stay, per the scope boundary.
_Tests:_ unit tests for the pure derivations (shortfall arithmetic, `unmet_targets`
projection, the percentage fallback, unmatched-value bucket, empty pool, a category
matching no attribute column); integration end-to-end over a seeded assembly; the
three `tests/unit/test_selection_report.py` cases listed in §3 re-pointed at the new
numbers; `tests/unit/test_dashboard_sections.py` updated only where the new required
row fields break its constructor calls.

**Phase 4 — generalise the GSheet export table.** Pure refactor, no new behaviour:
the rename, the `export_kind` column, the hand-written migration, and all 139
references. The respondent export must behave identically before and after — its
existing component, unit, contract and e2e tests are the proof, and should need no
changes beyond the renames. _Tests:_ the renamed contract test gains cases for two
kinds coexisting on one assembly and for the composite uniqueness; a migration
check that an existing row survives with `export_kind = RESPONDENTS`.

**Phase 5 — the dashboard export itself.** `build_dashboard_table`, the two
service functions, and the dev-console handler — which has to change, because the
service it calls no longer takes an `export_format` or returns a `DashboardExport`.
No export button or modal on the dashboard page: that is front-end work for a
follow-up, so until then the export is reachable only from the dev console.
_Tests:_ unit tests for `build_dashboard_table` (headers, one row per target value,
the percentages computed at this layer, an assembly with no targets); a service-level
test that a `CsvExportTarget` comes back with the expected text; a GSheet test using
the injected fake target that asserts the config row is written **after** a
successful write and not after a failure; permission tests for both.

**Phase 6 — xlsx. Separate ticket, not this one.** `tabular_export.py` has no xlsx
target and the project has **no xlsx library** — checked `pyproject.toml` and
`uv.lock`: no `openpyxl`, no `xlsxwriter`, no `pandas`. Adding one needs explicit
permission, and it wants its own conversation about whether an organiser who can
already get CSV and a Google Sheet needs a third format. Until then the format is
simply not offered — no `download_ready=False` placeholder advertising a feature
that does not exist.

## 8. Files touched

```txt
src/opendlp/service_layer/dashboard_stats.py      rewritten (mock -> real)
src/opendlp/service_layer/repositories.py         + 3 abstract methods, repo rename
src/opendlp/adapters/sql_repository.py            + 3 implementations, repo rename
src/opendlp/domain/targets.py                     + percentages_from_minmax()
src/opendlp/service_layer/selection_report.py     unified target_pct, _pct lifted, dead arg dropped
src/opendlp/entrypoints/blueprints/backoffice.py  positional args + user_id (minimal)
src/opendlp/entrypoints/blueprints/dev.py         positional args + reshaped export handler (minimal)
templates/backoffice/service_docs/_dashboard.html contract prose + format list (minimal)
src/js/components/service-docs/dashboard.js       format options (minimal)
tests/fakes.py                                    + 3 fake implementations, repo rename
tests/contract/test_respondent_repo.py            + contract tests
tests/unit/test_selection_report.py               3 cases re-pointed at the unified formula
tests/unit/test_dashboard_sections.py             constructor calls only
tests/component/test_assembly_dashboard.py        update: no more mock numbers
tests/unit/test_dashboard_stats.py                new (pure derivations)
tests/integration/test_dashboard_stats.py         new
```

Phase 4 additionally renames, across 139 references:

```txt
src/opendlp/domain/assembly_respondent_gsheet.py  -> assembly_export_gsheet.py (+ GSheetExportKind)
src/opendlp/adapters/orm.py                       table rename + export_kind + composite unique
src/opendlp/adapters/database.py, unit_of_work.py, respondent_export_service.py
src/opendlp/entrypoints/blueprints/respondents.py
templates/backoffice/respondents/export_modal.html, templates/backoffice/assembly_data.html
migrations/versions/<new>.py                      hand-written rename migration
tests/conftest.py, tests/bdd/conftest.py          delete-list entries
tests/contract/test_assembly_respondent_gsheet_repo.py -> ..._export_gsheet_repo.py
tests/unit/test_assembly_respondent_gsheet.py, tests/unit/test_respondent_export_service.py
tests/component/test_respondent_export.py, tests/e2e/test_respondent_export.py
```

## 9. Risks

Every open question from revisions 1 and 2 is answered. What is left is execution
risk, in the order it will bite:

- **The Phase 4 migration destroys data if it is autogenerated.**
  `alembic revision --autogenerate` renders a table rename as drop + create, which
  would discard every saved export config. The revision must be hand-written with
  `op.rename_table`, and the generated SQL read before it is run anywhere real.
- **The unified percentage is user-visible.** Anyone who exported a selection
  report from a pre-percentage run and compares it to a fresh export will see the
  target-% column change. Intended, but it needs saying in the commit message
  rather than being discovered.
- **The permission decorator fails open on keyword calls.** Every call site must
  pass `uow, user_id, assembly_id` positionally, and the negative test is what
  proves it — a decorated service with a keyword call site looks entirely correct
  and enforces nothing.
- **The service layer will run ahead of the UI.** `selected_count`,
  `confirmed_count` and the whole export land with no user-facing route. That is
  the agreed scope, but it means the only end-to-end exercise of the export before
  the follow-up ticket is the dev console.
