# Targets: percentages, comments, source URL, reordering

**Issue:** 666
**Branch:** `666-target-percentage`
**Status:** Plan — domain/data/service in detail, UI sketched only
**Date:** 2026-08-21

## Scope of this document

Detailed plan for the **domain, persistence and service layers**. The
entrypoint/UI layer is deliberately only sketched — we flesh that out once the
layers underneath are done and merged.

The behavioural spec this plan implements is
`docs/explainers/workflow-targets-and-fields.html` (flow 1, plus the
"Percentages", "Setting min and max by hand" and "Source URL and comments"
detail sections). Where this plan departs from that document, it says so.

---

## 1. What exists today

| Thing | Where | Notes |
| --- | --- | --- |
| `TargetValue` dataclass | `src/opendlp/domain/targets.py` | `value`, `min`, `max`, `min_flex`, `max_flex`, `percentage_target`, `description`, `value_id` |
| `TargetCategory` | `src/opendlp/domain/targets.py` | `id`, `assembly_id`, `name`, `description`, `sort_order`, `values`, timestamps |
| Persistence | `adapters/orm.py` | `target_categories` table; `values` is a **JSON column** via `TargetValueListJSON` |
| Mapping | `adapters/database.py:191` | imperative `map_imperatively` |
| Repository | `adapters/sql_repository.py:1066` | `SqlAlchemyTargetCategoryRepository`, ordered by `sort_order` |
| Services | `service_layer/assembly_service.py:558-880` | create/get/import/update/delete category, add/update/delete value |
| Checks | `service_layer/target_checking.py` | `check_targets_detailed` → `DetailedCheckResult` with per-value and per-category `TargetAnnotation`s |
| Algorithm feed | `adapters/sortition_data_adapter.py` | emits `feature, value, min, max[, min_flex, max_flex]` rows |
| Snapshot | `domain/targets.py:target_categories_to_snapshot` | written to `SelectionRunRecord.targets_used` |
| Live UI | `entrypoints/blueprints/targets.py` + `templates/backoffice/targets/category_block.html` | HTMX per-row edit, Alpine `editing` toggle |
| Legacy UI | `entrypoints/blueprints/targets_legacy.py` + `templates/targets/` | GOV.UK-styled older page, still registered |

Three facts that shape everything below:

1. **`percentage_target` already exists on `TargetValue`** — validated (0–100 or
   `None`), round-tripped through the JSON column, included in the snapshot,
   and **used by nothing**. We adopt it rather than adding a new field.
2. **`TargetValue` lives in a JSON column**, so adding fields to it needs **no
   migration** — old rows simply deserialise with the dataclass defaults.
   `TargetCategory` fields are real columns and do need one.
3. **`sort_order` already exists and is already the sort key** in the
   repository. Reordering is about *writing* it, not about adding it.

---

## 2. Decisions taken (agreed before drafting)

| Decision | Choice |
| --- | --- |
| min/max storage | **Stored fields, recalculated on change.** `min`/`max` remain real stored values; a service function recalculates them when the percentage changes, and `update_assembly` recalculates every linked value when `number_to_select` changes. Everything downstream (sortition adapter, `target_checking`, snapshots, selection report, CSV export) keeps reading `min`/`max` unchanged. |
| Comment field | **New `comment` field** on both `TargetCategory` and `TargetValue`. The existing unused `description` fields are left alone (see open question Q11). |
| Rounding | **`min = floor(pct/100 × n)`, `max = ceil(pct/100 × n)`** exactly as the explainer specifies. The min==max rigidity on exact divisions is recorded as open question Q1. |

---

## 3. Phase 0 — extract `target_service.py` (mechanical, own commit)

`assembly_service.py` is 1227 lines and about 380 of them are target CRUD. This
change adds roughly another 200. Before touching behaviour, move the target
functions to a new module.

**Move to `src/opendlp/service_layer/target_service.py`** (verbatim, no logic
changes):

