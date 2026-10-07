# 767 — Split the registration page intro from the form

Branch: `767-registration-intro`. The design questions below have been
decided (first review round); each records the choice and the reasoning that
survives. Nothing here is implemented yet.

## Goal

A registration page's HTML currently lives in one string,
`RegistrationPageHtml.form_html`, and the starter skeleton puts the assembly
title and question at the top of that string, above the `<form>`. We split it:

- `RegistrationPageHtml` gains `intro_html`. `render()` renders the intro,
  then the form, and returns them concatenated.
- The starter skeleton moves `{{ assembly_title }}` / `{{ assembly_question }}`
  out of the form skeleton and into a new intro skeleton.
- The editor modal gains a new step 1, "Intro", so the steps become
  Intro → Form → Auto-reply email → Preview and publish. The existing
  CodeMirror HTML editor is reused for the intro.
- The page name and URL inputs move from the form step to the intro step, so
  step 1 is "set up the page": name, URLs, intro.

## How it works today (what the change touches)

| Layer | Where | What it does now |
|---|---|---|
| Domain | `src/opendlp/domain/registration_page.py` | `RegistrationPageHtml(form_html)`, `update_html()`, `render(ctx)` runs `form_html` through a sandboxed Jinja env with `csrf_form_element`, `form_action`, `assembly_title`, `assembly_question` and the `value()`/`checked()`/… helpers. `readiness_problems()` checks non-empty, parses, and requires the two tokens. `generate_starter_form_html[_govuk]()` emit `<h1>{{ assembly_title }}</h1><p>{{ assembly_question }}</p>` before the `<form>`. |
| ORM | `src/opendlp/adapters/orm.py` `registration_page_html_sources` | Columns `id`, `registration_page_id`, `form_html`, `created_at`, `updated_at`. Mapped imperatively in `adapters/database.py`. |
| Service | `src/opendlp/service_layer/registration_page_service.py` | `update_registration_page_html()` (size check via `get_registration_form_html_max_bytes`, records "Updated form HTML"), `duplicate_registration_page()` copies `form_html`, `render_registration_form()` builds the `RenderContext`, `generate_starter_form_html_variants()` returns `StarterFormHtmlVariants(plain, govuk)`. |
| Routes | `src/opendlp/entrypoints/blueprints/backoffice_registration.py` | `view_registration_page` accepts `?section=form\|email\|preview` (default `form`) and `?edit=1`. `save_assembly_registration` handles `save`, `save_and_next` and the lifecycle actions; it updates HTML only when `html_content` is in the posted form, and `_apply_page_settings()` applies `page_name` / `url_slug` / `short_url_slug` only when posted; `_post_action_section()` decides where to land. `get_registration_skeleton` returns `{"html", "html_govuk"}`. `preview_registration_form` renders through `render_registration_form`. |
| Templates | `templates/backoffice/assembly_registration.html`, `templates/backoffice/registration/_step_form.html`, `_step_email.html`, `_step_preview.html`, `_modals.html`, `_page_data.html` | Three-item stepper; the form step holds the page name input (replacing the card heading in edit mode), the slug inputs with the "URLs are locked" alert, the Show Form Skeleton button, the `html_content` textarea and the Assets aside. |
| JS | `src/js/components/registration-skeleton.js` (+ `.test.js`), `registration-page-controller.js` | The skeleton slice fetches the JSON and holds `skeletonHtmlPlain` / `skeletonHtmlStyled` and the plain/GOV.UK toggle. |
| Public | `src/opendlp/entrypoints/blueprints/registration.py`, `templates/register/form.html` | Renders `rendered_form` from `render_registration_form`. No change needed if `render()` returns intro + form. |
| Dev docs | `src/opendlp/entrypoints/blueprints/dev.py` | `_handle_get_registration_page` and `_handle_update_registration_page_html` expose `form_html`. |

I could not read GitHub issue 767 from here (`gh issue view 767` returned
nothing), so this plan is built from the request text and the review notes.

## Decisions

### D1 — `render()` renders each part separately and concatenates the output

The intro and the form are rendered as two templates against the same context
(the same variables and helpers — harmless, and it means an author can move
markup between the two boxes without anything breaking), joined with a
newline. Concatenating the sources and rendering once was rejected: a
`{% if %}` opened in the intro and closed in the form would "work", and the
form's error line numbers would be offset.

### D2 — The intro is optional; its syntax errors still block publishing

