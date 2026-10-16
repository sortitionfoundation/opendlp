# 974 - Check access to a Google Sheet when its URL is saved

Status: **spec, reviewed** - nothing implemented yet.

## The problem

An organiser pastes a Google Sheets URL on the Assembly Data page and saves.
Nothing checks the URL. They find out it is wrong, not shared with the service
account, or shared read-only only when they press "Check Spreadsheet" or run
a selection, several pages later. By then the error is a long way from the
place where it can be fixed.

Issue 907 built the pieces needed to classify these failures (see
[`history/907-not-shared-message/research.md`](../history/907-not-shared-message/research.md),
section 3, "A preflight check on the Assembly data page"). This spec puts them
on the page where the URL is entered.

What we want, after saving the Google Sheets configuration:

1. The sheet's **title**, so the organiser can see it is the sheet they meant.
   No error can catch a valid, shared URL for the wrong sheet.
2. A **specific message** when the sheet cannot be used: not found, not
   shared (naming the service account email), read-only, or not a native
   Google Sheet.
3. A **warning for each tab named in the configuration that the sheet doesn't have**.
4. All of it **without making the save slow**, and without using up the
   Google API quota that selections share.

Out of scope: checking columns, targets or data. The existing "Check
Spreadsheet" Celery task does that, and it is slow because it reads cell
data.

## Decisions (Chewie, 2026-10-16)

- **Saving is never blocked by the check.** The save stores the configuration
  exactly as it does now. Even "not found" is a warning shown afterwards, not
  a form error. The fix for "not shared" is in Google, and a Google outage
  must not stop someone saving.
- **The check runs in a separate HTMX request**, not inside the save request.
  The page loads straight away and the status panel shows a spinner until the
  result arrives.
- **Not Celery.** A check takes about 1-1.5s (see "Measurements"). A task, run
  record and polling would add more than they save.
- **Check on save, plus a "Check again" button.** Not on every page view, and
  not on each keystroke or when the field loses focus.
- **The result is cached in Redis for a short time, never stored in the
  database.** Access can change in Google at any moment, so a stored result
  would go stale and then be wrong.
- **Two-part timeout `(3.05, 8)`**, with a comment explaining it.
- **Only assembly managers can trigger a check** (`can_manage_assembly`).
- **An explicit check never reads the cache.** The cache only serves page
  views that didn't ask for a check.

## Measurements

Measured 2026-10-16 against the real API with the `demo-server@` service
account. Each check used a new client that doesn't retry (`gspread.HTTPClient`) and did
`open_gsheet()` then `spreadsheet.worksheets()`, the shape this spec
proposes before the library change. About 70 checks in total.

| Sheet                             | Result                      | Median | Max   | Requests |
| --------------------------------- | --------------------------- | ------ | ----- | -------- |
| Large, shared as Editor (15 tabs) | OK, `can_edit=True`         | 1.43s  | 1.95s | 3        |
| Small, shared as Editor (8 tabs)  | OK, `can_edit=True`         | 1.19s  | 2.53s | 3        |
| Shared as Viewer (19 tabs)        | OK, `can_edit=False`        | 0.97s  | 1.46s | 3        |
| Exists, not shared                | `SpreadsheetNotSharedError` | 0.81s  | 4.51s | 2        |
| Does not exist (made-up id)       | `SpreadsheetNotFoundError`  | 0.80s  | 1.22s | 2        |

Findings:

- **Sheet size barely matters.** The check reads metadata, never cells. The
  `> 10s` seen when loading a selection is spent reading data, which the
  check never does.
- **The slowest single request was 4.17s** (a Drive metadata call that would
  normally take 0.3s). That is why the read timeout is 8s and not 5s.
- **We hit Google's per-minute read quota.** About 30 checks in 35 seconds
  got `APIError [429]: Quota exceeded for quota metric 'Read requests'`.
  Google's documented default for the Sheets API is 60 read requests per
  minute _per user_. Every Google call OpenDLP makes, from selections,
  "Check Spreadsheet", exports and this check, uses the same service
  account, so they all share that one per-user budget. This is the real
  constraint on the design, more than speed.

