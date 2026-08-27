# Targets: percentages, comments, source URL, reordering

**Issue:** 666
**Branch:** `666-target-percentage`
**Status:** ✅ IMPLEMENTED — all phases done, on branch `666-target-percentage`
**Date:** 2026-08-21, revised 2026-08-24, implemented 2026-08-24

## Scope of this document

Detailed plan for the **domain, persistence and service layers**. The
entrypoint/UI layer is deliberately only sketched — we flesh that out once the
layers underneath are done and merged.

The behavioural spec this plan implements is
`docs/explainers/workflow-targets-and-fields.html` (flow 1, plus the
"Percentages", "Setting min and max by hand" and "Source URL and comments"
detail sections).

**Two deliberate departures from that spec:**

- The explainer says breaking the auto-calculate link is _permanent_. It isn't
  here — §6.3 adds an explicit re-link action (D4).
- The explainer gives `max = ceil(pct% of n)`. On an exact division that pins
  min and max to the same number, leaving the algorithm no room at all, so we
  add one seat in that case only (D3, §4.3).

Everything else follows the explainer.

---

## 1. What exists today

| Thing                   | Where                                                                                    | Notes                                                                                                |
| ----------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `TargetValue` dataclass | `src/opendlp/domain/targets.py`                                                          | `value`, `min`, `max`, `min_flex`, `max_flex`, `percentage_target`, `description`, `value_id`        |
| `TargetCategory`        | `src/opendlp/domain/targets.py`                                                          | `id`, `assembly_id`, `name`, `description`, `sort_order`, `values`, timestamps                       |
| Persistence             | `adapters/orm.py`                                                                        | `target_categories` table; `values` is a **JSON column** via `TargetValueListJSON`                   |
| Mapping                 | `adapters/database.py:191`                                                               | bare `map_imperatively`, no explicit `properties`                                                    |
| Repository              | `adapters/sql_repository.py:1066`                                                        | `SqlAlchemyTargetCategoryRepository`, ordered by `sort_order`                                        |
| Services                | `service_layer/assembly_service.py:558-880`                                              | create/get/import/update/delete category, add/update/delete value                                    |
| Checks                  | `service_layer/target_checking.py`                                                       | `check_targets_detailed` → `DetailedCheckResult` with per-value and per-category `TargetAnnotation`s |
| Algorithm feed          | `adapters/sortition_data_adapter.py`                                                     | emits `feature, value, min, max[, min_flex, max_flex]` rows                                          |
| Snapshot                | `domain/targets.py:target_categories_to_snapshot`                                        | written to `SelectionRunRecord.targets_used`                                                         |
| Report                  | `service_layer/selection_report.py`                                                      | `_target_pct` derives a percentage from the midpoint of min/max                                      |
| Live UI                 | `entrypoints/blueprints/targets.py` + `templates/backoffice/targets/category_block.html` | HTMX per-row edit, Alpine `editing` toggle                                                           |
| Legacy UI               | `entrypoints/blueprints/targets_legacy.py` + `templates/targets/`                        | hidden by default, slated for deletion — out of scope                                                |

Four facts that shape everything below:

1. **`percentage_target` already exists on `TargetValue`** — validated (0–100 or
   `None`), round-tripped through the JSON column, included in the snapshot,
   and **used by nothing**. We adopt it rather than adding a new field.
2. **`TargetValue` lives in a JSON column**, so adding fields to it needs **no
   migration** — old rows simply deserialise with the dataclass defaults.
   `TargetCategory` fields are real columns and do need one.
3. **`sort_order` already exists and is already the sort key** in the
   repository. Reordering is about _writing_ it, not about adding it.
4. **`sortition_algorithms.read_in_features` ignores unknown CSV columns** —
   `_feature_headers_flex` filters headers to the ones it knows and the
   docstring says so explicitly (`features.py:311`). We can add columns to the
   targets CSV without touching or forking that library.

---

## 2. Decisions taken

Agreed before drafting, plus the answers to the first review of this plan.

| #   | Decision                                                                                                                                                                                                                                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D1  | **min/max are stored fields, recalculated on change.** A service function recalculates them when the percentage changes, and `update_assembly` recalculates every linked value when `number_to_select` changes. Everything downstream (sortition adapter, `target_checking`, snapshots, report) keeps reading `min`/`max` unchanged. |
| D2  | **New `comment` field** on both `TargetCategory` and `TargetValue`.                                                                                                                                                                                                                                                                  |
| D3  | **`min = floor(pct% of n)`, `max = ceil(pct% of n)`, widened by one seat only when the two are equal** — so an exact division does not produce a rigid `min == max` quota, and the range is never wider than one seat. Two guards: a percentage of exactly zero is not widened, and `max` is clamped to `number_to_select` (§4.3). |
| D4  | **Breaking the link is reversible.** A "re-link to percentage" action restores auto-calculation (§6.3). Departs from the explainer.                                                                                                                                                                                                  |
| D5  | **Before `number_to_select` is set, a percentage-linked value has `min = max = 0`.** Not "leave the old numbers alone" — zero is the honest answer when the seat count is unknown, and everything fills in the moment `number_to_select` is agreed.                                                                                  |
| D6  | **`min_flex` / `max_flex` are out of scope.** Any write to min/max resets them to their defaults and lets the sortition library recalculate at selection time — which is what `update_target_value` already does today.                                                                                                              |
| D7  | **The existing unused `description` fields are removed now**, on both classes, rather than left to confuse alongside `comment`.                                                                                                                                                                                                      |
| D8  | **One `source_url` per category.** Extra sources go in the category comment, whose URLs linkify.                                                                                                                                                                                                                                     |
| D9  | **The selection report shows the real target percentage** when the run recorded one, falling back to the midpoint derivation for older runs (§6.6).                                                                                                                                                                                  |
| D10 | **CSV import gains optional `percentage`, `comment`, `category_comment` and `source_url` columns**, and derives a percentage from min/max when the column is absent (§6.5).                                                                                                                                                          |
| D11 | **Phase 0 (extracting `target_service.py`) goes ahead.**                                                                                                                                                                                                                                                                             |
| D12 | **The legacy targets page is not updated.** It is hidden by default and will be deleted.                                                                                                                                                                                                                                             |
| D13 | **`SORT_ORDER_STEP` moves to `service_layer/constants.py`**, with the two respondent-schema references updated to import it from there (§6.1).                                                                                                                                                                                       |
| D14 | **A category-level CSV column that disagrees between rows produces a visible import warning**, not a silent first-wins. `import_targets_from_csv` grows a warnings channel, which changes its return type (§6.5).                                                                                                                    |
| D15 | **A data migration strips `description` from the stored `values` JSON**, and backfills `minmax_manual = True` **only** where a percentage is already recorded — not blanket. The decoder filter ships regardless (§5.1).                                                                                                             |
| D16 | **The percentage-total tolerance is ±1.0**, as the module constant `PERCENTAGE_TOLERANCE`. A constant, deliberately not a per-assembly setting — one value we can revise on feedback, not a knob to configure (§4.4).                                                                                                                |
| D17 | **`comment` is a single mutable field**, on both classes. Change history is not this feature's job: a planned assembly-wide **activity log** domain model will record comment and min/max changes later (§4.2, and the forward note in §6.3).                                                                                        |
| D18 | **CSV import with no seat count derives percentages as `(min + max) / Σ(min + max)` within the category**, falling back to unset when that denominator is zero (§6.5).                                                                                                                                                               |
| D19 | **No domain events / message bus in this work.** The `number_to_select` recalculation stays a direct call. The reasoning, and where events _would_ pay off in this project, is in §10.                                                                                                                                               |
| D20 | **No live assembly has targets yet** — only test and demo data. The decoder filter still ships, but it no longer needs a commit of its own ahead of the field change (§9).                                                                                                                                                           |

---

## 3. Phase 0 — extract `target_service.py` (mechanical, own commit) ✅ DONE

`assembly_service.py` is 1227 lines and about 380 of them are target CRUD. This
change adds roughly another 250. Before touching behaviour, move the target
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

**Done.** All ten functions moved verbatim; `assembly_service.py` drops from 1228
to 834 lines. No shim. Callers updated in `blueprints/targets.py`,
`targets_legacy.py`, `dev.py` and seven test modules. Confirmed dead code as the
plan suspected: `get_feature_collection_for_assembly` has no caller in `src`,
only two in `tests/integration/test_assembly_service_targets.py`. Moved rather
than deleted — removing it is not this branch's job.

---

## 4. Phase 1 — Domain (`src/opendlp/domain/targets.py`) ✅ DONE

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
    comment: str = ""            # NEW — why min/max were set by hand
    minmax_manual: bool = False  # NEW — True when min/max were set directly
    value_id: uuid.UUID | None = None
