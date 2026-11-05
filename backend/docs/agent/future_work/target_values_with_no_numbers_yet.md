# A target value with no numbers yet is stored as min 0, max 0

## Background

Early in setting up a project, an organiser often knows the targets and their
values - Gender: Woman, Man, Non-binary - before working out any numbers.
The edit form lets them save a value with the population share, min and max
all left empty.

`_write_value_edit` in `service_layer/target_service.py` builds that value
with `min=value_edit.min or 0` and `max=value_edit.max or 0`, so it is stored
as 0-0. The edit form never puts a 0 in a box itself: new rows render empty
min and max inputs. The 0 comes from the save.

Found while settling what an empty box means in the targets edit form, on
`999-targets-improvements`. That branch decided:

- all three boxes empty saves, as above
- a min without a max, or a max without a min, is refused on the empty box
  ("Enter a max as well"), for new and existing values
- typed zeros are numbers: 0-0 deliberately excludes a value, 0-1 allows at
  most one person

## The problem

"No numbers yet" and "deliberately excluded" are stored the same way, as
0-0, and nothing can tell them apart afterwards:

- **The form loses the state.** After the first save the edit form reopens
  showing 0 and 0, so the organiser sees numbers they never typed.
- **Selection treats it as an exclusion.** A selection or target check run
  before the numbers are worked out gives the library a 0-0 band for every
  such value, so nobody holding that value can be selected. At best the
  organiser gets a confusing "Sum of maximums (0) is less than the panel
  size" rather than "these targets have no numbers yet".
- **The export writes 0s**, which upload again as real 0-0 exclusions.

## Proposal: a flag on the value

Add a field to `TargetValue` in `domain/targets.py`, say
`numbers_set: bool = True`. Min and max stay `int` and stay stored as 0 when
the flag is false, so every existing consumer keeps working unchanged.

### Writing it

- `_write_value_edit` sets it false for a new value saved with percentage, min
  and max all empty, and true otherwise.
- An existing value saved with all three empty: decide whether that returns it
  to "no numbers yet". It probably should - otherwise the only way back is to
  delete and re-add the value. Today, emptying all three keeps the stored min
  and max, because clearing the percentage leaves them alone
  (`_apply_value_numbers`).
- Setting a percentage, or typing both min and max, sets it true. So does
  `apply_percentage`, which covers a panel size change and re-linking.
- The CSV import (`service_layer/target_csv_import.py`) needs a decision:
  either accept empty min and max cells as "no numbers yet", or keep
  requiring them.

### Reading it

These need the flag:

| Where | What it does with an unset value |
| --- | --- |
| `templates/backoffice/targets/bulk_edit_form.html` | empty min and max boxes, not 0 |
| `templates/backoffice/targets/category_block.html` and `table_cells.html` | a dash, not 0-0 |
| `adapters/sortition_data_adapter.py` (`OpenDLPDataAdapter.read_feature_data`) | refuse, naming the values without numbers |
| `service_layer/target_export_service.py` | empty min and max cells |
| `service_layer/respondent_field_spec_service.py` and its JSON schema | expose it, or null the numbers - a response shape change, so the schema and fixture change too |

The adapter row is the one that matters most. DB selection
(`service_layer/sortition.py`), target checking
(`service_layer/target_checking.py`) and replacement selection
(`service_layer/replacement_targets.py`) all hand targets to the library
through `OpenDLPDataAdapter`, so one guard there covers every path that feeds
numbers to the library. The guard should raise an error the routes already
turn into a message, with the error text translated as the other selection
errors are.

The other readers of `target_categories.get_by_assembly_id` -
`dashboard_stats.py`, `target_suggestions.py`, `assembly_service.py` and the
rest - display or copy targets. Each needs a look, but a 0 there is a display
oddity rather than a wrong selection.

### Deploy safety

Safe in one release. `TargetValueListJSON.process_result_value` in
`adapters/orm.py` drops keys `TargetValue` does not know, so the previous
release reads a value with `numbers_set: false` as a plain 0-0 - which is
what it would have stored anyway. Values written before the change have no
key and default to true, which is correct for all of them except those
already saved as 0-0 with nothing typed. Those can't be told apart from real
exclusions, so they stay as they are.

### Risks

Two sources of truth: the flag, and the 0s it sits beside. Any future code
that reads `min` without checking the flag gets a quiet 0. The adapter guard
protects selection; the display paths are where it would slip through.

## Alternatives considered

- **Nullable min and max (`int | None`).** The truest model, and mypy strict
  would point at every consumer, so none could read a quiet 0. But it is much
  larger (about 14 service modules, 10 templates, the JavaScript, the JSON
  schema and its fixture), and not deploy-safe: the previous release builds
  `TargetValue(min=None)` and `_validate` raises `TypeError` on `None < 0`,
  failing the whole category - the targets page and selection both break. It
  would need two releases: first read null, then write it. Worth it only if
  much more code grows around values without numbers.
- **Reuse `minmax_manual` as the flag** ("no percentage and not typed by hand"
  meaning unset). No new field, but values already stored with real numbers,
  no percentage and `minmax_manual=False` would suddenly read as having no
  numbers.
- **Leave it.** What the branch does. Cheap, but selection quietly treats
  unfinished targets as exclusions.
