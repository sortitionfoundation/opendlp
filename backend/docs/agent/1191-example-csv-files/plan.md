# 1191 — Example CSV files

Status: in progress. Facts measured first, in [facts.md](facts.md).

## Goal

Give organisers an example file to download beside each CSV upload on the Data
tab, so the format can be seen rather than described, and so there is
something to upload when trying the product out. The story is about the
upload controls themselves, not the documentation site.

## Decisions

- **Two files, one pair.** `static/examples/example-targets.csv` and
  `static/examples/example-respondents.csv`, written so that they belong
  together: every target value occurs in the respondent data, and a selection of
  10 from the 20 respondents meets the targets. They derive from the 453 samples
  (`docs/agent/history/453-csv-upload/`). The monitoring fixtures load too, but
  100 respondents with 16 columns are too much for a first look.
- **The columns everyone needs, and no others.** The targets file has
  `feature,value,min,max`. The samples' `min_flex` and `max_flex` are gone: they
  are optional, no backoffice screen shows them, and the samples set them equal
  to min and max, which stops a selection relaxing anything when it finds no
  panel. `percentage`, `comment`, `category_comment` and `source_url` are optional
  too, and stay out so the example teaches the shape rather than every option.
- **A clean first upload at 10 people.** Each target's midpoints sum to exactly
  10, so the targets page shows no "Percentages for this target add up to…"
  warning. The samples' sums were 10, 11 and 12.
- **Realistic, and readable at a glance.** Twenty respondents with separate first
  and last names and `example.com` addresses, so nothing can reach a real
  mailbox. Gender has a `Non-binary` value with a min of 0, as the monitoring
  fixture does, which also shows that a min can be zero.
- **Static files, not a route.** The files hold no project data and nothing is
  computed, so WhiteNoise serves them as it serves every other asset, and the
  Docker image already ships `static/`. The links carry `v=static_hashes(...)`
  like the stylesheets, because WhiteNoise caches for a year, and the
  `download` attribute, so the browser saves the file instead of opening it.
- **One link under each file input**, text "Download an example CSV", in the
  Data tab's Targets and People cards. It sits in the field's own column,
  directly under the input, because that is where the organiser is deciding
  which file to choose. The card heading gives each link its context; a visually
  hidden suffix reusing the "Targets" and "People" strings does the same in a
  screen reader's list of links, where the two would otherwise be identical. The
  existing hint msgids are left alone so their translations survive.
- **The Targets link says what the example needs.** The targets only work with
  the number to select at 10, and that number can be anything, 0 by default, when
  the organiser arrives here. So one line under the link says "To run a selection
  with the example targets, set the number to select to 10 before uploading them."
  Without it, trying the files on a project of another size ends in a min/max error
  that reads as the example being broken. "Before uploading" matters: the import
  works out the percentages from the number to select at that moment and changing
  the number later does not redo them, so a project uploaded at 30 and then set to
  10 keeps totals of 33.3%. From 0 or 10 the totals are 100%.
- **Left out, deliberately.** The lookup-table dialog (Link targets to
  questions): its two-column format depends on the linked question, the dialog
  already states it with the question's keys filled in, and a generic file
  would be refused until "Allow new output values" is ticked. The legacy
  targets and respondents pages, which are due to be retired. The
  documentation site.

## Phases

- [x] P1. Inventory: every CSV upload control, its route and parser, the
  columns each accepts, how static files are served — [facts.md](facts.md)
- [ ] P2. The two example files under `static/examples/`, and an integration
  test that imports both through `import_targets_from_csv` and
  `import_respondents_from_csv` on a fresh project, then checks that the pair is
  coherent and that a real selection runs on it
- [ ] P3. The links in `assembly_data.html`, through a local macro so the URL,
  hash and `download` attribute are written once; component tests that the
  Data tab renders both links, and that what they serve uploads cleanly
- [ ] P4. Catalogue regenerated; `just check`; the touched test files
- [ ] P5. Pull request

## Testing

- `tests/integration/test_example_csv_files.py` — the files, through the
  service layer, against the database: no warnings, every value present among
  the respondents, the selection check passes in either upload order, and the
  selection task finds 10 people within the targets.
- `tests/component/test_backoffice_assembly.py` — each upload form links its own
  example with a hash and the `download` attribute, a link goes when its form
  goes, and the bytes a link serves upload cleanly through the route.
- A manual pass on the Data tab: download both files, upload them in turn, read
  the targets check, save the selection settings and see the Run buttons enabled.
  Running the selection from the page needs Celery, so that step is covered by the
  integration test, which runs the task in-process.