```

`description` is **removed** (D7). Keep `value_id` last, matching the existing
convention.

**Validation additions in `_validate`:**

- `comment` — stripped; cap at `MAX_COMMENT_LENGTH = 2000`, raise `ValueError`
  above that. (It lives in a JSON blob, so an unbounded free-text field wants a
  sanity limit even though the underlying column is unconstrained.)
- Everything else unchanged.

### 4.2 `TargetCategory` — new and changed fields

```python
def __init__(self, assembly_id, name, sort_order=0,
             values=None, category_id=None, created_at=None, updated_at=None,
             comment="", source_url=""):
```

`description` is **removed** (D7); `comment` and `source_url` are new.

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

`create_detached_copy` must pass the new kwargs through and drop `description`.
It rebuilds values with `TargetValue(**vars(v))`, so new value fields are
carried automatically.

### 4.3 The percentage → min/max calculation

New module-level function, pure and independently testable:

```python
SLACK_SEATS = 1


def min_max_for_percentage(percentage: float, number_to_select: int) -> tuple[int, int]:
    """Min/max seats implied by a percentage of the assembly.

    floor/ceil of the exact share. An exact division would otherwise give
    min == max, so those are widened at the top by SLACK_SEATS (D3).
    """
    exact = percentage * number_to_select / 100
    low, high = math.floor(exact), math.ceil(exact)
    if low == high and high > 0:
        high = min(high + SLACK_SEATS, number_to_select)
    return low, high
```

Use `percentage * number_to_select / 100` (not `percentage / 100 * n`) so the
float division happens once, at the end.

**Widen only when `low == high`.** A non-exact division already produces a range
of one seat from floor/ceil alone; only an exact one collapses to a point. So the
condition is the whole rule, and the useful way to describe what the function
guarantees is: **the range is never wider than one seat.** An earlier draft
widened unconditionally, which produced ranges of two and was worse in every
case.

Two guards go with it, both found by running the cases rather than reasoning
about them:

- **`high > 0`** — otherwise 0% of 100 gives `(0, 1)`. A deliberate zero target
  would permit one seat, which is precisely what the organiser said they did not
  want. Given `n > 0`, `ceil(exact) == 0` happens only when the percentage is
  exactly zero, so the guard reads as "do not widen a target of nothing".
- **`min(..., number_to_select)`** — otherwise 100% of 100 gives `(100, 101)`, a
  max above the size of the assembly. Harmless to the algorithm but visibly
  wrong in the UI. Clamped, it is `(100, 100)`: rigid, but correctly so, since
  there is no 101st seat to be flexible about.

  Note this clamp now fires **only at exactly 100%**. Widening requires `exact`
  to be a whole number, and `exact + 1 > n` requires `exact >= n`. Keep it
  anyway — 100% is a real input — but do not go looking for other cases.

Worked cases, for the tests in §8:

| pct  | n   | result       | range | note                                    |
| ---- | --- | ------------ | ----- | --------------------------------------- |
| 50   | 100 | `(50, 51)`   | 1     | the case Q1 was about — no longer rigid |
| 33.3 | 100 | `(33, 34)`   | 1     | not exact, so untouched                 |
| 50   | 101 | `(50, 51)`   | 1     | not exact, so untouched                 |
| 1    | 20  | `(0, 1)`     | 1     | not exact, so untouched                 |
| 0    | 100 | `(0, 0)`     | 0     | zero guard                              |
| 100  | 100 | `(100, 100)` | 0     | clamp                                   |
| 99   | 100 | `(99, 100)`  | 1     | exact, widened, no clamp                |

Category totals stay feasible for the library's `sum(mins) <= n <= sum(maxes)`
check — necessarily so, since `sum(floor)` cannot exceed `n` and `sum(ceil)`
cannot fall below it when the percentages total 100. Checked anyway across
50/50, thirds, quarters, fifths and a 1/99 skew. A 50/50 category at `n = 100`
gives mins summing to 100 and maxes to 102: slack where there was none.

**This also removes the wart an earlier draft had to accept.** Absolute slack
applied to every value made small percentages proportionally enormous — 1% of 20
is 0.2 seats and used to yield `(0, 2)`, a max of 10% of the assembly. Widening
only exact divisions leaves that case at `(0, 1)`, so there is nothing left to
revisit.

**One note on `SLACK_SEATS` as a tuning knob.** It is honest at 1 and misleading
above it: at 2, exact divisions would get a range of 2 while everything else kept
1. If we ever want to widen further, express it as a **minimum range** instead —
`high = min(max(high, low + MIN_SEAT_RANGE), number_to_select)`, still behind the
`high > 0` guard. That is exactly equivalent at 1 and stays coherent above it.
Not worth doing pre-emptively; worth knowing before someone edits the constant.

This is the second deliberate departure from the explainer, after D4.

And on `TargetValue`:

```python
def apply_percentage(self, number_to_select: int) -> bool:
    """Recalculate min/max from the percentage. Returns True if anything moved.

    No-op when there is no percentage, or when the auto-calculate link has been
    broken. When number_to_select is not yet agreed, min and max are both zero.
    """
```

Guard conditions, **in this order** — the ordering carries the D5 decision:

1. `self.percentage_target is None` → return `False`, leave min/max untouched.
   This is what protects every pre-existing hand-entered target, which has no
   percentage and must not be zeroed.
2. `self.minmax_manual` → return `False`.
3. `number_to_select <= 0` → set `min = max = 0` (D5), reset flex per D6, return
   whether anything moved.
4. Otherwise compute via `min_max_for_percentage`, assign, reset flex, validate.

```python
def set_manual_min_max(self, min_count: int, max_count: int) -> None:
    """Set min/max directly, breaking the auto-calculate link."""

def relink_to_percentage(self, number_to_select: int) -> None:
    """Restore auto-calculation and immediately recalculate (D4).

    Raises ValueError if there is no percentage to link back to.
    """
