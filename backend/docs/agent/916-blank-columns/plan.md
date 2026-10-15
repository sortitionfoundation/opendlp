# 916 - Blank columns in uploaded CSVs

Status: **third draft** - all decisions (D1-D12) agreed; ready to implement
once the "report every problem" design below has been reviewed.

## The problem

An uploaded CSV with a column that has no header crashes the upload. The most
common source is a spreadsheet export with trailing empty columns
(`id,name,age,,,` on every line), which the organiser cannot see when they look
at the sheet.

What we want:

1. **Header blank, every data cell blank** - skip the column silently, as if it
   were not in the file.
2. **Header blank, some data present** - reject the upload, with enough
   information to find the column, and tell the organiser to either delete the
   column or give it a header.

Two related changes are now in scope too: duplicate headers, and moving
the errors these uploads raise onto curated messages (`CuratedMessage`) that
are safe to show. See "Other ways a file ends in a generic error" for the
wider survey.

## Where CSV uploads happen

There are four CSV parsing sites. I traced what each does with a blank-header
column today (the targets and mapping behaviour I checked by running the parser
on sample files):

| # | Upload | Parse site | Blank header, blank data | Blank header, with data |
|---|--------|------------|--------------------------|-------------------------|
| 1 | Respondents (import) | `respondent_service.import_respondents_from_csv` (`csv.DictReader`) → `import_respondents_from_rows` | **Crash** | **Crash** |
| 2 | Respondents (schema diff, before the confirm page) | `respondent_field_schema_service._parse_csv_headers` (`csv.DictReader`) | Fine - `compute_reconciliation_diff` skips blank keys | Fine - same |
| 3 | Targets | `target_csv_import.import_targets_from_csv` (`csv.DictReader`) → `sortition_algorithms.features.read_in_features` | Fine - the library ignores headers it does not know | Ignored - the library never reads the column |
| 4 | Large mapping (derived fields) | `derivation_service.upload_large_mapping` (`csv.reader`, positional) | Wrong only if the blank column comes first and the headers don't match by name: the positional fallback takes column 0 as the input, every key is blank, and the result is a mapping with 0 rows | As before - a blank column is just another position |

Entrypoints that reach these:

- `blueprints/respondents.py` - `upload_respondents_csv`, `confirm_upload_diff`,
  `apply_upload_diff` (1 and 2; the stash means the CSV is parsed again on
  confirm/apply).
- `blueprints/respondents_legacy.py` - `upload_respondents_csv` (1).
- `blueprints/targets.py`, `targets_legacy.py`, `dev.py` (3).
- `blueprints/target_sources.py` - `upload_view` (4).

### Why respondents crash

`csv.DictReader` names a blank header `""`, so every row dict carries a `""`
key. `respondent_from_row` copies it into `attributes`, and the `Respondent`
constructor calls `validate_no_field_name_collisions`
(`domain/respondents.py:116`), which raises
`ValueError("Field name '' normalises to an empty string")`. A `ValueError`
is not an `InvalidSelection`, so it falls through to the route's
`except Exception`. The organiser sees **"An error occurred while uploading
respondents"** and we get a stack trace in the logs. The transaction rolls
back, so `replace_existing` has not deleted anything. Nothing is lost, but
there is no hint about what to fix.

Note that the schema side (2) *already* skips blank headers
(`populate_schema_from_headers` line 185, `compute_reconciliation_diff` line
843). So the diff page would happily show a confirmation for a file that
the import then fails on. The import and the diff disagree about what a blank
header means. That disagreement is the case for one shared cleaning step,
used by every upload, rather than each site making up its own rule.

### Related traps in the same code

