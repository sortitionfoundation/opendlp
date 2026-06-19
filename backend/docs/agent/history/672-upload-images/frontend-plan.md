<!-- ABOUTME: Implementation summary for the frontend/upload-route half of registration image uploads (PR #175). -->
<!-- ABOUTME: Covers Assets panel UI, JSON routes, button-macro extension, dev tools tab, and review follow-ups. -->

# Registration image uploads — frontend implementation summary

**Issue:** 672 · **Companion:** [data-service-plan.md](data-service-plan.md), [research.md](research.md)
**Date:** 2026-06-17 · **Branch:** `672-image-upload-frontend` · **PR:** [#175](https://github.com/sortitionfoundation/opendlp/pull/175)

> **Status: ✅ implemented and in review.** All endpoints, UI, dev-tools tab,
> and button-macro extension are committed; 27 new happy-path unit tests pass.
> A preliminary review pass has been done — two small follow-up fixes pushed
> (commit `adad23b`), and the remaining notes posted as a PR comment for
> @foobacca to scrutinise.

## 1. Scope

This is the **upload route + UI** half of the registration-image feature,
built on top of the data/service layer landed via [#171](https://github.com/sortitionfoundation/opendlp/pull/171)
(see [data-service-plan.md](data-service-plan.md)). The service seam
already existed (`add_registration_image`, `list_registration_images`,
`delete_registration_image`, `set_registration_image_alt`,
`list_image_snippets`, `get_registration_image_for_serving`); this work
wired them into the backoffice and exposed them in dev tooling.

**In scope**

- Three JSON endpoints under `/backoffice/assembly/<id>/registration/images`
  (POST upload, PATCH alt, DELETE).
- An **Assets panel** rendered on the registration tab, alongside the HTML
  editor — list, upload modal, copy-`<img>`-snippet, details/edit-alt modal,
  delete.
- An **Images tab** in `/backoffice/dev/service-docs` exercising all six
  service-layer functions via interactive forms.
- A new `alpine_disabled` parameter on the shared `button` macro that
  reactively toggles `disabled`, `aria-disabled`, and a runtime CSS class
  from an Alpine expression.
- Happy-path unit coverage for the route helpers, the JSON routes (with
  `LOGIN_DISABLED`), the dev handlers, and the macro extension.

**Out of scope**

- Replacing the headline UX flow with full e2e/BDD coverage (see §7).
- A modal-based delete confirmation (still `confirm()`).
- Configuration of `MAX_CONTENT_LENGTH` at the app level (see §7).

## 2. Architecture decisions

### 2.1 Assets panel lives outside the editor `<form>`

The HTML editor (`<textarea name="html_content">`) lives inside a `<form>`
that POSTs to `save_assembly_registration`. The Assets panel sits in a
sibling column **outside** that form so its buttons never submit the editor.
Uploads/deletes mutate the Alpine `images` array in place — no page reload
means uncommitted edits in the textarea survive any asset-panel action.
This is the headline UX promise of the PR.

Layout: `<div class="flex flex-col lg:flex-row gap-6">` with the editor on
the left (`flex-1 min-w-0`) and a fixed-width column on the right
(`w-full lg:w-[400px]`, `lg:flex-shrink-0`).

### 2.2 Server-rendered list, client-mutated state

The first render emits the full image list as JSON into Alpine state
(`images: {{ images|tojson }}`). All subsequent mutations happen client-side:

- **Upload** → POST multipart → server returns image dict → push (or splice
  in place if dedup returned an existing row).
- **Edit alt** → PATCH JSON → server returns updated image → splice in place.
- **Delete** → DELETE → 204 → filter out client-side.

This keeps the round-trip count low and avoids re-rendering the editor.

### 2.3 Alt text required at every entry point

- Modal Upload button stays muted until `imageAlt.trim()` is non-empty
  (via `alpine_disabled`).
- Server-side: every endpoint that takes alt rejects empty/whitespace with
  `400 {"error": "Alt text is required for accessibility"}`.
- The Details modal won't save with blank alt.

### 2.4 Dedup quirk: `_add_image_honouring_alt`

`add_registration_image` collapses identical bytes to one row and KEEPS the
first upload's alt. If the user supplies a different alt for a row that
already exists (typically replacing an empty legacy alt), the upload route
follows up with `set_registration_image_alt` so the snippet they copy
reflects what they typed. **Two distinct UoWs** — see §7.1.

### 2.5 `button` macro gains `alpine_disabled`

Compile-time `disabled=true` already existed; the new `alpine_disabled`
parameter takes an Alpine expression and emits:

```html
:disabled="<expr>"
:aria-disabled="(<expr>) ? 'true' : 'false'"
:class="{ 'btn-runtime-disabled': (<expr>) }"
```

A new `.btn-runtime-disabled` class in `main.css` layers the muted look on
top of the variant's inline style (CSS-class merge, not `:style` replace),
so padding and base styles survive.

The expression is rendered inside double-quoted attributes; Jinja
autoescape handles any `"` inside the expression, but authors should prefer
single quotes for string literals to keep the rendered HTML readable
(documented in the macro docstring).

### 2.6 Per-image URL contract

PATCH/DELETE share a URL pattern (`…/images/<uuid:image_id>`); only the
HTTP method differs. The template renders the URL **once** via `url_for`
with a sentinel UUID (`00000000-0000-0000-0000-000000000000`) and a small
`imageItemUrl(id)` helper swaps in the real id at call time. This keeps the
route-name dependency explicit instead of implying the URL hierarchy
(`upload_url + "/" + id` is what the v1 attempt did, fixed in commit
`adad23b`).

## 3. Endpoints added

| Method | Path | View | Returns |
|---|---|---|---|
| `POST` | `/backoffice/assembly/<assembly_id>/registration/images` | `upload_registration_image` | `201 {"image": {…}}` / `4xx {"error": "…"}` |
| `PATCH` | `/backoffice/assembly/<assembly_id>/registration/images/<image_id>` | `update_assembly_registration_image` | `200 {"image": {…}}` / `4xx {"error": "…"}` |
| `DELETE` | `/backoffice/assembly/<assembly_id>/registration/images/<image_id>` | `delete_assembly_registration_image` | `204` / `4xx {"error": "…"}` |

All three require `@login_required` and accept `X-CSRFToken` header. Error
mapping:

- `ImageValidationError` → 400 (includes `reason` field)
- `ImageQuotaExceeded` → 400
- `RegistrationPageNotFoundError` / `RegistrationImageNotFoundError` → 400/404
- `InsufficientPermissions` → 403
- `NotFoundError` → 404
- Catch-all → 500 with generic message; traceback logged

## 4. Files touched

| File | Adds | Notes |
|---|---|---|
| `src/opendlp/entrypoints/blueprints/backoffice_registration.py` | +175 | Three new routes + `_image_to_dict`, `_add_image_honouring_alt`, `_resolve_page_url_slug` helpers |
| `src/opendlp/entrypoints/blueprints/dev.py` | +190 | Six `_handle_*` functions + `_serialise_image`; wired into `_SERVICE_HANDLERS` and `valid_tabs` |
| `static/backoffice/src/main.css` | +11 | `.btn-runtime-disabled` runtime-muted class |
| `templates/backoffice/assembly_registration.html` | +595 / −140 | Two-column layout; Upload modal; Details/Edit modal; Alpine data + methods; URL contract via `imageItemUrl(id)` |
| `templates/backoffice/components/button.html` | +14 / −3 | `alpine_disabled` macro param + docstring |
| `templates/backoffice/service_docs.html` | +105 / −4 | "Images" tab + Alpine state + execute methods + base64 file-reader helper |
| `templates/backoffice/service_docs/_images.html` | +456 (new) | Interactive cards for all six service functions |
| `templates/backoffice/showcase/button_component.html` | +20 / −2 | Demo of reactive `Disabled (Alpine)` paired with a switch |
| `tests/unit/test_backoffice_registration_images.py` | +271 (new) | `_image_to_dict`, `_add_image_honouring_alt`, route happy paths |
| `tests/unit/test_button_macro_alpine_disabled.py` | +54 (new) | Macro render assertions |
| `tests/unit/test_dev_image_handlers.py` | +242 (new) | All six dev handler happy paths |

Total: ~2.1k additions / ~150 deletions across 11 files.

## 5. Tests added (27 happy-path)

- `_image_to_dict`: slug present/absent, blank-alt fallback to short-sha
  filename.
- `_add_image_honouring_alt`: no-dedup pass-through, dedup follow-up
  triggering `set_registration_image_alt`.
- Anonymous-user redirect on all three routes (sanity check that auth is
  wired).
- POST happy path with file + alt → 201 with image dict; rejects missing
  alt; rejects missing file.
- PATCH happy path with alt → 200 with image dict; rejects missing alt.
- DELETE happy path → 204 with empty body.
- All six dev handlers: serialisation, base64 decode (incl. `data:` URL
  strip), and the snippet handler's URL builder.
- Macro: emits Alpine bindings when `alpine_disabled` is set; doesn't
  otherwise; static `disabled=true` still produces the muted look and
  HTML attribute; padding/base styles survive when `alpine_disabled` is
  paired with a variant.

Authenticated routes use `app.config["LOGIN_DISABLED"] = True` +
`patch(current_user)` — a deliberate unit-test shortcut. See §7.2 for
the trade-off.

## 6. Review pass (PR #175)

A preliminary review was conducted on 2026-06-17 covering correctness,
project conventions, performance, test coverage, and security. Two small
follow-up fixes were pushed:

- **Commit `adad23b`** — explicit `url_for` for per-image PATCH/DELETE URLs
  (§2.6) and a docstring clarification on `alpine_disabled` autoescape
  behaviour (§2.5). All 27 tests still pass; `url_for` with the sentinel
  UUID renders it verbatim so the JS string-replace contract is sound.

The remaining notes were posted as
[PR comment #4728112593](https://github.com/sortitionfoundation/opendlp/pull/175#issuecomment-4728112593),
summarised in §7 below.

## 7. Known trade-offs and follow-ups

### 7.1 `_add_image_honouring_alt` runs two separate UoWs

```python
image = add_registration_image(bootstrap.bootstrap(), …, alt=alt)
if image.alt != alt:
    image = set_registration_image_alt(bootstrap.bootstrap(), …, alt=alt)
```

Distinct transactions. If the alt-update fails (race, transient DB error,
perms change mid-call), the image **is already stored** but the user gets a
500 with a misleading message. Low blast radius (alt text being wrong) but
worth either:

- catching the second-call failure and returning the stored image with a
  soft warning, or
- consolidating dedup-honours-alt into the service layer in a single
  transaction.

### 7.2 Test coverage relies on `LOGIN_DISABLED`

Unit tests bypass real auth via `LOGIN_DISABLED = True` + mocked
`current_user`. **The real `can_manage_assembly` / `can_view_assembly`
gates are never exercised** in this test layer. Worth following up with
integration tests for:

- An unauthorised user gets a 403 JSON response (not a redirect / HTML).
- Error-path JSON shapes for `ImageQuotaExceeded`,
  `ImageValidationError`, `RegistrationPageNotFoundError` — the frontend
  reads `data.error` and surfaces it inline; the shape contract matters.
- A browser-level smoke test confirming the textarea survives an upload
  (the headline UX promise).

### 7.3 `upload.read()` reads the full body before any size check

The service layer enforces `max_image_upload_mb`, but Flask reads the
multipart body into memory first. Worth confirming `MAX_CONTENT_LENGTH`
is set at the app level so a multi-GB upload never reaches the route
code. Not visible in this PR's diff; recommend a separate audit.

### 7.4 Minor

- `_handle_list_image_snippets` in `dev.py` opens its own bootstrap UoW
  to look up the page URL slug, mirroring `_resolve_page_url_slug` in
  `backoffice_registration.py`. Candidate for a shared helper.
- Delete uses native `confirm()` — fine for v1, but inconsistent with
  the modal pattern used elsewhere on the same page.
- DELETE returns `("", 204)` on success but JSON on error. Frontend
  handles both; flagging the asymmetry.

## 8. Things verified and happy with

- CSRF token sent in headers on all three new endpoints.
- `images|tojson` in the template properly escapes the seed.
- i18n: every user-facing string wrapped in `_()`.
- Generic 500 messages with full tracebacks logged server-side (no info
  leak).
- The Assets panel sitting outside the editor `<form>` cleanly solves the
  unsaved-state problem.
- All 27 unit tests pass; pre-commit hooks clean.
