# Respondent Field Spec

A read-only JSON endpoint describing an assembly's respondent columns and the
valid values for each, so a script outside the app can generate a respondent CSV
that will actually load and select.

```txt
GET /backoffice/assembly/<assembly_id>/respondent-schema.json
```

**It is not linked from anywhere in the UI.** It is reachable by anyone who knows
the URL and can view the assembly, but nothing surfaces it. That is deliberate
and temporary: it exists to support generating test data, and what it should
become — a documented API, an organiser-facing download, or nothing at all — has
not been decided.

## Access

`login_required`, then the same view permission as the schema page itself
(`can_view_assembly`: any role on the assembly, or global-organiser/admin).

| Situation                          | Response                            |
| ---------------------------------- | ----------------------------------- |
| Not logged in                      | `302` to the login page             |
| Logged in, no access to assembly   | `403` `{"error": "..."}`            |
| Assembly does not exist            | `404` `{"error": "..."}`            |
| Otherwise                          | `200` with the spec below           |

The error bodies use the standard envelope from
[JSON API Conventions](agent/json_api_conventions.md).

## The shape

The authoritative definition is the JSON Schema at
`src/opendlp/schemas/json_api/respondent-field-spec.schema.json`, and a real
recorded response is in `tests/fixtures/json_api/respondent-field-spec.json`.
Both are checked against the live route by
`tests/component/test_json_api_fixtures.py`, so neither can drift from what the
server actually returns. Read the fixture first — it is a worked example with a
fixed field, a plain text column, a choice column, a joined target category and
an unmatched one, all in one response.

```jsonc
{
  "spec_version": 1,
  "assembly": {
    "id": "...", "title": "Existing Assembly", "number_to_select": 40
  },
  "csv": {
    "id_column": "external_id",
    "columns": ["external_id", "eligible", "can_attend", "email", "gender"],
    "internal_columns_ignored_on_import": ["selection_status", "..."]
  },
  "fields": [ /* see below */ ],
  "unmatched_target_categories": [ /* see below */ ]
}
```

### `spec_version`

Bumped when the shape changes in a way a consumer has to notice. Consumers live
outside this repo and cannot be updated in the same commit, which is the whole
reason it is there.

### `csv`

- **`id_column`** — the assembly's configured `csv_id_column`, else
  `external_id`. Its value becomes `Respondent.external_id` and must be unique
  within the assembly; import skips rows with a blank or duplicate id.
- **`columns`** — the header row to write, in order: the id column, then every
  non-derived field key, in schema order. Import treats the first column as the
  id column when the upload form names none, so writing them in this order works
  either way.
- **`internal_columns_ignored_on_import`** — export-only columns that import
  recognises and skips (reporting each once in the import status). A generator
  should not emit them; they are listed so you know that an *exported* file
  re-imports cleanly.

### `fields`

Every field in the schema, in the order the schema page and the CSV export use:
`GROUP_DISPLAY_ORDER`, then `sort_order` within each group.

| Key                    | Meaning                                                                                 |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `field_key`            | The CSV column header, and the `Respondent.attributes` key                                |
| `label`                | Organiser-facing display label. Typed by an organiser, so not translated                  |
| `group`                | One of `eligibility`, `name_and_contact`, `address`, `about_you`, `consent`, `other`      |
| `sort_order`           | Position within the group                                                                 |
| `is_fixed`             | A reserved top-level `Respondent` field; its type and options cannot be edited            |
| `is_derived`           | Computed from other fields, never collected — **excluded from `csv.columns`**             |
| `derived_from`         | Field keys it is computed from; `null` unless `is_derived`                                |
| `field_type`           | See the table below                                                                       |
| `options`              | Permitted values for a choice field; `null` for every other type                          |
| `on_registration_page` | `no`, `yes_optional` or `yes_required` — governs the public form, **not** CSV import      |
| `target_values`        | Quotas from the matching target category; `null` when none matches                        |