## How it works

### The flow

```
Save (POST /assembly/<id>/gsheet/save)           unchanged, plus: drop the cached result
   -> redirect to Assembly Data, view mode, with ?check=1
        -> page renders; status panel sees check=1 and fires
           hx-post .../gsheet/check  (hx-trigger="load")
             -> route: permission check + read config (with uow), close uow
             -> check against Google (no uow open)
             -> store result in Redis, render the panel fragment
```

Later visits to the Assembly Data page, without `?check=1`:

- **Cached result** for this assembly _and the current URL_: render it
  directly in the page, with the time it was checked and a "Check again"
  button. No Google call.
- **Nothing cached**: render a "Check access" button and nothing else. No
  Google call until someone presses it.

"Check again" and "Check access" post to the same route, and the response
replaces the panel.

**The route never reads the cache.** Every request to it is a fresh check
against Google, and its result overwrites the cache. That includes the
check fired by `?check=1` after a save. The cache is read in one place
only: when the Assembly Data page renders without `?check=1`, to show the
last result to someone who is just passing through. So the cache can never
make an explicit check out of date. An organiser who sees "not shared", goes
to share the sheet and presses "Check again" always gets a new answer.

The quota risk from someone pressing "Check again" repeatedly is small. The
button is disabled while a check is running (`hx-disabled-elt`), so each check
takes at least the 1-1.5s a round trip takes. One person clicking as fast as
the button allows would make about 40-60 Sheets reads a minute before the
library change (2 per check), and half that after it. Not enough to justify
rate limiting the button, but the per-check log line (see "Logging") would show
it if it ever happens.

`?check=1` means reloading the page straight after a save checks again. That
is acceptable: someone chose to reload. A one-shot flag in the session would
avoid it, but costs more code for little gain.

### The route

`POST /assembly/<uuid:assembly_id>/gsheet/check`, in the `gsheets` blueprint,
returning an HTML fragment (the panel), not JSON.

- **POST, not GET.** It uses up quota and writes the cache, and a GET could be
  prefetched or followed by a crawler. HTMX sends the CSRF token, as the
  existing `hx-post` uses in `templates/targets/` do.
- **Permission: `can_manage_assembly`**, the same as saving the
  configuration. Anyone who can view the page sees the cached result.
- **The UnitOfWork is closed before the Google call.** Following the convention
  that only entrypoints open `with uow:`, the route opens one context to check
  permission and read the URL and tab names, closes it, _then_ calls Google.
  Holding a database connection open for up to 40 seconds of waiting is exactly
  what the export route does today (see
  [`future_work/gsheet_export_timeout.md`](../future_work/gsheet_export_timeout.md)).
- **No service account configured** (`get_service_account_email()` is
  empty): return the panel saying the check is unavailable. Don't build a
  client.

### Where the code goes

| Piece                               | Location                                                          | Notes                                                                                                           |
| ----------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Client factory and timeout constant | `adapters/gsheet_access.py` (new)                                 | `make_gsheet_client(..., request_timeout=GSHEET_CHECK_TIMEOUT, http_client=gspread.HTTPClient)`                 |
| The check itself                    | `service_layer/gsheet_access_check.py` (new)                      | Takes a client, a URL and the tab names, and returns a `GSheetAccessResult`. No uow, no Flask.                  |
| Cache read/write                    | same module                                                       | Same pattern as `service_layer/csv_upload_stash.py`, which takes an optional `redis_client` argument for tests. |
| Injection seam                      | `app.extensions["gsheet_access_client_factory"]`                  | Same pattern as `gsheet_export_target_factory` in `flask_app.py`, so e2e/BDD tests substitute a fake client.    |
| Route                               | `entrypoints/blueprints/gsheets.py`                               | Next to `save_gsheet_config`.                                                                                   |
| Panel fragment                      | `templates/backoffice/components/gsheet_access_status.html` (new) | Included by `assembly_data.html` in view mode, and returned by the route.                                       |
| Cache drop on save                  | `_handle_gsheet_save_success()`                                   | Delete the key so a stale result for the old URL is never shown.                                                |

The timeout constant, with its comment:

```python
# (connect, read) in seconds, applied to each request, not to the whole check.
# Connect: 3.05 rather than 3 because TCP retransmits an unanswered connection
# attempt after 3 seconds; a timeout just past that lets the retry happen.
# Read: the longest gap allowed between chunks of a response. Typical calls take
# 0.2-1.6s, and the slowest seen was 4.2s. A check makes at most 4 requests, so
# the worst case is about 45s, under the 60s gunicorn worker timeout.
GSHEET_CHECK_TIMEOUT = (3.05, 8)
```

### The result

```python
class GSheetAccessStatus(Enum):
    OK = "ok"                      # can read and write
    READ_ONLY = "read_only"        # can read, cannot write output tabs
    NOT_SHARED = "not_shared"
    NOT_FOUND = "not_found"
    NOT_NATIVE = "not_native"      # an uploaded .xlsx or similar
    GOOGLE_BUSY = "google_busy"    # 429 quota
    UNAVAILABLE = "unavailable"    # timeout, 5xx, anything else from Google


@dataclass(frozen=True)
class GSheetAccessResult:
    status: GSheetAccessStatus
    url: str                        # the URL that was checked
    checked_at: datetime
    title: str = ""
    missing_selection_tabs: tuple[str, ...] = ()
    missing_replacement_tabs: tuple[str, ...] = ()
    tab_suggestions: dict[str, str] = field(default_factory=dict)  # configured name -> near-miss in sheet
```

How exceptions map to a status:

| From `open_gsheet()`                                     | Status        |
| -------------------------------------------------------- | ------------- |
| returns, `can_edit=True`                                 | `OK`          |
| returns, `can_edit=False`                                | `READ_ONLY`   |
| `SpreadsheetNotSharedError`                              | `NOT_SHARED`  |
| `SpreadsheetNotFoundError`                               | `NOT_FOUND`   |
| `NotNativeGoogleSheetError`                              | `NOT_NATIVE`  |
| `gspread.exceptions.APIError` with code 429              | `GOOGLE_BUSY` |
| other `APIError`, `requests` timeout or connection error | `UNAVAILABLE` |

Anything else is a bug and goes to the route's outer handler, which logs it and
shows the "couldn't check" panel. Catch narrowly, as the JSON API conventions
require.

`GOOGLE_BUSY` and `UNAVAILABLE` results are **not cached**. They are about
Google right now, not about the sheet, so the next press of "Check again"
should try again.

### Tabs

Only checked when the sheet opens (`OK` or `READ_ONLY`).

- **Selection tabs** (`select_registrants_tab`, `select_targets_tab`): a missing
  one is a **warning**. A selection cannot start without it.
- **Replacement tabs** (`replace_registrants_tab`, `replace_targets_tab`,
  `already_selected_tab`): a missing one is **for information only**, worded as
  "needed only for replacements". These may well not exist yet on a
  sheet that hasn't had a selection run.
- **An empty tab name is not looked for.** `already_selected_tab` may be
  left empty, and replacements then don't read an already-selected tab, so
  the check skips it rather than reporting a tab called "" as missing. The
  same rule applies to any other tab field that is empty, to be safe.
  Note: `AssemblyGSheetForm.already_selected_tab` currently has a
  `DataRequired()` validator, so the form can't save it empty, although the
  domain and the selection code allow it. Whether the form should allow it
  is a separate question from this spec.

- **Near misses.** Google tab names must match exactly. If a configured name
  matches a real tab once both are stripped of surrounding spaces and compared
  without case, suggest it: "No tab called 'Respondents'. Did you mean
  'respondents '?" No fuzzy matching beyond that, and no new library. The
  comparison is `name.strip().casefold()` on both sides, and the first
  matching tab wins.

### The cache

- Key `gsheet_access_check:{assembly_id}`. The result is about what the
  service account can reach, which is the same for every viewer, so the key
  has no user in it.
- Value: the result as JSON, including the `url` that was checked. On read, a
  cached result whose `url` doesn't match the configured URL counts as a
  miss. That protects against an edit made without going through the save
  route (e.g. a CLI change).