- **Several blank headers collapse into one key.** `DictReader` builds a dict
  per row, so `id,,name,` has two `""` columns and the row dict keeps only the
  *last* one's value. Data in the first blank column becomes invisible.
  (Verified: `id,,name,` with a value in the first blank column parses to
  `{'id': '1', '': '', 'name': 'a'}` - no exception, the value is just gone,
  while `fieldnames` still lists `''` twice. The targets library then accepts
  the file without complaint.) Any fix that works on `DictReader` output
  cannot reliably tell "blank column" from "blank-header column with data".
  **The check has to run on positional rows, before anything is turned into
  dicts.**
- **Headers that are not blank but normalise to nothing.** `#`, `?`, `---`
  pass a "blank" test but `normalise_field_name` turns them into `""`, and
  the same `ValueError` fires. Handled by the respondent header check (D2).
- **Ragged rows.** A row with *more* cells than the header row: `DictReader`
  puts the extras under the key `None` (its `restkey`), and
  `normalise_field_name(None)` raises `AttributeError`. A row with *fewer*
  cells gets `None` values, and `.strip()` raises `AttributeError`. Both
  produce the generic error. Positionally, an overhanging cell is "a
  blank-header column with data in it", and a short row is padded with blanks.
- **Duplicate headers** (`age,age`) collapse silently in `DictReader` the same
  way. **Now in scope** - see "Duplicate headers" below.
- **Row numbers are wrong whenever the file has blank lines.** `DictReader`
  skips empty lines, but the respondent import numbers rows with
  `enumerate(rows, start=2)`. Verified: with two blank lines before it, the
  respondent in spreadsheet row 5 is reported as "row 3". A line of empty
  *cells* (`,,`, which is how Excel exports a blank row) is *not* skipped, and
  produces "Row N: skipped, empty id". The cleaned table carries each row's
  real row number, which fixes both (see design).

## Other ways a file ends in a generic error

A survey of the four upload routes for file *contents* (not permissions or
not-found) that end in a generic message or a 500. The cases were checked by
running the parsers on sample input; 6 and 7 are inferred from column limits in
`adapters/orm.py`, not run against the database.

How each route handles errors today:

- **Respondents upload** (`respondents.py:164`): `InvalidSelection`, permissions
  and not-found get specific messages; everything else gets "An error occurred
  while uploading respondents".
- **Respondents confirm-diff** (`respondents.py:274`, GET and POST at `:328`):
  catch only `InvalidSelection`, so anything else is a **500**. The POST's
  `finally` has already cleared the stashed upload, so the organiser starts
  again.
- **Respondents (legacy) and targets**: `UnicodeDecodeError` gets a specific
  message; anything else gets "An unexpected error occurred during import".
- **Large mapping** (`target_sources.py:939`): `UnicodeDecodeError` and
  `FieldDefinitionConflictError` get specific messages; there is no catch-all,
  so anything else is a **500**.

