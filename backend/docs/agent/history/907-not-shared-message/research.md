# 907: "Task failed with exception: APIError" when a Google Sheet is not shared

Research notes, 2026-10-01. Tested against the real Google API with the
`demo-server@opendlp.iam.gserviceaccount.com` service account, gspread 6.2.1 and
sortition-algorithms 0.12.11 (the versions pinned in `pyproject.toml`).

## TL;DR

- The message is built in OpenDLP, in `_on_task_failure()` in
  `src/opendlp/entrypoints/celery/tasks.py`. It is the Celery last-resort
  handler: it fires because the exception escaped every `except` in the task.
- The exception is `gspread.exceptions.APIError` with HTTP 404 and the body
  `File not found: <id>`. It comes from the **Drive** API call that
  sortition-algorithms makes in `GSheetDataSource._verify_native_gsheet()`
  (added in library commit `fff19c8`, 2026-04-14, to give a nice message for
  uploaded `.xlsx` files).
- It escapes because the first `try` in `_internal_load_gsheet()` (around the
  `data_source.spreadsheet.title` line) catches only `SpreadsheetNotFound` and
  `NotNativeGoogleSheetError`. gspread does not translate errors from raw
  `http_client.request()` calls, so the Drive 404 arrives as a plain `APIError`.
- The Drive API returns **404 for both "does not exist" and "exists but not
  shared with you"**. This is deliberate on Google's side: it does not reveal
  whether a file exists to a caller who cannot see it. So from the Drive call
  alone the two cases cannot be told apart.
- The **Sheets** API does distinguish them: 403 `The caller does not have
  permission` for not-shared, 404 `Requested entity was not found` for missing.
  gspread's `open_by_key()` maps those to `PermissionError` and
  `SpreadsheetNotFound` respectively. A follow-up Sheets call after a Drive 404
  gives a clean three-way classification. Prototype verified below.
- A sheet shared **read-only** (as Viewer, or by link) reads fine, runs the
  whole selection, and fails only when writing the output tabs with a bare
  "APIError: [403]". The Drive metadata call the library already makes can
  return `capabilities.canEdit` in the same request, so this can be caught
  before the selection starts. Measured, see "Read-only shares" below.
- Side finding: the respondent export flow (`adapters/gsheet_export.py`) has
  the same class of bug. For a not-shared target sheet it raises a bare
  builtin `PermissionError`, which is not a `GSpreadException`, so the user gets
  a 500 rather than the "check it is shared with ..." flash that the code
  intends.

## Where the message comes from

`tasks.py` `_on_task_failure()`:

```python
error_msg = f"Task failed with exception: {type(exc).__name__}"
...
record.error_message = f"{error_msg}. " + _("Please contact the administrators if this problem persists.")
```

This is registered as `on_failure` for `load_gsheet`, `run_select`,
`run_select_from_db` and `manage_old_tabs`. It only runs when an exception
propagates out of the task function, so the message is a symptom of a gap in
the task's own handling, not a design choice.

## The call chain (from the production trace)

```
tasks.load_gsheet
  -> _internal_load_gsheet
       spreadsheet_title = data_source.spreadsheet.title      # tasks.py ~L205
  -> sortition_algorithms.adapters.GSheetDataSource.spreadsheet  # property
       file_id = extract_id_from_url(url)                   # no API call
       self._verify_native_gsheet(file_id)                  # Drive files.get  <-- raises here
       self.client.open_by_url(url)                         # Sheets API, never reached
  -> gspread.http_client.BackOffHTTPClient.request
  -> gspread.http_client.HTTPClient.request -> raise APIError(response)
```

Two things worth noting about the library side:

1. `_verify_native_gsheet()` calls `self.client.http_client.request(...)`
   directly. That is the low-level path. gspread's error translation
   (`APIError` 404 -> `SpreadsheetNotFound`, 403 -> `PermissionError`) lives in
   `Client.open_by_key()` and is bypassed.
