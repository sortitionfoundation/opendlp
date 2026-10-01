# Merging 907-not-shared-message with 1029-auto-export

Both branches fork from main at `c43ad61d` and both edit
`src/opendlp/adapters/gsheet_export.py`, its unit tests, and the research
docs. Whichever lands second will conflict in the adapter. This file says how
to resolve it so the result keeps what each branch is for.

## What each branch did to the export adapter

| Concern | 907 | 1029 |
| --- | --- | --- |
| Building the gspread client | `make_gsheet_client()` from sortition-algorithms, with `http_client=gspread.HTTPClient` and the 20s timeout by default; `background=True` gives the back-off client and 120s | `gspread.service_account()` with a `timeout_seconds` argument; 120s for the task |
| Opening the sheet | `open_gsheet(client, url)` then `info.require_writable()`, so not-found, not-shared, read-only and `.xlsx` are classified | `client.open_by_url()` |
| Writing | unchanged: `clear()` then `update()` | write first, then `batch_clear()` the stale ranges via `_stale_ranges()` (D6 in the 1029 plan) |
| Error wrapping | `except (SelectionError, GSpreadException, PermissionError)` keeping the cause | `except GSpreadException` |
| Constructor | `client_factory: Callable | None = None`, `background: bool = False` | `client_factory: Callable | None = None`, `timeout_seconds: int = GSPREAD_TIMEOUT_SECONDS` |
| Constants | `GSPREAD_TIMEOUT_SECONDS = 20`, `GSPREAD_BACKGROUND_TIMEOUT_SECONDS = 120` | same two names, same values |

## Resolution

Take 907's client factory and open/error handling, take 1029's write path.
Concretely, the merged `gsheet_export.py` has:

- 907's imports: `make_gsheet_client`, `open_gsheet`, `SelectionError`, plus
  1029's `rowcol_to_a1`. Both need `import gspread`.
- 907's `_default_client_factory(background: bool = False)`. Drop 1029's
  version that calls `gspread.service_account()`; the whole point of 907 was
  one credential stack and a fail-fast client in requests.
- 1029's `_stale_ranges()` unchanged.
- Constructor: `client_factory`, `background`. Drop `timeout_seconds`; the
  flag chooses the timeout.
- `write_sheet()`:

  ```python
  values = [table.headers, *table.rows]
  try:
      client = self._client_factory()
      info = open_gsheet(client, self.spreadsheet_url)      # 907
      info.require_writable()                               # 907
      spreadsheet = info.spreadsheet
      try:
          worksheet = spreadsheet.worksheet(title)
      except WorksheetNotFound:
          worksheet = spreadsheet.add_worksheet(title=title, rows=_DEFAULT_ROWS, cols=_DEFAULT_COLS)
      worksheet.update(values)                              # 1029
      stale = _stale_ranges(worksheet, len(values), len(table.headers))
      if stale:
          worksheet.batch_clear(stale)
      self.result_url = worksheet.url
      self.result_title = spreadsheet.title
  except (SelectionError, GSpreadException, PermissionError) as exc:   # 907
      raise ExportTargetError(str(exc) or str(exc.__cause__)) from exc
  ```

  Keep 907's comments on the `except` (why `PermissionError`, why the cause is
  kept) and 1029's docstring on write-then-trim.

## Other files

- **`entrypoints/celery/tasks.py`** (1029): `_background_gsheet_export_target_factory`
  becomes `GSheetExportTarget(spreadsheet_url=spreadsheet_url, background=True)`
  and the `GSPREAD_BACKGROUND_TIMEOUT_SECONDS` import goes. 907 also changed
  this file (the title check in `_internal_load_gsheet`, `manage_old_tabs`,
  `_gsheet_api_error_message`); those hunks are in different functions and
  should merge cleanly.
- **`tests/unit/test_gsheet_export.py`**: both branches rewrote the fakes.
  Take 907's `_FakeClient` / `_FakeHTTPClient` (they satisfy `open_gsheet`:
  `http_client.request()` and `open_by_key()`), then add 1029's
  `row_count` / `col_count` / `batch_clear()` to 907's `_FakeWorksheet` so the
  trim tests run. Keep 907's `TestDefaultClientFactory` (web vs background)
  and drop 1029's `test_sets_timeout_on_gspread_client` and
  `test_target_passes_its_timeout_to_the_client`, which test the removed
  factory. Keep all of 1029's trim tests and all of 907's classification
  tests.
- **`entrypoints/gsheet_export_flow.py`** (907): flashes the translated
  library message when `ExportTargetError.__cause__` is a `SortitionBaseError`.
  The 1029 task logs `str(e)` on each retry; that string is now the library's
  message for classified failures, which is what you want in the log.
- **`docs/agent/1029-auto-export/plan.md`**: the "Future work" section was
  written when the one-off export used the back-off client. After 907 the
  web request fails fast, so the first bullet under "Why" is weaker; the
  quota and lock point still stands. Trim it or leave it, your call.
- **Translations**: both branches regenerated `translations/hu/LC_MESSAGES/messages.po`.
  Resolve by running `just translate-regen` after the merge rather than
  hand-merging the catalogue, then `just translate-check`.
- **`docs/agent/907-not-shared-message/research.md`**: the status section
  says the 1029 task "should pass that flag"; once it does, say so.

## After resolving

```bash
just check
just test-nobdd && just test-bdd-headless
```

Plus one manual run of a background export against a sheet shared read-only:
the task should log the library's read-only message and retry no more than
the configured three times, since `SpreadsheetReadOnlyError` arrives wrapped
in `ExportTargetError`, which is in `autoretry_for`. Consider whether a
classified permanent failure (not shared, read-only, not native) should skip
the retries; that is the "switch off after permanent failure" follow-up from
D4 in the 1029 plan, and the cause's `error_code` now makes it easy.
