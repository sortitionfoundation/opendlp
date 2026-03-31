# Replacement Selection Modal Specification

## Problem Statement

The current replacement selection flow uses a separate route (`/replacement`) with its own page layout when the user clicks "Go to Replacement Selection". This breaks consistency with the modal-based approach used for initial selection (implemented in commit `cdd5c7a`).

**Current behavior:**
- User clicks "Go to Replacement Selection" button on `/selection` page
- Browser navigates to `/assembly/<id>/replacement` (separate page)
- Replacement selection has a two-step flow:
  1. "Check Spreadsheet" → loads data, shows available replacement count (min/max)
  2. "Run Replacements" → user enters number to select, task runs
- Progress is shown inline on the `/replacement` page
- This creates an inconsistent UX compared to initial selection

## Solution

Integrate replacement selection into the `/selection` page using a modal overlay, consistent with the initial selection progress modal pattern.

**New behavior:**
- User clicks "Go to Replacement Selection" button → modal opens
- Modal shows replacement selection wizard with two states:
  1. **Form state**: Check Spreadsheet / Run Replacements form
  2. **Progress state**: Task progress with polling (when `current_replacement=<run_id>`)
- URL uses query parameter: `/selection?replacement_modal=open` and `/selection?current_replacement=<run_id>`
- Underlying Selection page remains visible and functional
- Modal prevents closing while task is running

## Technical Specification

### 1. URL Structure

| State | URL |
|-------|-----|
| Modal open (form) | `/selection?replacement_modal=open` |
| Modal open (task progress) | `/selection?current_replacement=<run_id>` |
| Modal closed | `/selection` |

### 2. New Template: `replacement_modal.html`

**File:** `templates/backoffice/components/replacement_modal.html`

A self-contained modal component handling both form and progress states:

```
┌─────────────────────────────────────────────────────────┐
│ Replacement Selection                              [X] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ STATE 1: Form (no current_replacement param)            │
│ ─────────────────────────────────────────────           │
│ Select replacement participants when original           │
│ selections decline or cannot participate.               │
│                                                         │
│ [Check Spreadsheet]  (if no min/max known)              │
│                                                         │
│ -- OR --                                                │
│                                                         │
│ Available replacements: 3 to 15 participants            │
│ Number to select: [___10___]                            │
│ [Run Replacements]  [Re-check Spreadsheet]              │
│                                                         │
│ STATE 2: Progress (with current_replacement param)      │
│ ─────────────────────────────────────────────           │
│ Task: Replacement Selection Load                        │
│ Status: [Running]                                       │
│ [spinner] Processing...                                 │
│                                                         │
│ Messages:                                               │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Loading spreadsheet data...                         │ │
│ │ Validating respondent data...                       │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ [Cancel Task]                                           │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ Footer:                                                 │
│ [Close] (disabled while task running)                   │
└─────────────────────────────────────────────────────────┘
```

### 3. Pure HTMX Approach

Following the pattern from `selection_progress_modal.html`:

- Server controls all state (close button enabled/disabled)
- HTMX polls `/selection/replacement-modal-progress/<run_id>` for updates
- Entire modal content is swapped via `hx-swap="outerHTML"`
- No Alpine.js state synchronization needed

**Key HTMX attributes:**
```html
<div id="replacement-modal"
     {% if current_replacement and not run_record.has_finished %}
         hx-get="/assembly/.../selection/replacement-modal-progress/..."
         hx-trigger="every 2s"
         hx-swap="outerHTML"
     {% endif %}>
```

### 4. State Transitions

```
┌──────────────────┐
│  Selection Page  │
│  (no modal)      │
└────────┬─────────┘
         │ Click "Go to Replacement Selection"
         ▼
┌──────────────────┐
│  Modal: Form     │ ?replacement_modal=open
│  (no task yet)   │
└────────┬─────────┘
         │ Click "Check Spreadsheet" (POST)
         │ Starts load task
         ▼
┌──────────────────┐
│  Modal: Progress │ ?current_replacement=<run_id>
│  (load running)  │ HTMX polling
└────────┬─────────┘
         │ Task completes
         │ Server includes min/max in response
         ▼
┌──────────────────┐
│  Modal: Form     │ ?current_replacement=<run_id>&min_select=3&max_select=15
│  (with min/max)  │ (task finished, form shown)
└────────┬─────────┘
         │ Click "Run Replacements" (POST)
         │ Starts selection task
         ▼
┌──────────────────┐
│  Modal: Progress │ ?current_replacement=<new_run_id>
│  (select running)│ HTMX polling
└────────┬─────────┘
         │ Task completes (success/fail/cancel)
         ▼
┌──────────────────┐
│  Modal: Result   │ Close button enabled
│  (can close)     │
└────────┬─────────┘
         │ Click Close / Escape / Backdrop
         ▼
┌──────────────────┐
│  Selection Page  │ ?replacement_modal (removed)
│  (refreshed)     │ History updated
└──────────────────┘
```

