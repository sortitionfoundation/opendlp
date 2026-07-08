# Respondent Export

Organisers can export an assembly's respondents from the Respondents page via
the **Export** button, which opens a modal (loaded with HTMX).

## Destinations

- **CSV download** — generated in memory and streamed as an attachment. No file
  is written to disk or long-term storage, consistent with the GDPR
  requirements in `CLAUDE.md`.
- **Google Sheets** — written into a worksheet of an existing spreadsheet via
  `gspread`, using the same service account as the selection Google Sheets
  workflow. The organiser supplies the spreadsheet URL and worksheet name; these
  are saved to the `AssemblyRespondentGSheet` model and pre-filled on later
  exports. The service account must have edit access to the sheet (share it with
  the service-account email shown in the modal).

## Filtering

Exports cover either all respondents, a single `selection_status`, or the
combined `SELECTED`-or-`CONFIRMED` set. `DELETED` respondents are never
exported.

## Columns

The export is the richer inverse of CSV import:

1. the id column (the assembly's configured `csv_id_column`, else `external_id`);
2. every field in the assembly's field schema, in schema order (fixed fields,
   attributes and derived fields);
3. any leftover attribute keys not in the schema, sorted;
4. internal columns: `selection_status`, `source_type`, `selection_run_id`,
   `created_at`, `updated_at`.

## Re-importing an exported file

CSV import recognises and skips the internal columns above, so an exported file
re-imports cleanly (skipped columns are reported in the import status). A fresh
import always lands respondents in `POOL`. `stay_on_db` is honoured when
creating a new record but must never be silently overwritten on an existing one.

## Design

The export machinery lives behind an abstract target so CSV and Google Sheets
share the same tabular-data builder:

- `service_layer/respondent_export_service.py` — `build_respondent_table`,
  `resolve_status_filter`, `export_respondents`, `export_respondents_to_gsheet`.
- `adapters/tabular_export.py` — `TabularData`, `AbstractTabularExportTarget`,
  `CsvExportTarget`, `ExportTargetError`.
- `adapters/gsheet_export.py` — `GSheetExportTarget` (gspread).

The two targets are wired differently on purpose. The **CSV target is
constructed inline** in the blueprint: it is pure in-memory work with no external
service, so it is fully exercised by the normal tests and needs no seam. The
**Google Sheets target is injected** through an app factory
(`gsheet_export_target_factory`, registered in `flask_app.py`): writing to it
calls the real Google Sheets API, so tests override the factory with
`FakeGSheetExportTarget` (in `tests/fakes.py`) and no real Google access is
needed.

When a Google Sheets write fails — most commonly because the sheet has not been
shared with the service account — `GSheetExportTarget` raises `ExportTargetError`
(wrapping the underlying `gspread` exception) so the blueprint can flash a
controlled "share the sheet with …" message instead of returning a 500.
