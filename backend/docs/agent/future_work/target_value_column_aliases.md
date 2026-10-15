# Targets CSV value-column aliases that the library never accepts

## Background

`target_csv_import.py` keeps the columns of an uploaded targets CSV that are
named in `TARGET_CSV_COLUMNS` (via `tabular_data.select_columns`) and ignores the
rest. As well as the library's `ALL_FEATURE_FIELD_NAMES`, that list includes
`_LIBRARY_VALUE_COLUMN_ALIASES`: `category value`, `category_value` and
`category-value`. The aliases are copied by hand from
`_get_feature_value_from_row()` in sortition-algorithms' `features.py`, which
looks for the value column under
`("value", "name", "category value", "category_value", "category-value")`.

## The problem

In sortition-algorithms 0.12.14 the aliases cannot be used.

- `read_in_features()` calls `_feature_headers_flex()` before it reads any row.
  That function accepts only a header set made from `ALL_FEATURE_FIELD_NAMES`
  (`feature`/`value` or `category`/`name`, plus min, max and the optional
  flex columns). The aliases are not in it, so a file using one is refused
  with "Did not find required column name 'value' in the input".
- A file that passes the header check has a `value` or `name` column, and
  `_get_feature_value_from_row()` tries those first, so it never falls through
  to an alias.

`read_in_features()` is the only caller of both functions, so the aliases are
unreachable. Checked by calling `read_in_features(["feature", alias, "min",
"max"], ...)` for each alias: `value` passes, all three aliases fail.

## Ideas

- Report it upstream. Either `_feature_headers_flex()` should treat the aliases
  as the value column, or `_get_feature_value_from_row()` should drop them.
- If upstream accepts them, export the alias tuple from the library (as
  `ALL_FEATURE_FIELD_NAMES` is) and build `TARGET_CSV_COLUMNS` from it, so the
  two lists cannot drift. Then add a parametrised import test over the aliases.
- If upstream drops them, delete `_LIBRARY_VALUE_COLUMN_ALIASES` here.
- Until then, keeping the aliases in `TARGET_CSV_COLUMNS` is harmless: the
  library refuses such a file with its own message.