### 5. Backend Route Changes

**File:** `src/opendlp/entrypoints/blueprints/backoffice.py`

#### 5.1 Update `view_assembly_selection`

Add handling for replacement modal parameters:

```python
# Existing: current_selection for initial selection modal
current_selection_str = request.args.get("current_selection")

# NEW: replacement modal parameters
replacement_modal_open = request.args.get("replacement_modal") == "open"
current_replacement_str = request.args.get("current_replacement")
current_replacement: uuid.UUID | None = None
replacement_run_record = None
replacement_log_messages: list = []
replacement_min_select: int | None = request.args.get("min_select", type=int)
replacement_max_select: int | None = request.args.get("max_select", type=int)

if current_replacement_str:
    try:
        current_replacement = uuid.UUID(current_replacement_str)
        check_and_update_task_health(uow, current_replacement)
        result = get_selection_run_status(uow, current_replacement)

        if result.run_record and result.run_record.assembly_id == assembly_id:
            replacement_run_record = result.run_record
            replacement_log_messages = result.log_messages
            # If load task completed, extract min/max
            if isinstance(result, LoadRunResult) and result.features and result.success:
                replacement_min_select = minimum_selection(result.features)
                replacement_max_select = maximum_selection(result.features)
    except (ValueError, NotFoundError):
        current_replacement = None
```

Pass to template:
```python
return render_template(
    "backoffice/assembly_selection.html",
    # ... existing vars ...
    replacement_modal_open=replacement_modal_open or current_replacement is not None,
    current_replacement=current_replacement,
    replacement_run_record=replacement_run_record,
    replacement_log_messages=replacement_log_messages,
    replacement_min_select=replacement_min_select,
    replacement_max_select=replacement_max_select,
)
```

#### 5.2 Add replacement modal progress endpoint

```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/selection/replacement-modal-progress/<uuid:run_id>")
@login_required
def replacement_progress_modal(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Return replacement modal progress HTML fragment for HTMX polling."""
    # Similar to selection_progress_modal but renders replacement_modal.html
    # Include min_select/max_select when load task completes
```

#### 5.3 Update redirect URLs

Change all replacement redirects to use query parameters:

```python
# OLD:
url_for("backoffice.view_assembly_replacement_with_run", assembly_id=assembly_id, run_id=task_id)

# NEW:
url_for("backoffice.view_assembly_selection", assembly_id=assembly_id, current_replacement=task_id)
```

Affected routes:
- `start_replacement_load` → redirect to `?current_replacement=<task_id>`
- `start_replacement_run` → redirect to `?current_replacement=<task_id>`
- `cancel_replacement_run` → redirect to `?current_replacement=<task_id>`

#### 5.4 Convert legacy routes to redirects

```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/replacement")
@login_required
def view_assembly_replacement(assembly_id: uuid.UUID):
    """Legacy route - redirects to selection page with modal open."""
    return redirect(url_for("backoffice.view_assembly_selection",
                            assembly_id=assembly_id,
                            replacement_modal="open"))

@backoffice_bp.route("/assembly/<uuid:assembly_id>/replacement/<uuid:run_id>")
@login_required
def view_assembly_replacement_with_run(assembly_id: uuid.UUID, run_id: uuid.UUID):
    """Legacy route - redirects to query parameter version."""
    # Preserve min/max params if present
    min_select = request.args.get("min_select")
    max_select = request.args.get("max_select")
    return redirect(url_for("backoffice.view_assembly_selection",
                            assembly_id=assembly_id,
                            current_replacement=run_id,
                            min_select=min_select,
                            max_select=max_select))
```

### 6. Template Changes

#### 6.1 `assembly_selection.html`

Replace the "Go to Replacement Selection" button with a link that opens the modal:

```jinja2
{# Replacement Selection Card #}
{% call card(title=_("Replacement Selection"), composed=true) %}
    {% call card_body() %}
        <p class="text-body-md mb-4" style="color: var(--color-body-text);">
            {{ _("Select replacement participants when original selections decline or cannot participate.") }}
        </p>
        <p class="text-body-sm" style="color: var(--color-secondary-text);">
            {{ _("First check the spreadsheet to see how many replacement participants are available.") }}
        </p>
    {% endcall %}
    {% call card_footer() %}
        {# Changed from href to button that triggers modal via query param #}
        <a href="{{ url_for('backoffice.view_assembly_selection', assembly_id=assembly.id, replacement_modal='open') }}"
           class="...button styles...">
            {{ _("Go to Replacement Selection") }}
        </a>
    {% endcall %}
{% endcall %}

{# Replacement Selection Modal - shown when replacement_modal or current_replacement param present #}
{% if replacement_modal_open %}
    {% include "backoffice/components/replacement_modal.html" %}
{% endif %}
```

#### 6.2 Delete `assembly_replacement.html`

This template is no longer needed as all replacement functionality moves into the modal.

### 7. Form Actions

Forms inside the modal POST to existing endpoints but with updated redirects:

```html
{# Check Spreadsheet form #}
<form method="post"
      action="{{ url_for('backoffice.start_replacement_load', assembly_id=assembly.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    {{ button(_("Check Spreadsheet"), type="submit", variant="primary") }}
</form>

{# Run Replacements form #}
<form method="post"
      action="{{ url_for('backoffice.start_replacement_run', assembly_id=assembly.id, min_select=min_select, max_select=max_select) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="number" name="number_to_select" min="{{ min_select }}" max="{{ max_select }}" required>
    {{ button(_("Run Replacements"), type="submit", variant="primary") }}
</form>
```

### 8. Close Behavior

**Close URL:** `url_for('backoffice.view_assembly_selection', assembly_id=assembly.id)`

- Removes all replacement-related query params
- Page refreshes showing updated Selection History
- Close button disabled while task is pending/running
- Escape key only works when task is finished
- Backdrop click only works when task is finished

### 9. Selection History Integration

The Selection History table on `/selection` already shows all task types including replacement tasks. When the modal closes after a replacement task completes, the history will show the new entry.

## Implementation Checklist

### Phase 1: Backend routes ✅
- [x] Add `replacement_modal_open`, `current_replacement`, `replacement_*` vars to `view_assembly_selection`
- [x] Add `replacement_progress_modal` endpoint for HTMX polling
- [x] Update `start_replacement_load` redirect to use query params (via legacy redirects)
- [x] Update `start_replacement_run` redirect to use query params (via legacy redirects)
- [x] Update `cancel_replacement_run` redirect to use query params (via legacy redirects)
- [x] Convert `view_assembly_replacement` to redirect with `?replacement_modal=open`
- [x] Convert `view_assembly_replacement_with_run` to redirect with `?current_replacement=<id>`

### Phase 2: Frontend templates ✅
- [x] Create `replacement_modal.html` template
  - [x] Initial form state (Check Spreadsheet)
  - [x] Form with min/max state (Run Replacements)
  - [x] Progress state (task running)
  - [x] Result state (completed/failed/cancelled)
  - [x] HTMX polling attributes
  - [x] Close button with disabled state
  - [x] Escape key handler (vanilla JS)
- [x] Update `assembly_selection.html` to include modal
- [x] Update "Go to Replacement Selection" button to use query param link

### Phase 3: Cleanup ✅
- [x] Delete `assembly_replacement.html` template
- [x] Remove `replacement_progress` JSON endpoint (used by old Alpine.js polling)
- [x] Legacy redirect routes retained for backwards compatibility:
  - `view_assembly_replacement` → redirects to `?replacement_modal=open`
  - `view_assembly_replacement_with_run` → redirects to `?current_replacement=<id>`

## Testing Checklist

- [ ] Click "Go to Replacement Selection" → URL is `/selection?replacement_modal=open`
- [ ] Modal opens with form content
- [ ] "Check Spreadsheet" starts load task, URL becomes `?current_replacement=<uuid>`
- [ ] Modal shows progress with HTMX polling
- [ ] Close button disabled while task runs
- [ ] Escape key does not close modal while running
- [ ] Backdrop click does not close modal while running
- [ ] After load completes, form appears with min/max values
- [ ] "Run Replacements" starts selection task
- [ ] Progress shows for selection task
- [ ] Cancel button cancels running task
- [ ] After task completes, close button enabled
- [ ] Closing modal refreshes page
- [ ] Selection History shows completed replacement task
- [ ] Old URLs `/replacement` and `/replacement/<uuid>` redirect correctly
- [ ] Pagination and other page features work while modal is open