`field_type` is the *effective* type. For a fixed field the hardcoded
`FIXED_FIELD_TYPES` entry wins over the stored one — the domain refuses to change
a fixed field's type, so the stored value is unreachable and reporting it would
describe a field the app does not have.

| `field_type`      | Write into the CSV as                                          |
| ----------------- | -------------------------------------------------------------- |
| `text`            | any string                                                     |
| `longtext`        | any string                                                     |
| `bool`            | `true` / `false` (see below)                                   |
| `bool_or_none`    | `true` / `false` / empty                                       |
| `choice_radio`    | one of `options[].value`, matched exactly                      |
| `choice_dropdown` | one of `options[].value`, matched exactly                      |
| `integer`         | digits                                                         |
| `email`           | an email address                                               |

**Booleans.** Only the five fixed fields (`eligible`, `can_attend`, `consent`,
`stay_on_db`, plus `email` which is a string) are lifted out of the CSV row into
top-level `Respondent` attributes. Import reads them as
`value.lower() == "true"`, so anything other than some casing of `true` is
`False`, and a missing or empty cell leaves the field `None`. Export writes
`true`, `false` or the empty string. Every other column, whatever its
`field_type`, is stored as the raw string — the type is a display and validation
hint, not a parser.

Note that `eligible` and `can_attend` matter beyond the data. DB selection draws
only from respondents in `POOL` status that are not *explicitly* ruled out: the
filter excludes rows where either flag is `false`, and treats an unset flag as
fine. So a generated row that omits both columns is selectable, and one carrying
`false` in either is not — which is the lever to pull if you want a pool with
some ineligible rows in it.

### `target_values` and `unmatched_target_categories`

A target category constrains which values a stratification column may hold, and
it is usually the only place those values are written down. A column imported
from a CSV starts as `text` with no `options`, and the "guess types" button
cannot help before there are respondents to guess from — so on a fresh assembly
the target values are the only source of valid values there is.

Each entry carries `value`, `min`, `max`, `min_flex`, `max_flex`,
`percentage_target` and `description`. `min`/`max` are the quota for the
*selected* committee, not for the pool, but they are a reasonable steer for the
distribution to generate. `max_flex` of `-1` means unset, and
sortition-algorithms calculates a safe default; `min_flex`/`max_flex` are
selection tolerances and constrain nothing about generated data.

**The join is exact.** A category is attached to the field whose `field_key`
equals its `name` character for character. This mirrors selection: the data
adapter feeds category names to sortition-algorithms as feature names and
respondent attribute keys as the people columns, and the library pairs them by
exact string match. The heuristics that bucket a newly-imported column into a
group *do* match target names loosely (`normalise_field_name`), but copying that
here would report a category as wired up when selection would find no column for
it.

Categories left over after the join appear in `unmatched_target_categories`.
Seeing one there is a signal worth acting on — as things stand, selection will
not find a column for it.

## Where the code lives

- `service_layer/respondent_field_spec_service.py` — `build_field_spec`, the
  whole of the logic. Permission is enforced by the `get_schema` call it opens
  with.
- `entrypoints/blueprints/respondent_field_schema.py` — `field_spec_json`, the
  route.
- Tests: `tests/unit/test_respondent_field_spec_service.py` (the builder),
  `tests/component/test_backoffice_respondent_field_schema.py::TestFieldSpecJson`
  (the route over a fake UoW), `tests/e2e/…` (the same over PostgreSQL), and
  `tests/component/test_json_api_fixtures.py` (schema and fixture).

The id column resolution and the internal-column list are imported from
`respondent_export_service` and `respondent_service` rather than restated, so the
columns this spec advertises cannot drift from the ones import and export
actually use.

## Related

- [Respondent Export](respondent_export.md) — the inverse: respondents out as CSV
- [JSON API Conventions](agent/json_api_conventions.md) — response shape rules
