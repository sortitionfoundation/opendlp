# The Celery tasks import a Flask context processor module

## Background

`get_service_account_email()` reads the Google service account's email address
from the credentials file. It has nothing to do with templates, but it lives in
`src/opendlp/entrypoints/context_processors.py`. Seven modules import it from
there, including `src/opendlp/entrypoints/celery/tasks.py`:

```python
from opendlp.entrypoints.context_processors import get_service_account_email
```

So the Celery worker imports the Flask context processor module, and
everything that module imports, to read one field from a JSON file.

Found while planning the email and task adapters
([more-adapters/plan.md](../more-adapters/plan.md)). That plan removes the
service layer's imports of `entrypoints.celery`, and this was the next
surprising edge in the import graph.

## What the change could be

Move `get_service_account_email()` next to the other Google credential
handling. That is `opendlp.config` (which already has
`get_google_auth_json_path()`) or an adapter module such as
`adapters/gsheet_access.py`. Update the seven importers, and keep the context
processor calling it from its new home. It is a pure move.
