# Uploaded CSVs that still end in a generic error, or go wrong quietly

## Background

Issue 916 (blank columns in uploaded CSVs) added `service_layer/tabular_data.py`:
every CSV upload is read into a list of rows and cleaned before it is used,
and problems with the *columns* are reported together, by spreadsheet column
letter, in a curated `TabularDataError`. See
[`916-blank-columns/plan.md`](../916-blank-columns/plan.md).

The survey made for that issue found other ways a file's contents end in a
generic message, a 500, or a silently wrong result. The ones about
columns and headers were fixed there. These are the ones left.

A separate, more serious problem has its own file:
[`empty_upload_replaces_everything.md`](empty_upload_replaces_everything.md).

## Cell values too long to store

| Upload | Trigger | What happens |
| --- | --- | --- |
| Respondents | An ID or email cell over 255 characters (`respondents.external_id`, `respondents.email`) | Database `DataError` on commit. The upload route shows "An error occurred while uploading respondents"; the confirm-diff POST shows the same. |
| Large mapping | A lookup key or output value over 255 characters (`respondent_field_mapping_entries`) | `DataError` on commit; the route has no catch-all, so a 500. |

Headers that are too long are now caught up front (`respondent_header_check`).
Cell values are not, because they are a per-row problem.

Possible fix: check lengths in the row loop. For respondents, skip the row
with a warning ("Row 7: skipped, the id is longer than 255 characters"),
like an empty ID. For the mapping, reject the file and name the rows, because
a lookup table with rows silently missing is worse than no upload.

## Quiet failures

- **An unclosed quote in a small file** swallows the rest of the file into one
  cell. The csv module only fails when that cell passes its 131,072-character
  limit, which `rows_from_csv` now reports. Below that, the file parses
  "successfully" with fewer rows than expected. This can't be detected
  reliably. A heuristic (a cell containing several newlines and commas) could
  warn.
- **`consent=yes` imports as False.** `respondent_from_row` treats only `true`
  (any case) as true for `consent`, `eligible`, `can_attend` and `stay_on_db`.
  `yes`, `y` and `1` all become False without a word. Either accept the common
  spellings or warn about values that are neither true nor false.

## Messages that are not translated

- **Targets import errors.** `import_targets_from_csv` wraps the library's
  error as `f"Failed to parse CSV: {e!s}"`. That is English, and sometimes
  internal (`'None' is not a number`). The percentage errors (`_parse_percentage`)
  and the domain `ValueError` text it embeds ("min cannot be negative") are
  English too. The targets routes still flash `str(e)` so these messages are
  not replaced by the generic one (decision D11 in the 916 plan).
  `translate_sortition_error` (`service_layer/error_translation.py`) already
  translates library errors by `error_code`. Use it here, wrap the rest in
  curated errors, and then switch the targets routes to `e.user_msg()`.
- **Per-row respondent import warnings** ("Row 2: skipped, empty id", "Row 3:
  skipped duplicate id: …", "Ignored internal column not imported: …") are
  built in `import_respondents_from_rows` without `_()`.
