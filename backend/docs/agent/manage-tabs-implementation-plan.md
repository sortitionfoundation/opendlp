# Phase 4: Manage Generated Tabs Implementation Plan

**Branch:** `manage-gsheet-tabs`
**Last Updated:** 2026-03-11

## Overview

Implement the "Manage Generated Tabs" feature in the backoffice Selection tab. This allows users to list and delete old selection output tabs from their Google Spreadsheet.

## Design Decision: Modal vs Inline

**Decision: Use modal pattern with query parameters**

Rationale:
- Follows existing selection pattern (`?current_selection=<uuid>`)
- Progress states (LIST_RUNNING, DELETE_RUNNING) need polling UI
- Consistent UX with other task-based operations
- Tab list display fits well in modal format

Query parameter: `?current_manage_tabs=<uuid>`

## Files to Modify

### 1. Routes: `src/opendlp/entrypoints/blueprints/backoffice.py`

**Add 4 new routes** (after `cancel_selection_run` at line ~438):

| Route | Method | Function |
|-------|--------|----------|
| `/assembly/<id>/manage-tabs/start-list` | POST | Start LIST_OLD_TABS task |
| `/assembly/<id>/manage-tabs/start-delete` | POST | Start DELETE_OLD_TABS task |
| `/assembly/<id>/manage-tabs/<run_id>/progress` | GET | HTMX modal polling |
| `/assembly/<id>/manage-tabs/<run_id>/cancel` | POST | Cancel running task |

**Update `view_assembly_selection`** (lines 191-279):
- Add handling for `current_manage_tabs` query parameter
- Fetch manage tabs run record when present
- Get tab names from result for display
- Pass additional context to template

### 2. Template: `templates/backoffice/assembly_selection.html`

Update the Manage Generated Tabs card:
- Enable the "List Old Tabs" button (currently disabled)
- Add form to POST to `start-list` route
- Conditionally include modal when `current_manage_tabs` is set

### 3. New Template: `templates/backoffice/components/manage_tabs_progress_modal.html`

Create modal component with HTMX polling:
- Uses existing `progress_modal()` macro from modal.html
- Shows spinner and status badge during LIST_RUNNING/DELETE_RUNNING
- Shows tab list when LIST_COMPLETED
- Shows "Delete These Tabs" button when LIST_COMPLETED with tabs found
- Shows success message when DELETE_COMPLETED
- Shows error message on ERROR state
- Cancel button during running states
- Close/Done button on terminal states

## Implementation Steps

### Step 1: Add routes to backoffice.py

Location: After `cancel_selection` route (~line 423)

Routes to add:
1. `start_manage_tabs_list(assembly_id)` - POST
2. `start_manage_tabs_delete(assembly_id)` - POST
3. `manage_tabs_progress(assembly_id, run_id)` - GET
4. `cancel_manage_tabs(assembly_id, run_id)` - POST

### Step 2: Update view_assembly_selection route

Add handling for `current_manage_tabs` query parameter:
```python
current_manage_tabs = request.args.get("current_manage_tabs", type=uuid.UUID)
if current_manage_tabs:
    # Fetch run record and compute status
    manage_tabs_run_record = ...
    manage_tabs_status = get_manage_old_tabs_status(...)
```

### Step 3: Create manage_tabs_progress_modal.html

Structure:
```jinja
{% from "backoffice/components/modal.html" import progress_modal, spinner, status_badge, ... %}

{% call progress_modal(title, can_close, close_url, hx_get, hx_trigger) %}
    {# Status and spinner for running states #}
    {# Tab list for LIST_COMPLETED #}
    {# Success message for DELETE_COMPLETED #}
    {# Error message for ERROR #}
    {# Action buttons in footer #}
{% endcall %}
```

### Step 4: Update assembly_selection.html