```

Two traps to write into the code:

- **`_validate` requires `max >= min`**, so a bad pair must be rejected _before_
  either field is assigned — otherwise a failed call leaves the object dirty.
  Check `max_count >= min_count >= 0` up front, then assign.
- **`_validate` requires `min_flex <= min`.** When min drops (to 0 under D5, or
  to a smaller derived value), a stale `min_flex` makes validation fail on data
  the user never touched. Per D6, every write to min/max resets
  `min_flex = 0` and `max_flex = MAX_FLEX_UNSET`. That both fixes the invariant
  and matches what `update_target_value` already does — lift its existing
  comment ("the sortition library recalculates safe defaults at selection
  time") to the domain where the reset now lives.

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

`PERCENTAGE_TOLERANCE = 1.0` as a module constant (D16) — a constant we revise
on feedback, explicitly **not** a per-assembly setting. Compare inclusively
(`abs(total - 100.0) <= PERCENTAGE_TOLERANCE`) and round the sum to 2dp first,
so float addition of values like `33.3` cannot push a total sitting exactly on
the boundary over it.

±1.0 comfortably accepts the 99.9/100.1 that published statistics produce, and
also absorbs the rounding drift that D18's CSV derivation introduces — three
values at 33.333% round to 33.3 and sum to 99.9.

A category where _some_ values have a percentage and some don't will sum to
well under 100 and warn. That is correct — a half-filled category is exactly
the mistake worth flagging.

### 4.5 Snapshot

`target_categories_to_snapshot` gains `comment` and `source_url` at the category
level, `comment` and `minmax_manual` at the value level, and **loses
`description` at both levels** (D7). `percentage_target` is already there.

**This changes a persisted format.** Old `SelectionRunRecord.targets_used` rows
will have `description` and none of the new keys, so every reader must use
`.get()` with a default. The only reader today is
`selection_report._build_category_report`, which reads `value`, `min` and `max`
— all still present. §6.6 adds a `.get()` read of `percentage_target` there.

---

## 5. Phase 2 — Persistence ✅ DONE

### 5.1 `TargetValue` — no migration, but harden the decoder

Adding and removing dataclass fields needs no migration:

- `process_bind_param` uses `vars(v).copy()` → new fields serialise automatically.
- `process_result_value` does `TargetValue(**item)` → rows written before this
  change lack the new keys and get the dataclass defaults.

**But `TargetValue(**item)` raises `TypeError` on _unknown_ keys**, and after D7
every existing row carries a `description` key that the dataclass no longer has.
So the decoder must filter to known field names — this is not a nice-to-have,
it is what makes both the removal and any future rollback survivable:

```python
_TARGET_VALUE_FIELDS = {f.name for f in dataclasses.fields(TargetValue)}
...
kwargs = {k: v for k, v in item.items() if k in _TARGET_VALUE_FIELDS}
```

Log at `debug` with the dropped key _names_ when anything is filtered, so real
schema drift isn't silent. Names only, never values — a target label is not
personal data, but a free-text comment could be.

**Ship this filter in the same commit as the field removal** (commit 4). Without
it, the moment the `description` field leaves the dataclass every existing target
row fails to load. It had a commit to itself in the previous draft so it could
land first and protect live rows mid-deploy; D20 removed the live rows, so the
ordering no longer buys anything — but the filter itself still does.

#### Why not a data migration instead of the filter? (D15)

The alternative is to delete `description` from every stored value in a data
migration and keep the decoder naive. Worth asking, and the answer is that these
are not really alternatives: the migration cleans the **data**, the filter keeps
the **code** safe. Only the filter covers the failure modes that bite _after_ the
migration has run.

| Scenario                                                                 | Migration only                                 | Filter only     | Both    |
| ------------------------------------------------------------------------ | ---------------------------------------------- | --------------- | ------- |
| Rows written before the change                                           | clean                                          | tolerated       | clean   |
| Rolling deploy — an old instance still writing `description` mid-migrate | **breaks** until the old instances are drained | tolerated       | fine    |
| `alembic downgrade` and then `upgrade` again                             | **breaks** — downgrade re-adds the key         | tolerated       | fine    |
| Restoring a pre-migration backup                                         | **breaks** until re-run                        | tolerated       | fine    |
| Some future field removal                                                | needs another migration                        | already handled | handled |
| Stale key lingers in the JSON indefinitely                               | no                                             | **yes**         | no      |

What settles it is the shape of the failure in those "breaks" cells. It is not
partial: `TargetValue(**item)` raises, the repository cannot materialise the
category, and the targets page 500s for **every** assembly — not just the row
carrying the stale key. Three lines of defensive decoding against a site-wide
outage is not a close call.

So write both, in commit 4. The data migration is a tidy-up that rides along in
the §5.2 revision at no extra cost, since we are already writing a migration
against that table.

D20 does soften the table above: with no live targets, the three "breaks" rows
threaten a demo database rather than a customer's data. It does not empty it.
The failure is still site-wide rather than per-row, a demo database is the one
someone is being shown, and "no live targets" has a shelf life.

#### Backfilling `minmax_manual` — yes, but narrowly

Setting `minmax_manual = True` on every existing value aims at the right hazard,
but a blanket backfill costs more than it buys.

**What it buys: nothing today.** Guard 1 in `apply_percentage` (§4.3) already
leaves a value untouched when `percentage_target` is `None`, and
`percentage_target` **has no writer anywhere in `src`** — verified by grep, the
only hits are its own declaration, its validation and the snapshot. Every
production row therefore has `percentage_target = null` and is already immune.

**What it costs: friction on the happy path, in every assembly that exists.**
§6.3 sets the percentage and then calls `apply_percentage`, which no-ops when the
link is broken. After a blanket backfill, an organiser typing a percentage into
an existing target watches min/max not move, and has to find and click "re-link"
before the feature does anything at all. That is a poor first encounter with the
feature, repeated across every category of every existing assembly.

**The real hazard is narrower than "existing rows".** It is: _a percentage
appearing on a value that already has deliberate min/max, without the link being
broken at the same time_. That is exactly the CSV trap in §6.5, and the rule that
closes it is a rule about **writers**, not about legacy data:

> Any code path that populates `percentage_target` in bulk, or by derivation,
> must set `minmax_manual = True` in the same operation. Only a percentage a
> human typed into one specific value leaves the link intact — because typing
> one is a deliberate opt-in to auto-calculation.

CSV import is the only such path in this plan, and §6.5 already obeys it.

So do the backfill as defence in depth, **scoped to the rows that could actually
be affected**: set `minmax_manual = True` only where `percentage_target` holds a
number. In production that is expected to match zero rows; in dev databases, in
local fixtures, and in whatever environments we cannot see, it closes the hole
for nothing and with no UX cost. It rides in the same `op.execute` as the
`description` strip.

### 5.2 `TargetCategory` — one migration

In `orm.target_categories`: add two columns, drop one.

```python
Column("comment", Text, nullable=False, server_default="", default=""),
Column("source_url", Text, nullable=False, server_default="", default=""),
# Column("description", ...)  -- removed
```

`server_default=""` on both so the migration can add them `NOT NULL` against
existing rows in one step.

```bash
uv run alembic revision --autogenerate -m "add comment and source_url to target categories, drop description"
```

Then **read the generated file** — autogenerate against this schema has a habit
of picking up unrelated drift. Strip anything that isn't these three operations.
The `drop_column` loses data irreversibly, so make sure `downgrade()` re-adds
`description` with a server default rather than leaving a stub.

No change needed in `adapters/database.py`: `TargetCategory` is mapped with a
bare `map_imperatively(targets.TargetCategory, orm.target_categories)` and no
explicit `properties`, so column changes are picked up automatically.

No new table, so `tests/conftest.py::_delete_all_test_data` and
`tests/bdd/conftest.py::delete_all_except_standard_users` need no change.

#### The same revision carries the data migration (D15)

Autogenerate will not produce this — hand-write it into `upgrade()`, after the
column operations:

```python
op.execute("""
    UPDATE target_categories
    SET "values" = (
        SELECT COALESCE(
            jsonb_agg(
                CASE
                    WHEN jsonb_typeof(elem -> 'percentage_target') = 'number'
                    THEN (elem - 'description') || '{"minmax_manual": true}'::jsonb
                    ELSE elem - 'description'
                END
                ORDER BY ord
            ),
            '[]'::jsonb
        )::json
        FROM jsonb_array_elements("values"::jsonb) WITH ORDINALITY AS t(elem, ord)
    )
    WHERE "values"::text <> '[]'
""")
```

Four things in there are not obvious and will cost an hour each if missed:

- **`values` is a reserved word in Postgres** and must be double-quoted. An
  unquoted `SET values = ...` is a syntax error — at least a loud failure.
- **The column is `json`, not `jsonb`.** `TargetValueListJSON.impl` is
  SQLAlchemy's generic `JSON`, which maps to `json` on Postgres, and `json` has
  no key-delete operator. Hence the cast in and back out again.
- **`WITH ORDINALITY` and `ORDER BY ord` are load-bearing.** The order of values
  within a category _is_ the display order. `jsonb_agg` over
  `jsonb_array_elements` happens to preserve input order today, but nothing
  guarantees it, and a silent reshuffle of every target list in the database is
  not a bug anyone would enjoy tracing.
- **`jsonb_typeof(...) = 'number'`** distinguishes a real percentage from both a
  missing key (`NULL`) and a stored JSON `null` (`'null'`), which a plain
  `IS NOT NULL` would not.

The round-trip through `jsonb` normalises key order within each object. That is
cosmetic — we decode by key — but it makes the before/after diff look larger than
it is if anyone inspects rows directly.

`downgrade()` needs no data change: the old dataclass declares
`description: str = ""`, so a missing key simply takes the default.

That `UPDATE` was run against the local Postgres on a temp table holding the
three interesting shapes — a value with a numeric `percentage_target`, one with
a JSON `null`, one with the key absent — plus a category with an empty `values`
list. It reported `UPDATE 1`, correctly skipping the empty category, and produced
`minmax_manual: true` on only the first value, with `description` gone from all
three and the order intact.

Test it against a database that actually holds pre-change rows — an empty test
database will pass this migration without exercising a single line of the
`UPDATE`. See §8 for how.

---

## 6. Phase 3 — Service layer ✅ DONE

All new functions go in `target_service.py`. All follow the house conventions:
take `uow` as first arg, **never** open a `with uow:` block, permission-check via
`can_manage_assembly` / `require_assembly_permission`, return
`create_detached_copy()`, and call `flag_modified(category, "values")` after any
in-place mutation of the JSON list.

### 6.1 Reorder categories

```python
def reorder_target_categories(
    uow, user_id, assembly_id, ordered_category_ids: list[uuid.UUID]
) -> None:
```

Modelled directly on `respondent_field_schema_service.reorder_group`
(`src/opendlp/service_layer/respondent_field_schema_service.py:507`):

- require the submitted set to be **exactly** the assembly's current category ids
  — raise otherwise, so a stale page can't silently drop a category from the
  ordering;
- re-issue `sort_order` as `(i + 1) * SORT_ORDER_STEP` with
  `SORT_ORDER_STEP = 10`, moved from `domain/respondent_field_schema.py:169`
  to `service_layer/constants.py` with both existing references updated (D13);
- bump `updated_at` on every touched category.

Existing rows have `sort_order` values of `0` or a bare index; re-issuing on the
first reorder fixes that with no data migration. Gaps of 10 leave room for a
future drag-and-drop insert without a full renumber.

**While here:** `create_target_category` takes `sort_order=0` and the blueprint
computes `sort_order = len(existing)` at `blueprints/targets.py:305` and `:811`.
That is policy in an entrypoint. Move it: when `sort_order` is not supplied, the
service picks `max(existing) + SORT_ORDER_STEP`. Two call sites to simplify.

### 6.2 Percentages

```python
def set_target_value_percentage(
    uow, user_id, assembly_id, category_id, value_id, percentage: float | None
) -> TargetCategory:
```

Sets `percentage_target`, then calls `value.apply_percentage(assembly.number_to_select)`.
Needs the assembly loaded for `number_to_select`.

```python
def recalculate_minmax_for_assembly(uow, assembly_id: uuid.UUID) -> list[TargetValueChange]:
    """Re-derive min/max for every value with an intact auto-calculate link.

    Returns the values that moved, with their old and new min/max — see the
    activity-log note in §6.3 for why this is a list and not a count. No
    permission check: this is an internal consequence of an already-authorised
    change, not a user action.
    """
