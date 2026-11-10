# 1191 — Example CSV files: fact sheet

What the code does today, measured on `main` at 25e72c62 before anything was
changed, and the demo data the example files come from. The plan is in
[plan.md](plan.md).

## Where a CSV can be uploaded

| Where | Template | Route | Service function |
| --- | --- | --- | --- |
| Data tab, Targets card (only while the project has no targets) | `templates/backoffice/assembly_data.html:361` — `file_input(name="csv_file", hint="Select a CSV file with targets.")` | `targets.upload_targets_csv` (`blueprints/targets.py`), `POST /backoffice/project/<id>/targets/upload` | `target_csv_import.import_targets_from_csv(..., replace_existing=True)` |
| Data tab, People card (only while the project has no respondents) | `templates/backoffice/assembly_data.html:423` — `file_input(name="file", hint="Select a CSV file with respondent data.")` plus the `ID Column` text input | `respondents.upload_respondents_csv` (`blueprints/respondents.py`), `POST /backoffice/project/<id>/data/upload-respondents` | `respondent_service.import_respondents_from_csv`, after `compute_diff_for_pending_csv` when a field schema already exists (the organiser then confirms the column changes first) |
| Link targets to questions, lookup-table dialog | `templates/backoffice/target_sources/_upload_modal.html:52` — `file_input("mapping_file")` | `target_sources.upload_view`, `POST /backoffice/project/<id>/target-sources/<category>/upload` | `derivation_service.upload_large_mapping`, then `recompute_derived_field` |
| Legacy targets page | `templates/targets/view_targets.html:247` | `targets_legacy.upload_targets_csv`, `/assemblies/<id>/targets/upload` | `import_targets_from_csv` |
| Legacy respondents page | `templates/respondents/view_respondents.html:29` | `respondents_legacy.upload_respondents_csv`, `/assemblies/<id>/respondents/upload` | `import_respondents_from_csv` |

