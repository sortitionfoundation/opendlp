# JSON API schemas

One JSON Schema per JSON response shape our routes return. They live in `src/` rather than
`docs/` because a schema is a property of the API, not documentation about it — and because
both pytest and Vitest load them by path from here, with no `../../..` climb from either side.

Each schema sets `additionalProperties: false`, so a field added to a response without a
schema update fails the Python side immediately rather than silently reaching the browser.

These are paired with the recorded responses in `tests/fixtures/json_api/`. See
[docs/agent/json_api_conventions.md](../../../../docs/agent/json_api_conventions.md) for how the
two halves fit together and how to regenerate a fixture.