```

Called from **`assembly_service.update_assembly`**, the single funnel for both
the full assembly edit form and the dedicated `backoffice.update_number_to_select`
route (`blueprints/backoffice.py:252`).

`update_assembly` applies updates with a blind `setattr` loop
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
create a cycle (`target_service` wants permission helpers). If it does, import
only from `service_layer/permissions.py`, where they already live — do **not**
import `assembly_service` from `target_service`.

### 6.3 Value and category edits, and re-linking

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

Semantics, and this is the fiddly bit — write it into the docstring:

- `min_count`/`max_count` supplied and **different from the current stored
  values** → `set_manual_min_max(...)`, which sets `minmax_manual = True`.
- `min_count`/`max_count` supplied and **identical** to the current values →
  do nothing, do **not** break the link. Without this rule, a "save all" form
  that round-trips every field on every save would break every link in the
  assembly on first use. **This is the load-bearing decision that makes the
  bulk-save UI possible at all.**
- `percentage` supplied → set it, then `apply_percentage(...)`, which no-ops if
  the link is already broken.
- If both a changed percentage **and** a changed min/max arrive in one
  submission, the explicit min/max wins and the link breaks. Apply the
  percentage first, then the manual min/max.
- `None` means "not submitted, leave alone" for each parameter. `percentage` is
  ambiguous here — `None` is also a legitimate value meaning "clear the
  percentage". Use a sentinel (`UNSET = object()`) rather than overloading
  `None`. Note **`FBT` is enabled in ruff**, so a `clear_percentage` bool
  alternative would have to be keyword-only.
- Clearing the percentage leaves `min`/`max` where they are and leaves
  `minmax_manual` as it was.

```python
def relink_target_value_to_percentage(
    uow, user_id, assembly_id, category_id, value_id
) -> TargetCategory:
    """Restore auto-calculation for one value and recalculate it now (D4)."""
```

Refuses with a clear error when the value has no percentage — "re-link to the
percentage" is meaningless without one, and silently clearing the flag would
leave a value claiming to be linked while showing hand-typed numbers.

`add_target_value` gains the same optional `percentage` and `comment`
parameters, applying the percentage on construction.

**Forward note for the activity log (D17).** History is a later, assembly-wide
feature, but it will want to hook exactly the mutations this section defines:
`set_manual_min_max`, `relink_to_percentage`, comment edits, and the sweep in
`recalculate_minmax_for_assembly`. Two cheap things now make that easy later,
and neither is speculative generality:

- Keep every target mutation funnelled through these service functions rather
  than letting a route touch the domain object directly. The plan already does
  this; it is worth stating as the reason.
- Have `recalculate_minmax_for_assembly` return the **list of values it
  changed** rather than a count. A caller wanting the count calls `len()`. An
  activity log wanting old and new numbers cannot recover them from an `int`.
  The int in §6.2's signature should become that list.

`two_factor_audit_log` (`orm.py:491`) is the existing precedent for the shape —
`action` string, `performed_by`, `timestamp`, JSON `metadata`. Whoever builds
the activity log should start there rather than inventing a second convention.

```python
def update_target_category(
    uow, user_id, assembly_id, category_id,
    name: str, comment: str = "", source_url: str = "",
) -> TargetCategory:
```

`description` drops out of the signature (D7). Domain validation on `source_url`
surfaces as `ValueError`; the route turns that into a field error, not a 500.

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

### 6.5 CSV import (D10)

`import_targets_from_csv` currently parses with `DictReader`, hands headers and
body to `read_in_features`, and discards the two column names it returns.

Because the library **ignores unknown headers** (`features.py:311`), we do not
need to filter, fork or pre-process anything. The change is additive:

1. Keep `read_in_features(headers, body)` for validating and parsing min/max.
2. Capture its return values instead of discarding them — it returns
   `(features, feature_column_name, feature_value_column_name)`, which tell us
   whether the file used the modern `feature`/`value` headers or the legacy
   `category`/`name` ones. Use those names to key back into the raw rows.
3. Build a side-index from the raw `body`: value-level extras keyed by
   `(feature, value)`, category-level extras keyed by feature.
4. Attach them when constructing each `TargetCategory` / `TargetValue`.

New optional columns, matched case-insensitively in our own code:

| Column             | Level    | Behaviour                                                                                                                       |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `percentage`       | value    | 0–100. Absent or empty → derived, see below.                                                                                    |
| `comment`          | value    | Free text.                                                                                                                      |
| `category_comment` | category | First non-empty row for that feature wins; disagreement between rows is warned about (D14).                                     |
| `source_url`       | category | Same first-wins-plus-warning rule; validated by the domain, so a bad URL fails the import outright with a row-specific message. |

None of these collide with the library's reserved names. Note that `category`
_is_ reserved (it is the legacy feature column), which is why the category-level
comment column is `category_comment`.

**Deriving the percentage when the column is absent:**

- `number_to_select > 0` → `round(midpoint(min, max) / number_to_select * 100, 1)`.
  This is deliberately the same formula `selection_report._target_pct` uses, so
  an imported percentage and the report agree by construction.
- `number_to_select == 0` → derive **within the category** as
  `(min + max) / Σ(min + max) × 100`, rounded to 1dp (D18). Equivalent to the
  ratio of midpoints, since the halves cancel, and it needs no seat count.
- `Σ(min + max) == 0` for the category → leave `percentage_target` as `None`.
  That is the `create_target_category` case, where respondent-derived values
  arrive at `min = 0, max = 0` and there is genuinely nothing to infer from.

**The two formulas are not interchangeable, and that is deliberate.** D18
normalises to exactly 100 by construction, so it can never trip the sum-to-100
warning. `midpoint / n` can, and when it does that is real signal — a CSV whose
midpoints sum to 90% of the assembly has a problem worth surfacing. So the
seat-count formula stays in charge whenever there is a seat count, and D18 is
strictly the fallback.

Two details on D18:

- **The sums are per category, never across the file.** Summing `min + max`
  across features would be meaningless — each feature independently covers the
  whole assembly.
- **Rounding to 1dp breaks the exact 100.** Three values at 33.333% become 33.3
  and total 99.9. Within D16's ±1.0 tolerance, so no warning; worth knowing
  before someone reports it as a bug.

Put the derivation on the domain as `TargetCategory.derive_percentages_from_minmax()`
rather than inside the CSV parser. It is pure arithmetic over a category, it is
where §4.4's totals already live, and it is unit-testable without constructing a
CSV. It also becomes reusable if we later offer a "fill in percentages from the
existing min/max" action on an ordinary category — worth noting, out of scope.

**Every CSV-imported value gets `minmax_manual = True`.**

This matters more than it looks. The CSV format makes min and max mandatory, so
every imported value carries deliberate, hand-set numbers. If the link were left
intact, the first change to `number_to_select` would recalculate min/max from
the _derived_ percentage and silently **narrow** every imported range:
`min=10, max=15, n=100` derives 12.5%, which recalculates to `min=12, max=13`.
The organiser's deliberate range would vanish without anyone touching it.

So imported min/max are manual, the derived percentage is informational — it
drives the report and the sum-to-100 warning — and the D4 re-link action is
there for an organiser who _wants_ percentage-driven min/max.

**Surfacing disagreement between rows (D14).**

`category_comment` and `source_url` are properties of the _feature_, but the CSV
is one row per _value_, so they get repeated on every row of a category and can
disagree. First-wins stays the resolution — there is no better one available —
but it is reported rather than silent.

That needs a channel for non-fatal messages, which `import_targets_from_csv` does
not have: it returns `list[TargetCategory]`. Give it a NamedTuple return in
`target_service`:

```python
class TargetImportResult(NamedTuple):
    categories: list[TargetCategory]
    warnings: list[str]