`create_target_category`, `get_targets_for_assembly`, `import_targets_from_csv`,
`update_target_category`, `delete_target_category`, `add_target_value`,
`update_target_value`, `delete_target_value`, `delete_targets_for_assembly`,
`get_feature_collection_for_assembly`.

**Callers to update:** `blueprints/targets.py` and `blueprints/targets_legacy.py`
in `src`, plus `tests/integration/test_assembly_service_targets.py` and the other
test modules listed in §8. `get_feature_collection_for_assembly` has no caller in
`src` at all — only tests — so check whether it is dead code while moving it.
Confirm the full list with
`grep -rn "from opendlp.service_layer.assembly_service import" src tests`.

Do **not** re-export from `assembly_service` — a shim would leave two names for
one function. Fix the imports instead.

*This is a pure move. If you would rather not have it, say so in the annotations
and the rest of the plan still applies with `assembly_service` as the home.*

---

## 4. Phase 1 — Domain (`src/opendlp/domain/targets.py`)

### 4.1 `TargetValue` — new and changed fields

```python
@dataclass
class TargetValue:
    value: str
    min: int
    max: int
    min_flex: int = 0
    max_flex: int = MAX_FLEX_UNSET
    percentage_target: float | None = None
    description: str = ""
    comment: str = ""            # NEW — why min/max were set by hand
    minmax_manual: bool = False  # NEW — True once min/max set directly
    value_id: uuid.UUID | None = None
```

`comment` and `minmax_manual` must be declared **before** `value_id` only if we
care about positional construction; all real call sites use keywords, so append
them wherever reads best — but keep `value_id` last to match the existing
convention.

**Validation additions in `_validate`:**

- `comment` — strip on assignment; cap at `MAX_COMMENT_LENGTH = 2000`, raise
  `ValueError` above that. (The column is `Text`, but an unbounded free-text
  field on a JSON blob wants a sanity limit.)
- Everything else unchanged.

### 4.2 `TargetCategory` — new fields

```python
def __init__(self, assembly_id, name, description="", sort_order=0,
             values=None, category_id=None, created_at=None, updated_at=None,
             comment="", source_url=""):      # NEW
```

- `comment: str` — free text, same 2000-char cap, stripped.
- `source_url: str` — where the percentages came from.

**`source_url` validation, in the domain:**

- Empty string is valid and is the default (per the house rule: empty string,
  not `str | None`).
- Otherwise parse with `urllib.parse.urlsplit` and require `scheme` in
  `{"http", "https"}` and a non-empty `netloc`. Raise `ValueError` otherwise.
- Cap at 2048 chars.

Rejecting non-http(s) schemes in the domain is what makes it safe to render as
an `<a href>` later — it rules out `javascript:` and `data:` at the point of
entry rather than trusting the template. **This is a security-relevant
invariant; say so in a comment on the validator.**

`create_detached_copy` must pass the two new kwargs through. It rebuilds values
with `TargetValue(**vars(v))`, so new value fields are carried automatically.

### 4.3 The percentage → min/max calculation

New module-level function, pure and independently testable:

```python
def min_max_for_percentage(percentage: float, number_to_select: int) -> tuple[int, int]:
    """Min/max seats implied by a percentage of the assembly.

    min = floor(pct% of n), max = ceil(pct% of n), per the agreed spec.
    """
    exact = percentage * number_to_select / 100
    return math.floor(exact), math.ceil(exact)
```

Use `percentage * number_to_select / 100` (not `percentage / 100 * n`) so the
float division happens once, at the end.

And on `TargetValue`:

```python
def apply_percentage(self, number_to_select: int) -> bool:
    """Recalculate min/max from the percentage. Returns True if anything changed.

    No-op when there is no percentage, when the auto-calculate link has been
    broken, or when number_to_select is not yet agreed.
    """
```

Guard conditions, in order:

1. `self.percentage_target is None` → return False.
2. `self.minmax_manual` → return False.
3. `number_to_select <= 0` → return False. (Percentages are still stored; they
   just cannot be turned into seats yet. See open question Q5.)

Otherwise compute, assign `self.min` / `self.max`, run `self._validate()`, and
return whether the values moved.

```python
def set_manual_min_max(self, min_count: int, max_count: int) -> None:
    """Set min/max directly, permanently breaking the auto-calculate link."""
    self.min = min_count
    self.max = max_count
    self.minmax_manual = True
    self._validate()
```

Note the ordering trap: `_validate()` requires `max >= min`, so both must be
assigned before validating, and a failed validation leaves the object dirty.
Validate a candidate pair *before* assigning, or construct-and-swap. Prefer:
compute, check `max_count >= min_count >= 0` up front, then assign.

### 4.4 Percentage totals on the category

```python
def percentage_total(self) -> float | None:
    """Sum of the percentages across this category's values.

    Returns None if no value has a percentage set — an unset category is not
    a category that sums to zero.
    """

def percentage_total_is_plausible(self, tolerance: float = PERCENTAGE_TOLERANCE) -> bool:
    """True if the percentages sum to within `tolerance` of 100."""
```

`PERCENTAGE_TOLERANCE = 0.5` as a module constant — see open question Q2 for
the value. Round the sum to 2dp before comparing so float addition of values
like `33.3` doesn't produce a spurious failure.

Note that a category where *some* values have a percentage and some don't will
sum to something well under 100 and warn. That is correct — a half-filled
category is exactly the mistake worth flagging.

### 4.5 Snapshot

`target_categories_to_snapshot` gains `comment` and `source_url` at the category
level and `comment` / `minmax_manual` at the value level. `percentage_target` is
already there.

**This changes a persisted format.** Old `SelectionRunRecord.targets_used` rows
will not have the new keys; every reader of the snapshot must use `.get()` with
a default. Check `service_layer/selection_report.py` (`_build_category_report`
reads `v["value"]`, `v["min"]`, `v["max"]` — all still present, so it is safe)
and the recorded fixtures in `tests/fixtures/json_api/` if any carry a snapshot.

---

## 5. Phase 2 — Persistence

### 5.1 `TargetValue` — no migration

Adding fields to the dataclass is enough:

- `process_bind_param` uses `vars(v).copy()` → new fields serialise automatically.
- `process_result_value` does `TargetValue(**item)` → rows written before this
  change simply lack the keys and get the dataclass defaults.

**One risk to close:** `TargetValue(**item)` raises `TypeError` on *unknown*
keys. That bites on a rollback (new rows read by old code) or if a stray key
ever lands in the JSON. Harden `process_result_value` to filter to known field
names:

```python
_TARGET_VALUE_FIELDS = {f.name for f in dataclasses.fields(TargetValue)}
...
kwargs = {k: v for k, v in item.items() if k in _TARGET_VALUE_FIELDS}
```

Log at `debug` with the dropped key names when anything is filtered, so a real
schema drift isn't silent. (Key *names* only — never the values, which are
target labels and could in principle be personal-ish.)

### 5.2 `TargetCategory` — one migration

Add to `orm.target_categories`:

```python
Column("comment", Text, nullable=False, default=""),
Column("source_url", Text, nullable=False, server_default="", default=""),
```

`server_default=""` on both so the migration can add them `NOT NULL` against
existing rows without a two-step.

Generate with:

```bash
uv run alembic revision --autogenerate -m "add comment and source_url to target categories"
```

Then **read the generated file** — autogenerate against this schema has a habit
of picking up unrelated drift. Strip anything that isn't these two columns.

No new table, so `tests/conftest.py::_delete_all_test_data` and
`tests/bdd/conftest.py::delete_all_except_standard_users` need no change.

No change needed in `adapters/database.py`: `TargetCategory` is mapped with a
bare `map_imperatively(targets.TargetCategory, orm.target_categories)` and no
explicit `properties`, so new columns are picked up automatically.

