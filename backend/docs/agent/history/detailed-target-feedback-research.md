# Detailed Target Feedback on View/Edit Targets Page — Research

## Goal

Add a "Check targets in detail" button on the view/edit targets page that runs validation checks against targets and respondents, displaying errors **inline next to the specific target category or value** they relate to, rather than as a generic error summary on a separate page.

---

## Current Architecture

### Target Editing (view_assembly_targets)

**Route:** `GET /assemblies/<assembly_id>/targets` in `blueprints/targets.py:107-158`

The view loads:
- `target_categories` — list of `TargetCategory` domain objects (each with a list of `TargetValue`)
- `respondent_counts` — a dict mapping `{category_name: {value_name: count}}` for respondent attribute columns that match target category names (case-insensitive)
- `can_manage` — whether the current user can edit

**Template:** `templates/targets/view_targets.html` renders each category via `templates/targets/components/category_block.html`.

Each `category_block.html` renders a GOV.UK table with columns: Value, Min, Max, (Respondents if matched), (Actions if can_manage). It already shows respondent counts per value and highlights missing values from respondent data.

### Target Domain Model

**`domain/targets.py`**

- `TargetCategory`: has `id`, `assembly_id`, `name`, `sort_order`, `values: list[TargetValue]`
- `TargetValue`: has `value_id` (UUID), `value` (str), `min`, `max`, `min_flex`, `max_flex`, `percentage_target`, `description`

These are stored in `target_categories` table with values as a JSON column.

### Data Adapter

**`adapters/sortition_data_adapter.py`** — `OpenDLPDataAdapter`

Converts `TargetCategory` objects to the CSV-like format (`feature, value, min, max`) expected by the sortition-algorithms library. The adapter's `read_feature_data()` yields headers + rows of dicts.

### Current Check Flow (db_selection page)

**Route:** `POST /assemblies/<assembly_id>/db_select/check` in `blueprints/db_selection.py:92-127`

Calls `check_db_selection_data()` in `service_layer/sortition.py:386-440`, which:

1. Converts `AssemblyCSV` to `Settings`
2. Creates `OpenDLPDataAdapter` → `SelectionData`
3. Calls `select_data.load_features(assembly.number_to_select)` — parses targets, validates them
4. If features load OK, calls `select_data.load_people(settings_obj, features)` — loads respondents, validates against targets

Returns a `CheckDataResult(success, errors, features_report_html, people_report_html, num_features, num_people)`.

Errors are translated to HTML strings — **no structured data is preserved for mapping errors back to specific targets**.

---

## Validation Checks in the Sortition-Algorithms Library

### 1. Feature Parsing Validation (`features.py:read_in_features`)

Per-row validation in `_clean_row()` (line 283):

| Check | Error Type | Identifiers Available |
|-------|-----------|----------------------|
| Empty feature value | `ParseTableMultiError` with `error_code="empty_feature_value"` | `row_name=feature_name`, `error_params.feature_name` |
| Min/max not a number | `ParseTableMultiError` with `error_code="not_a_number"` or `"no_value_set"` | `row_name="feature_name/feature_value"`, `key="min"` or `"max"` |
| Min > max | `ParseTableMultiError` with `error_code="min_greater_than_max"` | `row_name="feature_name/feature_value"`, `keys=["min", "max"]` |
| min_flex > min | `ParseTableMultiError` with `error_code="min_flex_greater_than_min"` | `row_name="feature_name/feature_value"`, `keys=["min", "min_flex"]` |
| max_flex < max | `ParseTableMultiError` with `error_code="max_flex_less_than_max"` | `row_name="feature_name/feature_value"`, `keys=["max", "max_flex"]` |

**Key insight:** `row_name` uses the format `"feature_name/feature_value"` — we can split on `/` to get both the category name and value name.

### 2. Cross-Feature Min/Max Validation (`features.py:check_min_max`, line 236)

Called after all rows are parsed. Checks:

| Check | Error Type | Identifiers Available |
|-------|-----------|----------------------|
| Minimum selection > maximum selection across features | `SelectionMultilineError` | Error messages name the specific features, e.g. `"The smallest maximum is X for feature 'gender'"` |
| Feature minimum sum > number_to_select | `SelectionMultilineError` | Error messages name the specific feature, e.g. `"Minimum for feature gender (30) is more than number to select (25)"` |
| Feature maximum sum < number_to_select | `SelectionMultilineError` | Error messages name the specific feature |

**Now available:** Structured alternatives `report_min_max_error_details_structured()` and `report_min_max_against_number_to_select_structured()` return `MinMaxCrossFeatureIssue` objects with explicit feature names and numeric values (see "Available Library API" section below). The old string-returning functions now delegate to these internally.