```

Warnings are already-translated strings built with `_()` in the service layer,
which is where the context to phrase them lives. The conflicting values are
interpolated as parameters and **truncated** — they are arbitrary CSV content and
a comment column could be a paragraph:

```python
_(
    'Rows for "%(category)s" gave different values for %(column)s. '
    'Using "%(used)s" and ignoring %(count)s other value(s).',
    category=name, column="source_url", used=truncate(chosen), count=n,
)
```

This is the one place in the feature where CSV content is echoed back to the
user. Jinja autoescape handles the escaping in the flash, so the truncation is
there for legibility rather than safety — but keep it.

Three callers change, all mechanically:

- **`blueprints/targets.py:203`** — the real one. Flash each warning at
  `"warning"` alongside the existing success flash.
- **`blueprints/dev.py:367`** — the service-docs scratch page. Add `warnings` to
  the dict it returns and check `src/js/components/service-docs/targets.js`
  renders it. There is no JSON Schema or recorded fixture for this endpoint
  (`schemas/json_api/` has only error, registration-document and
  registration-image), so no re-recording is needed.
- **`blueprints/targets_legacy.py:148`** — **a wrinkle against D12.** The legacy
  page is not being updated, but it will not compile against the new return type.
  Give it the one-line unpack (`result.categories`) and stop there; do not add
  warning display to a page that is about to be deleted.

There is no targets CSV _export_ in the codebase, so this is import-only.

### 6.6 Selection report uses the real percentage (D9)

`selection_report._target_pct(target_min, target_max, number_to_select)` derives
a percentage from the midpoint of min/max. Change it to prefer the recorded one:

```python
def _target_pct(value_snapshot: dict, number_to_select: int) -> float:
    """The target percentage the run was configured with.

    Prefers the recorded percentage; falls back to the midpoint of min/max for
    runs recorded before percentages existed, and for values that never had one.
    """
    stored = value_snapshot.get("percentage_target")
    if stored is not None:
        return round(float(stored), 1)
    ...  # existing midpoint derivation