---

## 6. Phase 3 — Service layer

All new functions go in `target_service.py` (or `assembly_service.py` if Phase 0
is dropped). All follow the house conventions: take `uow` as first arg, **never**
open a `with uow:` block, permission-check via `can_manage_assembly` /
`require_assembly_permission`, return `create_detached_copy()`, and call
`flag_modified(category, "values")` after any in-place mutation of the JSON list.

### 6.1 Reorder categories

```python
def reorder_target_categories(
    uow, user_id, assembly_id, ordered_category_ids: list[uuid.UUID]
) -> None:
```

Modelled directly on `respondent_field_schema_service.reorder_group`
(`src/opendlp/service_layer/respondent_field_schema_service.py:507`):

- require the submitted set to be **exactly** the assembly's current category ids
  — raise `ValueError` (or a `TargetConflictError`, see below) otherwise, so a
  stale page can't silently drop a category from the ordering;
- re-issue `sort_order` as `(i + 1) * SORT_ORDER_STEP` with
  `SORT_ORDER_STEP = 10` (import the existing constant from
  `domain/respondent_field_schema.py`, or lift it somewhere neutral — see Q12);
- bump `updated_at` on every touched category.

Existing rows have `sort_order` values of `0` or a bare index; re-issuing on the
first reorder fixes that with no data migration. Gaps of 10 leave room for a
future drag-and-drop insert without a full renumber.

**While here:** `create_target_category` currently takes `sort_order=0` and the
blueprint computes `sort_order = len(existing)` at `blueprints/targets.py:305`
and `:811`. That is policy in an entrypoint. Move it: when `sort_order` is not
supplied, the service picks `max(existing) + SORT_ORDER_STEP`. Two call sites to
simplify.

### 6.2 Percentages

```python
def set_target_value_percentage(
    uow, user_id, assembly_id, category_id, value_id, percentage: float | None
) -> TargetCategory:
```

Sets `percentage_target`, then calls `value.apply_percentage(assembly.number_to_select)`.
Needs the assembly loaded for `number_to_select`.

```python
def recalculate_minmax_for_assembly(uow, assembly_id: uuid.UUID) -> int:
    """Re-derive min/max for every value with an intact auto-calculate link.

    Returns the number of values changed. No permission check — this is an
    internal consequence of an already-authorised change, not a user action.
    """
```

Called from **`assembly_service.update_assembly`**, which is the single funnel
for both the full assembly edit form and the dedicated
`backoffice.update_number_to_select` route (`blueprints/backoffice.py:252`).

`update_assembly` currently applies updates with a blind `setattr` loop
(`assembly_service.py:131`). Capture `number_to_select` **before** the loop,
compare after, and only recalculate when it actually changed:

```python
previous_number_to_select = assembly.number_to_select
for field, value in updates.items():
    if hasattr(assembly, field):
        setattr(assembly, field, value)
if assembly.number_to_select != previous_number_to_select:
    recalculate_minmax_for_assembly(uow, assembly_id)
```

Import direction: `assembly_service` → `target_service`. Check this doesn't
create a cycle (`target_service` will want `get_assembly_with_permissions` and
`can_manage_assembly`). If it does, put the shared permission helpers where they
already live (`service_layer/permissions.py`) and have `target_service` import
only from there — do **not** import `assembly_service` from `target_service`.

### 6.3 Value and category edits

Extend the existing functions rather than adding parallel ones:

```python
def update_target_value(
    uow, user_id, assembly_id, category_id, value_id,
    value: str,
    min_count: int | None = None,
    max_count: int | None = None,
    percentage: float | None = None,
    comment: str | None = None,
) -> TargetCategory:
```

Semantics, and this is the fiddly bit — write it down in the docstring:

- `min_count`/`max_count` supplied and **different from the current stored
  values** → `set_manual_min_max(...)`, which sets `minmax_manual = True`.