### 3. People Validation (`people.py:read_in_people`, line 295)

When loading respondents against features:

| Check | Error Type | Identifiers Available |
|-------|-----------|----------------------|
| Respondent has value not in feature values | `ParseTableMultiError` with `error_code="value_not_in_feature"` | `error_params.feature_name`, `error_params.value` |
| Respondent has empty value for feature | `ParseTableMultiError` with `error_code="empty_value_in_feature"` | `error_params.feature_name` |
| Feature column missing from respondent data | `BadDataError` with `error_code="missing_column"` | `error_params.column` (= feature name) |

### 4. Enough People Check (`people.py:check_enough_people_for_every_feature_value`, line 306)

**IMPORTANT: This is NOT currently called in `check_db_selection_data()`.** It's only called during actual selection in `core.py:563`.

| Check | Error Type | Identifiers Available |
|-------|-----------|----------------------|
| Not enough people with value X in category Y | `SelectionMultilineError` | Plain strings with embedded `feature_name` and `value_name`, plus min and actual count |

**Now available:** `check_people_per_feature_value()` returns `list[FeatureValueCountCheck]` with structured `feature_name`, `value_name`, `min_required`, `actual_count` — without raising. The existing `check_enough_people_for_every_feature_value()` now delegates to it internally. Also `count_people_per_feature_value()` returns counts for ALL feature values (not just those with issues). See "Available Library API" section below.

### 5. Feasibility / ILP Check (`committee_generation/common.py:setup_committee_generation`)

Only run during actual selection. When infeasible:

| Check | Error Type | Identifiers Available |
|-------|-----------|----------------------|
| Quotas are infeasible | `InfeasibleQuotasError` | `features` (relaxed FeatureCollection), `all_lines` with format `"feature:value minimum/maximum target -> change from X to Y."` |
| Can't relax within flex bounds | `InfeasibleQuotasCantRelaxError` | Generic message, no structured data |

**Key insight:** `InfeasibleQuotasError.features` contains a complete `FeatureCollection` with relaxed values — we could diff these against the originals to annotate exact value rows with suggested changes.

---

## Error Data Structures — Detail

### ParseTableErrorMsg (errors.py:88)

```python
@define
class ParseTableErrorMsg:
    row: int                    # Row number in input
    row_name: str               # "feature_name/feature_value" or "person_id"
    key: str                    # Column name ("min", "max", etc.)
    value: str                  # The problematic value
    msg: str                    # Human-readable message
    error_code: str             # i18n code
    error_params: dict          # Parameters for translation
```

### ParseTableMultiValueErrorMsg (errors.py:102)

```python
@define
class ParseTableMultiValueErrorMsg:
    row: int
    row_name: str               # "feature_name/feature_value"
    keys: list[str]             # Multiple column names
    values: list[str]           # Multiple problematic values
    msg: str
    error_code: str
    error_params: dict
```

### ParseTableMultiError (errors.py:116)

```python
class ParseTableMultiError(SelectionMultilineError):
    all_errors: list[ParseTableErrorMsg | ParseTableMultiValueErrorMsg]
```

### InfeasibleQuotasError (errors.py:207)

```python
class InfeasibleQuotasError(SelectionMultilineError):
    features: FeatureCollection  # Relaxed feature values
    all_lines: list[str]         # Human-readable suggestions
    # Line format: "feature_name:value_name minimum/maximum target -> change from X to Y."
```

---

## Mapping Errors to Target UI Elements

### Strategy: Build an error annotations dict

The goal is to produce a data structure like:

```python
# Errors that apply to a whole category
category_errors: dict[str, list[str]]  # category_name -> [error messages]

# Errors that apply to a specific value within a category
value_errors: dict[str, dict[str, list[str]]]  # category_name -> {value_name -> [error messages]}

# Errors that apply to a specific field (min/max) of a specific value
field_errors: dict[str, dict[str, dict[str, list[str]]]]  # category_name -> {value_name -> {field -> [messages]}}

# Suggested relaxations for infeasible quotas
relaxation_suggestions: dict[str, dict[str, dict]]  # category_name -> {value_name -> {suggested_min, suggested_max}}
```

### How each error type maps:

**ParseTableMultiError errors** (from feature parsing):
- `row_name` = `"feature_name/feature_value"` → split to get category + value
- `key` = `"min"`, `"max"`, `"min_flex"`, `"max_flex"` → identifies the field
- These map perfectly to `field_errors[category][value][field]`

