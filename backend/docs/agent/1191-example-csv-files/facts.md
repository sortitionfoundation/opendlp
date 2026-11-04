# 1191 — Example CSV files: fact sheet

What the code does today, measured on `main` at 25e72c62 before anything was
changed. The plan is in [plan.md](plan.md).

## Where a CSV can be uploaded

| Where | Template | Route | Service function |
| --- | --- | --- | --- |
| Data tab, Targets card (only while the project has no targets) | `templates/backoffice/assembly_data.html:361` — `file_input(name="csv_file", hint="Select a CSV file with targets.")` | `targets.upload_targets_csv` (`blueprints/targets.py`), `POST /backoffice/project/<id>/targets/upload` | `target_csv_import.import_targets_from_csv(..., replace_existing=True)` |
| Data tab, People card (only while the project has no respondents) | `templates/backoffice/assembly_data.html:423` — `file_input(name="file", hint="Select a CSV file with respondent data.")` plus the `ID Column` text input | `respondents.upload_respondents_csv` (`blueprints/respondents.py`), `POST /backoffice/project/<id>/data/upload-respondents` | `respondent_service.import_respondents_from_csv`, after `compute_diff_for_pending_csv` when a field schema already exists (the organiser then confirms the column changes first) |
| Link targets to questions, lookup-table dialog | `templates/backoffice/target_sources/_upload_modal.html:52` — `file_input("mapping_file")` | `target_sources.upload_view`, `POST /backoffice/project/<id>/target-sources/<category>/upload` | `derivation_service.upload_large_mapping`, then `recompute_derived_field` |
| Legacy targets page | `templates/targets/view_targets.html:247` | `targets_legacy.upload_targets_csv`, `/assemblies/<id>/targets/upload` | `import_targets_from_csv` |
| Legacy respondents page | `templates/respondents/view_respondents.html:29` | `respondents_legacy.upload_respondents_csv`, `/assemblies/<id>/respondents/upload` | `import_respondents_from_csv` |

`templates/backoffice/patterns/_file_upload.html` and
`templates/backoffice/showcase/input_component.html` are the pattern library
and the component showcase: demonstrations, not uploads. The only other file
inputs take images and documents for a registration page
(`registration/_assets.html` and the dev-only `service_docs/` pages).

The legacy pages (`templates/targets/`, `templates/respondents/`, served by the
`*_legacy` blueprints) are due to be retired and are out of scope for new
interface work — see the "legacy screens" paragraph in
[docs/language.md](../../language.md).

Both Data tab routes read the file as `utf-8-sig`, so a BOM from Excel is
tolerated. The respondents route also refuses files over `MAX_CSV_UPLOAD_MB`.

## What the targets parser accepts

`import_targets_from_csv` (`service_layer/target_csv_import.py`):

1. `select_columns(rows_from_csv(content), TARGET_CSV_COLUMNS)` keeps only the
   known columns, matching headers case-insensitively and ignoring surrounding
   space. Every other column, named or not, is ignored. A known header used
   twice is an error.
2. `read_in_features` (the library) then decides whether the columns it was
   left with will do. Measured through those two calls:

   | Header row | Result |
   | --- | --- |
   | `feature,value,min,max` | accepted |
   | `category,name,min,max` | accepted, the older naming |
   | `FEATURE, Value ,MIN,max` | accepted |
   | `feature,value,min,max,min_flex,max_flex` | accepted |
   | `feature,value,min,max,notes,percentage` | accepted; `notes` is ignored |
   | `feature,name,min,max`, `category,value,min,max` | refused: the pairs do not mix |
   | `feature,category value,min,max` (also `category_value`, `category-value`) | refused: "Did not find required column name 'value'" |
   | `feature,value,min` | refused: `max` is missing |
   | `feature,value,min,max,min_flex` | refused: `min_flex` and `max_flex` come together or not at all |

   `TARGET_CSV_COLUMNS` keeps the three `category value` spellings, and a
   comment there says the library accepts them, but the library's header check
   refuses them. Nothing here changes that.
3. Four more columns are read by OpenDLP itself and are all optional:
   `percentage` and `comment` per value, `category_comment` and `source_url`
   per category.
4. `min_flex` and `max_flex` bound how far a selection that finds no panel may
   relax that value's min and max (`committee_generation/common.py`). `min_flex`
   must not exceed `min`, and `max_flex` must not be below `max`. Left out, they
   default to 0 and to the largest sum of maxes across the targets, which leaves
   relaxation unbounded. No backoffice screen shows them; only the dev-only
   `service_docs/_targets.html` mentions them.
5. The import does not compare the numbers with the project's number to select:
   `read_in_features` is called without it, so it only checks min against max
   for each value and that the targets do not contradict each other. The
   comparison happens later, in `check_db_selection_data` and the selection
   itself (`load_features(assembly.number_to_select)`).
6. Every imported value is stored with `minmax_manual=True`. A percentage that
   is not given is derived. With a number to select, it is the midpoint of min
   and max over that number, so a target whose midpoints do not sum to the number
   to select shows "Percentages for this target add up to %(total)s%%, not 100%%"
   on the targets page (`target_checking.py`, tolerance one percentage point).
   Without one, it is normalised within the target and always totals 100.
7. The upload replaces whatever targets exist (`replace_existing=True`); the
   form itself only shows while the project has none.

The number to select defaults to 0 on the project form
(`entrypoints/forms.py`), and a selection refuses to start below 1.

