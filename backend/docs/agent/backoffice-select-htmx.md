# Plan: Convert Backoffice Selection Progress from Alpine.js to HTMX

## Current State Summary

### HTMX version (gsheets — the reference)

- `gsheet_select_progress` returns an HTML fragment (`gsheets/components/progress.html`)
- The fragment includes `hx-get` + `hx-trigger="every 2s"` + `hx-swap="outerHTML"` on the outer `<div>` — but **only when the task hasn't finished**
- Polling stops naturally because the finished HTML omits the `hx-get` attribute
- On completion, the endpoint sets `HX-Refresh: true` header to force a full page reload (updates buttons, history, etc.)
- The progress template is `{% include %}`'d into the main page on initial load, so the same template serves both purposes

### Alpine.js version (backoffice — to be converted)

- `selection_progress` returns JSON (`status`, `log_messages`, `error_message`, etc.)
- `assembly_selection.html` contains a `taskPoller` Alpine.js component that polls the JSON endpoint via `fetch()`
- Alpine.js conditionally renders status, spinner, log messages, error, and buttons using `x-show`, `x-bind`, `x-text`, `template x-if`, `template x-for`
- Polling stops via JS logic (`isTerminalStatus()` check)
- The `taskPoller` component is defined in `static/backoffice/js/alpine-components.js`

## Conversion Steps

### 1. Create a new progress template fragment

Create `templates/backoffice/components/selection_progress.html` — an HTMX-swappable HTML fragment modelled on the gsheets `progress.html` but using the backoffice design system (Tailwind/Pines classes, `card` macros, CSS variables).

This template should:

- Have an outer `<div id="progress-section">` with `hx-get`, `hx-trigger="every 2s"`, `hx-swap="outerHTML"` — **only when `not run_record.has_finished`**
- Render status badge, spinner, log messages, error, and action buttons server-side using Jinja2 conditionals (`run_record.is_running`, `is_pending`, `is_completed`, `is_failed`, `is_cancelled`)
- Include the cancel form when running/pending
- Include the "Back to Selection" link when finished
- Import and use the backoffice component macros (`button`, `card`, `alert`, etc.)

### 2. Convert the `selection_progress` endpoint from JSON to HTML

In `blueprints/backoffice.py`:

- Change the endpoint to render `backoffice/components/selection_progress.html` instead of returning `jsonify()`
- Pass `assembly`, `gsheet`, `run_record`, `run_id`, `log_messages`, `run_report`, and `translated_report_html` to the template (same as the gsheets version does)
- Add `HX-Refresh: true` header when `run_record.has_finished` — this forces a full page reload to update the action buttons and selection history
- Remove `jsonify` import if no longer needed by this module (but it's still used by `search_users` and `search_demo`, so it stays)

### 3. Update `assembly_selection.html` to include the progress fragment

Replace the entire `{% if run_id %}` Alpine.js block (lines ~51–138) with:

```jinja2
{% if run_id %}
    <div class="mb-8">
        {% include "backoffice/components/selection_progress.html" %}
    </div>
{% endif %}
```

This mirrors how `gsheets/select.html` uses `{% include "gsheets/components/progress.html" %}`.

### 4. Update `view_assembly_selection_with_run` to pass the same template context

The view already passes `run_record`, `log_messages`, `run_report`, and `run_id`. It will also need:

- `translated_report_html` — call `translate_run_report_to_html(result.run_report)` like the gsheets version does
- `progress_url` — the URL for the HTMX polling endpoint (or let the template generate it via `url_for`)

### 5. Clean up Alpine.js code

- Remove the `taskPoller` component from `static/backoffice/js/alpine-components.js` (lines 229–342)
- Remove the associated JSDoc comment block

### 6. Ensure HTMX is loaded in the backoffice base template

Check that `templates/backoffice/base_page.html` (or equivalent) includes the HTMX script. If not, add it.

## Improvements to Apply

1. **Full page refresh on completion (from gsheets pattern):** The gsheets version uses `HX-Refresh: true` on completion — this updates everything on the page (buttons become enabled, history table updates). The Alpine version doesn't do this. Adopting this pattern is a clear win.

2. **Assembly ownership validation:** The gsheets progress template validates `run_record.assembly_id != assembly_id` — the backoffice JSON endpoint does not. Add this check to the new HTML endpoint for safety.

3. **Pass `translated_report_html`:** The backoffice `view_assembly_selection_with_run` view doesn't pass `translated_report_html` — so the completed state can't show the run report. The gsheets version does. Add this.

4. **Load gsheet in progress endpoint:** The backoffice JSON endpoint doesn't load the gsheet — so it can't link to the spreadsheet on completion. The gsheets version loads it. Add this so the progress fragment can show a "view spreadsheet" link on success.

5. **Error display — keep `| safe` filter with comment:** The `error_message` field contains pre-rendered HTML where user-controlled content has already been escaped by the rendering code. Use `| safe` in the template and add a comment explaining why it is safe to do so (e.g. `{# error_message is HTML rendered by server code that escapes user content #}`).

6. **Remove dead Alpine code:** The `taskPoller` Alpine component becomes dead code after this change — remove it entirely rather than leaving it in place.

## Detailed Todo List

### Phase 1: Add HTMX to backoffice base template

HTMX is loaded in the GOV.UK `templates/base.html` but **not** in `templates/backoffice/base.html`. The backoffice has its own base template chain and CSP nonce support.

- [x] **1.1** Add HTMX `<script>` tag to `templates/backoffice/base.html`, matching the pattern used in `templates/base.html` (CDN with SRI hash, `nonce="{{ csp_nonce }}"`)
- [x] **1.2** Verify HTMX loads correctly — open any backoffice page in a browser and check the console for errors (CSP violations, 404s, etc.)

### Phase 2: Create the progress HTML fragment template

- [x] **2.1** Create `templates/backoffice/components/selection_progress.html` with ABOUTME comment
- [x] **2.2** Add outer `<div id="progress-section">` with conditional HTMX attributes:
  - `hx-get` pointing to progress URL (use `url_for('backoffice.selection_progress', ...)`)
  - `hx-trigger="every 2s"`
  - `hx-swap="outerHTML"`
  - Only include these attributes when `not run_record.has_finished`
- [x] **2.3** Add import macros at the top of the fragment (`button`, `card`, `card_body`, `card_footer`, `alert`) — same as `assembly_selection.html` uses
- [x] **2.4** Implement the **pending/running** state: status badge with info styling, spinner SVG, "Processing..." text, log messages list (Jinja2 `{% for %}` loop), cancel form with CSRF token
- [x] **2.5** Implement the **completed** state: success status badge, success message with participant count, link to spreadsheet (`gsheet.url`), run report section using `translated_report_html | safe` with comment explaining safety
- [x] **2.6** Implement the **failed** state: error status badge, error message display using `run_record.error_message | safe` with `{# error_message is HTML rendered by server code that escapes user content #}` comment
- [x] **2.7** Implement the **cancelled** state: warning status badge, cancellation message, optional error message
- [x] **2.8** Add the **full run report** collapsible section for finished tasks (log messages, translated report HTML, started/completed timestamps) — similar to gsheets `<details>` pattern but using backoffice styling
- [x] **2.9** Add footer with conditional content: cancel button when running/pending, "Back to Selection" link when finished
- [x] **2.10** Add task type info display (`run_record.task_type_verbose`)

### Phase 3: Convert the `selection_progress` endpoint to return HTML

- [x] **3.1** In `blueprints/backoffice.py`, update the `selection_progress` function to load the `assembly` object (via `get_assembly_with_permissions`) — already done
- [x] **3.2** Add `gsheet` loading (via `get_assembly_gsheet`) so the template can link to the spreadsheet on completion
- [x] **3.3** Add assembly ownership validation: check `result.run_record.assembly_id != assembly_id` and return 404 if mismatched (matching the gsheets version's safety check)
- [x] **3.4** Add `translate_run_report_to_html` import and call it on `result.run_report`
- [x] **3.5** Replace the `jsonify()` return with `render_template("backoffice/components/selection_progress.html", ...)` passing: `assembly`, `gsheet`, `run_record=result.run_record`, `run_id`, `log_messages=result.log_messages`, `run_report=result.run_report`, `translated_report_html`
- [x] **3.6** Add `HX-Refresh: true` response header when `result.run_record.has_finished` — use `current_app.make_response()` pattern from the gsheets version
- [x] **3.7** Update error responses: change `jsonify({"error": ...})` returns to empty string responses with appropriate status codes (`"", 404` / `"", 403` / `"", 500`) — HTMX handles these more gracefully than JSON error bodies
- [x] **3.8** Update the endpoint docstring from "JSON progress endpoint for Alpine polling" to describe HTMX HTML fragment polling

### Phase 4: Update the main selection page template

- [x] **4.1** In `templates/backoffice/assembly_selection.html`, replace the entire `{% if run_id %}` Alpine.js block (the `<div class="mb-8" x-data="taskPoller(...)">` through its closing `</div>`, approximately lines 51–138) with:
  ```jinja2
  {% if run_id %}
      <div class="mb-8">{% include "backoffice/components/selection_progress.html" %}</div>
  {% endif %}
  ```
- [x] **4.2** Remove any Alpine-specific attributes that are no longer needed from surrounding elements in the template (if any)

### Phase 5: Update the `view_assembly_selection_with_run` view function

- [x] **5.1** In `blueprints/backoffice.py`, add import for `translate_run_report_to_html` from `opendlp.service_layer.report_translation`
- [x] **5.2** In `view_assembly_selection_with_run`, add `translated_report_html=translate_run_report_to_html(result.run_report)` to the `render_template` call
- [x] **5.3** Confirm `run_record`, `log_messages`, `run_report`, `run_id`, `assembly`, and `gsheet` are all passed to the template (most already are — verify `log_messages` is passed, it currently comes from `result.log_messages` but check if the template variable name matches)

### Phase 6: Remove dead Alpine.js code

- [x] **6.1** In `static/backoffice/js/alpine-components.js`, remove the `taskPoller` component definition (the `Alpine.data("taskPoller", ...)` block and its preceding JSDoc comment, approximately lines 229–342)
- [x] **6.2** Verify no other templates reference `taskPoller` — grep for `taskPoller` across all templates
- [x] **6.3** Check that the remaining Alpine components (`autocomplete`, `urlSelect`, `$confirm` magic) still work — they are unaffected but verify the JS file still parses correctly after the deletion

### Phase 7: Update existing tests

The existing tests in `tests/e2e/test_backoffice_assembly_data.py` assert JSON responses from the progress endpoint. These must be updated for HTML responses.

- [x] **7.1** Update `test_selection_progress_endpoint_returns_status` (line ~590): change from asserting `response.get_json()` to asserting HTML content (e.g. `assert b"running" in response.data` or checking for the `progress-section` div, HTMX attributes present because task is running)
- [x] **7.2** Update `test_selection_progress_not_found` (line ~744): change from asserting `response.get_json()["error"]` to asserting status code 404 with empty body
- [x] **7.3** Update `test_selection_progress_permission_denied` (line ~767): change from asserting `response.get_json()["error"]` to asserting status code 403 with empty body
- [x] **7.4** Add mock for `get_assembly_gsheet` in the progress endpoint test (since the endpoint will now load the gsheet) — not needed, the `assembly_with_gsheet` fixture creates real DB records that work
- [x] **7.5** Add mock for `translate_run_report_to_html` in the progress endpoint test — not needed, guarded with `if result.run_report` check

### Phase 8: Add new tests for HTMX-specific behaviour

- [x] **8.1** Test that the progress endpoint returns HTML containing `hx-get` when task is running (polling should continue)
- [x] **8.2** Test that the progress endpoint returns HTML **without** `hx-get` when task is completed (polling should stop)
- [x] **8.3** Test that the progress endpoint returns `HX-Refresh: true` header when task has finished
- [x] **8.4** Test that the progress endpoint returns `HX-Refresh: true` header for failed and cancelled states too
- [x] **8.5** Test assembly ownership validation: request progress for a run_id that belongs to a different assembly, assert 404
- [x] **8.6** Test that `view_assembly_selection_with_run` renders the progress fragment with HTMX attributes (integration check that the include works)

### Phase 9: Run full test suite and quality checks

- [x] **9.1** Run `just test` — all tests pass (7 pre-existing failures in `test_health_check.py` unrelated to this change)
- [x] **9.2** Run `just check` — all checks pass (pre-existing typos issue in Hungarian translation only)
- [x] **9.3** Manually test in browser: verified HTMX loads on backoffice pages; full task lifecycle testing requires login credentials (automated tests cover HTMX polling, stop-on-completion, and HX-Refresh behaviour)
