# Enhance Targets Page: Summary Statistics & Respondent Data

## Goal

Add useful numeric summaries and respondent-awareness to the targets page, so organisers can see at a glance how their targets relate to the actual respondent pool.

---

## Research Summary

### Current State

- **`view_assembly_targets`** (targets.py:48) renders `view_targets.html`, passing `target_categories`, `assembly`, forms, and `can_manage`.
- **`category_block.html`** renders each category with a values table (columns: Value, Min, Max, Actions). Uses HTMX for all CRUD; Alpine.js for inline edit toggle.
- **Respondent attributes** are stored as a JSON dict on each `Respondent.attributes` field (e.g. `{"Gender": "Male", "Age": "25-34", ...}`).
- **`get_respondent_attribute_columns(uow, assembly_id)`** in `respondent_service.py:224` returns sorted list of attribute column names by sampling the first respondent.
- **`get_attribute_columns()`** in `sql_repository.py:943` just reads keys from one respondent's attributes dict.
- There is currently **no** service function to count respondents by attribute value, or to get distinct values for a given attribute. These will need to be created.
- The HTMX partial responses (edit/add/delete value) re-render `category_block.html`. Any new data (respondent counts, totals) needs to be passed through all these render calls too.

### Key Files

| File                                                 | Role                              |
| ---------------------------------------------------- | --------------------------------- |
| `src/opendlp/entrypoints/blueprints/targets.py`      | Routes                            |
| `templates/targets/view_targets.html`                | Main page template                |
| `templates/targets/components/category_block.html`   | Per-category block (HTMX partial) |
| `src/opendlp/service_layer/respondent_service.py`    | Respondent service functions      |
| `src/opendlp/service_layer/assembly_service.py`      | Target service functions          |
| `src/opendlp/adapters/sql_repository.py`             | Repository layer                  |
| `src/opendlp/service_layer/repositories.py`          | Abstract repository interfaces    |
| `tests/fakes.py`                                     | Fake repositories for testing     |
| `tests/integration/test_targets_routes.py`           | Route-level tests                 |
| `tests/integration/test_assembly_service_targets.py` | Service-level tests               |

---

## Features to Add

### Feature 1: Min/Max Totals per Category

**What:** Show a totals row at the bottom of each category's values table with `Sum(min)` and `Sum(max)`.

**Where:** `category_block.html` — add a `<tfoot>` row to the existing `<table>`. This is pure template logic, no backend changes needed.

**Behaviour:** Updates automatically when HTMX re-renders the category block (add/edit/delete value all re-render the whole block).

### Feature 2: Respondent Counts per Value

**What:** If the assembly has respondents, and the category name matches a respondent attribute column (case-insensitive), show a "Count" column in the values table showing how many respondents have each value.

**Backend changes needed:**

1. **New repository method** on `SqlAlchemyRespondentRepository`: `get_attribute_value_counts(assembly_id, attribute_name) -> dict[str, int]` — query respondents for this assembly, count occurrences of each distinct value for the given attribute key using PostgreSQL JSON operators: `SELECT attributes->>'Gender' as val, COUNT(*) FROM respondents WHERE assembly_id = :id GROUP BY val`.
2. **New abstract method** on `AbstractRespondentRepository` in `repositories.py`.
3. **New fake method** on the fake repository in `tests/fakes.py`.
4. **New service function** in `respondent_service.py`: `get_respondent_attribute_value_counts(uow, assembly_id, attribute_name) -> dict[str, int]`.
5. **Pass data to template**: In `view_assembly_targets` and all HTMX handlers that render `category_block.html`, compute counts for categories whose names match respondent attribute columns. Pass a `respondent_counts` dict (keyed by category name) to the template context.

**Column name matching:** Use case-insensitive matching between category names and respondent attribute column names, since the sortition algorithm also does case-insensitive matching. One query per category is acceptable (unlikely to exceed ~10 categories).

**Template changes:** Add a "Respondents" column header (conditionally, when counts are available for that category) and show the count per value row. Show total in the footer row.

### Feature 3: Distinct Respondent Values for Matching Categories

**What:** If a category name matches a respondent attribute column, show the distinct values present in respondent data that are *not already* in the target values list. This helps organisers see what values exist in their data that they haven't yet defined targets for.