2. Before `fff19c8` the first API call was `open_by_url()`, so a missing sheet
   surfaced as `SpreadsheetNotFound` and an unshared one as `PermissionError`.
   The OpenDLP handlers for both of those (`except gspread.exceptions.SpreadsheetNotFound`
   at the title check, added 2025-12-12 in `e810563c`; `except PermissionError`
   later in the same function, added 2025-11-12 in `8fc5d0da`) were correct
   when written and are now dead code for URL-based sources. The Drive check
   runs first and raises before either can trigger. The manual test plan step
   "Error displayed: Spreadsheet not found, check URL" in
   `tests/manual/backoffice-gsheet/gsheet-manual-test-plan.md` would fail today.
   There are no automated tests for either path.

## What each failure actually raises (measured)

Script: `probe.py` (in the session scratchpad; reproduced at the end of this
doc). Each URL was tried via `GSheetDataSource.spreadsheet.title` (what
OpenDLP does) and via raw `client.open_by_url()` (what OpenDLP did before the
Drive check existed).

| Case | Via `GSheetDataSource` (Drive check first) | Via raw `open_by_url` (Sheets API only) |
| --- | --- | --- |
| Shared, native Sheet | OK | OK |
| Shared, uploaded `.xlsx` | `NotNativeGoogleSheetError` (handled, good message) | `APIError [400] FAILED_PRECONDITION: ... must not be an Office file` |
| **Not shared** | **`APIError [404] File not found: <id>`**, `errors[0].reason == "notFound"` | `PermissionError` (empty str), `__cause__` = `APIError [403] The caller does not have permission` |
| Does not exist | `APIError [404] File not found: <id>`, `errors[0].reason == "notFound"` | `SpreadsheetNotFound`, `__cause__` = `APIError [404] Requested entity was not found` |

The Drive responses for "not shared" and "does not exist" are byte-for-byte
identical apart from the file id. There is nothing in the status, `reason`,
`domain`, `location` or message to distinguish them.

### Why Drive hides the difference

Google's Drive error guide lists `404 notFound` as "the user does not have read
access to a file, or the file does not exist". Not-shared files are reported as
missing so the API does not leak which ids exist. The Sheets API is not so
careful and returns 403 for a known-but-unshared spreadsheet. Sources:

