# A slow Google API can outlast the gunicorn timeout during a Google Sheets export

## Background

Exports to Google Sheets started from the web (the dashboard report and the
respondents export, both via `entrypoints/gsheet_export_flow.py`) call the
Google API inside the request. `adapters/gsheet_export.py` gives that client a
timeout so a stalled Google API "fails before the gunicorn worker timeout":

```python
GSPREAD_TIMEOUT_SECONDS = 20
```

Production runs gunicorn with `gthread`, 3 workers × 3 threads and
`timeout=60`. (None of this is in the repo: `gunicorn.conf.py` sets no
workers or timeout.)

Found while designing the Google Sheets access check for the Assembly Data
page, which has the same budget to fit in.

## The problem

gspread's timeout applies to **each HTTP request**, not to the export as a
whole. `GSheetExportTarget.write_sheet()` makes several requests:

| Step | Request | When |
| --- | --- | --- |
| `open_gsheet()` | Drive file metadata | always |
| `open_gsheet()` → `open_by_key()` | Sheets metadata | always |
| `spreadsheet.worksheet(title)` | Sheets metadata, again | always |
| `add_worksheet()` | batchUpdate | new tab only |
| `worksheet.update(values)` | values update | always |
| `worksheet.batch_clear(stale)` | values batchClear | when the old tab was bigger |

Not shown: the OAuth token exchange, which happens before the first request
when the client is new. Whether gspread's timeout covers it has not been
checked.

That makes 4 to 6 requests at up to 20s each: **80 to 120 seconds in the
worst case, against a 60 second worker timeout.** The ordinary case is a few
seconds. It goes wrong only when Google is slow, which is when a clean error
matters most.

It is worse than that sum, because a `requests` read timeout limits the
**gap between bytes received**, not the total time. A large `update()` whose
response comes back slowly but steadily is not limited at all.

## What happens when it goes wrong

- gunicorn kills the worker thread at 60s. The user sees an error from the
  reverse proxy, not the "Could not write to the spreadsheet" flash.
- The export may be half done. `write_sheet()` writes before clearing, so the
  worst case is fresh data with stale rows still below it, not an empty tab.
  The user is not told.
- The export callables open `with uow:` around the export, so a database
  connection stays checked out for the whole wait.

## Possible fixes

Not decided. Roughly in order of effort:

1. **Shorter timeouts for each request**, e.g. `(3.05, 8)` for connect and read.
   The worst case is still about 6 × 11s = 66s, so this only shrinks the problem.
   And it does nothing for a slow but steady response.
2. **One deadline for the whole export.** `write_sheet()` starts a clock, and
   before each call it sets the client's timeout to the time remaining (or
   gives up with an `ExportTargetError` once it runs out). This needs
   `client.set_timeout()` between calls, which gspread supports. It gives a
   real limit, such as 40s, and a clean flash instead of a killed worker.
3. **Fewer requests.** The `worksheet(title)` lookup fetches the metadata again,
   right after `open_by_key()` fetched it. If `open_gsheet()` kept the tab list
   (`GSheetInfo` in sortition-algorithms), the lookup could be dropped. That
   saves one request, but doesn't fix anything on its own.
4. **Run web exports in Celery**, as the 1029 auto-export already does with
   `GSheetExportTarget(background=True)`. This removes the worker timeout from
   the picture, but changes the UX from "flash on redirect" to a task and
   polling. Worth it only if large exports are routinely slow.

2 is the smallest change that actually guarantees a time limit, and 3 goes
naturally with it. Whatever is chosen, measure real export times first,
including a large respondents export.