- TTL: **10 minutes**. Since the check route never reads the cache (see
  "The flow"), the TTL only decides how long someone *passing through* the
  page sees the last result instead of a "Check access" button. It never
  delays an answer someone asked for. The result always shows "checked at
  14:02", so its age is visible. Ten minutes covers moving around the
  assembly pages after saving. A shorter TTL would mostly replace a dated,
  probably-still-true result with a button.
- The title and tab names sit in Redis with a TTL. That meets the GDPR rule
  in CLAUDE.md (no long-term copies). A sheet title is rarely personal data
  anyway.
- If Redis is down: log it and carry on without the cache. The check still
  works, it just isn't remembered.

### What the user sees

The panel sits directly under the Spreadsheet URL field in view mode. Load
the `ui-components` skill before building it.

| State          | Shows                                                                                                                                          |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Checking       | Spinner and "Checking access to the spreadsheet..."                                                                                            |
| `OK`           | "Connected to **<title>**" in success styling, plus any tab warnings                                                                           |
| `READ_ONLY`    | Warning: shared as read-only. "Share it with <email> as Editor. A selection writes its results to new tabs." Plus the title, plus tab warnings |
| `NOT_SHARED`   | Error: "...is not shared with <email>". The existing translated message                                                                        |
| `NOT_FOUND`    | Error: "...does not exist. Check the URL". The existing translated message                                                                     |
| `NOT_NATIVE`   | Error: the existing "uploaded Excel file" message                                                                                              |
| `GOOGLE_BUSY`  | "Google is busy right now. Try again in a minute."                                                                                             |
| `UNAVAILABLE`  | "Couldn't check the spreadsheet just now."                                                                                                     |
| Nothing cached | "Check access" button only                                                                                                                     |

Every state except "Checking" shows when it was checked and a "Check again"
button.

- **Reuse the existing messages.** `translate_sortition_error()` already
  translates the library's `spreadsheet_not_found`, `spreadsheet_not_shared`
  and `spreadsheet_read_only` codes. Keep the caught exception long enough
  to translate it, and cache the translated message alongside the status.
  `NotNativeGoogleSheetError` is the exception: `load_gsheet` in
  `celery/tasks.py` writes its own OpenDLP wording inline ("Open it in Google
  Sheets and choose File → Save as Google Sheets"). Move that into a helper in
  `service_layer/error_translation.py` that both callers use, rather than
  copying the msgid. New strings are needed only for OK, busy,
  unavailable, the tab warnings and the panel chrome. Check
  [`docs/language.md`](../../language.md) for wording, and load the
  `translate-catalogues` skill afterwards.
- **Accessibility.** The result region is `aria-live="polite"`, so a screen
  reader announces the outcome. The button is disabled while a check is running
  (`hx-disabled-elt`). The spinner has text, not just an animation.
- **The title is user-controlled text** from Google. Render it escaped (the
  Jinja default). Never pass it through `| safe`.

### Logging

One structured log line per check: `assembly_id`, `user_id`, `status`, the
time taken, and the number of requests. No title. This tells us whether
`(3.05, 8)` can come down, and how often we hit `GOOGLE_BUSY`.

## The library change: one Sheets read per check

Today a successful check costs **2 Sheets reads plus 1 Drive read**:

1. Drive `files.get` (mimetype, `canEdit`). A separate quota, much larger than
   the Sheets one.
2. Sheets `spreadsheets.get`, inside `client.open_by_key()`.
   `Spreadsheet.__init__` fetches the full metadata, _including the tab list_,
   keeps only `properties`, and throws the tab list away.
3. Sheets `spreadsheets.get` again, in `spreadsheet.worksheets()`, to get the
   tab list back.

Reads 2 and 3 fetch the same thing. Under a 60 per minute limit shared with
selections, halving this check's Sheets reads is worth a small library change.

### Proposal

Add to `sortition_algorithms/gsheet.py`:

```python
@dataclass(frozen=True)
class GSheetSummary:
    """What the service account can see of a Google Sheet, without opening it for use."""

    file_id: str
    title: str
    url: str
    mimetype: str
    can_edit: bool
    worksheet_titles: tuple[str, ...]
    service_account_email: str = ""


def inspect_gsheet(client: gspread.client.Client, url_or_id: str) -> GSheetSummary:
    """
    Report what the service account can do with a Google Sheet, using one Drive
    and one Sheets request. Raises the same errors as open_gsheet().
    """
```

- It shares the Drive call and `_classify_drive_not_found()` with
  `open_gsheet()`. Factor the first half of `open_gsheet()` (the Drive request,
  the 404 classification and the mimetype check) into a private helper that
  both call.
- Instead of `open_by_key()`, it calls
  `client.http_client.fetch_sheet_metadata(file_id, params={"fields": "spreadsheetUrl,properties.title,sheets.properties.title"})`.
  gspread 6.2.1 has that signature. The `fields` mask keeps the response small
  for a sheet with many tabs. One request gives the title, URL and tab list.
- It doesn't build a `gspread.Spreadsheet`. That is the point: building one costs a
  request. Callers that need to read or write (`GSheetDataSource`, the export
  adapter) keep using `open_gsheet()`, unchanged.
- On the failure path the cost is the same as today (Drive 404, then one Sheets
  call to classify it).

Result: **1 Sheets read for a successful check**, down from 2.

### Why a new function and not a change to `GSheetInfo`

Adding `worksheet_titles` to `GSheetInfo` seems more natural. But the tab list
is only available from the metadata request that `Spreadsheet.__init__` makes
and then discards, so it can't be kept without a second request (which saves
nothing) or reaching into gspread internals. A separate function
that never builds a `Spreadsheet` is the clean version.