Enable Manage Tabs card:
```jinja
{% call card_footer() %}
    {% if current_manage_tabs %}
        {# Include modal #}
        {% include "backoffice/components/manage_tabs_progress_modal.html" %}
    {% endif %}

    <form method="post" action="{{ url_for('backoffice.start_manage_tabs_list', assembly_id=assembly.id) }}">
        {{ button(_("List Old Tabs"), variant="outline") }}
    </form>
{% endcall %}
```

## State Flow

```
FRESH → click "List Old Tabs" → LIST_RUNNING → LIST_COMPLETED
                                      ↓
                              (if tabs found)
                                      ↓
              click "Delete These Tabs" → DELETE_RUNNING → DELETE_COMPLETED
```

## Service Layer Functions Used

From `src/opendlp/service_layer/sortition.py`:
- `start_gsheet_manage_tabs_task(uow, user_id, assembly_id, dry_run=True/False)`
- `get_selection_run_status(uow, run_id)`
- `get_manage_old_tabs_status(result)` - Returns ManageOldTabsStatus
- `cancel_task(uow, run_id)`

## Testing

### Manual Testing
1. Navigate to Selection tab with configured GSheet
2. Click "List Old Tabs" - modal should appear with progress
3. Wait for completion - should show list of tabs (or "No old tabs found")
4. If tabs found, click "Delete These Tabs" - modal shows deletion progress
5. Wait for completion - should show success message
6. Test cancel button during running states
7. Test error handling (e.g., spreadsheet access issues)

### BDD Tests (Future)
- Test list tabs flow
- Test delete tabs flow
- Test cancel functionality
- Test error states

## Detailed Implementation

### Step 0: Update imports (backoffice.py:33-40)

Add `start_gsheet_manage_tabs_task` to the sortition imports:
```python
from opendlp.service_layer.sortition import (
    InvalidSelection,
    cancel_task,
    check_and_update_task_health,
    get_selection_run_status,
    start_gsheet_load_task,
    start_gsheet_manage_tabs_task,  # NEW
    start_gsheet_select_task,
)
```

### Step 1: Update view_assembly_selection (backoffice.py:191-279)

Add after line 205 (`translated_report_html = ""`):
```python
# Manage tabs variables
current_manage_tabs_param = request.args.get("current_manage_tabs")
current_manage_tabs: uuid.UUID | None = None
manage_tabs_run_record = None
manage_tabs_tab_names: list = []
```

Add handling block after the `current_selection` handling (around line 232):
```python
# Handle current_manage_tabs parameter for showing manage tabs modal
if current_manage_tabs_param:
    try:
        current_manage_tabs = uuid.UUID(current_manage_tabs_param)
        check_and_update_task_health(uow, current_manage_tabs)
        result = get_selection_run_status(uow, current_manage_tabs)
        if result.run_record and result.run_record.assembly_id == assembly_id:
            manage_tabs_run_record = result.run_record
            # Get tab names from TabManagementResult if available
            if hasattr(result, 'tab_names') and result.tab_names:
                manage_tabs_tab_names = result.tab_names
        else:
            current_manage_tabs = None
    except (ValueError, TypeError):
        current_manage_tabs = None
```

Add to render_template context:
```python
current_manage_tabs=current_manage_tabs,
manage_tabs_run_record=manage_tabs_run_record,
manage_tabs_tab_names=manage_tabs_tab_names,
```

### Step 2: Add routes (after cancel_selection_run ~line 438)

**start_manage_tabs_list:**
```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/start-list", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_list(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start listing old tabs task."""
    uow = bootstrap.bootstrap()
    with uow:
        task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=True)
    return redirect(url_for("backoffice.view_assembly_selection",
                            assembly_id=assembly_id, current_manage_tabs=task_id))
```

**start_manage_tabs_delete:**
```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/start-delete", methods=["POST"])
@login_required
@require_assembly_management
def start_manage_tabs_delete(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Start deleting old tabs task."""
    uow = bootstrap.bootstrap()
    with uow:
        task_id = start_gsheet_manage_tabs_task(uow, current_user.id, assembly_id, dry_run=False)
    return redirect(url_for("backoffice.view_assembly_selection",
                            assembly_id=assembly_id, current_manage_tabs=task_id))
```

