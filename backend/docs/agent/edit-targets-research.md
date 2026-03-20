# Editable Targets: Research & Design Analysis

## Current State

### Domain Model

Targets are a two-level nested structure:

- **TargetCategory** — top level (e.g. "Gender", "Age"). Has `id`, `assembly_id`, `name`, `description`, `sort_order`, `values[]`. Stored as a DB row in `target_categories`.
- **TargetValue** — second level (e.g. "Male" min=12 max=17). A dataclass with `value`, `min`, `max`, `min_flex`, `max_flex`, `percentage_target`, `description`, `value_id`. Stored as **JSON inside the TargetCategory row** via `TargetValueListJSON`. Note: `min_flex` and `max_flex` are advanced concepts not exposed to users — they always default to `min_flex=0` and `max_flex=MAX_FLEX_UNSET` and should not be editable in the UI.

Key constraints:
- Category names are unique per assembly (DB unique index)
- Value names are unique per category (enforced in `add_value()`)
- `min >= 0`, `max >= min`
- Flex constraints exist (`min_flex <= min`, `max_flex >= max`) but are not user-facing
- Values are validated on construction (`__post_init__`)

### Current UI & Capabilities

- **View**: Read-only GOV.UK table showing categories with rowspan, values, min/max
- **Create/Replace**: CSV upload only, always replaces all categories (`replace_existing=True`)
- **No individual CRUD**: No routes for editing a single category/value, deleting one category, reordering, etc.

### Service Layer

- `create_target_category()` — exists but unused by any route
- `get_targets_for_assembly()` — used by view route
- `import_targets_from_csv()` — used by upload route
- Repository has `delete()` and `delete_all_for_assembly()` — only bulk delete is used

### Key Files

| Layer | File | Lines |
|-------|------|-------|
| Domain | `src/opendlp/domain/targets.py` | Full file |
| ORM | `src/opendlp/adapters/orm.py` | 165–204 (JSON type), 407–428 (table) |
| Repository | `src/opendlp/adapters/sql_repository.py` | 801–834 |
| Service | `src/opendlp/service_layer/assembly_service.py` | 440–574 |
| Routes | `src/opendlp/entrypoints/blueprints/targets.py` | Full file |
| Template | `templates/targets/view_targets.html` | Full file |
| Form | `src/opendlp/entrypoints/forms.py` | 539–549 |

---

## Design Questions & Recommendations

### 1. Save Strategy: Immediate vs Build-then-save

**Option A: Build in browser, save all at once**
- The entire target tree is assembled client-side (Alpine.js state), then POSTed as a single JSON payload
- Pros: No partial states in DB; simpler rollback; works offline; single transaction
- Cons: Complex client-side state management; risk of losing work on navigation; validation only at submission time; large Alpine component

**Option B: Immediate server-side saves (HTMX per-action)**
- Each add/edit/delete operation is a separate HTMX request that persists immediately
- Pros: No lost work; server-side validation with immediate feedback; simpler client code; matches existing HTMX patterns
- Cons: Partial/inconsistent states possible; more endpoints; more DB transactions

**Option C: Hybrid — build in browser with server-side validation**
- Alpine.js manages the tree state. On each change, an HTMX request validates but doesn't persist. A final "Save" button persists the whole tree.
- Pros: Immediate validation feedback; no partial DB state; good UX
- Cons: Most complex; needs a validation-only endpoint; session or hidden state management

**Recommendation: Option B (immediate saves)**

Reasons:
1. Matches the existing project patterns (traditional form submissions, HTMX for partials)
2. The data structure is simple enough that partial states aren't dangerous — an assembly with 2 of 3 categories saved is not broken
3. Server-side validation gives immediate, trustworthy feedback
4. Less client-side JavaScript to maintain and audit for CSP compliance
5. The sortition-algorithms validation lives in Python — easier to call server-side
6. Each category is independent (no cross-category constraints), so saving them individually is natural
7. Values within a category are dependent (stored as JSON in one row), so a category + its values should be saved atomically — which fits perfectly since they're one DB row

### 2. UI Structure

The page should have three modes of interaction:

#### a) Category-level operations
- **Add category**: A form at the bottom (or triggered by a button) to add a new empty category with a name
- **Delete category**: A delete button per category with confirmation (existing `$confirm` pattern)
- **Rename category**: Inline edit of category name
- **Reorder categories**: Change `sort_order` — could be simple up/down arrows or a sort_order number input

#### b) Value-level operations (within a category)
- **Add value**: A form row within the category to add value name + min + max
- **Edit value**: Inline editing of value name, min, max
- **Delete value**: Remove button per value row

Note: `min_flex` and `max_flex` are not exposed in the UI. They use their defaults (`0` and `MAX_FLEX_UNSET` respectively) and are preserved as-is on edits.

#### c) Bulk import (keep existing)
- CSV upload should remain as an alternative for power users
- It already replaces everything, which is fine

### 3. HTMX + Alpine.js Integration Pattern

The recommended pattern combines HTMX for server communication with Alpine.js for local UI state:

**Page structure:**
```
[Add Category button] ──────────────────────────────

Category: Gender  [Rename] [Delete] [▲] [▼]
┌─────────┬─────┬─────┐
│ Value   │ Min │ Max │
├─────────┼─────┼─────┤
│ Male    │ 12  │ 17  │ [Edit] [Delete]
│ Female  │ 12  │ 17  │ [Edit] [Delete]
│ + Add value...       │
└─────────┴─────┴─────┘

Category: Age  [Rename] [Delete] [▲] [▼]
┌─────────┬─────┬─────┐
│ 16-29   │ 17  │ 22  │ [Edit] [Delete]
│ 30-44   │  5  │  9  │ [Edit] [Delete]
│ + Add value...       │
└─────────┴─────┴─────┘
```