- `min_count`/`max_count` supplied and **identical** to the current values →
  do nothing, do **not** break the link. Without this, a "save all" form that
  round-trips every field on every save would break every link on first use.
  This rule is what makes the bulk-save UI possible at all.
- `percentage` supplied → set it, then `apply_percentage(...)`, which no-ops if
  the link is already broken.
- If both a changed percentage **and** a changed min/max arrive in the same
  submission, the explicit min/max wins and the link breaks. Apply the
  percentage first, then the manual min/max.
- `None` means "not submitted, leave alone" for each parameter. `percentage`
  is ambiguous here — `None` is also a legitimate value meaning "clear the
  percentage". Use a sentinel (`UNSET = object()`, or an explicit
  `clear_percentage: bool` keyword) rather than overloading `None`.
  **Note `FBT` is enabled in ruff** — any bool parameter must be keyword-only.
- Clearing the percentage leaves `min`/`max` at their current values and leaves
  `minmax_manual` as it was.
- Keep the existing "reset flex to defaults" behaviour and its comment.

`add_target_value` gains the same optional `percentage` and `comment`
parameters, applying the percentage on construction.

```python
def update_target_category(
    uow, user_id, assembly_id, category_id,
    name: str, description: str = "", comment: str = "", source_url: str = "",
) -> TargetCategory:
```

Existing signature plus two. Domain validation on `source_url` surfaces as
`ValueError`; the route turns that into a field error, not a 500.

### 6.4 Bulk save ("save all")

```python
@dataclass
class TargetValueEdit:
    value_id: uuid.UUID | None   # None = a new value
    value: str
    percentage: float | None
    min: int | None
    max: int | None
    comment: str

@dataclass
class TargetCategoryEdit:
    category_id: uuid.UUID
    name: str
    comment: str
    source_url: str
    values: list[TargetValueEdit]

def save_all_targets(
    uow, user_id, assembly_id, edits: list[TargetCategoryEdit]
) -> list[TargetCategory]:
```

One permission check, one pass, all-or-nothing (the entrypoint's single
`with uow:` gives us the transaction for free — if any edit raises, nothing
commits). Internally it reuses the per-value logic from §6.3 so there is exactly
one implementation of the link-breaking rules.

Deletion is **not** part of bulk save — deleting a value or category stays its
own explicit action with its own confirmation. Values absent from the payload
are left alone, not deleted.

### 6.5 Percentage-sum warning

Two levels, deliberately:

1. **Cheap, always-on.** The domain's `percentage_total_is_plausible()` is
   called from the targets page render — no algorithm run, no database work
   beyond what is already loaded. This is the warning the explainer describes.
2. **Part of the full check.** Add a category-level annotation in
   `target_checking.check_targets_detailed` so "check the targets" reports it
   alongside everything else:

```python
TargetAnnotation(
    level="warning",
    message=_("Percentages for this category add up to %(total)s%%, not 100%%",
              total=total),
)
```

Add it in a new `_annotations_from_percentage_totals(categories, category_annotations)`
called from `check_targets_detailed` before the feature collection is loaded, so
it still reports when the sortition library rejects the data for other reasons.

Level is `warning`, never `error`, and it must **not** set `result.success = False`.
The explainer is explicit that this never blocks.

---

## 7. Phase 4 — Entrypoints and UI (sketch only)

Enough detail to know the layers below are shaped right. We design this properly
in a follow-up.

**Forms** (`entrypoints/forms.py`)

- `TargetValueForm` gains `percentage` (`DecimalField`, `NumberRange(0, 100)`,
  `Optional()`) and `comment` (`TextAreaField`, `Length(max=2000)`).
  `min_count` / `max_count` become `Optional()` — a value can be defined by
  percentage alone.
- `EditTargetCategoryForm` gains `comment` and `source_url` (`URLField` with a
  custom validator that mirrors the domain's http/https rule, so the user gets a
  field error rather than a 500).
