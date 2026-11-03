# Bool attributes are stored in more than one form

## Background

A respondent's answer to a `BOOL` or `BOOL_OR_NONE` question lives in the
`respondents.attributes` JSON column, but nothing decides what form the value
takes. Each writer picks its own:

| Writer | Code | Stores |
| --- | --- | --- |
| Registration form | `_coerce_form_bool()` in `service_layer/registration_submission_service.py` | JSON `true` / `false` |
| Back-office edit form | `_collect_attribute_updates()` in `entrypoints/blueprints/respondents.py` | strings `"true"` / `"false"` (and `""` for not set) |
| CSV / Google Sheets import | `respondent_from_row()` in `service_layer/respondent_service.py` | the cell text as it was: `"Yes"`, `"TRUE"`, `"1"`… |

So one respondent who registered online and was then edited holds `true`
before the edit and `"true"` after it, and two respondents in the same
assembly can hold different forms of the same answer.

The fixed booleans (`eligible`, `can_attend`, `consent`, `stay_on_db`) aren't
affected: they are real columns, and import lowers them to `True`/`False`.

## What has been done

The edit form reads every form tolerantly. `_stored_bool_to_radio()` in
`entrypoints/edit_respondent_form.py` runs the stored value through
`domain.validators.validate_bool()`, so a JSON `true`, `"true"`, `"Yes"` and
`"1"` all pre-select "Yes". Before that, only the lower-case strings did, so a
registration-form answer showed as unanswered, and a required question then
blocked the save.

That fixes the display only. The data is still mixed.

## Why it may matter beyond the edit form

Everything that reads the attribute sees whichever form it got:

- **Selection.** `sortition_data_adapter.py` passes each attribute to the
  library as `str(v)`, so a JSON `true` becomes `"True"` and an edited value
  stays `"true"`. If a target category is built on a bool question, its values
  must match one spelling. Respondents holding the other spelling may not match
  any target value. **Not yet checked**: whether the library or our target
  import compares values case-insensitively.
- **Export.** `_serialise_field()` in `respondent_export_service.py` writes
  `str(value)`, so one CSV column can contain `True`, `true` and `Yes`.
- **Email templates.** `email_context.py` hands attributes to the auto-reply
  template, so a template that tests the value sees different types.

## Ideas

- Pick one canonical form. JSON `true`/`false` is the natural one: it is what
  the registration form already writes, and what `email_context.py`'s sample
  values assume. Have the edit form and the import convert to it, with
  `validate_bool()` as the one parser. Decide what an unreadable import value
  becomes: kept as text and flagged, or rejected at import.
- Backfill existing rows with a data migration over the attributes of every
  field whose schema type is in `BOOL_TYPES`. It has to be safe to run while
  the old code is serving requests (see `docs/deploy.md`). Old code reads
  tolerantly after this fix, but the old *import* would keep writing raw text
  until the release is out.
- Decide how a bool should appear wherever it leaves the system (selection
  input, CSV export, Google Sheets export), and serialise it there in one place,
  rather than relying on `str()` of whatever was stored.
- Before any of that, check the selection risk above. If target matching is
  case-sensitive, mixed forms can affect selection results today, and this
  becomes a bug rather than tidying.
