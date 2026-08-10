"""ABOUTME: Records and checks the "API fixtures" - real JSON responses saved for the JS tests
ABOUTME: Validates a response against its JSON Schema, then pins it byte-for-byte on disk

Two halves guard against the server and the browser drifting apart:

* the **schema** (``src/opendlp/schemas/json_api/``) says what a response shape is
  allowed to be, and is checked here and again by the Vitest side with ajv;
* the **fixture** (``tests/fixtures/json_api/``) is a real recorded response, so a
  JS test never hand-types an API payload it merely believes in.

A shape change therefore has to be made deliberately in three places or the build
fails: the route, the schema, and the fixture.

This is deliberately *not* called a contract test - that term is already taken in
this repo for fake-repository-versus-SQL-repository parity (``tests/contract/``).

To regenerate after an intended shape change::

    UPDATE_API_FIXTURES=1 uv run pytest tests/component/test_json_api_fixtures.py

then read the diff before committing it. An unexplained diff is the point of the
mechanism working.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent.parent / "src" / "opendlp" / "schemas" / "json_api"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "json_api"

_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_UUID_PLACEHOLDER = "00000000-0000-4000-8000-000000000000"

_UPDATE_ENV_VAR = "UPDATE_API_FIXTURES"


def load_schema(name: str) -> dict[str, Any]:
    """Load a JSON Schema by name, e.g. ``registration-image``."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


def assert_matches_schema(body: Any, schema_name: str) -> None:
    """Assert a response body validates against the named schema.

    Raises ``jsonschema.ValidationError`` with the offending path, which is a far
    more useful failure than an assertion on a single key would be.
    """
    jsonschema.validate(instance=body, schema=load_schema(schema_name))


def normalise(value: Any, replacements: dict[str, str] | None = None) -> Any:
    """Make a response body stable enough to be compared run to run.

    Every UUID becomes a single placeholder, and each caller-supplied volatile
    string (a generated slug, a content hash) becomes the placeholder it is mapped
    to. Replacements run first, so a caller can pin something the UUID rule would
    otherwise flatten.

    Note this normalises *values*, never keys - a renamed field must show up as a
    diff, since that is exactly the drift being guarded against.
    """
    replacements = replacements or {}
    if isinstance(value, dict):
        return {key: normalise(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [normalise(item, replacements) for item in value]
    if isinstance(value, str):
        for volatile, placeholder in replacements.items():
            value = value.replace(volatile, placeholder)
        return _UUID_RE.sub(_UUID_PLACEHOLDER, value)
    return value


def check_api_fixture(
    name: str,
    body: Any,
    *,
    schema_name: str,
    replacements: dict[str, str] | None = None,
) -> None:
    """Validate a response against its schema, then pin it against the recorded fixture.

    With ``UPDATE_API_FIXTURES=1`` set, the fixture is rewritten instead of compared.

    Args:
        name: fixture file name without the ``.json`` suffix
        body: the parsed response body
        schema_name: schema file name without the ``.schema.json`` suffix
        replacements: volatile substrings to swap for stable placeholders
    """
    assert_matches_schema(body, schema_name)

    normalised = normalise(body, replacements)
    serialised = json.dumps(normalised, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path = FIXTURE_DIR / f"{name}.json"

    if os.environ.get(_UPDATE_ENV_VAR):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialised)
        return

    assert path.exists(), (
        f"No API fixture recorded at {path}. If this response shape is new, "
        f"run `{_UPDATE_ENV_VAR}=1 uv run pytest` to record it."
    )
    assert path.read_text() == serialised, (
        f"The {name} response no longer matches its recorded API fixture, so the JS "
        f"tests that import it are testing a shape the server no longer returns. If "
        f"the change is intended, re-record with `{_UPDATE_ENV_VAR}=1 uv run pytest` "
        f"and check the diff."
    )