- Bulk save does **not** fit WTForms' one-form-one-object model. Parse the
  `request.form` directly into the `TargetCategoryEdit` dataclasses with a
  dedicated parser function, keeping WTForms for CSRF only. Field naming:
  `cat[<category_id>][values][<value_id>][percentage]`. Validate in the parser
  and return field-keyed errors the template can re-render.

**Routes** (`blueprints/targets.py`)

- `POST .../targets/reorder` (or `.../targets/categories/<id>/move` with a
  `direction` of `up`/`down`, mirroring
  `respondent_field_schema.move_field:435`). Start with up/down buttons —
  keyboard-accessible for free, and no drag-and-drop accessibility problem to
  solve. The service takes a full ordering either way, so drag-and-drop can be
  added later without a service change.
- `POST .../targets/save-all` → `save_all_targets`, re-render the whole list.
- Existing per-row routes stay — they are what the HTMX partials use, and
  keeping them means "edit all" can ship without a big-bang template rewrite.

**Template** (`templates/backoffice/targets/category_block.html`)

- New `Percentage` column between `Value` and `Min`.
- `tfoot` gains a percentage total, styled as a warning when
  `percentage_total_is_plausible()` is false.
- A visual marker on rows where `minmax_manual` is true — the explainer's whole
  argument for the comment field is that a hand-set number needs its reason
  visible next to it. An icon plus the comment inline, not a tooltip.
- Category header shows `source_url` as a link (`target="_blank"`,
  `rel="noopener noreferrer"`) and the category comment.
- Comments render with URLs linkified. **Do this in a Jinja filter over
  already-escaped text**, not with `|safe` on raw user input, and emit only
  `http`/`https` links. Check `docs/frontend_security.md` before writing it.
- "Edit all" / "Save all": one Alpine `x-data` at the page level holding a flat
  `editingAll` boolean (Alpine here is CSP-constrained — flat `x-model`
  properties only, no string arguments in `@click`; see
  `templates/backoffice/patterns.html`).

**i18n:** every new string in `_()` / `_l()`, then `just translate-regen`.

**Tests for this phase:** component tests for the page, e2e for the routes, a
new `features/targets.feature` BDD scenario for edit-all → save-all → reorder,
plus vitest for any new JS. To be specified with the UI plan.

---

## 8. Phase 5 — Tests

Every layer, per the no-exceptions policy. Existing files to extend:

| File | What to add |
| --- | --- |
| `tests/unit/test_targets.py` | The bulk of the new coverage — see below |
| `tests/unit/test_target_checking.py` | Percentage-total annotation: fires, is `warning`, does not flip `success` |
| `tests/contract/test_target_category_repo.py` | Round-trip of `comment`, `source_url`, `minmax_manual` through fake and real repo |
| `tests/integration/test_target_category_repository.py` | Same against real Postgres, plus reading a row written **without** the new JSON keys |
| `tests/integration/test_assembly_service_targets.py` | All the new service functions |
| `tests/unit/test_selection_report.py` | Snapshot with and without the new keys |
| `tests/component/test_targets_pages.py`, `tests/e2e/test_targets_pages.py` | UI phase |

**Unit (`tests/unit/test_targets.py`), the cases that matter:**

- `min_max_for_percentage`: 50% of 100 → (50, 50); 33.3% of 100 → (33, 34);
  50% of 101 → (50, 51); 0% of 100 → (0, 0); 100% of 100 → (100, 100).
- `apply_percentage` no-ops when: percentage is `None`; `minmax_manual` is True;
  `number_to_select` is 0.
- `set_manual_min_max` sets the flag; a subsequent `apply_percentage` does not
  move the numbers.
- `set_manual_min_max` with `max < min` raises **and leaves the object
  unmodified** (this is the ordering trap from §4.3 — test it explicitly).
- `percentage_total` returns `None` for a category with no percentages at all,
  and a float otherwise.