```

The signature changes from `(min, max, n)` to `(value_snapshot, n)`; the single
call site is `_build_category_report` at `selection_report.py:116`. `target_pct`
feeds the report CSV (`selection_report.py:235`) and nothing else — no template
reads it.

The existing fixtures in `tests/unit/test_selection_report.py` already carry
`percentage_target: 50.0` alongside min/max that derive to the same 50.0, so
expect little or no assertion churn — but add a case where the two _differ_,
which is the only way to prove which branch ran.

### 6.7 Percentage-sum warning

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

## 7. Phase 4 — Entrypoints and UI (sketch only) ✅ DONE

Enough detail to know the layers below are shaped right. We design this properly
in a follow-up.

**Done — built to this sketch.** Everything listed below is implemented: the form
fields, all three new routes, the bulk-save parser, the template changes and the
`linkify` filter. It is deliberately plain, because this is the part most likely
to be redesigned by the follow-up plan; the layers underneath do not depend on
any of these choices. The one addition not sketched here is
`entrypoints/save_all_parser.py`, which holds the `cat[...][values][...]` parsing
so the route stays thin, and `templates/backoffice/targets/bulk_edit_form.html`,
which is the edit-all form as a separate partial rather than a second mode inside
`category_block.html` — mixing the two sets of field names in one template was
markedly worse to read.

**Forms** (`entrypoints/forms.py`)

- `TargetValueForm` gains `percentage` (`DecimalField`, `NumberRange(0, 100)`,
  `Optional()`) and `comment` (`TextAreaField`, `Length(max=2000)`).
  `min_count` / `max_count` become `Optional()` — a value can be defined by
  percentage alone.
- `EditTargetCategoryForm` gains `comment` and `source_url` (`URLField` with a
  custom validator mirroring the domain's http/https rule, so the user gets a
  field error rather than a 500).
- Bulk save does **not** fit WTForms' one-form-one-object model. Parse
  `request.form` directly into the `TargetCategoryEdit` dataclasses with a
  dedicated parser, keeping WTForms for CSRF only. Field naming:
  `cat[<category_id>][values][<value_id>][percentage]`. Validate in the parser
  and return field-keyed errors the template can re-render.

**Routes** (`blueprints/targets.py`)

- `POST .../targets/categories/<id>/move` with a `direction` of `up`/`down`,
  mirroring `respondent_field_schema.move_field:435`. Up/down buttons are
  keyboard-accessible for free and dodge the drag-and-drop accessibility
  problem. The service takes a full ordering either way, so drag-and-drop can
  be added later without a service change.
- `POST .../targets/save-all` → `save_all_targets`, re-render the whole list.
- `POST .../targets/values/<id>/relink` → `relink_target_value_to_percentage`.
- Existing per-row routes stay — they are what the HTMX partials use, so
  "edit all" can ship without a big-bang template rewrite.

**Template** (`templates/backoffice/targets/category_block.html`)

- New percentage column between `Value` and `Min`, headed `Population (%)`.
  Written in the template as `Population (%%)`: flask-babel applies percent
  formatting to every translated string, so a lone `%` raises `ValueError`. A
  test asserts what actually reaches the page, since the escaping is invisible
  in the rendered output.
- `tfoot` gains a percentage total, styled as a warning when
  `percentage_total_is_plausible()` is false.
- A visual marker on rows where `minmax_manual` is true, and a `Notes` column
  after `Max` carrying the comment — not a tooltip, and not tucked under the
  value. The explainer's whole argument for the comment field is that a
  hand-set number needs its reason _visible_, and a column of its own is what
  makes a table of reasons readable down the page. The column order matches
  the bulk edit form, so both tables read the same left to right.
- The re-link control belongs on those same rows: it is the one place where a
  broken link is already being shown.
- Category header shows `source_url` as a link (`target="_blank"`,
  `rel="noopener noreferrer"`) and the category comment.
- Comments render with URLs linkified. **Escape, do not `|safe` raw user
  input**, and emit only `http`/`https` links. Check `docs/frontend_security.md`
  first. The filter subclasses Django's `Urlizer` (Django is already a
  dependency, and already borrowed from for password and email validation)
  rather than carrying its own regex — punctuation, IDN quoting and length
  limits are all handled there. Its bare-`www.` branch reads a Django setting,
  which a Flask app has none of, so that branch is disabled; the effect is the
  http/https-only rule we wanted anyway. Link _text_ is trimmed to
  `MAX_URL_TEXT_LENGTH` (40) with an ellipsis — a real source URL in our data
  is 170 characters, which wraps over several lines and buries the value it
  explains. The `href` keeps the whole URL.
- "Edit all" / "Save all": one Alpine `x-data` at page level holding a flat
  `editingAll` boolean (Alpine here is CSP-constrained — flat `x-model`
  properties only, no string arguments in `@click`; see
  `templates/backoffice/patterns.html`).

**i18n:** every new string in `_()` / `_l()`, then `just translate-regen`.

**Tests for this phase:** component tests for the page, e2e for the routes, a
new `features/targets.feature` BDD scenario for edit-all → save-all → reorder,
plus vitest for any new JS. To be specified with the UI plan.

### 7.1 Follow-up — all editing moved into the bulk form

The sketch above left mutation controls on the read-only page and put only field
edits in the bulk form. That split does not survive contact with use: the two
surfaces offer overlapping ways to change the same thing, and neither is
complete. The follow-up makes the division absolute.

- The read-only page offers **"Add category" and "Edit targets", and nothing
  else**. Rename, reorder, add value, delete value and delete category are gone
  from it, along with the per-row "Edit" and the "Add all missing values" button.
  The missing-values panel stays as information, pointing at "Edit targets".
- The bulk form gains all of them: per-row **Delete value**, per-category
  **Delete target**, **Move up** / **Move down**, **Add value**, and **Add values
  found in respondent data**.
- Both views show the assembly's `number_to_select` under the title. Every
  percentage on the page is a share of that number, and it was nowhere on screen.
- **"Edit targets" sits beside the `<h2>`**, right-aligned on the heading row
  rather than stacked in a band beneath it. The heading itself reads "Targets",
  not "Target Categories". It is hidden while editing, being what got you there.
- **There is no "Check targets in detail" button.** `save_all` redirects to
  `targets.check_targets` rather than back to the plain view, so the detailed
  check runs on every save and its annotations are already on the page you land
  on. The route stays — it is the redirect target — but nothing links to it.
  Two consequences worth knowing:
  - Every save now pays for the check, which loads the whole respondent pool and
    runs an LP feasibility solve. Saving is deliberate and infrequent, so this is
    the right place for it; a page _view_ would not be.
  - Saving targets before any respondents are uploaded shows "No eligible
    respondents found for selection". That is the check working, and the message
    says what to do, but it does arrive in an error banner during ordinary setup.

**A rejected save comes back as the form, not as a toast.** `save_all` re-renders
`assembly_targets.html` with `editing_all` true, the bulk form rebuilt from the
submission, and each message against the input that caused it. Redirecting - what
it used to do - threw away every edit on the page and left the message pointing
at nothing. Four things this needs:

- `save_all_targets` **collects** errors instead of raising on the first, and
  raises `TargetsNotSaved` at the end. One round trip per mistake is what makes a
  bulk form miserable. Raising is still what rolls the unit of work back, so
  "nothing was saved" stays true - including the half of the save that was fine.
- Errors carry the **form ids** of the category and value they belong to, so the
  edit dataclasses gain `form_id`. `value_id` will not do: two rows the user has
  just added both have `value_id` of `None`. The entrypoint turns those ids into
  a form field name (`errors_by_field`); the service knows which value is wrong,
  not what its input was called.
- The redisplayed form is built from the **raw submission** (`pending_categories`),
  not from the parsed edits, so a number the parser could not read comes back as
  typed - which is exactly the one that has to be corrected. A bad row still
  produces an edit for the same reason: dropping it would take it off the page.
- Pending **deletions and relink requests** ride in the hidden fields and are
  seeded into the Alpine components (`deleted:` on both), or saving again would
  quietly undo them.

`_value_problem` names the cases we can phrase well - min above max, a negative,
a percentage outside 0-100 - so the form says which box is wrong in words aimed
at the person filling it in. The domain still enforces all of them; it just
raises on the first with a message written for a developer. Anything the named
checks miss falls through to the generic catch and lands on the row.

**Where min and max came from is shown in the cells themselves.** The read-only
table used to carry a "Set by hand" badge in the value cell, which said nothing
about the values that were calculated and nothing about where either number
lives. Instead each min and max cell is tinted: `--color-warning-100` with a
raised-hand icon for a number typed in by hand, `--color-info-100` with a
sparkles icon for one calculated from the percentage. A value with no percentage
has nothing to calculate from, so neither reading applies and its cell stays
plain. This follows the Figma at node `4686-9425`, which uses our own tokens.

Two things worth knowing about the markup. The icon carries the wording as a
`title` for the hover and as `sr-only` text for anything not looking at the
screen - a tint and a glyph on their own say nothing to a screen reader.
`sr-only` rather than `govuk-visually-hidden`, because the backoffice ships
Tailwind and the govuk stylesheet is not loaded there; the govuk class renders
as ordinary visible text. The min and max columns are left-aligned so the
number sits at the left of its tinted block and the icon at the right, which is
also what puts the heading and the total in line with the values.

**Deletion and addition are provisional.** A per-row request would throw away
every other unsaved edit on the page, so instead a deleted row stays in place,
struck through, with its own undo, and carries a hidden `[deleted]` flag; a row
the user added and then deleted simply leaves the DOM. Nothing is destroyed
until "Save all". `save_all_targets` therefore deletes only what is explicitly
marked: absence from the payload still means "leave alone", so a partial
submission cannot destroy anything.

Reordering works the same way — moving a block reorders the DOM and re-issues
every category's hidden `sort_order`, sent as a complete set because
`reorder_target_categories` requires one.

**Re-linking** is a per-row `[relink]` flag rather than its own request. When set,
the submitted min/max are ignored entirely: the point of re-linking is that the
seat counts stop being the user's to type.

**The totals row is now in both views.** In the bulk form the browser keeps it up
to date as the numbers are typed (`bulk-targets-category.js`). It previews what
is entered rather than predicting what will be stored: a re-linked row still
shows the seat counts it holds now, because recalculating them is the server's
job, and duplicating `min_max_for_percentage` in JavaScript would put the rule in
two places. Live min/max preview is a possible follow-up, and would need that
duplication weighed against it.

**The respondent counts sit beside the percentage, in both views.**
"Respondents" and "Selected" used to trail the read-only row after the notes.
They now sit between "Population (%)" and "Min", which is where they are read: a
percentage is judged against how many respondents actually hold that value, and
min and max against both. The bulk form gained the same two columns in the same
place, so a column means the same thing whichever view you are on. Four things
follow:

- A column appears only when there is something to count. "Respondents" needs
  the category name to match a respondent data column; "Selected" needs some
  respondents to have been selected. A category with neither shows neither
  column, rather than a column of dashes.
- **"Selected" means selected _or_ confirmed.** Confirmed is selected and then
  confirmed, so both statuses count. Its heading carries an info icon saying so,
  for the same reason "Respondents" does: the word alone names one of the two.
- **"Respondents" means the pool, plus whoever has been taken from it** - `POOL`,
  `SELECTED` and `CONFIRMED`. A withdrawn person has left the pool a target is
  measured against, a test submission was never in it, and a deleted one has had
  its details blanked. Both counts name the statuses they *include*
  (`COUNTED_RESPONDENT_STATUSES` and `SELECTED_RESPONDENT_STATUSES` in
  `domain/value_objects.py`, shared by the SQL repository and the fake), so a
  status added later has to be considered rather than quietly counted - which is
  what the previous "anything but `DELETED`" filter did. The heading carries an
  info icon saying so, because a column of numbers cannot: none of this is
  guessable from the word "Respondents". The icon itself is
  `components/info_icon.html` - hover text and `sr-only` wording from one string,
  because a glyph on its own says nothing to a screen reader. The change reaches
  everything counting values off respondent data, including the columns offered
  as new categories and the values auto-added with them.
- In the bulk form the numbers are read-only and **as they were when the page
  loaded**. They describe the respondent data, which the form never touches, so
  renaming a value does not move its count, and a row whose value is blank - or
  names something no respondent answered - shows a dash rather than a zero. A
  zero would claim the value was asked about and nobody chose it. Making the
  count follow what is typed would mean a live lookup for a number that is only
  on the page for reference.

**Adding a target is provisional too.** A text box and "Add target" at the foot
of the form clone a blank category block under a `new-<n>` id — the same shape
`new-<n>` value rows use — and `save_all_targets` creates a category for any edit
with no `category_id`. Unlike `create_target_category` it does not auto-populate
values from a matching respondent column: the user is looking at the form where
they would add them, and rows appearing under a name they had just typed would be
a surprise.

`(assembly_id, name)` carries a unique index, so `_CategoryNaming` checks names
during the save and raises a `ValueError` the route can flash. It keeps a name
claimed for its own category even when the save deletes or renames it away:
freeing it would need the DELETE flushed before the INSERT, and SQLAlchemy orders
those the other way round. Deleting "Gender" and adding a new "Gender" in one go
is therefore refused — do it in two saves. `save_all` also gained a catch-all
handler, because a whole page of edits should not be lost to a stack trace.

**The row controls are icons**, following the Figma at node `4771-32435`:
"Use percentage" is the undo circle, "Delete value" the bin. Both are icon-only
buttons whose `aria_label` is the wording they replaced, so they still answer to
`get_by_role("button", name="Delete value")` and a screen reader still hears the
verb. Two things worth knowing:

- **"Use percentage" is disabled, not hidden**, when there is nothing to re-link -
  a value with no percentage, or one whose min and max are already calculated -
  and again once re-linking has been asked for. A control that comes and goes is
  harder to find than one plainly unavailable, and the row keeps its shape either
  way. The bin keeps the pending-delete swap: it is replaced by "Undo" while the
  row is struck through.
- The `attrs` string is built with `{% set %}…{% endset %}`, **not** `~`
  concatenation. Under autoescape `~` escapes the quotes, so `@click` arrives as
  `@click=&#34;remove()&#34;` - which renders, looks right, and does nothing when
  clicked. The component tests were perfectly happy; only the BDD suite noticed.
  Hence `test_the_row_controls_carry_live_click_handlers`.

**Layout:** "Save all" and "Cancel" sit at the top right of the form, with "Save
all" primary and to the right; "Add value" sits inside the table between the last
value and the totals row. "Edit targets" on the view page is the primary action.

**The category header row follows the same Figma.** "Move up" and "Move down"
are chevron icons - `aria_label` carrying the wording they replaced, so
`get_by_role("button", name="Move down")` still finds them - and they sit with
"Delete target" in an `ml-auto` group at the right edge of the row, clear of the
name, source and comment fields. The controls that reshape the page are worth
separating from the ones that fill it in. `moveUp` / `moveDown` do not grey out
at the ends of the list: knowing a block is first or last means watching the
DOM the buttons reorder, which the Figma implies but the component does not
track. The category comment box is labelled "Comment", and so is the per-value
column beside it: they hold the same kind of thing, and "Notes" for one of them
was two words for one idea.

**The heading says the number to select, not how many categories there are.**
`number_to_select` moved out of the page header and into the line under the
`<h2>`, replacing "%(count)s categories defined." Every min and max on the page
is a share of the seat count, and the categories are listed immediately below,
so a tally of them says nothing the page does not already show. The empty state
still says "No target categories defined yet", now alongside the seat count
rather than instead of it. The legacy page keeps the tally: it is hidden and
slated for deletion (D12).

