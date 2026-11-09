# 1191 — Example CSV files

Status: implemented — all phases below are done. Facts measured first, in
[facts.md](facts.md).

## Goal

Give organisers an example file to download under each of the two CSV uploads
on the Data tab, so the format can be seen rather than described, and so there
is something to upload when trying the product out. The story is about the
upload controls themselves, not the documentation site.

## Decisions

- **Two files, one pair, from the demo data.** `static/examples/example-targets.csv`
  and `static/examples/example-respondents.csv` are the demo data in the
  "OpenDLP Dummy Data" Google Sheet attached to story sc-1191, the data the
  product has been demonstrated with: its Categories tab is the targets file and
  its Respondents tab the people. It is the same data, cell for cell, as the
  end-to-end monitor's fixtures in `docs/fixtures/monitoring/`. Every target
  value occurs among the respondents and every respondent value is a target
  value, and a selection of 30 from the 100 respondents meets the targets. The
  sheet's other tabs hold its notes, the number of participants (30), the
  wording of the opinion questions, and three empty output tabs; none of them is
  an upload. See [facts.md](facts.md#the-demo-data-the-examples-come-from).
- **The respondents as they are in the demo.** All 100 rows and 16 columns,
  unchanged: the file is byte for byte `docs/fixtures/monitoring/respondents.csv`.
  The people of a fictional country, Sortonia, with names, age and age group,
  gender, ethnicity, province, town, a street line, education, economic
  stability and four opinion answers coded 1 to 4. There is no email or phone
  column, so a file anyone can download reaches no one. The ID column,
  `unique_id`, comes first, which is the column the upload takes when the ID
  Column field is left blank. About 10 KB: it reads in a spreadsheet.
- **The targets in today's format.** The demo's `category,name` headers become
  `feature,value`: the import takes both, and the example shows the current
  names. Its three empty helper columns (`suggest min`, `suggest max`,
  `Current #`), which the import ignores, are dropped. Min and max are the
  demo's. `min_flex`, `max_flex`, `comment`, `category_comment` and `source_url`
  are optional and stay out, so the example teaches the shape rather than every
  option.
- **One optional column added: `percentage`.** The demo's midpoints sum to 29.5
  (gender), 30.5 (ethnicity), 33 (province) and 32 (education). A targets file
  without percentages gets them worked out at upload as each value's midpoint
  over the panel size at that moment, so on a project of 30 the four
  targets would total 98.3%, 101.6%, 110.1% and 106.6%, and the targets page would
  greet the upload with four "Percentages for this target add up to…" warnings.
  The column gives each value the percentage its min and max imply within its
  target, by the rule the app itself uses when there is no panel size
  (`percentages_from_minmax`, one decimal place). Every target then totals 100
  within the page's one-point tolerance, whatever the panel size was at
  upload. The column adds no numbers of its own, and a test holds it to the min
  and max.
- **Static files, not a route.** The files hold no project data and nothing is
  computed, so WhiteNoise serves them as it serves every other asset, and the
  Docker image already ships `static/`. The links carry `v=static_hashes(...)`
  like the stylesheets, because WhiteNoise caches for a year, and the
  `download` attribute, so the browser saves the file instead of opening it.
- **One link under each upload, not one link for the tab.** The text is
  "Download an example CSV", once in the Data tab's Targets card and once in its
  People card, each linking the file that upload takes. It sits in the field's
  own column, directly under the input, because that is where the organiser is
  deciding which file to choose. The card heading gives each link its context; a
  visually hidden suffix reusing the "Targets" and "People" strings does the same
  in a screen reader's list of links, where the two would otherwise be
  identical. The existing hint msgids are left alone so their translations
  survive.
- **The Targets link says what the example needs.** The targets are made for a
  selection of 30, the demo's number of participants; their mins and maxes leave
  only 28 to 33 that every target's sums allow. The panel size can be
  anything, 0 by default, when the organiser arrives here. So one line under the
  link says "To run a selection with the example targets, set the panel size to
  30." Without it, trying the files on a project of another size
  mostly ends in a min/max error that reads as the example being broken. The
  order does not matter: the file gives its own percentages, so the panel size
  can be set before or after uploading.
- **No example in the lookup-table dialog** (Link targets to questions). Its
  two-column format depends on the linked question, the dialog already states it
  with the question's keys filled in, and a generic file would be refused until
  "Allow new output values" is ticked. See
  [facts.md](facts.md#what-the-lookup-table-parser-accepts).
- **Left out as well.** The legacy targets and respondents pages, which
  [docs/language.md](../../language.md) lists among the legacy screens that are
  due to be retired, and the documentation site, which the story rules out.

## Phases

- [x] P1. Inventory: every CSV upload control, its route and parser, the
  columns each accepts, how static files are served — [facts.md](facts.md)
- [x] P2. The two example files under `static/examples/`, and an integration
  test that imports both through `import_targets_from_csv` and
  `import_respondents_from_csv` on a fresh project, then checks that the pair is
  coherent and that a real selection runs on it
- [x] P3. The links in `assembly_data.html`, through a local macro so the URL,
  hash and `download` attribute are written once; component tests that the
  Data tab renders both links, and that what they serve uploads cleanly
- [x] P4. Catalogue regenerated; `just check`; the touched test files
- [x] P5. The examples replaced by the demo data (its Categories and
  Respondents tabs), the note under the Targets link from 10 to 30, the tests and
  the catalogue to match

## Testing

- `tests/integration/test_example_csv_files.py` — the files, through the
  service layer, against the database: no warnings; every target's percentages
  total 100 whether the panel size was set before the upload or not, and
  are what its min and max imply; every value present among the respondents; no
  contact details; the selection check passes in either upload order; and the
  selection task finds 30 people within the targets.
- `tests/component/test_backoffice_assembly.py` — each upload form links its own
  example with a hash and the `download` attribute, a link goes when its form
  goes, and the bytes a link serves upload cleanly through the route.
- A manual pass in the browser, on a project with a panel size of 30:
  both links serve their files, which upload cleanly (4 targets with 18 values,
  each target's percentages totalling 100.0 or 100.1 with no warning; 100
  respondents); once the selection settings are saved, Run Selection on the
  Selection tab, with Celery running, selects 30 people with every target value
  within its min and max. The integration test runs the same task in-process.