- [Drive API: Resolve errors](https://developers.google.com/workspace/drive/api/guides/handle-errors)
- [Why you get 404 from Drive even if the file exists](https://www.tutorialpedia.org/blog/file-not-found-error-google-drive-api/)
- [n8n: File not found with service account](https://community.n8n.io/t/google-drive-node-file-not-found-with-service-account-on-shared-drive/180671)

Also relevant: gspread's `BackOffHTTPClient` docstring notes that the Drive
API uses 403 for both "forbidden" and "quota exceeded" (it distinguishes by
`errors[0].domain == "usageLimits"`). That affects writes and quota, not this
read path, but is a reason not to treat a bare 403 as "not shared" without
checking `domain`.

## Distinguishing "not shared" from "does not exist"

Prototype (`classify.py`): on a Drive 404 with `reason == "notFound"`, call
`client.open_by_key(file_id)` and look at what gspread raises.

```
shared_native -> drive_ok
shared_xlsx   -> drive_ok (then NotNativeGoogleSheetError as today)
not_shared    -> NOT_SHARED       (Drive 404 notFound, Sheets 403)
missing_404   -> DOES_NOT_EXIST   (Drive 404 notFound, Sheets 404)
```

Cost: one extra Sheets API call, and only on the failure path. The success
path is unchanged (Drive check, then `open_by_url` as now).

### Read-only shares: measured

Two more sheets, both native, both readable by the service account but not
writable: one shared with the account as Viewer, one shared "anyone with the
link" (view) and not with the account at all. Script `readonly_probe.py`.

| Step | Shared as Viewer | Link-shared, view |
| --- | --- | --- |
| Drive `files.get` | OK, `capabilities.canEdit: false` | OK, `capabilities.canEdit: false` |
| `GSheetDataSource.spreadsheet.title` + `worksheets()` | OK | OK |
| `add_worksheet()` | `APIError [403] PERMISSION_DENIED: The caller does not have permission` | same |

So both read paths succeed, the whole selection runs, and the failure appears
only when writing the output tabs. `_internal_write_selected` catches it with
`except Exception` and shows "Writing results failed: APIError: [403]: The
caller does not have permission". The user gets a message, but nothing says
"the sheet is read-only, give <email> edit access", and the selection's
compute time is wasted.

The fix is almost free. The library's `_verify_native_gsheet()` already
fetches `fields=mimeType,name` from Drive. Asking for
`mimeType,name,capabilities/canEdit` in the same request costs nothing extra
and lets it raise a `spreadsheet_read_only` error before any work starts.
`canEdit` was `false` for both read-only sheets and (checked separately)
`true` for the sheet shared as Editor. Whether read-only should be an error at
all depends on the caller: a test selection that never writes, or a tool that
only reads, should be allowed to proceed, so the library should expose it as a
check (`is_writable()` or a flag on the data source) and let OpenDLP decide
when to fail. OpenDLP's selection path always writes, so for `load_gsheet`
feeding `run_select` it should fail up front.

Note the link-shared sheet behaves exactly like one shared with the account:
the Drive and Sheets APIs both honour link sharing for a service account. So
"shared by link, view only" is a read-only problem, not a not-shared problem,
and the classification needs no extra branch for it.

## Where to catch it

There are three candidate layers. I recommend doing the first two.

### 1. sortition-algorithms: classify in `GSheetDataSource.spreadsheet` (preferred home for the logic)

The library already owns "turn gspread's exceptions into a `SelectionError`
with an `error_code`" (`spreadsheet_not_found`, `tab_not_found`,
`not_native_gsheet`). OpenDLP already translates those codes via
`service_layer/error_translation.py` and the `except errors.SortitionBaseError`
branch in each task. So the smallest change that fixes OpenDLP *and* every other
library user is:

- In `_verify_native_gsheet()`, catch `gspread.exceptions.APIError`. On a 404,
  try `self.client.open_by_key(file_id)` purely to classify:
  - `PermissionError` -> raise `SelectionError(error_code="spreadsheet_not_shared", error_params={"spreadsheet_name": ..., "spreadsheet_id": ...})`
  - `SpreadsheetNotFound` -> raise the existing `spreadsheet_not_found`
  - anything else -> re-raise the original Drive `APIError`
- Non-404 Drive errors (403 quota, 5xx after back-off, 401 bad credentials)
  stay as `APIError` so callers see the real thing.
- Add `capabilities/canEdit` to the `fields` of the same Drive request and
  record it on the data source (say `self.can_edit`). Expose a check the
  caller can run before a selection that will write, raising
  `SelectionError(error_code="spreadsheet_read_only", ...)`. Do not make the
  `spreadsheet` property itself refuse read-only sheets: read-only uses are
  legitimate.
- Add `spreadsheet_not_shared` to `error_messages.py` with a message that
  includes the service account email if the library can see it. It can:
  `self.client.http_client.auth.service_account_email` is set on the
  credentials object gspread keeps (verified for both the oauth2client
  credentials the library builds and gspread's own `service_account()` path).
  OpenDLP's `get_service_account_email()` reads the same JSON file. Better to
  pass it as an `error_param` and let the caller word the sentence.
- Make `get_title()` and the three `read_*` methods consistent: they catch
  `SpreadsheetNotFound` but not `PermissionError` or `APIError`. Since the
  `spreadsheet` property would now raise `SelectionError` for both, they could
  drop the local try/except entirely.

This is also the right place because the library already has the half-built
pieces: `NotNativeGoogleSheetError` shows the pattern (specific subclass of
`SelectionError`, `error_code`, `error_params`, picklable via `__reduce__`,
which matters because Celery pickles exceptions into the failure callback).

### 2. OpenDLP `tasks.py`: widen the title-check `try` (defence in depth, and needed until the library ships)

Independently of the library change, the first `try` around
`data_source.spreadsheet.title` should not let anything through. Suggested
shape:

```python
try:
    spreadsheet_title = data_source.get_title()   # the TODO above this line is already satisfied by 0.12.11
except errors.NotNativeGoogleSheetError as error:
    ...  # as now
except errors.SortitionBaseError as error:
    ...  # translate via translate_sortition_error(); covers spreadsheet_not_found and the new spreadsheet_not_shared
except PermissionError:
    ...  # move the existing handler up here; still reachable via open_by_name sources, and harmless
except gspread.exceptions.APIError as error:
    ...  # "Google returned an error reading the spreadsheet: [code] message. Check the URL and that it is shared with <email>." plus log the body
```

Points:

- `get_title()` exists in 0.12.11 and already wraps `SpreadsheetNotFound` into
  a `SelectionError`, which is what the stale TODO on that line asks for. Using
  it removes the direct `gspread` dependency from this spot.
- Catching `APIError` here is the one-line fix that would have turned the
  production trace into a readable message today, even before any library work.
  `str(error)` is safe to show: it is Google's own text, contains the file id
  (already in the URL the user typed) and no PII. The JSON API rule about
  `str(e)` is about response bodies; `error_message` is rendered with `| safe`
  from server-built HTML, so escape it (`markupsafe.escape`) as the other
  branches do.
- The `except PermissionError` block that currently sits further down should
  move up to the title check (or be duplicated there). Today, for URL sources,
  it can never fire.
- The same gap exists in `manage_old_tabs` (`tasks.py` ~L911): its first
  `data_source` touch is `delete_old_output_tabs()`, which hits the
  `spreadsheet` property, so the Drive 404 falls into its `except Exception`
  branch. That one at least shows "Failed to listing old tabs: APIError:
  [404]: File not found: ...", which is better than the selection case but still
  does not say "share it". Route it through the same classifier.

### 3. A preflight check on the Assembly data page (nice to have)

The user only learns the sheet is unusable when they press "select", several
clicks after pasting the URL. The Assembly Data page already shows the
service account email; it could also call `get_title()` at save time (or on an
HTMX "check access" button) and show the title on success or the specific error
on failure. This is UX work rather than error handling and is out of scope for
907, but the classifier in (1) makes it cheap. Note the request is synchronous
in a Flask route, so it needs the short `request_timeout` the data source
already supports and a non-retrying HTTP client.

## Proposed library API: one helper to open and inspect a Google Sheet

Two OpenDLP callers (`GSheetDataSource` via the library, and
`adapters/gsheet_export.py` directly) open a sheet by URL, and each has its
own gaps: the data source misses "not shared" and "read-only", the export
adapter misses "not shared" and ".xlsx". One helper in sortition-algorithms
that both use closes all of them at once.

### Shape

```python
# sortition_algorithms/gsheet.py  (new module; adapters.py is already 900+ lines)

@dataclass(frozen=True)
class GSheetInfo:
    spreadsheet: gspread.Spreadsheet   # already opened; callers do not open it again
    file_id: str
    title: str
    url: str
    mimetype: str
    can_edit: bool

    def require_writable(self) -> None:
        """Raise SpreadsheetReadOnlyError if the service account cannot edit."""


def open_gsheet(client: gspread.Client, url_or_id: str) -> GSheetInfo:
    """
    Open a Google Sheet by URL or file id and report what the service account can do with it.

    Raises:
        SpreadsheetNotFoundError   - Drive 404 and Sheets 404: the id does not exist
        SpreadsheetNotSharedError  - Drive 404 and Sheets 403: exists, not shared with this account
        NotNativeGoogleSheetError  - Drive mimetype is not a native Sheet (uploaded .xlsx etc.)
        gspread.exceptions.APIError - anything else from Google (quota 403, 5xx, bad credentials)
    """
```

Internals, in order:

1. `file_id = extract_id_from_url(url_or_id)` if it looks like a URL, else use
   it as the id. No API call.
2. Drive `files.get` with
   `fields=mimeType,name,capabilities/canEdit` and `supportsAllDrives=true`.
   One request, same as the existing `_verify_native_gsheet()` plus one field.
3. On Drive 404 with `errors[0].reason == "notFound"`: call
   `client.open_by_key(file_id)` purely to classify. `PermissionError` means
   not shared, `SpreadsheetNotFound` means not found, anything else re-raises
   the original Drive error. (Measured in `classify.py` above.)
4. Non-404 Drive errors propagate unchanged as `APIError`.
5. Mimetype not `application/vnd.google-apps.spreadsheet`: raise
   `NotNativeGoogleSheetError` as today.
6. `spreadsheet = client.open_by_key(file_id)` and return the dataclass.

Cost on the success path: two API calls (Drive, Sheets), which is what
`GSheetDataSource.spreadsheet` does today. The classification call only
happens on failure.

### Design decisions

**Raise for the fatal cases, return data only for the judgement call.**
"Not found", "not shared" and "not native" are errors for every caller that
exists, and each wants a specific message. Returning `is_native_gsheet=False`
would move the `if` and the wording into every caller. The library already has
the better pattern in `NotNativeGoogleSheetError`: a `SelectionError` subclass
with `error_code` and `error_params`, picklable via `__reduce__` so Celery can
carry it to the failure callback, and translated by OpenDLP's
`translate_sortition_error()` with no new plumbing. The new errors follow it:

| Error | `error_code` | `error_params` |
| --- | --- | --- |
| `SpreadsheetNotFoundError` | `spreadsheet_not_found` (exists already) | `spreadsheet_name` |
| `SpreadsheetNotSharedError` | `spreadsheet_not_shared` | `spreadsheet_name`, `service_account_email` |
| `SpreadsheetReadOnlyError` | `spreadsheet_read_only` | `spreadsheet_name`, `title`, `service_account_email` |

The email comes from `client.http_client.auth.service_account_email`,
present on both the oauth2client and google-auth credential objects (verified).

Writability is the one thing that varies by caller. A test selection, a
"list old tabs" dry run, or a read-only tool should all proceed on a Viewer
share. So `can_edit` is data, and `require_writable()` is a one-liner for the
callers that do write (OpenDLP's selection path and the export adapter).

**Hand back the opened `Spreadsheet`.** The helper has to call `open_by_key`
anyway. Putting the result on the dataclass means neither caller opens the
sheet twice, and `GSheetDataSource` can store the whole `GSheetInfo` where it
now stores `_spreadsheet` and `_native_checked`.

**No by-title variant of the helper.** gspread's `open(title)` is a Drive
search already filtered to native Sheets, so unshared, missing and `.xlsx`
sheets all come back as "no results": there is no file id to send to the
Sheets API, so the 403-versus-404 classification is impossible. Titles are
also ambiguous. OpenDLP never opens by title (the only `set_g_sheet_name()`
call passes the assembly URL). `GSheetDataSource` keeps its title path for
other library users, but after the search succeeds it feeds the found id into
`open_gsheet()`, so the title path gets `can_edit` and the native check for
free and there is one classifier, not two.

### How the callers change

`GSheetDataSource.spreadsheet`:

```python
if self._info is None:
    if self._g_sheet_name.startswith("https://"):
        self._info = open_gsheet(self.client, self._g_sheet_name)
    else:
        found = self.client.open(self._g_sheet_name)   # SpreadsheetNotFound as today
        self._info = open_gsheet(self.client, found.id)
return self._info.spreadsheet
```

plus a public `can_edit` property and a `require_writable()` passthrough.
`get_title()` and the three `read_*` methods can drop their local
`except gspread.SpreadsheetNotFound` blocks, since the property now raises
`SelectionError` subclasses for every access failure.

OpenDLP `tasks.py`, title check in `_internal_load_gsheet`:

```python
try:
    spreadsheet_title = data_source.get_title()
    data_source.require_writable()   # selection always writes output tabs
except errors.NotNativeGoogleSheetError as error:
    ...  # as now
except errors.SortitionBaseError as error:
    ...  # translate_sortition_error(); covers not_found, not_shared, read_only
except gspread.exceptions.APIError as error:
    ...  # generic "Google returned [code]: message" plus log
```

OpenDLP `adapters/gsheet_export.py`:

```python
info = open_gsheet(client, self.spreadsheet_url)
info.require_writable()
spreadsheet = info.spreadsheet
```

inside the existing `try`, with `except (SelectionError, GSpreadException,
PermissionError)` wrapping into `ExportTargetError`, and the flow handler
picking the flash wording from `error_code` rather than one blanket message.

### Client factories

The export adapter builds its client with `gspread.service_account()`
(google-auth, plain `HTTPClient`), while the library uses oauth2client with
`BackOffHTTPClient`. `open_gsheet()` only needs a `gspread.Client`, so both
work, but having two credential stacks for the same JSON file is a wart.

Decision: the library update exports its client factory (the body of
`GSheetDataSource.client`) as `make_gsheet_client(auth_json_path,
request_timeout)` in the new `gsheet.py` module, and `GSheetDataSource.client`
calls it. OpenDLP's export adapter keeps its own factory for now and switches
to the library one when convenient; that swap is not part of 907.

### Tests

Library: unit tests with a fake `http_client` returning recorded Drive and
Sheets bodies for each of the six cases measured in this document (shared
editable, shared viewer, link view, not shared, missing, `.xlsx`). The bodies
are in the tables above. No live API in the library test suite.

OpenDLP: patch `GSheetDataSource.get_title` / `require_writable` to raise each
error class and assert `error_message` on the run record; one test per class,
plus one for a raw `APIError` to prove the Celery failure callback is no longer
reached.

### The BDD shim needs two small additions

`CSVGSheetDataSource` in `src/opendlp/adapters/sortition_algorithms.py` is
the fake that `update_data_source_from_assembly_gsheet()` substitutes when
`USE_CSV_DATA_SOURCE=true`. It is not a subclass of `GSheetDataSource`; it
hand-mirrors the attributes `tasks.py` touches (`spreadsheet.title`,
`feature_tab_name`, `_g_sheet_name`, `delete_old_output_tabs()` and so on).
The task code proposed above calls two things it does not have:

- `get_title()`: add it, returning `self.spreadsheet.title`. The existing
  `FakeSpreadsheet` stays, since `tasks.py` still reads
  `data_source.spreadsheet.title` until the title check moves to `get_title()`.
- `require_writable()` and a `can_edit` property: add them as a no-op and
  `True`. Optionally back them with a `simulate_read_only()` toggle in the
  same style as `add_simulated_old_tab()`, so a BDD scenario can exercise the
  read-only message end to end. Without that, the read-only path is covered
  by the unit tests above only.

Nothing else changes: `_g_sheet_name` is already exposed, and the shim never
calls the real Google API, so `open_gsheet()` does not touch it.
`tests/unit/test_csv_gsheet_adapter.py` gets a test for each new method.

## Side finding: the export flow has the same bug

`adapters/gsheet_export.py` `write_sheet()` catches `GSpreadException` and
wraps it in `ExportTargetError`, which `entrypoints/gsheet_export_flow.py`
turns into a "check the spreadsheet is shared with ..." flash. But
`client.open_by_url()` raises a **builtin** `PermissionError` for a not-shared
sheet, which is not a `GSpreadException`. Measured (`export_probe.py`):

```
not_shared  -> ESCAPED: PermissionError '' | cause: APIError: [403]: The caller does not have permission
missing_404 -> ExportTargetError: <Response [404]>
shared_xlsx -> ExportTargetError: APIError: [400]: ... must not be an Office file.
```

So the one case the handler's comment names first ("typically it is not shared
with the service account") produces a 500. Fix: `except (GSpreadException,
PermissionError) as exc`. Also worth noting `str(SpreadsheetNotFound)` is
`<Response [404]>`, which is what ends up in the warning log; `exc.__cause__`
holds the readable text. And the `.xlsx` case gets a generic "check the URL"
flash when the specific "save as Google Sheets" advice is available from the
library's `NotNativeGoogleSheetError` mapping if the export adapter did the
same Drive mimetype check.

## Generally useful things noticed on the way

- **gspread's `PermissionError` has an empty message.** `str(e) == ""`, and the
  useful text is on `e.__cause__`. Any log line or UI string built from
  `str(e)` for this exception is blank. Both existing OpenDLP handlers already
  know this (the comment says so), but new code keeps tripping on it.
- **`str(SpreadsheetNotFound)` is `<Response [404]>`**, for the same reason.
- **`BackOffHTTPClient` retries only 408, 429, 5xx and Drive `usageLimits`
  403s**, so none of the cases here are slowed down by back-off. But a real
  outage (5xx) will retry with 2, 4, 8 ... 128 second sleeps, up to 7 times,
  inside the Celery task. That is well under `TASK_TIMEOUT_HOURS` but worth
  knowing when reading a slow failure.
- **The `except Exception` branch in `_internal_load_gsheet` puts the full
  traceback into the run report** that is shown to the user. For an `APIError`
  that is noisy but not sensitive. The TODO above it ("just say error occurred,
  contact admins") is still open.
- **`_on_task_failure` is the only place the generic
  "Please contact the administrators" wording appears**, so grepping logs for
  `Celery task failure callback` finds every instance of this class of problem.
  In production logs the three entries pasted into this task's description are
  exactly that signature.

## Recommended plan

1. OpenDLP, this branch: widen the title-check `try` as in section 2, move the
   `PermissionError` handler up, do the same in `manage_old_tabs`, and fix the
   export adapter's `except`. Add unit tests that patch `GSheetDataSource` to
   raise each of `APIError(404)`, `PermissionError`, `SpreadsheetNotFound`,
   `NotNativeGoogleSheetError` and check `error_message`. This ships a real
   message immediately. Until the library can tell the two apart it is one
   interim message: "Google reported the spreadsheet as not found. Either the
   URL is wrong or the spreadsheet is not shared with <email>." Add
   `get_title()`, `can_edit` and `require_writable()` to the BDD shim at the
   same time so the task code can call them unconditionally.
2. sortition-algorithms: add `open_gsheet()` and `GSheetInfo` as described in
   "Proposed library API" (Drive-404-then-Sheets classification,
   `capabilities/canEdit`, the three error classes, `make_gsheet_client()`),
   have `GSheetDataSource` use it, with tests using recorded responses. On a
   branch, in parallel with step 1. Release, bump the pin.
3. OpenDLP: once the pin lands, the `SortitionBaseError` branch picks up the
   new code automatically; add the translation and swap the interim "not found
   or not shared" wording for two precise messages.
4. Optional: preflight access check on the Assembly Data page.

## Status (2026-10-01)

- Step 1 landed on `907-not-shared-message` (commit `3c65581f`).
- Step 2 shipped as sortition-algorithms 0.12.12 and OpenDLP's pin was bumped.
- Step 3 done on the same branch: `load_gsheet` and the delete path of
  `manage_old_tabs` call `require_writable()` up front; the interim 404
  wording is gone (the library's `spreadsheet_not_found`,
  `spreadsheet_not_shared` and `spreadsheet_read_only` codes flow through
  `translate_sortition_error()`); the export adapter opens sheets through
  `open_gsheet()` and the export flow flashes the classified reason when the
  cause is a library error. The BDD shim gained `can_edit`,
  `require_writable()` and `simulate_read_only()`.
- The export adapter builds its client with the library's
  `make_gsheet_client()`, so both callers share one credential stack. From
  sortition-algorithms 0.12.14 the factory takes an `http_client`, and the
  adapter uses gspread's plain `HTTPClient` with the 20 second timeout by
  default so a web request fails fast. `GSheetExportTarget(background=True)`
  is for a Celery task: the retrying back-off client and a 120 second
  timeout. The 1029 auto-export task passes that flag.
- Not done: the optional preflight check on the Assembly Data page (step 4).

## Decisions (Chewie, 2026-10-01)

- **Two messages.** "Does not exist" and "not shared with <email>" are
  reported separately. The extra Sheets API call on the failure path is worth
  it.
- **Fail early on read-only.** `load_gsheet` calls `require_writable()` at
  the title check, before any selection work, because the OpenDLP flow always
  writes output tabs.
- **Library change on a branch, in parallel.** The sortition-algorithms work
  goes on a branch in `~/sftop/sortition-algorithms` and can be done by a
  subagent while the OpenDLP interim fix (plan step 1) proceeds on
  `907-not-shared-message`. The two land independently; step 3 reconciles them
  once the library is released and the pin bumped.

## Appendix: probe scripts

Kept in the session scratchpad; copied here so they can be re-run. All need
`GOOGLE_AUTH_JSON_PATH`-style credentials at the path in `AUTH`.

### probe.py

```python
import json
from pathlib import Path
import gspread
from sortition_algorithms import adapters

AUTH = Path("/path/to/service-account.json")
URLS = {
    "shared_native": "https://docs.google.com/spreadsheets/d/1B-S6esBj7rqbSJulqAZUh4-x1FXU-rPdNabMVDtsynM/edit",
    "shared_xlsx": "https://docs.google.com/spreadsheets/d/1JtJEIw5_ub5Z0wPRG1nf6uwh9936CA5t/edit",
    "not_shared": "https://docs.google.com/spreadsheets/d/1j0j0FYnWp6Kl44Oym22pK3F2F-L2Y-uP6xAcedOHjnA/edit",
    "missing_404": "https://docs.google.com/spreadsheets/d/1JtJEIw5_ub4Y0wPRG1nf6uwh9936CA5t/edit",
}

def describe(e):
    print("  type:", type(e).__module__ + "." + type(e).__name__)
    print("  str:", repr(str(e)))
    if isinstance(e, gspread.exceptions.APIError):
        print("  code:", e.code, "| error:", json.dumps(e.error))
    if e.__cause__:
        print("  cause:", type(e.__cause__).__name__, repr(str(e.__cause__)))

for label, url in URLS.items():
    print(f"\n===== {label} via GSheetDataSource.spreadsheet.title")
    ds = adapters.GSheetDataSource(feature_tab_name="Targets", people_tab_name="Respondents", auth_json_path=AUTH)
    ds.set_g_sheet_name(url)
    try:
        print("  OK title:", ds.spreadsheet.title)
    except Exception as e:
        describe(e)
    print(f"----- {label} via raw gspread open_by_url")
    try:
        print("  OK title:", ds.client.open_by_url(url).title)
    except Exception as e:
        describe(e)
```

### classify.py

```python
import gspread
from gspread.urls import DRIVE_FILES_API_V3_URL

def classify(client, file_id):
    try:
        resp = client.http_client.request(
            "get", f"{DRIVE_FILES_API_V3_URL}/{file_id}",
            params={"supportsAllDrives": True, "fields": "mimeType,name"},
        )
        return "drive_ok", resp.json()
    except gspread.exceptions.APIError as drive_err:
        if drive_err.code != 404:
            return "drive_other_api_error", str(drive_err)
        # Drive hides unshared files behind 404; the Sheets API tells 403 from 404.
        try:
            client.open_by_key(file_id)
            return "drive_404_but_sheets_ok", None
        except PermissionError as perr:
            return "NOT_SHARED", str(perr.__cause__)
        except gspread.exceptions.SpreadsheetNotFound as nf:
            return "DOES_NOT_EXIST", str(nf.__cause__)
```

### export_probe.py

```python
import gspread
from opendlp.adapters.gsheet_export import GSheetExportTarget
from opendlp.adapters.tabular_export import ExportTargetError, TabularData

factory = lambda: gspread.service_account(filename="/path/to/service-account.json")
for label, url in {...same URLS...}.items():
    try:
        GSheetExportTarget(url, client_factory=factory).write_sheet("probe", TabularData(headers=["a"], rows=[["1"]]))
    except ExportTargetError as e:
        print(label, "-> ExportTargetError:", e)
    except Exception as e:
        print(label, "-> ESCAPED:", type(e).__name__, "| cause:", e.__cause__)
```

### readonly_probe.py

```python
from gspread.urls import DRIVE_FILES_API_V3_URL
from gspread.utils import extract_id_from_url

# ds is a GSheetDataSource with set_g_sheet_name(url) already called
file_id = extract_id_from_url(url)
r = ds.client.http_client.request(
    "get", f"{DRIVE_FILES_API_V3_URL}/{file_id}",
    params={"supportsAllDrives": True, "fields": "mimeType,name,capabilities/canEdit"},
)
print(r.json())  # {"name": ..., "mimeType": ..., "capabilities": {"canEdit": false}}
print(ds.spreadsheet.title, [w.title for w in ds.spreadsheet.worksheets()])  # both succeed
ws = ds.spreadsheet.add_worksheet(title="probe-907", rows=2, cols=2)  # APIError [403] PERMISSION_DENIED
```