| # | Trigger | Where it fails | Organiser sees | Proposed |
|---|---------|----------------|----------------|----------|
| 1 | Not UTF-8 (Excel's Windows-1252 `café`, or UTF-16 "Unicode Text") | `raw.decode("utf-8")` at `respondents.py:197` | Respondents: generic. Others: specific. | **Fix here** - catch it, as the other routes do |
| 2 | UTF-8 with a byte-order mark, ID column typed as `id` | First header becomes `"﻿id"`, so the id-column check fails | A message listing an `id` column that looks right, because the mark is invisible | **Fix here** - decode with `utf-8-sig`, as the legacy route does |
| 3 | Row with more cells than headers | `AttributeError` on the `None` key | Upload: generic. Confirm-diff: 500. Targets: silently ignored. | **Fix here** - covered by the design |
| 4 | Row with fewer cells than headers | `AttributeError` on a `None` value | Upload: generic. Confirm-diff: 500. Targets: "'None' is not a number". | **Fix here** - covered by the design (rows padded) |
| 5 | Headers that collide after normalising (`Age`/`age `, `Email`/`email`), punctuation-only (`???`), or reserved (`external_id`, `comments`, `registration_page_id`, or `id` when another column is the ID) | `ValueError` from `validate_no_field_name_collisions`, raised once per row, never checked up front | Upload: generic. Confirm-diff: 500. | **Fix here** - respondent header check (D2) |
| 6a | A header over 255 characters (`field_key`/`label`), or an ID column name over 100 (`assembly_csv.csv_id_column`) | Database `DataError` on commit; the 100 case fails in `update_csv_config` *after* the import committed | Generic, and in the 100 case the respondents were imported anyway | **Fix here** - respondent header check |
| 6b | A cell value over the column limit (ID or email over 255) | `DataError` on commit | Generic, or 500 on confirm-diff | **Future work** - per-row checks, separate from headers |
| 7 | A NUL byte in a cell | Postgres rejects it on commit | Respondents: generic or 500. Mapping: 500. | **Fix here** - the reader rejects it, naming the row and column |
| 8 | A field over 131,072 characters (usually an unclosed quote in a large file) | `csv.Error` while reading | Respondents/targets: generic. Mapping: 500. | **Fix here** - the reader catches `csv.Error` |
| 9 | Large mapping key or output over 255 characters | `DataError` on commit | 500 | **Future work** |

Problems that don't error at all but go wrong quietly. All are **future work**
except where noted:

- An unclosed quote in a small file swallows the rest of the file into one
  cell. It can't be detected reliably.
- **A respondents file with only a header row deletes every respondent**
  (`replace_existing=True`) and reports "uploaded successfully: 0 imported".
  A targets file with only a header row deletes every target. This is the most
  serious item in the survey, but it is a data-safety question (should an
  upload with zero rows be allowed to replace everything?) rather than a
  parsing one. It has its own issue file:
  [`future_work/empty_upload_replaces_everything.md`](../future_work/empty_upload_replaces_everything.md).

- Targets with capitalised headers (`Feature,Value,Min,Max`) fail with a
  misleading message asking for the *old* column names. **Fixed here** as a
  side effect of the wanted-headers mode, which matches case-insensitively
  (D9).
- `consent=yes` imports as False.

Untranslated or internal-detail messages that reach `str(e)` today:

- "CSV file is empty or has no header row" (`respondent_service.py:184`,
  `respondent_field_schema_service.py:928`) and "CSV file is empty or
  malformed" (`target_csv_import.py:164`) - English. **Replaced here** by the
  tabular-data errors.
- `target_csv_import.py:172` `f"Failed to parse CSV: {e!s}"` passes the
  library's English text through. `translate_sortition_error`
  (`service_layer/error_translation.py`) exists and is not used here. The
  percentage errors (lines 67/69) and the embedded domain `ValueError` text
  (lines 205/224) are English too. See D11.
- `check_id_column_in_headers` is translated and safe to show. **Made
  curated here.**
- The per-row import warnings ("Row 2: skipped, empty id", "Ignored internal
  column...") are untranslated. They are warnings, not exceptions. **Future work.**

The "Future work" items get written up as
`docs/agent/future_work/csv_upload_errors.md` once this plan is agreed.

## Agreed decisions (first round)

- **D1** - Option A: one shared positional cleaning step used by every
  upload. (Options B "respondents only", C "filter the dicts" and D "make the
  domain tolerate it" are rejected. C can't be made correct because the
  data is already gone. D turns data loss into a silent outcome.)
- **D2** - "Blank" means empty or whitespace only, for the skip/reject rule.
  Respondent headers that normalise to nothing (`#`, `?`) get their own clear
  message from the respondent header check.
- **D3** - Targets use a "wanted headers" variant: only columns the targets
  import reads are looked at, and everything else, including blank-header
  columns with comments in them, is ignored as it is today. See the design.
- **D4** - The large mapping is in scope.
- **D5** - Ragged rows are in scope (both too long and too short).
- **D6** - No extra guard in `import_respondents_from_rows`; add a comment
  noting that a future Sheets/xlsx import must go through the tabular-data
  cleaning first.
- **D7** - Skipped blank columns are dropped silently; log a count at debug
  level.
- Duplicate headers are in scope.

## Design

### `service_layer/tabular_data.py`

The pipeline is split into **reading** (source-specific, producing a list of
lists) and **cleaning** (source-independent). Supporting Google Sheets or an
uploaded xlsx later means writing a new reader. Google Sheets already gives
`list[list[str]]` from `worksheet.get_all_values()`, and the sortition library
handles sheets that way in `find_header_row` / `get_valid_people_rows`. The
cleaning, and every check in this plan, comes for free.

```python
def rows_from_csv(csv_content: str) -> list[list[str]]:
    """Read CSV text into a list of rows, the first being the header row.

    Raises TabularDataError for content the csv module cannot read (csv.Error,
    e.g. an over-long field from an unclosed quote) or for a NUL byte, naming
    the row.
    """


@dataclass(frozen=True)
class Column:
    header: str  # stripped
    position: int  # 0-based position in the source, counting dropped columns

    @property
    def letter(self) -> str: ...  # "A", "Z", "AA" - what a spreadsheet shows


@dataclass(frozen=True)
class Table:
    columns: list[Column]
    rows: list[list[str]]  # aligned with `columns`, one per non-blank data row
    row_numbers: list[int]  # the spreadsheet row of each entry in `rows`

    @property
    def headers(self) -> list[str]: ...

    def as_dicts(self) -> list[dict[str, str]]: ...


def clean_table(raw: list[list[str]]) -> Table:
    """Every column counts (respondents, large mapping)."""


def select_columns(raw: list[list[str]], wanted: Iterable[str]) -> Table:
    """Only columns whose header is in `wanted` count (targets)."""
```

Both cleaning functions do the following in order:

1. Treat the first row as headers and strip them. An empty `raw`, or one
   with no non-blank header, raises "the file is empty or has no header row".
2. Pad every row, the header row included, to the widest row. Overhanging
   cells become blank-header columns (too-long rows), and short rows get
   blank cells (too-short rows).
3. Drop rows where every cell is blank, keeping the original row number for
   each row that remains. Row numbering is spreadsheet rows: the header is row
   1, and *records*, not physical lines, are counted, so a quoted cell with a
   newline in it doesn't shift the count.
4. Apply the column rules for the mode (below), then any header checks the
   caller passed in, collecting **every** problem and raising one
   `TabularDataError` that lists them all. See "Reporting every problem".

**`clean_table` - all columns:**

- Blank header, every cell blank: drop the column.
- Blank header, some data: reject. Name the letter, the neighbouring headers,
  and the first row with data.
- The same header twice or more (exact match after stripping): reject. Name
  the header and every letter it appears at.

**`select_columns` - wanted headers only:**

- Headers are matched against `wanted` case-insensitively after stripping
  (D9), and the returned `Column.header` is the canonical name from `wanted`.
- Columns that don't match, including blank-header ones with or without
  data, are ignored. They are not part of the returned table and are never
  checked.
- A wanted header appearing twice or more: reject, as above.
- A wanted header that is *missing* is not checked here. Which headers are
  required is the caller's knowledge: targets accept `feature/value` *or*
  `category/name`, and the flex columns are optional. The library already
  reports missing required columns. See D10.

### Reporting every problem

Every check adds to one list of problems rather than raising, and the list is
raised once, as one `TabularDataError`, at the end. An organiser with three
bad columns fixes them in one round trip rather than three.

To make that work across the generic and the respondent-specific checks,
the respondent checks do not run *after* `clean_table` (which would mean a
file with a blank-header column never got its duplicate `Email`/`email`
reported). They are **passed in**:

```python
HeaderCheck = Callable[[list[Column]], list[TableProblem]]

def clean_table(raw: list[list[str]], header_checks: Sequence[HeaderCheck] = ()) -> Table: ...
def select_columns(raw: list[list[str]], wanted: Iterable[str], header_checks: Sequence[HeaderCheck] = ()) -> Table: ...
```

The header checks run on the columns that have a header, **even when the
column rules have already found problems**. They don't need the bad columns
removed first: a blank-header column is never handed to them, and a
duplicate header is just two columns with the same name.

Problems are reported **per column, not per cell**, so the list stays
bounded by the width of the file however many rows there are. For example, a
blank-header column with data is reported once, with the first row that has
data. A NUL byte is reported once per column, with the first row it appears in.

What stops the checks early, because nothing after it makes sense:

- **`csv.Error` while reading** (malformed quoting, an over-long field). The
  csv module can't resume after it, so there are no rows to check. This
  reports the row the reader had reached.
- **An empty file, or one with no non-blank header.** There are no columns
  to check.

Everything else is collected: blank headers with data, duplicate headers,
NUL bytes, and every respondent header problem, including the ID column not
being found (`check_id_column_in_headers` becomes one of the respondent
header checks rather than a separate raise).

### Duplicate headers

Exact duplicates are caught generically above. Respondents also need to
catch headers that are different strings but the *same field* once
normalised (`Age` and `age `, `Email` and `email`). That is the domain's
`normalise_field_name` rule, so it belongs in the respondent header check
below, not in the generic cleaner, which knows nothing about field names.
Its message names both columns by letter.

For the large mapping, the headers matched against the source and derived
field keys are compared normalised. `normalised.index()` takes the first of
two matching columns today. With `clean_table` the exact case is rejected. A
normalised near-duplicate (`Postcode`, `postcode`) would still pick the first.
That is acceptable for a two-column file and isn't worth a special rule.

### The respondent header check

This is a new function in `respondent_field_schema_service.py` (next to
`check_id_column_in_headers`). It is a `HeaderCheck`: it takes the
columns, so every message can cite a column letter, and returns its problems
rather than raising. Both `compute_diff_for_pending_csv` and
`import_respondents_from_csv` pass it to `clean_table`, so the diff page and
the import can't disagree again. It is built per upload (a small factory
taking the ID column and the previous ID column), because the reserved-name
and ID-column rules depend on which column is the ID. It reports:

- the ID column not being one of the headers - today's
  `check_id_column_in_headers` message, including the "pre-filled from your
  last upload" hint;

- a header that normalises to nothing (`#`, `???`) - "Column D's header '#'
  has no letters or numbers in it. Rename it.";
- two headers that normalise to the same field - "Columns B ('Age') and F
  ('age') would be the same field. Rename or delete one.";
- a non-ID header that collides with a reserved respondent field;
- a header longer than the 255-character field limit, or an ID column name
  longer than 100.

These are the up-front versions of what `validate_no_field_name_collisions`
already enforces, so the domain check stays as the last line of defence. If it
ever fires on an upload path, that is a bug in this check.

### Errors

```python
class TabularDataError(CuratedMessage, InvalidSelection):
    """A problem with the shape of an uploaded table, written for the organiser."""
```

- It subclasses `InvalidSelection`, so every existing upload handler that
  catches `InvalidSelection` catches it without change. The large-mapping
  route doesn't catch `InvalidSelection`; it gets a clause added.
- The respondent header problems go into the same `TabularDataError`, with
  no separate class: one class for "your file's shape is wrong", and the
  respondent checks are still about the shape of the file.
- `check_id_column_in_headers` keeps its current signature for any other
  callers. Its check moves into the respondent header check, which reports
  through `TabularDataError` and so is curated.
- Messages are built with `_()` / `_l()` and named parameters, in the
  constructor, as `UserAlreadyExists` does.
- The exception also carries its problems as structured data (a list of
  small dataclasses: kind, letter, header, row). Tests can then assert on
  the data rather than on translated text, and a future JSON endpoint can use
  them.
- Routes flash `e.user_msg()` for these rather than `str(e)` (D11).

### Identifying the column

The organiser opens the file in Excel, Sheets or LibreOffice to fix it, so
messages use what they see there. `docs/language.md` already calls them
"columns".

- **Spreadsheet column letter** (`C`, `AB`), counted in the original file
  *including* any dropped blank columns, so it matches the sheet.
- **The headers on either side**: "between 'name' and 'age'". At the edges it
  becomes "after 'age'" or "before 'id'".
- **The first row with data in it**, as a spreadsheet row number.

> Column C (between 'name' and 'age') has no header but has data in it,
> starting at row 4. Delete the column, or give it a header.

With several problems, a lead line then one line per problem:

> There are 2 problems with the columns in this file:
> Column C (between 'name' and 'age') has no header but has data in it, starting at row 4. Delete the column, or give it a header.
> The header 'email' appears in columns B and G. Delete one of them, or rename it.

**Deliberately not included: a sample of a cell's value.** The routes log the
exception text, and respondent cells are personal data. `censor_pii` catches
emails but not names or dates of birth.

### Callers

- `import_respondents_from_csv`: `rows_from_csv` → `clean_table(raw,
  header_checks=[respondent header check])` →
  `import_respondents_from_rows(headers, table.as_dicts())`.
  `import_respondents_from_rows` takes the row numbers too, so its per-row
  warnings report real spreadsheet rows.
- `_parse_csv_headers` / `compute_diff_for_pending_csv`: the same first two
  steps, with the same header check, so the diff page rejects the file *before* offering a confirmation.
  The stash is already cleared on `InvalidSelection`.
- `import_targets_from_csv`: `rows_from_csv` → `select_columns(wanted)`, where
  `wanted` is the library's `ALL_FEATURE_FIELD_NAMES`, its value-column aliases
  (`category value`, `category_value`, `category-value`), and our four
  extras (`percentage`, `comment`, `category_comment`, `source_url`). The
  library gets canonical lowercase headers. This also replaces the
  case-insensitive `columns` lookup in `_collect_csv_extras`.
- `upload_large_mapping`: `rows_from_csv` → `clean_table`, then work with
  `table.rows` positionally. Its row cap stays, and is applied to
  `table.rows`. It loses the "stop parsing after cap + 2 rows" shortcut, since
  the whole file is read first. The upload size cap (`MAX_CSV_UPLOAD_MB`)
  already bounds that.
- Respondents route: decode with `utf-8-sig` and catch `UnicodeDecodeError`
  (survey 1, 2).
- Confirm-diff GET/POST: give them the same handler shape as the upload route
  (specific `InvalidSelection`, generic catch-all with logging), so they stop
  returning 500.

## Agreed decisions (second round)

- **D8** - Develop in OpenDLP. The module has no OpenDLP imports apart from
  the exception and translations, so the generic part could move to
  sortition-algorithms later. If it does, its messages would be translated
  through `error_code` + `error_params`, like the library's other errors.
- **D9** - Targets match wanted headers case-insensitively after stripping, and
  hand the library the canonical names, so `Feature,Value,Min,Max` works. A
  file with both `min` and `Min` is now rejected as a duplicate.
- **D10** - `select_columns` doesn't check for missing required headers.
  The library already does, and "required" isn't a simple set for targets.
- **D11** - The respondents and mapping routes flash `e.user_msg()`. The
  targets routes keep `str(e)` for now, so their existing English messages
  don't become generic. `TabularDataError` is curated, so it shows properly
  on every route either way. Translating the targets errors (library
  messages via `translate_sortition_error`, percentage and domain errors) is
  future work.
- **D12** - The upload with no data rows that replaces everything is a separate
  issue: [`future_work/empty_upload_replaces_everything.md`](../future_work/empty_upload_replaces_everything.md).

## Out of scope

- The items marked **Future work** in the survey table, the quiet-failure
  list and the per-row warnings. They go to
  `docs/agent/future_work/csv_upload_errors.md`.
- Google Sheets data sources - they go through the sortition library, not
  these parsers. Note for later: gspread's `get_all_records()` *raises* on
  duplicate headers, two blank ones included. The library works around it with
  `expected_headers=[]` (`sortition_algorithms/adapters.py:684`). So for a
  Sheets source a pair of blank columns crashes rather than silently losing
  data like the CSV reader does. A future Sheets respondent import should read
  `get_all_values()` and go through `tabular_data` instead.

## Testing

- **Unit** (`tests/unit/test_tabular_data.py`), for the pure functions:
  - `rows_from_csv`: `csv.Error` and NUL bytes become `TabularDataError` with
    the row; quoted newlines are fine.
  - `clean_table`: trailing blank columns dropped; a blank column in the middle
    dropped; two blank columns, both empty, both dropped; two blank columns
    with data only in the *first* (the collapse trap: a dict-based parser loses
    it) and, separately, only in the *second*, each rejected with the right
    letter; the error names letter, neighbours and first row; several problems
    reported together; letters past `Z` (`AA`, `AZ`, `BC`); a too-long row
    rejected as a blank-header column; a too-short row padded; whitespace-only
    cells count as blank; blank lines and `,,` lines dropped and later row
    numbers stay right; header-only file; empty file; exact duplicate headers
    rejected with every letter.
  - Reporting every problem: a file with a blank-header column with data, a
    duplicate header *and* a NUL byte gets all three in one error; a header
    check passed in still runs, and its problems are added, when the column
    rules have already found problems; `csv.Error` stops early and reports the
    row; a NUL byte in many rows of one column is reported once.
  - `select_columns`: unwanted columns ignored, including blank-header columns
    with data; case-insensitive matching returns canonical names; a duplicate
    wanted header is rejected; an unwanted duplicate is ignored.
  - The respondent header check: ID column missing (with and without the
    pre-filled hint), punctuation-only, normalised collision, reserved name,
    over-long header and over-long ID column name, each with the right
    letters, and several of them reported together.
  - The error class: `user_msg()` returns the curated message.
- **Integration** (`tests/integration/`), at the service layer with a real uow:
  - `import_respondents_from_csv` imports a file with trailing blank columns,
    and no `""` attribute or schema field appears;
  - it rejects a blank header with data, and `replace_existing` leaves
    existing respondents in place;
  - its per-row warnings report the right row after blank lines;
  - `compute_diff_for_pending_csv` raises for the same files;
  - targets: a blank-header comments column is ignored, `Feature,Value,Min,Max`
    imports, and a duplicate `min` is rejected;
  - mapping: a leading blank column no longer produces an empty mapping, and a
    duplicate header is rejected.
- **E2E**:
  - respondents upload: the flash names the column letter and the guidance;
  - confirm-diff: a bad file no longer returns 500;
  - a BOM'd file with `id` typed as the ID column imports;
  - a Windows-1252 file gets the specific encoding message;
  - targets upload: the success path with a blank comments column;
  - mapping upload: the error is shown in the modal.
- Check the convention in `tests/csv_fixtures/` before adding file fixtures;
  inline strings may be clearer for these small cases.

## Implementation sketch

- [x] 1. `tabular_data.py` (reader, `Table`, `clean_table`, `select_columns`,
   `HeaderCheck`, error) + unit tests, TDD.
- [x] 2. Respondent header check + unit tests.
- [ ] 3. Switch respondents import and the diff to the pipeline; row numbers
   through to warnings; `utf-8-sig` and `UnicodeDecodeError` on the route;
   confirm-diff handlers; `user_msg()`. Integration and e2e tests.
- [ ] 4. Targets via `select_columns`; integration and e2e tests.
- [ ] 5. Large mapping via `clean_table`; route handler; integration and e2e tests.
- [ ] 6. Write `docs/agent/future_work/csv_upload_errors.md`.
- [ ] 7. `translate-catalogues`, `just check`, `just test-nobdd`, then BDD.