**Backend:** The `get_attribute_value_counts` method from Feature 2 already gives us distinct values (they're the dict keys). We just need to compute the difference in the template or view: `respondent_values - target_values`.

**Template:** Below the values table, show the missing values with an actionable "Add all missing values" button. Clicking it creates all missing values as target values with `min=0, max=0` as defaults. This uses a new HTMX endpoint.

**New endpoint:** `POST /assemblies/<id>/targets/categories/<id>/values/add-missing` — accepts a list of value names (from respondent data) and bulk-adds them with min=0, max=0. Returns the updated `category_block.html`.

### Feature 4: Respondent Attribute Columns List

**What:** Below all target categories (before the CSV import section), show the list of all columns available in respondent data. This helps organisers know what categories they could create.

**Backend:** Already exists: `get_respondent_attribute_columns(uow, assembly_id)`. Just needs to be called in `view_assembly_targets` and passed to the template. Also need `assembly.csv.id_column` (available via the assembly object already in context) to exclude the ID column from the list.

**Template:** Show as a checkbox list of available respondent attribute columns. Each entry shows the column name. Columns that already have a matching target category (case-insensitive) are shown but disabled with an "already defined" indicator. The `id_column` from `assembly.csv` is excluded entirely (it's not a useful target category). An "Add selected categories" button at the bottom submits the checked columns. This POSTs to a new bulk endpoint that creates all the selected categories at once, then does a full page reload.

**New endpoint:** `POST /assemblies/<id>/targets/categories/add-from-columns` — accepts a list of column names, creates a target category for each, then redirects to the targets page (full reload).

**Only shown when respondents are present.** If there are no respondents, this section is hidden entirely.

---

## Implementation Plan

### Step 1: New Repository + Service Methods

1. Add `get_attribute_value_counts(assembly_id, attribute_name) -> dict[str, int]` to `AbstractRespondentRepository` in `repositories.py`.
2. Implement in `SqlAlchemyRespondentRepository` in `sql_repository.py` using PostgreSQL JSON extraction:
   ```python
   def get_attribute_value_counts(self, assembly_id: uuid.UUID, attribute_name: str) -> dict[str, int]:
       rows = self.session.execute(
           select(
               orm.respondents.c.attributes[attribute_name].as_string().label("val"),
               func.count().label("cnt"),
           )
           .where(
               and_(
                   orm.respondents.c.assembly_id == assembly_id,
                   orm.respondents.c.attributes[attribute_name].isnot(None),
               )
           )
           .group_by("val")
       ).all()
       return {row.val: row.cnt for row in rows if row.val is not None}
   ```
3. Implement in the fake repository in `tests/fakes.py` (iterate over fake respondents and count in Python).
4. Add `get_respondent_attribute_value_counts(uow, assembly_id, attribute_name) -> dict[str, int]` to `respondent_service.py`.

### Step 2: New Endpoints

**Bulk-add missing values (Feature 3):**
1. Add `POST /assemblies/<id>/targets/categories/<id>/values/add-missing` in `targets.py`.
2. Accepts a hidden form field with the missing value names.
3. For each value name, calls `add_target_value` with `min_count=0, max_count=0`.
4. Returns the updated `category_block.html` (same HTMX pattern as other endpoints).

**Bulk-add categories from columns (Feature 4):**
1. Add `POST /assemblies/<id>/targets/categories/add-from-columns` in `targets.py`.
2. Accepts checkbox form values — a list of column names to create as categories.
3. For each column name, calls `create_target_category`.
4. Redirects to the targets page (full page reload) with a flash message summarising what was created.

### Step 3: Update the View Function and HTMX Handlers

1. In `view_assembly_targets`: call `get_respondent_attribute_columns` to get available columns. For each target category whose name matches an attribute column (case-insensitive), call `get_respondent_attribute_value_counts` to get counts. Pass both `respondent_attribute_columns` and `respondent_counts` (a `dict[str, dict[str, int]]` keyed by category name) to the template.
2. Create a helper function (e.g. `_get_respondent_data_for_targets`) that computes this, since it's needed in both the main view and every HTMX handler that renders `category_block.html`.
3. Update all HTMX handlers that render `category_block.html` to also pass `respondent_counts` for the relevant category.

### Step 4: Template Changes — category_block.html

1. **Totals row:** Add `<tfoot>` with summed min/max (Jinja `sum` filter on `category.values`).
2. **Respondent count column:** Conditionally add a "Respondents" column when `respondent_counts` is provided for this category. Show count per value, and total respondents in the footer.
3. **Missing values section:** Below the table, if there are respondent values not covered by target values, list them with an "Add all missing values" button that POSTs to the new bulk-add endpoint via HTMX.

### Step 5: Template Changes — view_targets.html

1. **Respondent columns section:** After the target categories div and before the CSV import section. Render as a `<form>` with checkboxes for each respondent attribute column (excluding the `id_column`). Columns that already have a matching target category (case-insensitive) are shown disabled with a tick/tag indicating "already defined". Unchecked, enabled columns can be selected. An "Add selected categories" button submits to the `add-from-columns` endpoint.
2. Only render this section when `respondent_attribute_columns` is non-empty.

### Step 6: Tests

1. **Unit tests** for the new repository method `get_attribute_value_counts` (both SQL and fake implementations).
2. **Integration tests** for the new service function.
3. **Integration tests** for the new bulk-add-missing-values endpoint.
4. **Integration tests** for the new bulk-add-categories-from-columns endpoint.
5. **Integration tests** for the route — verify that respondent data appears in template context when respondents are present, and is absent when not.
6. **Template rendering tests** — verify totals row appears, respondent counts appear when data is available, missing values hint shows correctly, checkbox list renders with correct enabled/disabled state.

### Step 7: Translations

Run `just translate-regen` to pick up any new translatable strings.

---

## Decisions

1. **Performance:** One query per category is acceptable — unlikely to exceed ~10 categories.
2. **Column name matching:** Case-insensitive, matching the sortition algorithm's behaviour.
3. **Missing values:** Actionable — "Add all missing values" button creates them with min=max=0.
4. **Respondent columns placement:** Before the CSV import section.
5. **No respondents:** Respondent-related sections are hidden. Totals row (Feature 1) always appears.