**Cross-feature min/max errors** (via `report_min_max_error_details_structured` / `report_min_max_against_number_to_select_structured`):
- `MinMaxCrossFeatureIssue` objects provide `feature_name`, `issue_type`, and numeric details
- `inconsistent_min_max` issues identify TWO features (`smallest_maximum_feature` and `largest_minimum_feature`) → annotate both categories
- `min_exceeds_number_to_select` / `max_below_number_to_select` identify ONE feature → `category_annotations[issue.feature_name]`

**Not enough people errors** (via `check_people_per_feature_value`):
- `FeatureValueCountCheck` objects provide `feature_name`, `value_name`, `min_required`, `actual_count`
- Maps directly to `value_errors[issue.feature_name][issue.value_name]`
- e.g. "Need minimum 25 but only 15 respondents match"

**Infeasible quota errors** (`InfeasibleQuotasError`):
- Already has `features` (relaxed FeatureCollection) — can diff against original
- `all_lines` has format `"feature_name:value_name minimum/maximum target -> change from X to Y."` — can also be parsed
- Maps to `relaxation_suggestions[category][value]` with suggested min/max

**People validation errors** (from `read_in_people`):
- `error_params.feature_name` identifies the category
- `error_params.value` (if present) identifies the respondent's value that doesn't match
- These are respondent-level errors, not target-level — but we could surface summary info like "N respondents have values not in your targets for category X"

---

## Available Library API (sortition-algorithms)

All new functions are exported from the top-level `sortition_algorithms` package and listed in `__all__`.

### 1. FeatureValueCountCheck & check_people_per_feature_value (`people.py:265-293`)

```python
@define(kw_only=True, slots=True, eq=True)
class FeatureValueCountCheck:
    """A structured result for a feature value where there are not enough people."""
    feature_name: str
    value_name: str
    min_required: int
    actual_count: int

def check_people_per_feature_value(
    features: FeatureCollection, people: People
) -> list[FeatureValueCountCheck]:
    """Return structured data about feature values with insufficient people.
    Does NOT raise — returns a list of issues that callers can inspect."""
```

**Backward compatibility:** `check_enough_people_for_every_feature_value()` now delegates to this function internally and still raises `SelectionMultilineError` for existing callers.

**Mapping to UI:** Each `FeatureValueCountCheck` maps directly to `value_errors[issue.feature_name][issue.value_name]` with a message like "Need min {min_required} but only have {actual_count} respondents".

### 2. count_people_per_feature_value (`people.py:296-303`)

```python
def count_people_per_feature_value(
    features: FeatureCollection, people: People
) -> dict[str, dict[str, int]]:
    """Return {feature_name: {value_name: count}} for ALL feature values."""
```

**Use case:** Provides respondent counts per target value through the sortition-algorithms validated features, ensuring the counts match what the selection algorithm will actually see. This complements the existing `respondent_counts` already shown in `category_block.html` but is authoritative (uses the same matching logic as selection).

### 3. MinMaxCrossFeatureIssue & structured reporters (`features.py:61-222`)

```python
@define(kw_only=True, slots=True, eq=True)
class MinMaxCrossFeatureIssue:
    """A structured result for a cross-feature min/max validation issue."""
    issue_type: str       # "inconsistent_min_max", "min_exceeds_number_to_select", "max_below_number_to_select"
    message: str          # Human-readable message

    # Fields for inconsistent_min_max:
    smallest_maximum_feature: str = ""
    smallest_maximum_value: int = 0
    largest_minimum_feature: str = ""
    largest_minimum_value: int = 0

    # Fields for per-feature number_to_select issues:
    feature_name: str = ""
    feature_sum: int = 0
    limit: int = 0        # number_to_select

def report_min_max_error_details_structured(
    fc: FeatureCollection, feature_column_name: str = "feature"
) -> list[MinMaxCrossFeatureIssue]:
    """Return structured data about inconsistent min/max across features.
    Returns empty list if features are consistent."""

def report_min_max_against_number_to_select_structured(
    fc: FeatureCollection, number_to_select: int, feature_column_name: str = "feature"
) -> list[MinMaxCrossFeatureIssue]:
    """Return structured data about features whose min/max conflict with number_to_select."""
```

**Backward compatibility:** The old string-returning `report_min_max_error_details()` and `report_min_max_against_number_to_select()` now delegate to these structured versions internally.

**Mapping to UI:**
- `inconsistent_min_max` → `category_annotations[issue.smallest_maximum_feature]` and `category_annotations[issue.largest_minimum_feature]` — these are category-level errors since they relate to the sum of all mins/maxes in a category
- `min_exceeds_number_to_select` → `category_annotations[issue.feature_name]` with message about the sum of mins being too high
- `max_below_number_to_select` → `category_annotations[issue.feature_name]` with message about the sum of maxes being too low