`readiness_problems()` treats an empty intro as fine. A template syntax error
in the intro is reported with its own message ("The intro HTML has a template
syntax error on line N: …"). The `csrf_form_element` / `form_action` tokens are
required **in the form HTML only** — a form must be self-contained for the
error line numbers and the helpers to make sense.

### D3 — Schema-only migration; existing pages are untouched

Add `intro_html TEXT NOT NULL server_default ''`. Existing pages keep their
heading inside `form_html`; `render("") + render(form_html)` is byte-for-byte
what they render today, so no live page changes. Authors move the heading when
they next edit. A data migration that splits a leading `<h1>` / `<p>` out of
each `form_html` was rejected as too fragile for live public pages.

### D4 — The intro gets its own size limit

New `REGISTRATION_INTRO_HTML_MAX_BYTES` with
`get_registration_intro_html_max_bytes()` in `config.py`, same 200 KiB default
as the form, documented in `docs/configuration.md`. The thank-you HTML already
has its own, so this follows the pattern, and the error message's label
("The intro HTML must be at most…") is right.

### D5 — The intro step posts to the existing `/save` route

The form step posts `html_content`; the route updates the form only when that
field is present. The intro step posts `intro_content` and the route updates
the intro on the same rule. `_post_action_section(action)` becomes
`_post_action_section(action, origin)` where `origin` is `"intro"` when
`intro_content` was posted and `"form"` otherwise. So: `save` from intro →
intro; `save_and_next` from intro → form; `save` from form → form;
`save_and_next` from form → email, as now. The error redirect
(`error_kwargs["section"]`) uses the same origin. The lifecycle actions are
unaffected. A second route was rejected: it would duplicate the permission
check, the five `except` blocks and the flash messages for a two-line
difference.

### D6 — The default section is `intro`

`?section=` defaults to `intro`, so a freshly created page (the create route
redirects to the bare editor URL) opens on step 1. Links with an explicit
`section=form` keep working.

**Consequence for tests:** `tests/component/test_backoffice_registration_view.py`
has around a dozen tests that `GET …/my-slug?edit=1` with no section and
assert on the `html_content` textarea. Those requests will now land on the
intro step. Each needs `section=form` added (or, where the assertion is about
edit mode in general rather than the form textarea, it can stay bare and
assert on `intro_content` instead). The script test's view list
(`test_backoffice_registration_page_script.py`) gains the intro views.

### D7 — The page name and URL inputs move to the intro step

Step 1 becomes "set up the page": in edit mode the card heading is the
`page_name` input, followed by the `url_slug` / `short_url_slug` inputs with
the "URLs are locked" alert, then the intro editor. The form step's card
heading becomes the static page name in both modes, and its edit mode is just
the form HTML and the Assets aside.

The save route needs no change for this: `_apply_page_settings()` already
applies whichever of the three fields are posted. The form step simply stops
posting them. `rename_registration_page` and `update_registration_page` are
untouched.

**Consequence for tests:** `test_edit_mode_offers_name_and_slug_inputs` and
the three save tests that post `page_name` / `url_slug` alongside
`html_content` move to the intro step (post `intro_content` instead, GET
`section=intro&edit=1`). A new test asserts the form step's edit mode does
**not** render the three inputs. The BDD scenarios do not touch the name or
URL inputs, so they are unaffected.

### D8 — One skeleton route, four strings; the modal shows the part for the step you are on

`get_registration_skeleton` returns
`{"html", "html_govuk", "intro_html", "intro_html_govuk"}`. The skeleton slice
stores all four. The intro step renders a "Show Intro Skeleton" button and the
form step keeps "Show Form Skeleton"; each opens the same modal with the
matching pair, titled accordingly. In the CSP Alpine build the two buttons
call two methods (`fetchIntroSkeleton()` / `fetchFormSkeleton()`) rather than
passing a string argument — load the `ui-components` skill before touching
this and follow what it says about arguments.

The skeleton route has no entry in `src/opendlp/schemas/json_api/` or
`tests/fixtures/json_api/`, and we are **not** adding one in this PR. The JS
unit test for the slice therefore builds its response inline, as the existing
`registration-skeleton.test.js` already does for this route.

### D9 — Accept that saving the intro clears the "questions changed" warning

`fields_changed_after_save` compares every field's `updated_at` against the
HTML row's `updated_at`. Saving the intro bumps the same row, so it clears the
form step's warning even though the form was not touched. The warning is a
nudge and the row is one object, so we accept it rather than add a
`form_html_updated_at` column. The warning shows on the form step only, as
now; the intro step never shows it, because the intro does not depend on the
field schema.

### D10 — It is called "Intro"

Stepper label "Intro"; "Intro HTML" wherever the form step says "Form HTML";
"Show Intro Skeleton" for the button. Add a glossary row to
`docs/language.md`.

### D11 — `dev.py` stays truthful

`_handle_get_registration_page` adds `intro_html_preview` next to
`form_html_preview`; `_handle_update_registration_page_html` accepts an
`intro_html` param and reports both previews. The service-docs template
(`templates/backoffice/service_docs/_registration.html`) and
`tests/component/test_dev_registration_page_handlers.py` follow.

## Implementation steps

Ordered so each step leaves `just check` and `just test-nobdd` green.

### 1. Domain (`src/opendlp/domain/registration_page.py`)

- `RegistrationPageHtml.__init__` gains `intro_html: str = ""` (after
  `form_html`); `create_detached_copy()` copies it.
- New `update_intro_html(intro_html)` mirroring `update_html()`. Keep
  `update_html()` as-is — its name and callers do not change.
- `render(ctx)`: pull the kwargs into a helper `_render_kwargs(ctx)` so the
  two calls cannot drift; render `intro_html` and `form_html` through
  `_SANDBOX_ENV` separately; return `intro + "\n" + form` (D1).
- `readiness_problems()`: parse the intro first and report a syntax error with
  "intro HTML" in the message (D2); the existing checks on `form_html` are
  unchanged.
- Starter generators: two new functions `generate_starter_intro_html()` and
  `generate_starter_intro_html_govuk()` that take no fields and return the
  `<h1>{{ assembly_title }}</h1>` / `<p>{{ assembly_question }}</p>` lines
  (the GOV.UK one wrapped in its own `govuk-grid-row` / two-thirds column so
  the intro and form each stand alone). Remove those lines from
  `generate_starter_form_html[_govuk]()` and fix their docstrings, which
  currently promise the placeholders.
- Update the `RenderContext` docstring ("substituted into the form HTML" →
  intro and form HTML) and the `HtmlSource` protocol docstring.

### 2. Persistence

- `orm.py`: `Column("intro_html", Text, nullable=False, default="", server_default="")`
  between `form_html` and `created_at`.
- `uv run alembic revision --autogenerate -m "add intro_html to registration_page_html_sources"`,
  then read the generated file. `just check` runs `alembic check` against the
  local dev DB, so upgrade it first (see the memory note on `alembic check`).
  No new table, so no change to `_delete_all_test_data()` or
  `delete_all_except_standard_users()`.
- `tests/fakes.py` needs nothing — the fake repository stores the object.

### 3. Config

- `get_registration_intro_html_max_bytes()` next to the form one, same
  `_registration_html_max_bytes` helper, same default (D4). Export it where
  the form one is exported. Document in `docs/configuration.md`.

### 4. Service (`registration_page_service.py`)

- `update_registration_page_intro_html(uow, user_id, page_id, intro_html)`
  mirroring `update_registration_page_html`: size check with label
  `_("intro HTML")`, no-op when unchanged, records "Updated intro HTML".
- `duplicate_registration_page()` copies `intro_html` as well as `form_html`.
- `StarterFormHtmlVariants` gains `intro_plain` and `intro_govuk`;
  `generate_starter_form_html_variants()` fills them. The older
  `generate_starter_form_html()` service function (used by `dev.py`) is left
  returning the form only.

### 5. Routes (`backoffice_registration.py`)

- `view_registration_page`: allow `section in ("intro", "form", "email", "preview")`,
  default `intro` (D6); pass `intro_content=html.intro_html` to the template;
  compute `fields_changed_after_save` as now (D9).
- `save_assembly_registration`: when `"intro_content" in request.form` call
  `update_registration_page_intro_html`; derive `origin` from field presence
  and feed it to `_post_action_section()` and to `error_kwargs["section"]`
  (D5). Update the route docstring's action table. `_apply_page_settings()`
  is unchanged (D7).
- `get_registration_skeleton`: return the two extra keys (D8).
- `dev.py` per D11.

### 6. Templates

- New `templates/backoffice/registration/_step_intro.html`, built from the
  form step's structure: card whose heading is the page name (an input in
  edit mode, as the form step does today); Edit/Cancel/Save and "Show Intro
  Skeleton" in the header; in edit mode the slug inputs and the "URLs are
  locked" alert (moved from the form step, D7); help text naming
  `{{ assembly_title }}` and `{{ assembly_question }}`; the `intro_content`
  textarea with `code_editor=true`; the Assets aside in edit mode (images are
  as likely in an intro as in a form); a footer with "Next →" only. No
  "questions changed" alert (D9).
