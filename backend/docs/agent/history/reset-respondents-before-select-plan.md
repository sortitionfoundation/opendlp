# Plan: Reset Respondents Before Selection

## Problem

When a user navigates to the DB Selection page and some respondents already have non-POOL status (SELECTED, CONFIRMED, WITHDRAWN, etc.), the selection will only operate on the POOL respondents. This is because the `OpenDLPDataAdapter` (with `eligible_only=True`, the default) filters to `status=RespondentStatus.POOL`.

This can be confusing: the user might expect a fresh selection across everyone, but silently only gets a selection from the remaining pool. There are two legitimate workflows when non-POOL respondents exist:

1. **Replacements** — keep current selections, pick replacements from the pool (not yet implemented for DB selection)
2. **Fresh selection after reset** — reset everyone to POOL first, then run selection (common during test selections before all respondents are gathered)

## Current State

- **Selection page** (`templates/db_selection/select.html`): Shows "Run Selection", "Run Test Selection", and "Check Targets & Respondents" buttons with no awareness of respondent statuses.
- **Selection service** (`service_layer/sortition.py:start_db_select_task`): No pre-check for non-POOL respondents; just starts the Celery task.
- **Data adapter** (`adapters/sortition_data_adapter.py`): Silently filters to POOL-only when `eligible_only=True`.
- **Reset functionality** (`service_layer/respondent_service.py:reset_selection_status`): Already exists, calls `uow.respondents.reset_all_to_pool(assembly_id)`.
- **Reset button** (`blueprints/respondents.py:reset_respondent_status`): Already exists on the respondents page, redirects back to the respondents page after reset.
- **Replacement page** (`templates/db_selection/replace.html`): Placeholder "coming soon" page exists.

## Design

### Data Flow

Add a check in the `view_db_selection` route (and `view_db_selection_with_run`) to determine whether any respondents have non-POOL status. Pass this information to the template so it can conditionally show appropriate UI.

### Service Layer Changes

**New function in `respondent_service.py`:**

```python
def has_non_pool_respondents(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> bool:
    """Check if any respondents for this assembly have non-POOL status."""
```

This queries the repository to check if `count_by_assembly_id(assembly_id) > count_with_status(assembly_id, POOL)` or similar. The repository likely needs a small helper or we can use the existing `get_by_assembly_id` with status filtering.

**Repository addition** (if needed): Add `count_non_pool(assembly_id) -> int` to the respondent repository for efficiency (avoids loading all respondents just to check). This returns the count of respondents whose `selection_status != POOL`.

### Blueprint Changes

**`blueprints/db_selection.py` — `view_db_selection` and `view_db_selection_with_run`:**

- Query `has_non_pool_respondents()` and pass the result (e.g., `has_non_pool`) to the template.
- Also pass the count of non-pool respondents for a more informative message (e.g., "12 respondents are already selected/confirmed/withdrawn").

**`blueprints/respondents.py` — `reset_respondent_status`:**

- Accept an optional `redirect_to` query parameter (or form field). If `redirect_to=db_selection`, redirect to the DB selection page instead of the respondents page. This allows the reset button on the selection page to send the user back to selection after resetting.

Alternatively (simpler): add a new route in `db_selection_bp` that calls the same `reset_selection_status` service function but redirects to the selection page. This avoids coupling between blueprints.

**Recommended approach:** Add a new POST route in `db_selection_bp`:

```python
@db_selection_bp.route("/assemblies/<uuid:assembly_id>/db_select/reset-respondents", methods=["POST"])
```

This calls `reset_selection_status()` from `respondent_service` and redirects back to `db_selection.view_db_selection`.

### Template Changes

**`templates/db_selection/select.html`:**

