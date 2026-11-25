# A respondent's external ID is written to the logs when a CSV row is skipped

Turned up in the review of `1024-create-project`, which added two more places
that do it. Left as it is for now, on purpose. Written to be pasted into an
issue.

## The problem

When a respondents CSV is imported, a row with an ID that is already there is
skipped, and the reason is kept as a string that carries the ID:

```python
errors.append(f"Row {row_number}: skipped duplicate {id_column}: {external_id}")
```

(`service_layer/respondent_service.py`, twice: once for an ID already in the
database, once for an ID repeated within the file.)

Those strings are there to be shown to the organiser, which is fine. But the
routes also hand the whole list to the logger:

| Where | Call |
| --- | --- |
| `entrypoints/blueprints/respondents.py`, `_run_csv_import` | `logger.warning("respondent CSV import completed with warnings", ..., errors=errors)` |
| `entrypoints/blueprints/data_source.py`, `new_project_upload_respondents` | `logger.warning(..., errors=skipped)` |
| `entrypoints/blueprints/data_source.py`, `upload_respondents` | `logger.warning(..., errors=skipped)` |

So every skipped row puts one external ID into the logs.

## Why that matters

The ID column is whatever the organiser's file uses. Nothing stops it being an
email address, a phone number or a name -
[personal_data_leak.md](personal_data_leak.md) covers the same assumption from
the erasure side.

The rule in [docs/personal-data.md](../../personal-data.md) is that we log a
UUID, never raw personal data, and that `log_redaction.censor_pii` is a
backstop and not a licence. Here the backstop is the only thing in the way:

- An ID that is an **email address** is scrubbed, because `censor_pii` walks
  lists and redacts anything shaped like an email.
- An ID that is a **phone number, a name, or a membership number** that
  identifies someone is not recognised and is logged as it stands.

Logs are also outside the reach of erasure: blanking a respondent does nothing
to a log line written last month.

## What to do

The log line needs to say that rows were skipped and how many, which it already
does with `error_count`. It does not need the rows themselves.

1. Drop `errors=` from the three log calls, keeping `error_count` (and
   `imported` where it is there).
2. If knowing *which* rows is useful for support, log the row numbers alone.
   That means the import returning something more structured than a list of
   sentences - a row number and a reason code - which the message shown to the
   organiser can then be built from. That is the larger change, and it would
   also let the messages be translated, which they are not today.

A test that uploads a file with a duplicate ID and asserts the ID is absent
from the captured log output would hold the fix in place.
