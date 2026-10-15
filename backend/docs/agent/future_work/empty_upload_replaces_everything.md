# An upload with no data rows deletes everything it replaces

## The problem

Uploading respondents or targets **replaces** what the assembly already has.
Both routes pass `replace_existing=True`. Neither checks that the upload
contains anything before deleting.

A CSV with a header row and no data rows therefore:

- **Respondents** (`respondent_service.import_respondents_from_rows`): calls
  `uow.respondents.delete_all_for_assembly(assembly_id)`, imports nothing,
  commits, and flashes "Respondents uploaded successfully: 0 imported".
- **Targets** (`target_csv_import.import_targets_from_csv`): the library
  accepts an empty body (`read_in_features(headers, [])` returns an empty
  collection without error). Then every target category is deleted
  (`release_links_before_deleting_all` and `delete_all_for_assembly`), nothing
  is created, and the success message reports 0 targets.

The same happens when every data row is blank or skipped: rows with an empty
ID are all skipped, so a file with the wrong ID column wipes the respondents
and imports none.

It is easy to do by accident: exporting the wrong tab, an export that went
wrong, or a template file with only the headers filled in. It's also quiet:
the message says "successfully". For respondents the loss includes selection
statuses and comments.

## Where it happens

- `entrypoints/blueprints/respondents.py` - `upload_respondents_csv` and
  `apply_upload_diff` via `_run_csv_import(..., replace_existing=True)`.
- `entrypoints/blueprints/respondents_legacy.py` - `upload_respondents_csv`.
- `entrypoints/blueprints/targets.py`, `targets_legacy.py` -
  `import_targets_from_csv(..., replace_existing=True)`.

## Options

1. **Refuse an upload that would import nothing.** Check before deleting:
   no data rows, or no row that would actually be imported, raises a
   curated error ("This file has no respondents in it, so nothing was
   changed"). This is simple and covers the accident. The cost is that
   someone who really wants to clear everything needs another way, and a
   "delete all respondents" action may already exist or be wanted anyway.
2. **Confirm before replacing with fewer.** If the upload would remove
   existing rows and leave fewer, or none, show a confirmation with the
   numbers ("This will replace 1,240 respondents with 0"). The respondents
   upload already has a confirmation step (the schema diff page), which
   could carry this. Targets has none.
3. **Both:** refuse zero outright, and confirm a large drop.

Recommendation to discuss: option 1 now, as it is small and closes the
dangerous case. Option 2 is worth considering for respondents in particular,
where a large drop in count is the other likely accident (an export filtered
by mistake).

## Notes

- Respondents that are not in the POOL state (selected, confirmed, and so on)
  make a replacement more dangerous still. Check whether the respondent
  upload should refuse, or warn, when it would delete respondents who have
  been part of a selection.
- Found while planning issue 916 (blank columns in uploaded CSVs); see
  [`916-blank-columns/plan.md`](../916-blank-columns/plan.md).