## What the respondents parser accepts

`import_respondents_from_csv` (`service_layer/respondent_service.py`):

1. `clean_table(rows_from_csv(content), header_checks=[respondent_header_check(...)])`:
   every column counts. An unnamed column that holds data, a header used twice,
   or a NUL character is an error; an unnamed empty column is dropped.
2. The ID column is the form's `ID Column` field, or the first column when that
   is blank. After a first upload the field is prefilled with the column used
   last time. Its value becomes `external_id`; a blank or repeated ID skips the
   row with a per-row message.
3. `respondent_header_check` refuses, before any row is imported: a missing ID
   column, headers with no letters or digits, two headers that normalise to the
   same field (`Person Ref` beside `person_ref`), headers longer than the
   schema allows, and a column other than the ID column that normalises to `id`,
   `assembly_id`, `external_id`, `registration_page_id` or `comments`. Those five
   are what `is_reserved_import_header` answers true for; the rest of
   `_RESERVED_FIELD_NAMES` is lifted or skipped, as below. So `ID` is fine as the
   ID column and refused as any other column.
4. Five headers are lifted into fields rather than kept as attributes: `email`,
   `consent`, `eligible`, `can_attend`, `stay_on_db` (the booleans read `true`
   case-insensitively). The export-only columns `selection_status`,
   `selection_run_id`, `source_type`, `registration_page`, `created_at`,
   `updated_at`, `view_url` are skipped with a notice, so an exported file
   re-imports.
5. Every other column becomes a respondent attribute, header as given. The
   first import seeds the field schema from the headers, grouping them by their
   normalised name (`respondent_field_schema_heuristics.py`): `First name`,
   `Last name` and `first_name` are all recognised.

## What the lookup-table parser accepts

`upload_large_mapping` (`service_layer/derivation_service.py`): a two-column
file. Headers are matched by normalised name to the linked question's source
and derived field keys; when they do not match, the first column is the input
and the second the output. Output values must already be options of the
computed question unless "Allow new output values" is ticked. The dialog text
states this format with the question's own keys filled in. An example file for
it would therefore be specific to one project's questions, and a generic one
would be refused until the organiser ticks the box. This upload stays as it is.

## Sample files already in the repository

| File | Rows | Columns | Used by |
| --- | --- | --- | --- |
| `docs/agent/history/453-csv-upload/sample_respondents.csv` | 20 | `ID,Name,Email,Gender,Age,Region` | nothing; documentation of the original CSV upload work |
| `docs/agent/history/453-csv-upload/sample_targets.csv` | 9 | `feature,value,min,max,min_flex,max_flex`, flex equal to min and max | nothing |
| `docs/fixtures/monitoring/respondents.csv` | 100 | 16 columns | the end-to-end monitor (`docs/monitoring.md`) |
| `docs/fixtures/monitoring/categories.csv` | 18 | `category,name` naming, three columns the import ignores; for 30 people | the end-to-end monitor |
| `tests/csv_fixtures/selection_data/candidates.csv` | 150 | 13 columns, a NationBuilder-style export | the BDD suite and the CSV data source default (`config.py`) |
| `tests/csv_fixtures/selection_data/features.csv` | 20 | `feature,value,min,max,min_flex,max_flex` | as above |

The monitoring targets load through the CSV import; 100 respondents with 16
columns are simply too much for a first look. The 453 pair is the right size and
its values match each other, but as it stands `sample_targets.csv` has two
problems for an example. Its midpoints sum to 10 for Gender, 11 for Age and 12
for Region, so no number to select avoids the percentage warning on every target.
And its flex equals its min and max, which allows a selection no relaxation at
all.

## How static files reach the browser

- `static/` is served by WhiteNoise (`entrypoints/extensions.py`), prefix
  `/static/`, `max_age` one year, `charset=utf-8`. Templates build URLs with
  `url_for('static', filename=...)` and add `v=static_hashes(<path>)` — the
  first eight characters of the file's SHA-256 (`context_processors.py`) — so a
  changed file gets a fresh URL despite the year-long cache.
- WhiteNoise has no media type for `.csv` (`MediaTypes().get_type` answers
  `application/octet-stream`), so a browser saves the file whether or not it
  honours the `download` attribute.
- The Docker build copies `static/` wholesale into the image (`Dockerfile`,
  `cp -r /src/static /app/static`), and `.dockerignore` excludes neither `static/`
  nor `.csv`. `.gitignore` excludes only the built bundles, so a new folder under
  `static/` is tracked and shipped.
- Precedent for a download link in the backoffice design:
  `registration/_step_preview.html` ("Download QR Code", `download` attribute).
  Inline links use `underline` (or `hover:underline`) with
  `color: var(--color-links)` (`static/backoffice/tokens/semantic.css`).
- `file_input` (`components/input.html:535`) renders label, hint, input and
  error in a `flex flex-col gap-1.5` column. A link placed below the field leaves
  the existing hint msgids, and so their Hungarian translations, as they are.

## Translations

One catalogue, `translations/hu/LC_MESSAGES/messages.po`. `just translate-regen`
adds new msgids with empty msgstr; `just translate-check` (part of `just check`)
runs `msgfmt --check` and `pybabel compile`. A proposed translation is flagged
fuzzy, so it shows in English until a reviewer clears the flag with
`just translate-accept-fuzzy`. The style guide is `translations/styleguide-hu.md`;
the catalogue already says `CSV fájl` and `Kiválasztandó emberek száma`.
