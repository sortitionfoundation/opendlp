# Selection Progress Modal Specification

## Problem Statement

The current selection run flow uses a URL path segment (`/selection/<run_id>`) when a user clicks "Run Selection". This changes the URL from the base `/selection` route to a separate route, which breaks the intended design where the selection tab should always maintain consistent layout with Selection Replacement, Manage Generated Tabs, and Selection History boxes visible and functional.

**Current behavior:**
- User clicks "Run Selection" → POST to `/selection/run`
- Backend redirects to `/selection/<run_id>` (separate route: `view_assembly_selection_with_run`)
- This separate route renders progress inline on the page
- Selection History and other components may not work correctly due to URL context change

## Solution

Use a query parameter (`?current_selection=<run_id>`) instead of a URL path segment, and display task progress in a modal overlay that prevents closing while the task is running.

**New behavior:**
- User clicks "Run Selection" → POST to `/selection/run`
- Backend redirects to `/selection?current_selection=<run_id>`
- Modal opens with task progress
- Underlying page remains unchanged (all boxes visible and functional)
- Modal prevents closing while task is running (polling active)
- When task completes, close button is enabled; closing refreshes page

## Technical Specification

### 1. Modal Component

**File:** `templates/backoffice/components/modal.html`

A reusable Jinja2 macro with:
- Fixed positioning with backdrop overlay
- Centered content panel
- Optional title and close button
- Alpine.js integration for state management
- Close button disabled state via `:disabled="!canClose"`
- Escape key handling that respects `canClose` state
- Backdrop click handling that respects `canClose` state
- ARIA attributes for accessibility (`role="dialog"`, `aria-modal="true"`)

**Macro signature:**
```jinja2
{% macro modal(id, title="", show_close=true) %}
    {{ caller() }}
{% endmacro %}
```

### 2. Alpine.js Modal Component

**File:** `static/backoffice/js/alpine-components.js`

Register a `modal` component using CSP-safe `Alpine.data()` pattern:

```javascript
Alpine.data("modal", function(options) {
    var initialOpen = options.initialOpen || false;
    var initialCanClose = options.canClose !== undefined ? options.canClose : true;
    var refreshOnClose = options.refreshOnClose || false;

    return {
        isOpen: initialOpen,
        canClose: initialCanClose,

        open: function() { this.isOpen = true; },

        close: function() {
            if (this.canClose) {
                this.isOpen = false;
                if (refreshOnClose) {
                    window.location.reload();
                }
            }
        },

        closeIfAllowed: function() { this.close(); },

        setCanClose: function(value) { this.canClose = value; }
    };
});
```

**Options:**
- `initialOpen`: Whether modal starts open (default: false)
- `canClose`: Whether close is allowed initially (default: true)
- `refreshOnClose`: Whether to reload page on close (default: false)

### 3. Modal Progress Template

**File:** `templates/backoffice/components/selection_progress_modal.html`

HTMX-powered fragment that:
- Polls `/selection/modal-progress/<run_id>` every 2 seconds while task is running
- Uses `hx-swap="outerHTML"` to replace itself with updated content
- Stops polling when `run_record.has_finished` is true (HTMX attributes not rendered)
- Dispatches `task-finished` event when task completes to enable close button

**Content structure:**
1. Task type display
2. Status badge (pending/running/completed/failed/cancelled)
3. Spinner animation (while pending/running)
4. Error message (if failed)
5. Success message (if completed)
6. Log messages in scrollable container
7. Footer with Cancel button (while running) or Close button (when finished)

**Alpine state update mechanism:**
```html
{% if run_record.has_finished %}
    hx-on::after-swap="$dispatch('task-finished')"
{% endif %}
```

The parent modal listens with `@task-finished.window="setCanClose(true)"`.

### 4. Main Template Changes

**File:** `templates/backoffice/assembly_selection.html`

Add modal rendering when `current_selection` query param is present:

```jinja2
{% if current_selection %}
    <div x-data="modal({
        initialOpen: true,
        canClose: {{ 'true' if run_record and run_record.has_finished else 'false' }},
        refreshOnClose: true
    })"
    @task-finished.window="setCanClose(true)">
        {% call modal(id="selection-progress-modal", title=_("Task Progress")) %}
            {% include "backoffice/components/selection_progress_modal.html" %}
        {% endcall %}
    </div>
{% endif %}
```

Remove existing inline progress section that was conditionally rendered with `{% if run_id %}`.

### 5. Backend Route Changes

**File:** `src/opendlp/entrypoints/blueprints/backoffice.py`

#### 5.1 Update `view_assembly_selection`

Add handling for `current_selection` query parameter:

```python
current_selection_str = request.args.get("current_selection")
current_selection: uuid.UUID | None = None
run_record = None
log_messages: list = []
translated_report_html = ""

if current_selection_str:
    try:
        current_selection = uuid.UUID(current_selection_str)
        check_and_update_task_health(uow, current_selection)
        result = get_selection_run_status(uow, current_selection)

        if result.run_record and result.run_record.assembly_id == assembly_id:
            run_record = result.run_record
            log_messages = result.log_messages
            if result.run_report:
                translated_report_html = translate_run_report_to_html(result.run_report)
        else:
            current_selection = None  # Invalid - don't show modal
    except (ValueError, NotFoundError):
        current_selection = None  # Invalid UUID or not found
```

Pass to template:
```python
return render_template(
    "backoffice/assembly_selection.html",
    # ... existing vars ...
    current_selection=current_selection,
    run_id=current_selection,
    run_record=run_record,
    log_messages=log_messages,
    translated_report_html=translated_report_html,
)
```

#### 5.2 Add new modal progress endpoint

```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/modal-progress/<uuid:run_id>")
@login_required
def selection_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return modal progress HTML fragment for HTMX polling."""
    # Fetch assembly, gsheet, run status
    # Render selection_progress_modal.html
    # No HX-Refresh header - modal handles refresh via Alpine
```

#### 5.3 Update redirects

Change all redirects from:
```python
url_for("backoffice.view_assembly_selection_with_run", assembly_id=assembly_id, run_id=task_id)
```
To:
```python
url_for("backoffice.view_assembly_selection", assembly_id=assembly_id, current_selection=task_id)
```

Affected routes:
- `start_selection_run`
- `start_selection_load`
- `cancel_selection_run`

#### 5.4 Convert legacy route to redirect

```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/<uuid:run_id>")
@login_required
def view_assembly_selection_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID):
    """Legacy route - redirects to query parameter version."""
    return redirect(url_for("backoffice.view_assembly_selection",
                            assembly_id=assembly_id,
                            current_selection=run_id))
```

## User Experience

1. User clicks "Run Selection" button
2. Page reloads with modal overlay showing "Task Progress"
3. Modal displays task type, status badge with "Pending" or "Running"
4. Spinner animates while task runs
5. Log messages appear in real-time (2s polling)
6. Close button (X) and backdrop clicks are disabled
7. Escape key does not close modal
8. Cancel button allows stopping the task
9. When task completes (success/failure/cancelled):
   - Polling stops
   - Status badge updates
   - Success/error message shown
   - Close button becomes enabled
10. Clicking Close or backdrop refreshes page
11. Selection History shows completed run

## Testing Checklist

- [ ] Click "Run Selection" → URL is `/selection?current_selection=<uuid>`
- [ ] Modal opens with progress content
- [ ] Close button is disabled while task is pending/running
- [ ] Escape key does not close modal while running
- [ ] Clicking backdrop does not close modal while running
- [ ] Log messages update every 2 seconds
- [ ] Cancel button cancels the task
- [ ] After task completes, close button is enabled
- [ ] Escape key closes modal after task completes
- [ ] Clicking backdrop closes modal after task completes
- [ ] Closing modal refreshes page
- [ ] Selection History is updated after page refresh
- [ ] Selection History links work while modal is open
- [ ] Old URLs `/selection/<uuid>` redirect to `/selection?current_selection=<uuid>`
- [ ] Invalid `current_selection` param does not show modal
- [ ] Task belonging to different assembly does not show modal