Of these five, the example links go with the first two only, the Data tab's
uploads. The lookup-table dialog gets none, because its format is set by the
linked question ([below](#what-the-lookup-table-parser-accepts)), and neither do
the legacy pages, which are out of scope, as the paragraph on them below says.

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
   default to 0 and to the largest sum of maxes across the targets, which gives
   relaxation its full range. No backoffice screen shows them; only the dev-only
   `service_docs/_targets.html` mentions them.
5. The import does not compare the numbers with the project's panel size:
   `read_in_features` is called without it, so it only checks min against max
   for each value and that the targets do not contradict each other. The
   comparison happens later, in `check_db_selection_data` and the selection
   itself (`load_features(assembly.number_to_select)`).
6. Every imported value is stored with `minmax_manual=True`. A percentage that
   is not given is derived. With a panel size, it is the midpoint of min
   and max over that number, so a target whose midpoints do not sum to the panel
   size shows "Percentages for this target add up to %(total)s%%, not 100%%"
   on the targets page (`target_checking.py`, tolerance one percentage point).
   Without one, it is normalised within the target and always totals 100.
   Changing the panel size later does not redo them. Measured with a
   targets file whose midpoints sum to 10: uploaded at 10, or at 0 and then set
   to 10, each total is 100%; uploaded at 30 and then set to 10, the totals stay
   at 33.3%. Measured with the demo targets without their percentage column
   (below): uploaded at 30 the totals are 98.3%, 101.6%, 110.1% and 106.6%, each
   a warning; uploaded at 0 they are 100.0% to 100.1%. A percentage that is given
   is stored as given, whatever the panel size.
7. The upload replaces whatever targets exist (`replace_existing=True`); the
   form itself only shows while the project has none.

The panel size defaults to 0 on the project form
(`entrypoints/forms.py`), and a selection refuses to start below 1. On the Selection
tab the Run buttons stay disabled until the selection settings on the Data tab have
been saved once. The backoffice's own check of targets against respondents is
`GET /backoffice/project/<id>/targets/check`; `check_db_selection_data` is reached
from the legacy `db_selection/select.html`.

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
would be refused until the organiser ticks the box. This upload stays as it is,
with no example link.

## Sample files already in the repository

| File | Rows | Columns | Used by |
| --- | --- | --- | --- |
| `docs/agent/history/453-csv-upload/sample_respondents.csv` | 20 | `ID,Name,Email,Gender,Age,Region` | nothing; documentation of the original CSV upload work |
| `docs/agent/history/453-csv-upload/sample_targets.csv` | 9 | `feature,value,min,max,min_flex,max_flex`, flex equal to min and max | nothing |
| `docs/fixtures/monitoring/respondents.csv` | 100 | 16 columns | the end-to-end monitor (`docs/monitoring.md`) |
| `docs/fixtures/monitoring/categories.csv` | 18 | `category,name` naming, three columns the import ignores; for 30 people | the end-to-end monitor |
| `tests/csv_fixtures/selection_data/candidates.csv` | 150 | 13 columns, a NationBuilder-style export | the BDD suite and the CSV data source default (`config.py`) |
| `tests/csv_fixtures/selection_data/features.csv` | 20 | `feature,value,min,max,min_flex,max_flex` | as above |

The 453 pair is small and its values match each other, but `sample_targets.csv`
has two problems for an example. Its midpoints sum to 10 for Gender, 11 for Age
and 12 for Region, so no panel size avoids the percentage warning on every
target. And its flex equals its min and max, which allows a selection no
relaxation at all. The monitoring pair loads through both imports, and it is the
demo data below.

## The demo data the examples come from

The "OpenDLP Dummy Data" Google Sheet attached to story sc-1191, read from an
xlsx export. Its README tab calls it "just enough to use opendlp and strat
select on it": the questions and respondents come from the "Beanocracy" game and
are set in a fictional country, Sortonia. The tabs carry the names a Google
Sheet data source reads by default (`adapters/orm.py`: `Respondents` and
`Categories` for a selection; `Remaining`, `Replacement Categories` and
`Selected` for replacements).

| Tab | Size | Header row | Used for the examples |
| --- | --- | --- | --- |
| README | 7 lines of notes | — | no |
| Respondents | 100 rows, 16 columns | `unique_id,first_name,last_name,age_bucket,economic_stability,gender,age,ethnicity,address_line_1,province,town,education,money_fairness,env_daily_life,belong_shared_space,education_next_gen` | the people file, unchanged |
| Selected | empty | — | no |
| Categories | 18 rows, 7 columns | `category,name,suggest min,suggest max,Current #,min,max`, the middle three empty | the targets file |
| Replacement Categories | empty | — | no |
| Remaining | empty | — | no |
| Specification | one row | `Number of participants`, 30 | the panel size |
| Question Details | 16 rows, 4 columns | `Category,Key Question,Answer,Attitude Match` | no; the wording behind the four opinion columns' codes |

- The Respondents and Categories tabs are, cell for cell, the monitoring
  fixtures `docs/fixtures/monitoring/respondents.csv` and `categories.csv`,
  whose README gives the same settings: 30 to select, `unique_id` as the ID
  column. Written as CSV, the Respondents tab is that fixture byte for byte.
- No tab holds an email address, a phone number, a postcode or a web address.
  The provinces (Artesa, Harborview, Ironhold, Nexor, Verdelands), the towns and
  the six ethnicities (Agrican, Artis, Forian and three more) are invented, and
  seven street lines each recur for two people with different
  surnames in different towns. One cell is blank: `education_next_gen` for
  `unique_id` 45.
- The two tabs agree: every target value occurs among the respondents and every
  respondent value of a target column is a target value. Against 30, the mins
  and maxes sum to 26–33 for gender, 24–37 for ethnicity, 28–38 for province and
  27–37 for education, so only a panel size from 28 to 33 fits every
  target's sums; and every value has at least its min among the 100
  people, with room to spare: the smallest groups are Forian (3 people, min 0),
  Mixed Ethnic (5, min 1) and Non-binary (8, min 0).
- The midpoints sum to 29.5, 30.5, 33 and 32, not 30, which is why the example
  targets carry a percentage column (point 6 above, and the plan).

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
  error in a `flex flex-col gap-1.5` column. A link outside the field leaves
  the existing hint msgids, and so their Hungarian translations, as they are.

## The two upload cards

- The Targets and People cards are the two children of
  `grid grid-cols-1 md:grid-cols-2 gap-6` in `assembly_data.html`: side by side
  from `md` (768px) up, stacked below it. A grid stretches the items of a row,
  so side by side the two cards are already equal in height; each card's
  content runs down from its top.
- The People form is taller than the Targets form by its ID Column field, so the
  two Upload buttons sit at different heights: 126px apart at 1440 wide on a
  project with an earlier upload, whose two-line hint names the column used last
  time. Whatever follows the last field of each card therefore starts at a
  different height in each, unless the cards share rows.
- The card component's way of putting content at the bottom of grid cards
  (`components/card.html`: `flex flex-col` on the card, an `mt-auto` block) lines
  up the bottoms of the two blocks. The Targets example, with its note under the
  link, is taller than the People one, so the two links themselves would not
  line up. No backoffice template used `subgrid` before this change.
- At phone width the Data tab is wider than the screen because of the tab bar:
  its last tab, Team Members, ends at 789px, so the page scrolls sideways by 399px
  at 390 wide and by 21px at 768. The cards themselves fit at both widths.

## Translations

One catalogue, `translations/hu/LC_MESSAGES/messages.po`. `just translate-regen`
adds new msgids with empty msgstr; `just translate-check` (part of `just check`)
runs `msgfmt --check` and `pybabel compile`. A proposed translation is flagged
fuzzy, so it shows in English until a reviewer clears the flag with
`just translate-accept-fuzzy`. The style guide is `translations/styleguide-hu.md`;
the catalogue already says `CSV fájl` and `Kiválasztandó emberek száma`.