- `_step_form.html`: remove the `page_name` input and the slug block; the
  heading is the static page name; footer gains "← Back" to the intro step
  (disabled while editing, like the email step's). `Next →` still goes to
  email.
- `assembly_registration.html`: four stepper items; include the intro panel
  when `active_section == "intro"`; update the comment that documents the URL
  contract.
- `_modals.html`: the skeleton modal's title and intro copy become
  step-aware (bound to the slice's current part).
- `_page_data.html`: add any new translated message the slice needs.
- Load the `ui-components` skill before writing any of this.

### 7. JavaScript

- `registration-skeleton.js`: store `skeletonIntroPlain` / `skeletonIntroStyled`
  alongside the form pair; a `skeletonPart` ("intro" | "form") chosen by
  `fetchIntroSkeleton()` / `fetchFormSkeleton()`; the modal's textareas and
  `copySkeletonToClipboard()` read from the current part. Update
  `registration-skeleton.test.js` and the property list in
  `tests/component/test_backoffice_registration_page_script.py`.
- Rebuild the bundle with the `just` target in `docs/frontend_build.md`.

### 8. Translations and docs

- New strings → run the `translate-catalogues` skill before committing.
- `docs/language.md`: glossary row for the intro (D10).
- `docs/configuration.md`: the new env var (D4).

## Tests

Every layer that changes gets coverage; nothing is marked not applicable.

**Unit — domain** (`tests/unit/domain/test_registration_page.py`)
- `intro_html` defaults to `""`, round-trips through `create_detached_copy()`.
- `update_intro_html()` sets the value and bumps `updated_at`; `update_html()`
  leaves the intro alone.
- `render()` returns intro then form; the intro sees `assembly_title`,
  `assembly_question` and the helpers; empty intro renders the form unchanged
  (the backwards-compatibility guarantee behind D3).
- `readiness_problems()`: syntax error in the intro is reported and names the
  intro; required tokens in the intro alone still fail; empty intro is not a
  problem.
- Starter intro generators (plain and GOV.UK) carry both placeholders; the
  form generators no longer do.

**Unit — service** (`tests/unit/test_registration_page_service.py`)
- `update_registration_page_intro_html`: size limit, permission, no-op when
  unchanged, activity text.
- `duplicate_registration_page` copies the intro.
- `generate_starter_form_html_variants` returns the four strings.

**Unit — config** (`tests/unit/test_config.py`): the new limit reads its env
var and defaults.

**Contract / integration** (`tests/contract/test_registration_page_html_repo.py`,
`tests/integration/test_orm.py`): `intro_html` persists and loads.

**Component** (`tests/component/test_backoffice_registration_view.py`, the
script test, `test_dev_registration_page_handlers.py`):
- `?section=intro` renders the `intro_content` textarea with the code-editor
  marker; the stepper has four items; the bare editor URL lands on the intro
  (D6).
- Intro edit mode renders the `page_name`, `url_slug` and `short_url_slug`
  inputs; form edit mode does not (D7).
- `save` with `intro_content` persists and redirects to `section=intro`;
  `save_and_next` from the intro redirects to `section=form`; `save` with
  `html_content` still redirects to `section=form`; an oversize intro
  redirects back to `section=intro&edit=1` with a flash; posting `page_name`
  with `intro_content` renames the page.
- The skeleton JSON has the four keys; the preview iframe route output starts
  with the intro.
- The existing bare `?edit=1` tests gain `section=form` (D6).
- The dev handlers report `intro_html_preview` (D11).

**JS unit** (vitest): the skeleton slice's part switching and copy.

**End-to-end** (`tests/e2e/test_registration_stepper_journey.py`): the walk
becomes intro → form → email → preview → publish.

**BDD** (`features/backoffice-registration-editor.feature`,
`tests/bdd/test_backoffice.py`): one scenario that opens the intro step in
edit mode, types into the code editor, saves, and sees the content persisted;
one that opens the intro skeleton. Existing scenarios that visit
`?section=form&edit=1` keep working unchanged.

## Risks and things to watch

- **Live pages must not change.** D3's empty-intro default is what guarantees
  it; the domain test for "empty intro renders the form unchanged" is the
  regression guard.
- **GOV.UK layout.** Rendered separately, the intro and the form each need
  their own grid wrapper, otherwise the intro's heading sits outside the
  two-thirds column. The GOV.UK intro skeleton carries its own wrapper.
- **Edit-guard and scroll preservation** are page-level directives already
  wired in `_step_form.html`; copying that structure keeps them working for the
  intro step without touching `registration-edit-guard.js`.
- **The default-section change (D6)** is the one that silently reroutes
  existing tests and bookmarks; the test consequences are listed under D6 so
  nothing is "fixed" by loosening an assertion.
- **`just check` on a skewed dev DB** fails on the new migration until the dev
  DB is upgraded.

## Out of scope

- A richer editor for the intro (the request says the current HTML editor
  stays for now).
- A JSON schema and fixture for the skeleton route (D8).
