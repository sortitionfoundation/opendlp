# A domain model imports bootstrap to choose a test data source

## Background

`AssemblyGSheet.to_data_source()` in `src/opendlp/domain/assembly.py` imports
from `opendlp.bootstrap` at call time:

```python
def to_data_source(self, *, for_replacements: bool = False, id_column: str = ""):
    # import here to avoid circular import
    from opendlp.bootstrap import update_data_source_from_assembly_gsheet  # noqa: PLC0415
```

`update_data_source_from_assembly_gsheet` swaps the Google Sheets data source
for a CSV one when `USE_CSV_DATA_SOURCE` says we are testing.

The domain layer should be the bottom of the dependency graph: plain objects,
testable without Flask, SQLAlchemy or config. Here a domain method reaches up to
bootstrap, which imports the database, email and Flask adapters. The deferred
import keeps that from being a circular-import error, but the dependency is
still there. Calling `to_data_source()` in a unit test pulls in all of
bootstrap and reads the environment.

Found while planning the email and task adapters
([more-adapters/plan.md](../more-adapters/plan.md)). The layering check that
plan adds to `scripts/check_uow_convention.py` would flag this. Either fix this
first, or start the check with an allowlist entry for it.

## What the change could be

- `to_data_source()` builds and returns the `GSheetDataSource` only.
- The service-layer callers in `sortition.py` (and anything else that calls
  `to_data_source()`) pass the result through
  `bootstrap.update_data_source_from_assembly_gsheet`. Or better, they ask an
  injected data-source factory, so tests pass a CSV one explicitly instead of
  setting an environment variable.
- The second option is the same "adapter from bootstrap" shape as the task
  runner, and could follow that work.