When `has_non_pool` is true and no run is in progress, show a warning panel *above* the action buttons:

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠ Some respondents already have selection status             │
│                                                              │
│ N respondents are already SELECTED, CONFIRMED, or other      │
│ non-pool status. A fresh selection will only draw from the   │
│ remaining pool.                                              │
│                                                              │
│ Your options:                                                │
│ • Do replacements (link to replacement page)                 │
│ • Reset all respondents to Pool status, then run selection   │
│                                                              │
│ [Reset all respondents to Pool]  (warning button)            │
└──────────────────────────────────────────────────────────────┘
```

When `has_non_pool` is true:
- **Disable** the "Run Selection" and "Run Test Selection" buttons (add `disabled` attribute)
- Keep "Check Targets & Respondents" enabled (checking data with only POOL respondents is still valid and useful)
- Show the warning panel with:
  - A link to the replacements page (`db_selection.view_db_replacement`)
  - A "Reset all respondents to Pool" button that POSTs to the new `db_select/reset-respondents` route
  - The reset button should have a confirmation dialog (like the existing one on the respondents page)

When `has_non_pool` is false:
- Show the normal buttons as today, no warning panel

## Implementation Steps

### Step 1: Repository — add `count_non_pool` method

Add to `AbstractRespondentRepository` and `SqlAlchemyRespondentRepository`:

```python
def count_non_pool(self, assembly_id: uuid.UUID) -> int:
```

Queries respondents where `assembly_id` matches and `selection_status != POOL`. Also add to `FakeRespondentRepository` for tests.

### Step 2: Service layer — add `count_non_pool_respondents`

Add to `respondent_service.py`:

```python
def count_non_pool_respondents(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> int:
```

Simple pass-through to the repository method. No permission check needed since this is called from within views that already have `@require_assembly_management`.

### Step 3: Blueprint — add reset route and pass data to template

- Add `POST /assemblies/<uuid:assembly_id>/db_select/reset-respondents` route to `db_selection_bp`
- Modify `view_db_selection` and `view_db_selection_with_run` to query and pass `non_pool_count` to the template

### Step 4: Template — add conditional warning panel

Update `templates/db_selection/select.html`:
- Add warning panel when `non_pool_count > 0`
- Disable selection buttons when `non_pool_count > 0`
- Add reset button inside the warning panel
- Keep existing "Check Targets & Respondents" button always enabled

### Step 5: Tests

**Unit tests:**
- Test `count_non_pool` repository method (in `test_respondent_repository.py`)
- Test `count_non_pool_respondents` service function (in `test_respondent_service.py`)

**E2E tests** (in `test_db_selection_routes.py`):
- Test selection page shows warning when non-POOL respondents exist
- Test selection buttons are disabled when non-POOL respondents exist
- Test reset route resets respondents and redirects to selection page
- Test selection page shows normal buttons when all respondents are POOL
- Test "Check Targets & Respondents" button remains enabled even with non-POOL respondents

### Step 6: i18n

Run `just translate-regen` after adding new translatable strings.

## Questions / Decisions for Doctor Chewie

1. **Should we completely hide vs disable the selection buttons?** Plan above says disable them with a message explaining why. Hiding might be cleaner but gives less context.

COMMENT: I think disable is better - it could confuse the user to come to the selection page and not see the buttons.

2. **Should "Check Targets & Respondents" remain enabled?** It will only check POOL respondents, which is still useful to verify data before resetting. But it could be confusing if the user doesn't realise it's only checking the pool subset.

COMMENT: Maybe we make it have a confirm pop up saying "this will only check against those who are in the pool so it may give misleading warnings. Are you sure you want to run the checks?"  If the user primarily wants to check the targets are self consistent it is still useful. Or maybe that is too much. Actually: just leave it enabled with no other changes. I'll do some user testing after this change and base further changes on that.

3. **The replacement page is currently a placeholder.** The link to "do replacements" will go to a "coming soon" page. Is that acceptable, or should we omit that option until replacements are implemented?

COMMENT: Yes it is acceptable to go the "coming soon" page.