- `percentage_total_is_plausible`: 99.9 and 100.1 pass; 95.0 fails; a
  half-filled category fails.
- `source_url` accepts http/https, rejects `javascript:`, `data:`, a bare
  `example.com` with no scheme, and anything over 2048 chars.
- `comment` over 2000 chars raises.
- `create_detached_copy` carries every new field on both classes.
- `target_categories_to_snapshot` includes the new keys.

**Service (integration):**

- `reorder_target_categories` re-issues 10, 20, 30…; rejects a partial id set;
  rejects an id from another assembly.
- `create_target_category` with no `sort_order` lands after the existing ones.
- `update_assembly` changing `number_to_select` moves min/max on linked values
  and leaves manual ones alone. **And the negative case:** updating some *other*
  assembly field does not touch any target.
- `update_target_value` submitting unchanged min/max does **not** break the link
  (the rule the whole bulk-save UI rests on).
- `update_target_value` with a changed percentage and a changed min/max in one
  call: min/max wins, link breaks.
- `save_all_targets` across two categories in one call; and a failure partway
  through leaves **nothing** committed.
- Permission denial on every new entry point.

---

## 9. Suggested commit sequence

Docs commit separately from code, per house rule.

1. `docs: plan target percentages, comments and reordering` — this file.
2. `refactor: move target services out of assembly_service` — Phase 0, no
   behaviour change, tests pass untouched apart from imports.
3. `feat: add percentage-derived min/max to target values` — domain only,
   §4.1/§4.3, plus unit tests. Nothing calls it yet.
4. `feat: add comments and source URL to targets` — domain + ORM + migration
   (§4.2, §5), plus contract/integration tests.
5. `feat: recalculate target min/max when number to select changes` — §6.2,
   the `update_assembly` hook.
6. `feat: reorder target categories` — §6.1.
7. `feat: warn when target percentages do not total 100` — §6.5.
8. `feat: save all target edits in one operation` — §6.4.
9. UI, in its own sequence, after the follow-up plan.

Run `just test-js`, then `just check`, then `just test` before each commit that
touches code. Full runs take 10+ minutes — pipe to a file in the scratchpad
rather than into the terminal.

---

## 10. Risks

- **`update_assembly`'s blind `setattr` loop** is the single point where the
  recalculation hook can be bypassed. Anything that writes
  `assembly.number_to_select` through the repository directly would leave stale
  min/max. Grep for it after implementing; consider whether the domain's
  `Assembly.update()` needs the same hook.
- **`TargetValue(**item)` on unknown keys** — closed by §5.1, but it means a
  rollback after this ships is only safe *because* of that filter. Ship the
  filter in the same commit as the first new field.
- **The snapshot format change** is written into a JSON column on
  `selection_run_records`. Readers must use `.get()`; the recorded API fixtures
  in `tests/fixtures/json_api/` may need re-recording with
  `UPDATE_API_FIXTURES=1 uv run pytest` — read the diff rather than accepting it.
- **The legacy targets page** (`targets_legacy.py`, `templates/targets/`) reads
  the same domain objects and will keep working, but will not show or edit any
  of the new fields. See Q9.
- **No PII concerns** in this work — target names and comments are
  configuration, not personal data. Worth stating so the next reader doesn't
  re-derive it. The one thing to keep out of logs is the free-text comment,
  since nothing stops an organiser typing a name into it.

---

## 11. Open questions

Marked **[team]** where the answer needs the wider team rather than just us.

**Q1 — min == max on exact divisions. [team]**
`floor`/`ceil` of 50% × 100 gives min 50, max 50 on both gender values: a
completely rigid quota, and the sums of both min and max equal `number_to_select`
exactly, leaving the algorithm no slack anywhere. Real selections almost always
need some. Options: accept it and let organisers hand-set min/max (current
plan); widen by one seat by default (`floor - 0`, `ceil + 1`); or add an explicit
slack/tolerance setting. If we add slack later it goes inside
`min_max_for_percentage` and nothing else changes.