### Order

The OpenDLP work does **not** wait for this. Step 2 below uses
`open_gsheet()` and `worksheets()`, which works today, and step 4 swaps in
`inspect_gsheet()` once the library is released. Both return the same facts,
so the swap is confined to one function in `gsheet_access_check.py`.

## Implementation sketch

1. **Adapter and timeout.** `adapters/gsheet_access.py` with the commented
   `GSHEET_CHECK_TIMEOUT` and the client factory. Register
   `gsheet_access_client_factory` in `flask_app.py`.
2. **The check and the cache.** `service_layer/gsheet_access_check.py`: the
   `GSheetAccessStatus` enum, `GSheetAccessResult`, the classifier, the tab
   comparison, and cache get/set/delete. Unit tests use a fake client, in the
   style of `tests/unit/test_gsheet_export.py`, plus a test against Redis like
   the CSV stash tests.
3. **Route, panel and save hook.** The `POST .../gsheet/check` route, the panel
   fragment, the include in `assembly_data.html`, `?check=1` on the save
   redirect, and the cache drop on save. Component/e2e tests through the
   injected factory: every status, a permission refusal, no service account,
   and save then redirect then panel. BDD: save a configuration, then see the
   title.
4. **Library: `inspect_gsheet()`.** In `~/sftop/sortition-algorithms` on a
   branch, with tests using recorded responses. Release, bump the pin,
   then swap the call in `gsheet_access_check.py`.
5. **Translations.** Run the `translate-catalogues` skill.

Steps 1-3 can be one PR. Step 4 is independent until the swap.

## Resolved questions

1. **Who may trigger a check?** `can_manage_assembly`, the same as saving
   (Chewie, 2026-10-16). Read-only and confirmation-caller users see a cached
   result if there is one, or no panel at all. This can be widened later if
   it turns out to be needed.
2. **Cache TTL, and does the cache delay a fresh check?** No: the check route
   never reads the cache, so "share it in Google, come back, press Check again"
   always gets a new answer, as does a renamed sheet. The cache only serves
   page views that didn't ask for a check, and the "checked at" time on those makes
   their age visible. So the TTL can stay at 10 minutes. See "The flow" and
   "The cache".
3. **Is the near-miss suggestion worth it?** Yes, but keep it simple
   (Chewie, 2026-10-16). Strip surrounding spaces and ignore case, nothing
   more. See "Tabs".

## Deferred

- **Show the panel on other pages?** The selection page could show the
  cached result next to "Check Spreadsheet". Decision deferred (Chewie,
  2026-10-16). It is easy to add once the panel exists.
