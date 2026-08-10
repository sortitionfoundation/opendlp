# JSON API Conventions

Rules for Flask routes that return JSON to our own JavaScript. The point of writing them
down is that the unsafe version of each looks exactly like the safe version at the call
site — you cannot tell them apart by reading the route.

## Response shape

Success is the resource itself at a `2xx`:

```python
return jsonify({"images": [...]}), 200
```

Errors are `{"error": "..."}` — optionally with `"reason"` for a machine-readable code — at
a real status code, never `200` with an error body:

```python
return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
```

## A JSON body never contains `str(e)`

This is the rule, and it is deliberately mechanical so it can be checked by grep rather than
by judgement. An error string in a response body is one of exactly two things:

1. **A literal you wrote**, translated: `_("Please create a registration page first.")`
2. **`exc.user_msg()`** on an exception whose message is written for a user

```python
# ✅
except ImageQuotaExceeded as e:
    return jsonify({"error": e.user_msg()}), 400

# ❌ - may be a curated message, may be a stack of internal detail. Nothing at
#      the call site tells you which, and the safe and unsafe versions are
#      character-for-character identical.
except ImageQuotaExceeded as e:
    return jsonify({"error": str(e)}), 400
```

### `user_msg()` and `CuratedMessage`

`OpenDLPError.user_msg()` returns a **generic** message by default, not `str(self)`. An
exception message may carry internal detail — ids, hostnames, a driver's error string — so
the default assumes it does.

Exceptions whose message is genuinely written for a user opt in by mixing in
`CuratedMessage` (`service_layer/exceptions.py`), which makes `user_msg()` return `str(self)`:

```python
class ImageQuotaExceeded(CuratedMessage, ServiceLayerError):
    def __init__(self, limit: int) -> None:
        super().__init__(_("This registration page already has the maximum of %(limit)s images", limit=limit))
```

So "is this safe to show?" is answered by the class, once, rather than at every call site.

A class that forgets the mixin degrades to a vague message. That is the intended failure
direction: too little information beats leaking internals, and beats raising, which would
turn a handled error into a 500 with no feedback at all. Reviewers should check that a new
user-facing exception opts in.

Domain exceptions cannot use the mixin — the domain must not import from the service layer —
so they define `user_msg()` directly, as `RegistrationPageNotReady` does. Callers duck-type
on the method rather than checking a base class.

## Catch narrowly

Catch what a call can actually raise. Let anything else reach the route's outer handler,
which logs it and returns a generic message.

```python
# ✅ - the four things these services raise
except (InsufficientPermissions, NotFoundError, RegistrationPageNotReady, ValueError) as e:
    logger.warning("Registration page lifecycle call failed", error=str(e))
    return {"status": "error", "error": _dev_error(e), "error_type": type(e).__name__}
```

A blanket `except Exception` around a service call turns a bug into a plausible-looking
error message and hides it. If you do need one — usually only in the outermost route
handler — it must log the real error and return a generic message:

```python
except Exception as e:
    logger.exception("Image upload error for assembly", assembly_id=str(assembly_id), error=str(e))
    return jsonify({"error": _("Something went wrong uploading the image")}), 500
```

Note that `error=str(e)` **in a log call** is correct and wanted. The rule is about response
bodies, not logs. (Do keep [personal-data.md](../personal-data.md) in mind for what may be
logged.)

## Dev-only routes are not exempt

`dev.py` follows the same rule, with one addition: the developer is looking at the page, not
the terminal, so `_dev_error(exc)` appends "check the Flask console log for full error
details" to the safe message. The full exception still goes to the log; the helper only
governs what reaches the page.

That helper is local to `dev.py` on purpose. It is not a method on the exception hierarchy,
because production code would then carry a method it must never call.

None of which makes `dev.py` an example to copy. It is a dev-only scratch space, not held to
the production bar, and its docstring says so. When you want a JSON route to model yours on,
use this document and the routes in `backoffice_registration.py` / `backoffice.py`.

## API fixtures: stopping the server and the JS drifting apart

A JSON route has two sides, and only one of them is in Python. Nothing about renaming
`display_name` to `title` makes the JavaScript that reads `display_name` fail to compile —
it just quietly renders `undefined` in production.

Two artefacts close that gap, and both live outside the tests that use them:

| Artefact       | Lives in                          | Says                                             |
| -------------- | --------------------------------- | ------------------------------------------------ |
| A JSON Schema  | `src/opendlp/schemas/json_api/`   | what this response shape is *allowed* to be      |
| An API fixture | `tests/fixtures/json_api/`        | what the server *actually returned*, recorded    |

The Python side (`tests/component/test_json_api_fixtures.py`) drives the real route, asserts
the response validates against the schema, and diffs it against the recorded fixture. The JS
side imports the fixture through `src/js/test-support/api-fixtures.js`, which validates it
against the *same* schema with ajv — so the schema and the fixture cannot drift from each
other either.

A shape change therefore has to be made in three places or the build fails: the route, the
schema, and the fixture. That is the whole point — the middle one is where you have to say
out loud what you are changing.

**Never hand-type an API response in a `.test.js` file.** A literal records what the author
believed the server returns; nothing makes it wrong when the server changes, which is exactly
the failure this machinery exists to prevent. Load a fixture instead:

```javascript
import { loadApiFixture } from "../test-support/api-fixtures.js";

const body = loadApiFixture("registration-image-upload", "registration-image");
```

### Adding a shape

1. Write the schema in `src/opendlp/schemas/json_api/<name>.schema.json`, with
   `additionalProperties: false` — without it, an added field slips through silently.
2. Add a test to `tests/component/test_json_api_fixtures.py` that drives the route and calls
   `check_api_fixture(...)`.
3. Record it: `UPDATE_API_FIXTURES=1 uv run pytest tests/component/test_json_api_fixtures.py`
4. Add the fixture to `FIXTURE_SCHEMAS` in `src/js/test-support/api-fixtures.test.js`, which
   fails if a recorded fixture is not paired with a schema.

### When a fixture test fails

The failure means the response changed. Either that was intended — re-record with
`UPDATE_API_FIXTURES=1` and **read the diff** before committing — or it was not, and you have
just caught the bug the mechanism is for. An unexplained diff is the mechanism working.

Note that a fixture pins real recorded values, including things like an encoded image's
`byte_size`. An image-library upgrade can therefore move a fixture legitimately; the diff
will make that obvious.

### Not "contract tests"

That term is already taken in this repo: `tests/contract/` means fake-repository-versus-SQL-
repository parity. These are **API fixtures**, and calling them anything else will get the two
confused in conversation and in CI output.