**Q2 — What tolerance counts as "close to 100.0"?**
Plan assumes ±0.5, which accepts the 99.9/100.1 that published statistics
routinely produce and rejects an obvious slip. The explainer flags this as
unresolved too. Should it be a constant, or configurable per assembly?

**Q3 — Is breaking the auto-calculate link really permanent? [team]**
The explainer says permanently. The domain stores it as an ordinary bool, so a
"re-link to percentage" action would be a one-line service function and a button.
Do we want that, or is the permanence the point?

**Q4 — Comments: single field or history? [team]**
Plan implements a **single mutable text field** on each of `TargetCategory` and
`TargetValue`, per your steer. If it turns out to be a list of dated comments,
`TargetValue.comment` is inside a JSON column so it can become a list cheaply;
`TargetCategory.comment` is a real column and would need a second migration (or
a JSON column). Related sub-questions, all still open:

- Do we record old/new values when an edit is made — i.e. is there an audit
  trail alongside the comment? (Nothing in the current design does this. If we
  want it, it is a new table, not a field.)
- Is a comment **required** when breaking the link by hand? Plan says no.
- Can one comment cover several edits made in a single "save all"? Plan says
  each value keeps its own comment; there is no submission-level comment.

**Q5 — What should percentages do before `number_to_select` is agreed?**
Plan: store the percentage, leave min/max at 0, recalculate everything the moment
`number_to_select` is set. Alternative: refuse to accept percentages until
`number_to_select` is set. The first is friendlier and matches the explainer's
"number-to-select already agreed" precondition being a *precondition*, not a gate.

**Q6 — Should a percentage also drive `min_flex` / `max_flex`?**
Currently `update_target_value` resets both to defaults on every edit and lets
the sortition library calculate them. Plan leaves that alone. If Q1 gets a
"slack" answer, flex might be the right place to put it rather than min/max.

**Q7 — Should the selection report use the stored percentage?**
`selection_report._target_pct` currently derives a percentage from the *midpoint*
of min/max. Once a real target percentage exists, the report could show that
instead — arguably more honest, since it is what was actually asked for. The
snapshot already carries `percentage_target`. Out of scope here; flagging it.

**Q8 — CSV import/export of the new fields?**
`import_targets_from_csv` goes through `sortition_algorithms.read_in_features`,
which knows only `feature, value, min, max, min_flex, max_flex`. Adding
percentage/comment/source columns means either extending that library or parsing
the extra columns ourselves alongside it. Plan does neither — imported targets
get no percentage and no comments. Is that acceptable for now?

**Q9 — Does the legacy targets page need any of this?**
`targets_legacy.py` and `templates/targets/` are the older GOV.UK-styled page,
still registered in `flask_app.py:146`. Plan leaves it untouched, so it will show
min/max only. Is it on a path to deletion, and if so can this branch delete it?

**Q10 — Multiple sources per category?**
One `source_url` per category is what the explainer specifies. But a category
can legitimately draw on two datasets (e.g. one source for the split, another
for the adjustment). Is one enough, or should this be a list from the start?
Note the category *comment* is the escape hatch — extra URLs in there will
linkify.

**Q11 — What about the existing unused `description` fields?**
Both `TargetCategory.description` and `TargetValue.description` exist, are
persisted, and are shown nowhere. After this change each object has both a
`description` and a `comment`, which will confuse the next reader. Separate issue
to remove them, or fold them in now?

**Q12 — Where should `SORT_ORDER_STEP` live?**
It is currently `domain/respondent_field_schema.py:169`. Targets importing it
from there is odd. Move to `service_layer/constants.py`, duplicate it, or leave
it and import across?

**Q13 — Phase 0 (the `target_service.py` extraction) — yes or no?**
It is a pure move and makes the rest cleaner, but it touches several import
lines across `src` and `tests` and would show up in the diff of an otherwise
feature-focused branch.