---

## Proposed Implementation Approach

### New service function: `check_targets_detailed()`

A new service function in `sortition.py` (or a new module) that:

1. Loads features via `SelectionData.load_features()` — catches `ParseTableMultiError` and extracts structured error info from `all_errors`
2. If features loaded, runs `report_min_max_error_details_structured()` and `report_min_max_against_number_to_select_structured()` to get structured cross-feature issues (these are already called inside `load_features` via `check_min_max`, but we call the structured versions directly to get mappable data)
3. If features loaded, loads people via `SelectionData.load_people()` — catches people validation errors
4. Runs `check_people_per_feature_value()` to get structured per-value insufficiency data — currently missing from the check flow entirely
5. Optionally calls `count_people_per_feature_value()` to get authoritative respondent counts for display
6. Optionally runs feasibility check via `setup_committee_generation()` — catches `InfeasibleQuotasError` and extracts relaxation suggestions
7. Returns a structured result:

```python
@dataclass
class TargetAnnotation:
    """An error or warning annotation for a specific target."""
    level: str  # "error", "warning", "suggestion"
    message: str
    field: str | None = None  # "min", "max", or None for whole-value
    suggested_value: int | None = None  # For relaxation suggestions

@dataclass
class DetailedCheckResult:
    success: bool
    # Global errors not attributable to a specific target
    global_errors: list[str]
    # Annotations keyed by (category_name, value_name)
    annotations: dict[str, dict[str, list[TargetAnnotation]]]
    # Category-level annotations (not tied to a specific value)
    category_annotations: dict[str, list[TargetAnnotation]]
    # Summary stats
    num_features: int
    num_people: int
    num_respondent_errors: int
```

### New route

Add a new route (or reuse the existing targets page with HTMX):

```
POST /assemblies/<assembly_id>/targets/check
```

This could either:
- **Option A:** Return the full page re-rendered with annotations injected into each `category_block.html` — simpler, works with existing HTMX patterns
- **Option B:** Return just the annotations as JSON and use Alpine.js to display them inline — more dynamic but more JS complexity

**Recommendation: Option A** — it's consistent with the existing HTMX pattern. The `category_block.html` template already handles conditional rendering. We'd add an `annotations` template variable and render error/warning badges next to the affected rows.

### Template changes to `category_block.html`

Add annotation display logic:

```html
{# After each value row's min/max cells #}
{% if annotations and annotations.get(category.name, {}).get(val.value) %}
    {% for ann in annotations[category.name][val.value] %}
        <div class="govuk-error-message">{{ ann.message }}</div>
        {% if ann.suggested_value is not none %}
            <span class="govuk-tag govuk-tag--yellow">
                Suggested {{ ann.field }}: {{ ann.suggested_value }}
            </span>
        {% endif %}
    {% endfor %}
{% endif %}
```

### Where to display the "Check targets in detail" button

On `view_targets.html`, add a button that POSTs to the check endpoint. Requirements:
- Assembly must have respondents uploaded
- Assembly must have `number_to_select` set (needed for cross-feature and feasibility checks)
- Button should use HTMX to re-render the targets section with annotations

---

## Checks Not Currently in `check_db_selection_data` That Should Be Added

1. **`check_enough_people_for_every_feature_value()`** — This is the most useful check for the targets page. It tells you "you need min 25 females but only have 15 respondents who are female." Currently only runs during actual selection.

2. **Feasibility check** — `setup_committee_generation()` tests whether the ILP is feasible. This is expensive (creates and solves an ILP) but gives the most definitive answer. Could be optional or run behind a "deep check" button.

3. **`check_desired()`** — Checks if `number_to_select` is within the min/max range of every feature. Also only runs during selection currently.

---

## Summary of Recommended Changes

### In sortition-algorithms library: DONE ✓

All library changes have been implemented in commit `6ece33c`:

1. ✓ `FeatureValueCountCheck` + `check_people_per_feature_value()` — structured non-raising alternative to `check_enough_people_for_every_feature_value()`
2. ✓ `count_people_per_feature_value()` — returns `{feature: {value: count}}` for all values
3. ✓ `MinMaxCrossFeatureIssue` + `report_min_max_error_details_structured()` + `report_min_max_against_number_to_select_structured()` — structured alternatives to string-returning cross-feature checkers
4. ✓ Old functions refactored to delegate to new structured versions (backward compatible)
5. ✓ All new types and functions exported in `__init__.py` and `__all__`

### In OpenDLP backend:

1. Create `check_targets_detailed()` service function that calls the new structured library APIs (`check_people_per_feature_value`, `report_min_max_error_details_structured`, `report_min_max_against_number_to_select_structured`, `count_people_per_feature_value`) and returns structured, annotatable results
2. Add `POST /assemblies/<assembly_id>/targets/check` route
3. Enhance `category_block.html` to accept and display annotations (errors, warnings, suggestions)
4. Add "Check targets in detail" button to `view_targets.html`
5. Optionally run feasibility check via `setup_committee_generation()` for the most thorough validation

### Key mapping strategy:

- `ParseTableMultiError.all_errors` → parse `row_name` ("feature/value") to get category + value
- `check_people_per_feature_value()` → `FeatureValueCountCheck` gives direct `feature_name` + `value_name` mapping
- `report_min_max_error_details_structured()` → `MinMaxCrossFeatureIssue` gives `smallest_maximum_feature` / `largest_minimum_feature` for category-level annotation
- `report_min_max_against_number_to_select_structured()` → `MinMaxCrossFeatureIssue` gives `feature_name` for category-level annotation
- `InfeasibleQuotasError.features` → diff against originals to get per-value relaxation suggestions
- `count_people_per_feature_value()` → authoritative respondent counts per value (can replace or supplement existing `respondent_counts` from the view)

---

## Implementation Todo List

### Phase 1: Data Structures and Service Layer ✓ COMPLETE

All implemented in `src/opendlp/service_layer/target_checking.py`.

- [x] **1.1** `TargetAnnotation` dataclass
- [x] **1.2** `DetailedCheckResult` dataclass
- [x] **1.3** `_annotations_from_parse_errors()` helper
- [x] **1.4** `_annotations_from_cross_feature_issues()` helper
- [x] **1.5** `_annotations_from_people_checks()` helper
- [x] **1.6** `_annotations_from_infeasible_quotas()` helper
- [x] **1.7** `check_targets_detailed()` service function — includes feasibility check (ILP) when `number_to_select > 0`
- [x] **1.8** Sequencing handled via `load_features(number_to_select=0)` then structured checks directly

### Phase 2: Route and View Integration ✓ COMPLETE

- [x] **2.1** `POST /assemblies/<assembly_id>/targets/check` route in `blueprints/targets.py`
- [x] **2.2** "Check targets in detail" button in `view_targets.html` (shown when targets exist)
- [x] **2.3** Global error/success display in `view_targets.html`
- [x] **2.4** `check_result` pass-through to `category_block.html` via `value_annotations` and `category_annotation_list`

### Phase 3: Template Annotation Display ✓ COMPLETE

- [x] **3.1** Category-level annotation display (errors, warnings, suggestions) after category header
- [x] **3.2** Value-level annotation display as separate rows below each value row (errors, suggestions, warnings)
- [x] **3.3** Annotation rows are outside the Alpine.js editing template — always visible regardless of edit state
- [x] **3.4** GOV.UK styling: `govuk-error-message` for errors, `govuk-tag govuk-tag--yellow` for suggestions, `govuk-tag govuk-tag--orange` for warnings

### Phase 4: Internationalisation ✓ COMPLETE

- [x] **4.1** All annotation messages use `_()` with parameterised translation
- [x] **4.2** All template strings wrapped in `_()`
- [x] **4.3** `just translate-regen` run successfully

### Phase 5: Testing ✓ COMPLETE

- [x] **5.1** Unit tests for annotation helpers — 11 tests in `tests/unit/test_target_checking.py`
- [x] **5.2** Unit tests for `check_targets_detailed()` — 6 tests using `FakeUnitOfWork`
- [x] **5.3** Integration tests — 5 tests in `tests/integration/test_target_checking_integration.py` against PostgreSQL
- [x] **5.4** E2E tests — 5 tests in `tests/e2e/test_targets_pages.py::TestCheckTargets`
- [x] **5.5** Full test suite: 1508 passed, 0 failed. `just check` passes (only pre-existing mypy errors in celery/app.py)

### Phase 6: Optional Enhancements (Post-MVP)

Feasibility check (6.1) was implemented as part of Phase 1 — it runs automatically when `number_to_select > 0`.

- [x] **6.1 Feasibility check integration** — implemented in `check_targets_detailed()`, runs `setup_committee_generation()` and maps `InfeasibleQuotasError` to relaxation suggestions
- [ ] **6.2 HTMX enhancement** — convert from full-page POST to HTMX partial swap
- [ ] **6.3 Persistent check state** — re-run check after edits
- [ ] **6.4 Authoritative respondent counts** — use `count_people_per_feature_value()` for validated counts