**manage_tabs_progress:**
```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/progress")
@login_required
@require_assembly_management
def manage_tabs_progress(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """HTMX endpoint for manage tabs progress modal."""
    # Similar to selection_progress_modal but renders manage_tabs_progress_modal.html
    # Returns HTML fragment for HTMX swap
```

**cancel_manage_tabs:**
```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/manage-tabs/<uuid:run_id>/cancel", methods=["POST"])
@login_required
@require_assembly_management
def cancel_manage_tabs(assembly_id: uuid.UUID, run_id: uuid.UUID) -> ResponseReturnValue:
    """Cancel a running manage tabs task."""
    # Similar to cancel_selection_run
```

### Step 3: Create manage_tabs_progress_modal.html

New file: `templates/backoffice/components/manage_tabs_progress_modal.html`

Based on `selection_progress_modal.html` structure:
- Import modal macros
- Use progress_modal with HTMX polling
- Show status badge and spinner during running states
- **Display tab list when LIST_COMPLETED** (key difference)
- Show "Delete These Tabs" button when tabs found
- Show success message when DELETE_COMPLETED
- Cancel button during running, Close button when finished

Tab list display (when LIST_COMPLETED with tabs):
```jinja
{% if manage_tabs_run_record.is_completed and manage_tabs_tab_names %}
    <div class="mb-4">
        <span class="text-body-md font-medium">{{ _("Found tabs:") }}</span>
        <ul class="list-disc ml-6 mt-2">
            {% for tab_name in manage_tabs_tab_names %}
                <li class="text-body-sm">{{ tab_name }}</li>
            {% endfor %}
        </ul>
    </div>
    <form method="post" action="{{ url_for('backoffice.start_manage_tabs_delete', assembly_id=assembly.id) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        {{ button(_("Delete These Tabs"), type="submit", variant="primary") }}
    </form>
{% elif manage_tabs_run_record.is_completed %}
    <div class="mb-4">
        <span class="text-body-md" style="color: var(--color-success-text);">
            {{ _("No old tabs found.") }}
        </span>
    </div>
{% endif %}
```

### Step 4: Update assembly_selection.html

Update Manage Generated Tabs card (lines 273-289):
```jinja
{% call card_footer() %}
    {% if current_manage_tabs %}
        {% include "backoffice/components/manage_tabs_progress_modal.html" %}
    {% endif %}

    {% if gsheet %}
        <form method="post" action="{{ url_for('backoffice.start_manage_tabs_list', assembly_id=assembly.id) }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            {{ button(_("List Old Tabs"), variant="outline") }}
        </form>
    {% else %}
        {{ button(_("List Old Tabs"), variant="outline", disabled=true) }}
    {% endif %}
{% endcall %}
```

## Verification

### Manual Testing
1. Navigate to `/backoffice/assembly/<id>/selection` with configured GSheet
2. Click "List Old Tabs" in Manage Generated Tabs card
3. Modal appears with progress, polls every 2 seconds
4. On completion, shows tab list (or "No old tabs found")
5. If tabs found, click "Delete These Tabs"
6. Modal shows deletion progress
7. On completion, shows success message
8. Click "Close" to dismiss modal
9. Test cancel button during running state
10. Test without GSheet configured (button should be disabled)

### Test Edge Cases
- Cancel during list operation
- Cancel during delete operation
- Error handling (spreadsheet access issues)
- Empty tab list
- Large number of tabs

## Reference Files

- Selection routes pattern: `backoffice.py:191-438`
- Selection progress modal: `selection_progress_modal.html`
- Old manage tabs implementation: `gsheets.py:742-961`
- ManageOldTabsStatus: `domain/value_objects.py`
- Service functions: `service_layer/sortition.py:307-370, 710-729`