**The respondent and selected counts are left-aligned in the edit form.** They
sit between boxed inputs whose text starts at the left edge, so a right-aligned
number drifts away from everything the eye is running down. The read-only table
keeps them right-aligned - there they are among numbers, not among fields.

**Parser and service additions:** `save_all_parser` reads `[deleted]` and
`[sort_order]` on a category and `[deleted]` and `[relink]` on a value; either id
may be `new-<n>`; a deleted category carries no value edits, a deleted row needs
no name, and a category that is staying needs one — which also closes a hole
where an existing category could be renamed to the empty string.
`save_all_targets` splits into `_apply_category_edit` and `_apply_value_edit`.

**New JS:** `bulk-targets-category.js` (live totals, add rows from a `<template>`,
reorder, mark deleted), `bulk-targets-value-row.js` (one row's pending-delete and
re-link flags) and `bulk-targets-form.js` (add a category), over shared helpers in
`lib/bulk-targets-dom.js`. Placeholder substitution has to descend into nested
`<template>` elements — a cloned category carries the template its own rows come
from — and to rewrite `for` alongside `name` and `id`, or a cloned block's labels
point at an id that never existed.

---

## 8. Phase 5 — Tests ✅ DONE

Every layer, per the no-exceptions policy. Existing files to extend:

| File                                                   | What to add                                                                                |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| `tests/unit/test_targets.py`                           | The bulk of the new coverage — see below                                                   |
| `tests/unit/test_target_checking.py`                   | Percentage-total annotation: fires, is `warning`, does not flip `success`                  |
| `tests/unit/test_selection_report.py`                  | Recorded percentage preferred; midpoint fallback for old snapshots                         |
| `tests/contract/test_target_category_repo.py`          | Round-trip of `comment`, `source_url`, `minmax_manual` through fake and real repo          |
| `tests/integration/test_target_category_repository.py` | Same against real Postgres, plus **reading a row whose JSON still contains `description`** |
| `tests/integration/test_assembly_service_targets.py`   | All the new service functions, including CSV import                                        |

Removing `description` (D7) touches roughly 29 references across
`tests/unit/test_targets.py`, `test_selection_report.py`, `test_sortition_service.py`,
`tests/unit/domain/test_assembly.py`, `tests/contract/test_selection_run_record_repo.py`,
`tests/integration/test_assembly_service_targets.py` and
`tests/e2e/test_db_selection_backoffice.py` — mostly snapshot dictionaries.

**Unit (`tests/unit/test_targets.py`), the cases that matter:**

- `min_max_for_percentage`, the D3 table in §4.3 verbatim: 50% of 100 →
  (50, 51) and 99% of 100 → (99, 100) for the widened case; 33.3% of 100 →
  (33, 34), 50% of 101 → (50, 51) and 1% of 20 → (0, 1) for the untouched case.
  Plus the two guards as named cases, because they are the ones a later refactor
  will quietly break: **0% of 100 → (0, 0)** (a zero target is never widened) and
  **100% of 100 → (100, 100)** (max clamped to the assembly size).
- A property-style check that the range is **never wider than one seat**, over a
  sweep of percentages and assembly sizes. It is the single sentence that
  describes what the function guarantees, so assert it directly rather than
  hoping the table covers it.
- `apply_percentage` leaves min/max **untouched** when percentage is `None` —
  the guard that protects every pre-existing hand-entered target.
- `apply_percentage` no-ops when `minmax_manual` is True.
- `apply_percentage` with `number_to_select == 0` sets min and max to 0 (D5).
- A value with a large `min_flex` survives min dropping to 0 — proves the flex
  reset in D6 keeps `_validate` satisfied.
- `set_manual_min_max` sets the flag; a subsequent `apply_percentage` does not
  move the numbers; `relink_to_percentage` clears the flag and recalculates.
- `relink_to_percentage` raises when there is no percentage.
- `set_manual_min_max` with `max < min` raises **and leaves the object
  unmodified** (the ordering trap in §4.3 — test it explicitly).
- `percentage_total` returns `None` for a category with no percentages at all,
  and a float otherwise.
- `percentage_total_is_plausible` with D16's ±1.0: 99.9 and 100.1 pass; **99.0
  and 101.0 pass** (the comparison is inclusive, so pin the boundary); 98.9 and
  101.1 fail; 95.0 fails; a half-filled category fails.
- `derive_percentages_from_minmax` (D18): a category of (10,20),(30,40) derives
  30.0 and 70.0 and totals exactly 100; a category where every min and max is 0
  derives nothing and leaves each `percentage_target` as `None`; three equal
  values derive 33.3 each and total 99.9, which
  `percentage_total_is_plausible` still accepts.
- `source_url` accepts http/https, rejects `javascript:`, `data:`, a bare
  `example.com` with no scheme, and anything over 2048 chars.
- `comment` over 2000 chars raises.
- `create_detached_copy` carries every new field on both classes.
- `target_categories_to_snapshot` includes the new keys and omits `description`.

**Service (integration):**

- `reorder_target_categories` re-issues 10, 20, 30…; rejects a partial id set;
  rejects an id from another assembly.
- `create_target_category` with no `sort_order` lands after the existing ones.
- `update_assembly` changing `number_to_select` moves min/max on linked values
  and leaves manual ones alone. **And the negative case:** updating some other
  assembly field does not touch any target.
- `update_target_value` submitting unchanged min/max does **not** break the link
  (the rule the whole bulk-save UI rests on).
- `update_target_value` with a changed percentage and a changed min/max in one
  call: min/max wins, link breaks.
- `relink_target_value_to_percentage` restores auto-calculation, and a later
  `number_to_select` change then moves that value again.
- `save_all_targets` across two categories in one call; and a failure partway
  through leaves **nothing** committed.
- CSV import: with an explicit `percentage` column; without one and
  `number_to_select > 0` (derives midpoint over n); without one and
  `number_to_select == 0` (derives the D18 ratio, and the derived percentages
  total 100); without one, `number_to_select == 0` and every min/max zero
  (leaves them `None`); with `comment`, `category_comment`
  and `source_url`; with an invalid `source_url` (fails cleanly); with the
  legacy `category`/`name` headers plus the new columns.
- CSV import sets `minmax_manual` — and a subsequent `number_to_select` change
  therefore leaves the imported ranges alone. This is the regression test for
  the silent-narrowing trap in §6.5.
- CSV import where two rows of one category give different `source_url` values:
  the first non-empty one is used **and** a warning comes back in
  `TargetImportResult.warnings` (D14). Same for `category_comment`. And the
  negative: consistent rows produce no warnings at all.
- Permission denial on every new entry point.

**The data migration (D15) needs its own test**, and it is the one that is easy
to fake. An empty test database runs that `UPDATE` without touching a row and
passes, proving nothing. The test must insert `target_categories` rows whose
`values` JSON is in the _old_ shape — carrying `description`, missing
`minmax_manual`, one with a `percentage_target` number and one without — then run
the migration and assert:

- `description` is gone from every value;
- `minmax_manual` is `true` on the value that had a percentage, and **absent**
  (so it decodes to the `False` default) on the one that did not;
- the values are still in their original order (the `WITH ORDINALITY` guarantee);
- a category with an empty `values` list is untouched and still valid.

Use raw SQL for the insert, not the repository — the repository writes the _new_
shape, which is precisely the shape this migration does not need to handle.

---

## 9. Suggested commit sequence ✅ DONE

Landed as five commits rather than twelve. The domain, persistence and service
work went in together because the field changes and the service functions that
use them do not compile apart; the commit message describes all three. Two
deviations from the plan are worth recording:

- **`_apply_value_numbers` compares against min/max as they were on entry**, not
  against the values the percentage has just recalculated. Written the other way
  first, and a component test caught it: a form that round-trips the min/max it
  displayed would break the link every time someone typed a percentage, which is
  exactly what §6.3's "identical means leave it alone" rule exists to prevent.
  There is now a named regression test for it.
- **Phase 4 was built to the §7 sketch** rather than deferred. Without it the
  feature is unreachable from the UI. It is deliberately plain, and §7 records
  the two structural choices made along the way.

One BDD test fails on this branch —
`test_a_saved_scroll_position_is_restored_on_load` — and fails identically with
the branch stashed. It concerns the registration form view, not targets.


Docs commit separately from code, per house rule.

1. `docs: plan target percentages, comments and reordering` — this file. _(done)_
2. `refactor: move target services out of assembly_service` — Phase 0, no
   behaviour change, tests pass untouched apart from imports.
3. `feat: add percentage-derived min/max to target values` — domain only,
   §4.1/§4.3, plus unit tests. Nothing calls it yet.