**HTMX patterns to use:**

1. **Add category**: `hx-post` to create endpoint, `hx-target` swaps in the new category block, `hx-swap="beforebegin"` on the add-category form
2. **Delete category**: `hx-delete` with `hx-target` removing the category block, `hx-swap="outerHTML"` replacing with empty string, `hx-confirm` for confirmation
3. **Edit value inline**: Alpine `x-data` toggles between display and edit mode per row. On save, `hx-post`/`hx-put` sends the updated values, response replaces the row
4. **Add value**: An inline form row at the bottom of each category's value table, `hx-post` adds the value, response replaces the whole category block (since values are stored as JSON in one row, the whole category is the natural swap unit)
5. **Delete value**: `hx-delete` on the value, response replaces the whole category block

**Key insight**: Since values are stored as JSON within the category row, any value-level operation is actually a category-level update. The swap target for value operations should be the entire category block, keeping the server as the single source of truth.

**Alpine.js patterns to use:**
- `x-data="{ editing: false }"` per value row for inline edit toggle
- `x-show="editing"` / `x-show="!editing"` to swap between display and form
- `x-data="{ adding: false }"` per category for the "add value" form visibility
- All complex logic in registered `Alpine.data()` components (CSP-safe)

### 4. Validation & User Feedback

**Server-side validation** (on every HTMX request):
- Category name not empty, unique per assembly
- Value name not empty, unique per category
- min/max constraints (delegated to `TargetValue.__post_init__`; flex fields use defaults)
- Return appropriate error HTML fragments that HTMX swaps in

**Feedback patterns:**
- **Success**: Flash message or inline success indicator, swap in updated content
- **Validation error**: Return the form with error messages highlighted (GOV.UK error pattern), HTTP 422 so HTMX can handle it
- **Server error**: Flash message

**HTMX error handling:**
- Use `hx-target-error` or response codes to show errors inline rather than replacing content with an error page
- 422 responses should return the form fragment with validation errors displayed
- Configure `htmx.config.responseHandling` or use `hx-on::response-error` if needed

### 5. Required Backend Changes

#### New service layer functions needed:

```python
def update_target_category(uow, user_id, assembly_id, category_id, name, description, sort_order) -> TargetCategory
def delete_target_category(uow, user_id, assembly_id, category_id) -> None
def add_target_value(uow, user_id, assembly_id, category_id, value, min, max) -> TargetCategory
def update_target_value(uow, user_id, assembly_id, category_id, value_id, value, min, max) -> TargetCategory
def delete_target_value(uow, user_id, assembly_id, category_id, value_id) -> TargetCategory
def reorder_target_categories(uow, user_id, assembly_id, ordered_category_ids) -> list[TargetCategory]
```

Note: Value operations return the whole TargetCategory since they modify the JSON column.

#### New routes needed:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/assemblies/<aid>/targets/categories` | Add category |
| PUT | `/assemblies/<aid>/targets/categories/<cid>` | Update category name/description |
| DELETE | `/assemblies/<aid>/targets/categories/<cid>` | Delete category |
| POST | `/assemblies/<aid>/targets/categories/<cid>/reorder` | Move category up/down |
| POST | `/assemblies/<aid>/targets/categories/<cid>/values` | Add value |
| PUT | `/assemblies/<aid>/targets/categories/<cid>/values/<vid>` | Update value |
| DELETE | `/assemblies/<aid>/targets/categories/<cid>/values/<vid>` | Delete value |

All routes return HTML fragments for HTMX to swap in.

#### Repository changes:
- No changes needed — `add()`, `get()`, `delete()` already exist
- Updates are handled by SQLAlchemy dirty tracking (modify the object, commit)

### 6. Template Structure

Recommended template decomposition:

```
templates/targets/
    view_targets.html              -- Full page (existing, modified)
    components/
        category_block.html        -- Single category with its values table
        category_form.html         -- Add/edit category form
        value_row.html             -- Single value display row
        value_form_row.html        -- Add/edit value form row
```

The `category_block.html` is the key fragment — it's the HTMX swap target for all value-level operations. It renders:
- Category header with name, edit/delete/reorder controls
- Values table with edit/delete per row
- "Add value" form (hidden by default, toggled by Alpine)

### 7. Progressive Enhancement

The edit UI should work without JavaScript as a baseline (forms submit normally), with HTMX enhancing the experience. This matches GOV.UK design principles.

- Without JS: Forms POST/redirect/GET as normal Flask routes
- With HTMX: Same forms use `hx-post` etc. for seamless in-page updates
- Routes detect HTMX requests via `request.headers.get("HX-Request")` and return fragments vs full pages accordingly

### 8. Migration Considerations

- No DB migration needed — the table schema doesn't change
- Values are already stored as JSON, so adding/editing values is just updating that column
- The CSV upload should remain as-is alongside the new editing UI
- Existing tests continue to pass since we're adding, not modifying

### 9. Scope Estimate

**Phase 1 — Category CRUD (smallest useful increment):**
- Add/delete categories via the UI
- ~3 new service functions, ~3 new routes, ~2 template fragments

**Phase 2 — Value CRUD:**
- Add/edit/delete values within categories
- ~3 new service functions, ~3 new routes, ~2 template fragments
- Alpine component for inline editing

**Phase 3 — Polish:**
- Reorder categories (up/down arrows)
- Inline category rename
- Validation of cross-category constraints (e.g. total quotas vs assembly size)

CSV upload remains throughout as a bulk/power-user alternative.