4. `feat: add comments and source URL to targets, drop unused description` —
   domain + ORM + the decoder filter (§5.1) + the single migration carrying both
   the column changes and the D15 data migration (§4.2, §5.2), plus
   contract/integration tests, the migration test and the test-fixture cleanup.

   The decoder filter had a commit to itself in the previous draft, so it could
   land before any field change and protect live rows mid-deploy. D20 removed
   the thing it was protecting — no live assembly has targets — so it folds in
   here, next to the removal that makes it necessary. It is still mandatory
   code; it just no longer needs to be mandatory _first_.

5. `feat: recalculate target min/max when number to select changes` — §6.2.
6. `feat: allow relinking a target value to its percentage` — §6.3.
7. `feat: reorder target categories` — §6.1, including the `SORT_ORDER_STEP`
   move to `service_layer/constants.py` (D13). Do the move as the first commit
   of the pair if it makes the diff easier to read.
8. `feat: warn when target percentages do not total 100` — §6.7.
9. `feat: read percentages and comments from the targets CSV` — §6.5. This is
   the commit that changes `import_targets_from_csv`'s return type (D14) and so
   touches all three callers, legacy page included.
10. `feat: report the configured target percentage` — §6.6.
11. `feat: save all target edits in one operation` — §6.4.
12. UI, in its own sequence, after the follow-up plan.

Run `just test-js`, then `just check`, then `just test` before each commit that
touches code. Full runs take 10+ minutes — pipe to a file in the scratchpad
rather than into the terminal.

---

## 10. Risks

- **`update_assembly`'s blind `setattr` loop** is the single point where the
  recalculation hook can be bypassed. Anything writing `assembly.number_to_select`
  through the repository directly would leave stale min/max. Grep for it after
  implementing; consider whether the domain's `Assembly.update()` needs the same
  hook.

  **Would a `NumberToSelectUpdated` domain event be better here? Not yet (D19).**

  Worth checking first: there is **no event infrastructure in this codebase at
  all** — no events module, no message bus, no `collect_new_events` on the
  UnitOfWork (grepped). So this is not "use the existing pattern", it is
  "introduce chapter 8 of _Architecture Patterns with Python_" to serve one
  publisher and one subscriber. A bus whose entire routing table is
  `{NumberToSelectUpdated: [recalculate_minmax]}` is indirection with no payoff,
  and it hides at the call site the very causal link §6.2 exists to make
  obvious.

  The deeper objection is that this is the wrong shape for an event.
  Recalculation is not "something else might like to know"; it is "this must
  also be true before the transaction ends". If min/max are stale the data is
  simply wrong. Events model optional, fan-out reactions — invariants belong in
  the handler.

  It also interacts badly with our UnitOfWork convention. Cosmic Python has the
  UoW collect events and the bus dispatch them around commit. Here only
  entrypoints open `with uow:`, so a dispatched handler either runs inside the
  still-open context — in which case the event bought nothing over a direct call
  — or after commit, in a second transaction that can fail _after_ the assembly
  change is durable, leaving exactly the stale min/max we were trying to
  prevent. That failure mode is strictly worse than the direct call.

  **Where events would earn their keep in this project** is the activity log
  from D17: assembly-wide, many publishers, and one subscriber whose failure
  genuinely should not roll back the user's action. That is the shape events are
  for. If we build them, build them for that — and let this recalculation be an
  early publisher rather than the justification. Converting is one call site.

- **Dropping `description` — downgraded by D20, not eliminated.** No live
  assembly has targets yet, only test and demo data, so the rolling-deploy and
  restore-a-backup scenarios in §5.1's table have nothing to damage. The blast
  radius is a demo database, and the fix is a re-import.

  Two things survive that. The failure is still **site-wide rather than
  per-row** — `TargetValue(**item)` raises inside the repository, so one stale
  key 500s the targets page for every assembly — and a demo database is
  precisely the one being shown to someone. And "no live targets yet" is true
  _today_; the migration ships whenever it ships. So keep the filter and the
  migration, and stop insisting the filter needs a commit to itself (§9).

- **The D15 data migration is easy to test vacuously.** It runs green against an
  empty database while doing nothing. §8 specifies inserting old-shape rows with
  raw SQL first. The order-preservation assertion matters most: a silent
  reshuffle of every target list would be found by a confused organiser, not by
  us.

- **`import_targets_from_csv`'s return type change (D14) reaches the legacy
  page**, which D12 says we are not updating. It gets a one-line unpack to keep
  it compiling and nothing more. Worth knowing before someone reads the diff and
  thinks the legacy page is back in scope.
- **The snapshot format change** is written into a JSON column on
  `selection_run_records`. Readers must use `.get()`; the recorded API fixtures
  in `tests/fixtures/json_api/` may need re-recording with
  `UPDATE_API_FIXTURES=1 uv run pytest` — read the diff rather than accepting it.
- **CSV import silently narrowing ranges** if `minmax_manual` were not set on
  import (§6.5). The failure is invisible at import time and only shows up when
  someone edits `number_to_select` weeks later, which is exactly the kind of bug
  nobody traces back. Covered by a named regression test.
- **No PII concerns** in this work — target names, comments and source URLs are
  configuration, not personal data. Worth stating so the next reader doesn't
  re-derive it. The one thing to keep out of logs is the free-text comment,
  since nothing stops an organiser typing a name into it.

---

## 11. Open questions

**None outstanding.** Every question raised across the three reviews of this plan
has an answer recorded in §12, and each answer is threaded into the body as a
numbered decision in §2.

Two of them were settled with a value rather than a principle, and both are
named constants specifically so that changing them later is a one-line diff
rather than an argument:

- `SLACK_SEATS = 1` (§4.3) — the seat added to an exact division so it is not a
  rigid quota. Honest at 1 and misleading above it; §4.3 gives the minimum-range
  formulation to switch to if we ever want more.
- `PERCENTAGE_TOLERANCE = 1.0` (§4.4) — how far a category's percentages may sum
  from 100 before we warn.

Both are worth revisiting once organisers have used the feature on a real
assembly. Neither should become a per-assembly setting (D16).

The one thing genuinely deferred rather than answered is the **activity log**
(D17): comments are a single mutable field now, and change history arrives with
that separate assembly-wide model. §6.3 lists the hooks it will want.

---

## 12. Questions answered

Recorded so the reasoning isn't lost once the review annotations are gone.

| Q                                               | Answer                                           | Where it landed    |
| ----------------------------------------------- | ------------------------------------------------ | ------------------ |
| Q3 — is breaking the link permanent?            | No, re-linking should be possible                | D4, §4.3, §6.3, §7 |
| Q5 — percentages before `number_to_select`?     | min/max sit at 0                                 | D5, §4.3 guard 3   |
| Q6 — should percentages drive flex?             | Out of scope this round                          | D6, §4.3           |
| Q7 — should the report use the real percentage? | Yes, definitely                                  | D9, §6.6           |
| Q8 — CSV import of the new fields?              | Yes, percentage optional and derived when absent | D10, §6.5          |
| Q9 — does the legacy page need updating?        | No, it is hidden and will be deleted             | D12, §1            |
| Q10 — multiple sources per category?            | One, with the comment as escape hatch            | D8                 |
| Q11 — the unused `description` fields?          | Remove them now                                  | D7, §4.1, §4.2, §5 |
| Q13 — do Phase 0?                               | Yes                                              | D11, §3            |

Answered in the second review:

| Q                                                   | Answer                                                    | Where it landed |
| --------------------------------------------------- | --------------------------------------------------------- | --------------- |
| Q12 — where should `SORT_ORDER_STEP` live?          | Move it to `service_layer/constants.py`                   | D13, §6.1       |
| Q15 — silent first-wins on category CSV columns?    | Make a disagreement a visible import warning              | D14, §6.5       |
| Data migration instead of the decoder filter?       | Both — the filter is mandatory, the migration rides along | D15, §5.1, §5.2 |
| Backfill `minmax_manual = True` on existing values? | Yes, but only where a percentage is already recorded      | D15, §5.1, §5.2 |

Answered in the third review, which closed the last of them:

| Q                                                          | Answer                                                              | Where it landed |
| ---------------------------------------------------------- | ------------------------------------------------------------------- | --------------- |
| Q1 — min == max on exact divisions                          | Widen by one seat, but only when floor and ceil are equal           | D3, §4.3        |
| Q2 — what tolerance counts as "close to 100.0"?            | ±1, as a constant, never a setting                                  | D16, §4.4       |
| Q4 — comments: single field or history?                    | Single field; history comes with a later assembly-wide activity log | D17, §4.2, §6.3 |
| Q14 — CSV percentages with no seat count                   | `(min + max) / Σ(min + max)`, unset when that is zero               | D18, §6.5       |
| Would DDD-style events suit the recalculation?             | Not yet — no bus exists, and this is an invariant, not a reaction   | D19, §10        |
| Does "no live targets data" change the `description` plan? | Softens the risk and merges two commits; keeps filter and migration | D20, §5.1, §9   |
