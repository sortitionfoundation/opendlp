# Story 613 — Accept Registration Form Submissions

**Branch:** `613-registration-page-accept`
**Date:** 2026-05-18
**Status:** Research only — open for review before a detailed plan is written.

This document captures what's already in place from story 610, what story 613 actually
adds, the main implementation options for each meaty decision, and the open technical
questions that need answering before a detailed plan can be cut.

---

## 1. What's already in place (from story 610)

### 1.1 Domain layer

`src/opendlp/domain/registration_page.py`:

- `RegistrationPage` aggregate per assembly with `url_slug`, `short_url_slug`,
  `is_published`, `preview_token`, `source_type` (HTML only for now), `thank_you_html`.
  Slugs are frozen while `is_published=True` (Q6 in plan-data-service.md).
- `RegistrationPageHtml` child holding the author's HTML.
  `render(RenderContext)` does **flat string substitution** of exactly two tokens —
  `{{ csrf_form_element }}` and `{{ form_action }}`. `readiness_problems()` insists
  on both being present.
- `HtmlSource` protocol so future source types (template builder, A/B variants,
  translations) plug in without touching the page aggregate.
- `is_visible_with(token)` — true if published, or if `token` matches the
  page's `preview_token` and is non-empty.
- `generate_starter_form_html(fields)` — pure helper that emits an unstyled HTML
  form from the assembly's `RespondentFieldDefinition` set. `name=` attributes
  match `field_key`; choice fields are emitted as radios/select; the four boolean
  fixed fields (`eligible`, `can_attend`, `consent`, `stay_on_db`) become yes/no
  radios via `effective_field_type` (always `BOOL_OR_NONE`).
- `SlugError(field, reason, message)` carries structured info so a UI can attach
  the right error to the right slug input.
- `RegistrationPageNotReady` carries a `.problems: list[str]`.

### 1.2 Service layer

`src/opendlp/service_layer/registration_page_service.py` exposes:

- **Management** (all require `can_manage_assembly`): `create_registration_page`,
  `get_registration_page`, `get_registration_page_with_source`,
  `update_registration_page` (slugs), `update_thank_you_html`,
  `update_registration_page_html`, `publish_registration_page`,
  `unpublish_registration_page`, `regenerate_preview_token`,
  `generate_starter_form_html`.
- **Public, unauthenticated**: `find_registration_page_by_url_slug`,
  `find_registration_page_by_short_url_slug`, `resolve_visibility(page, token)`
  → `RegistrationPageVisibility(page, is_visible, is_preview)`,
  `get_page_and_source_for_render(uow, page)`, `render_thank_you_html(page)`.

The public functions are intentionally read-only seams for the route layer to plug
into. `resolve_visibility` is pure — no DB hit.

### 1.3 Adapters + tests

ORM tables `registration_pages` and `registration_page_html_sources` exist;
migration is applied; repositories (`RegistrationPageRepository`,
`RegistrationPageHtmlRepository`) live on `AbstractUnitOfWork`; full contract
tests and unit tests are green (last verified 2026-05-15: 2764 passed).

### 1.4 What's NOT in place yet (the gap 613 sits in)

- No public Flask blueprint for `/register/<url_slug>` or `/r/<short_url_slug>`.
- No backoffice tab — `plan-frontend.md` is still unimplemented. (Story 613 only
  needs the public side, but **the backoffice tab is part of story 610**, not 613. If we ship 613 without it, an author can only set up a page via the
  Flask shell. See §6 — Q12.)
- No "registration closed" page template.
- `RespondentStatus.TEST_SUBMISSION` (or `.RegistrationTest`) doesn't exist yet.
  Currently the enum has POOL / SELECTED / CONFIRMED / WITHDRAWN / DELETED.
- `RespondentSourceType.REGISTRATION_FORM` **does** exist already.
- `FF_REGISTRATION_PAGE` flag isn't checked anywhere yet (the service layer
  intentionally doesn't gate; the route layer is meant to).

### 1.5 The bigger picture — raw HTML is just the first source type

The raw-HTML authoring path that 610 ships is only the **first** way users will
create registration forms. Two further paths are anticipated, and 613's
submission handler is intended to support all of them:

- **A form builder** — expected to be the most common option. A library of
  components (text input, radio group, dropdown, consent checkbox, ...) keyed
  off the fields the user said they need for targets and for contacting
  respondents. The author orders elements, groups them into sections, adds an
  introduction. The system writes most of the HTML and provides default
  styling. Because the system owns the markup, the form builder can show
  errors **next to** the relevant inputs.
- **A Jinja template the author can feed to their own LLM.** Same flexibility
  as raw HTML, but with `{% for %}` loops and error-bit placeholders pre-wired
  so the styled output still supports per-field error rendering.

Implications for story 613:

- The submission service **must return structured validation results** — a data
  shape any presentation layer (raw-HTML summary, form-builder inline errors,
  Jinja template with error bits) can consume. Don't pre-bake HTML inside the
  service. See §4.7.
- The respondent field schema may grow a `for_registration_page` flag (or an
  enum: `registration_page`, `derived_target`, `confirmation_call_only`, ...)
  so the validator and the form builder both know which fields belong on a
  registration form vs which are derived later or only collected during
  confirmation calls. See §6 — Q15.

---

## 2. What story 613 actually has to do

Boiled down from `story-notes.md`:

1. **GET** `/register/<url_slug>` — render the form HTML for the public.
   - If the page exists and is published → render `RegistrationPageHtml.render(...)`
     with a real CSRF input and real `form_action` URL.
   - If the page exists, is unpublished, and the URL carries a valid
     `?token=<preview_token>` → render as above, but the form submits as a
     "test" (see step 3).
   - Otherwise → **302 redirect** to a canonical "registration closed" page.
2. **GET** `/r/<short_url_slug>` — 302 redirect to
   `/register/<page.url_slug>` (not 301; the short slug may be cleared/reused).
3. **POST** to the form action — validate the body against the assembly's
   `RespondentFieldDefinition` set. On success:
   - Create a `Respondent` with `source_type=REGISTRATION_FORM`.
   - Status is **POOL** in the normal case, or a new **TEST_SUBMISSION** value
     when the preview-token path was used.
   - **302 redirect** to a "thank you" page that renders
     `page.thank_you_html` (or a Jinja fallback if it's blank).
   - On failure → re-render the form with the field-level errors attached
     somehow (the open question is how — see §5).
4. **Feature flag** the whole thing behind `FF_REGISTRATION_PAGE`.

Out of scope per the story notes:

- Bot protection.
- Field editing inside the registration page.
- Date-based publish/unpublish.
- QR code rendering.

Out of scope per `plan-data-service.md` §8 (still relevant):

- Rate-limiting.
- Thank-you page substitution (e.g. `{{ respondent_name }}`).
- What happens to submissions when an unpublished page is republished after a
  slug change (mitigated by the "slugs frozen while published" rule).

---

## 3. Big-picture shape

```
GET  /register/<url_slug>            → render form HTML (or 302 closed)
GET  /r/<short_url_slug>             → 302 to /register/<url_slug>
POST /register/<url_slug>/submit     → create Respondent, 302 to thank-you
GET  /register/<url_slug>/thank-you  → render thank_you_html
GET  /registration-closed            → static "closed" page
```

Open: does the POST live on the same URL as the GET (`/register/<url_slug>`,
method-dispatched) or on a sibling `/submit`? Story-notes line 34 explicitly
floats both options. See §5 — Q1.

The thank-you URL needs to be sticky enough that the redirect target works even
after a slug change — see §6 — Q5.

---

## 4. New code expected (rough sketch, subject to the open questions)

### 4.1 Domain

- Add `RespondentStatus.TEST_SUBMISSION` to `domain/value_objects.py`. Update
  `ALLOWED_SELECTION_STATUS_TRANSITIONS`: no **inbound** transitions
  (TEST_SUBMISSION rows are only created from the form), but **outbound
  TEST_SUBMISSION → POOL is allowed** so an organiser can promote a real
  person who happened to use the preview-token URL. The transition requires
  a comment (the existing rule) so the activity history records who promoted
  it and why. See §5 — Q10.
- A small **value object** for the parsed-and-validated form payload — `dict[str, Any]`
  is workable, but a typed `RegistrationFormSubmission` (with `email`,
  `eligible`, `can_attend`, `consent`, `stay_on_db`, `attributes`,
  `external_id`) would mirror the `Respondent` constructor and stop the route
  having to know about field-name normalisation.

### 4.2 Service layer

A new file, `service_layer/registration_submission_service.py` (kept
separate from `registration_page_service.py`, which is already getting busy),
that exposes something like:

```python
def submit_registration(
    uow: AbstractUnitOfWork,
    *,
    url_slug: str,
    form_data: Mapping[str, Any],
    preview_token: str = "",
) -> RegistrationSubmissionResult:
    """Validate the submission against the assembly's field schema, create a
    Respondent if valid, return either (Respondent, redirect_url) or an
    errors structure for the route to re-render with."""
```

The exact return shape is part of §5 — Q3. No `user_id` argument: the public
route is anonymous.

### 4.3 Form-validation helper

The single biggest piece of new logic. The author has written
`<input name="email">`, `<input name="first_name">`, `<input type="radio"
name="gender" value="...">` etc., where every `name` should correspond to a
`RespondentFieldDefinition.field_key`. The validator's job is to:

1. Pull each schema field's submitted value out of `form_data`.
2. Type-coerce per `effective_field_type` (string, integer, email, bool from
   yes/no, choice within `options`).
3. Reject the submission with structured errors if any required field is
   missing or a value is invalid.
4. Map fixed-field keys (`email`, `eligible`, `can_attend`, `consent`,
   `stay_on_db`) to the matching `Respondent` top-level fields; other keys
   land in `Respondent.attributes`.

`edit_respondent_form.py` already builds a `FlaskForm` dynamically from the same
schema and does most of these coercions for the _backoffice_ case. **A lot of
its logic should be liftable.** Whether we share code via extraction or
deliberately re-implement is one of the main calls in §5 — Q2.

### 4.4 Public Flask blueprint

A new `entrypoints/blueprints/registration_public.py` (or similar) hosting the
four GET/POST routes above plus the closed page. No `@login_required`. CSRF is
on by default (global `CSRFProtect`), so the form needs the real token from
`flask_wtf.csrf.generate_csrf()` substituted in via `RenderContext.csrf_form_element`.

Feature-flag gate at the top of every route: `if not has_feature("registration_page"):
abort(404)`. Same pattern in the backoffice tab (when 610's frontend work
lands).

**Open: split the short-URL redirect into its own blueprint?** A separate
`blueprints/redirects.py` mounted at `/r/` (no prefix on the routes) keeps the
registration blueprint focused on `/register/...`, and gives us a natural
home for future short-link patterns (e.g. invite codes, share links). The
trade-off is two blueprints to register instead of one. See §6 — Q16.

### 4.5 Templates

- `templates/registration/closed.html` — a Jinja "registration is closed" page.
  Story-notes line 110 implies a single canonical URL, not per-page.
- `templates/registration/thank_you.html` — the **wrapper** template. The
  author's `thank_you_html` is inserted as a body block via `|safe`. If the
  author's HTML is empty, the wrapper falls back to a default thank-you message
  (gettext'd).
- `templates/registration/form_wrapper.html` — the wrapper around the author's
  form HTML. The author's HTML is the body; surrounding page chrome (head,
  doctype, header) belongs to the wrapper. This decouples site chrome from
  what the author edits and is the only sensible way to keep e.g. the
  `Content-Security-Policy` consistent. See §5 — Q4.

### 4.6 Where the i18n boundary sits

The author's HTML is **not** gettext'd — it's user content. The wrapper, closed
page, and fallback thank-you message all are. Same rule as the rest of the codebase.

**Future-proofing note:** a later iteration will add the ability to have
**multiple registration forms in different languages** per assembly, with
workflows for adding the translations. That work isn't in 613, but the service
layer should not assume one form per assembly. The render-time substitution
mechanism, the submission handler, the error contract — all should be keyed
off the `RegistrationPage` (or a future `RegistrationPageTranslation` row)
that produced the form HTML, not off the assembly. The current public-lookup
seams (`find_registration_page_by_url_slug`) already lean this way; the
submission handler should follow the same pattern.

### 4.7 Structured-error contract (for current and future form sources)

Per §1.5, the validator's output has to be consumable by:

- The raw-HTML path (v1) — needs a flat list to render as a summary.
- The future form-builder — needs per-field errors keyed by `field_key` so it
  can attach them next to each rendered widget.
- The future Jinja-template path — needs both: a summary block AND per-field
  error data accessible by `{{ errors['first_name'] }}` style lookups.

Suggested service-layer return shape (concrete enough to be useful, not so
concrete that we commit to wire format):

```python
@dataclass
class FieldError:
    field_key: str           # matches RespondentFieldDefinition.field_key
    reason: str              # "invalid_choice" | "wrong_type" | "missing" | ...
    message: str             # human-readable, already gettext'd

@dataclass
class RegistrationSubmissionResult:
    respondent: Respondent | None   # set on success
    errors: list[FieldError]        # empty on success
    form_errors: list[str]          # non-field-level (CSRF expiry, etc.)
    is_test: bool                   # True iff preview-token path used
```

The raw-HTML path turns `errors + form_errors` into a single `{{ form_errors_summary }}`
block via a presentation helper. The form-builder will use `errors` directly
to drive per-field annotation. The Jinja-template path will get both shapes
exposed in the template context. **The service layer's job ends at populating
`RegistrationSubmissionResult`.**

Putting `field_key` on `FieldError` (rather than a label or position) keeps the
data source-agnostic — different rendering paths can re-resolve the key to
whatever they need (label, slot index, builder component id).

---

## 5. Main implementation options

Each subsection is a real fork in the road. The recommended option is listed first.

### Q1 — Where does the POST live? **DECIDED → Option A**

**Option A (chosen): separate URL — `POST /register/<url_slug>/submit`.**

The author's HTML emits `<form action="{{ form_action }}" method="post">` and
`form_action` is filled in with the submit URL. The GET URL stays a "view
this page" URL; the POST URL is its own thing.

- Pros: trivial route dispatch; bookmarks/back-button behaviour on the GET is
  cleaner; `form_action` is explicit so we can change it later without breaking
  HTML the author hand-edited (e.g. moving to `/register/<slug>/submissions`);
  matches the example in `plan-data-service.md` §5.3.
- Cons: two URLs to keep track of; on validation failure the redirect-then-
  re-render dance is slightly awkward (or we render the form HTML directly in
  the POST handler — see Q3).

**Option B: same URL, dispatch by method.**

`POST /register/<url_slug>` does the submission; GET still renders the form.

- Pros: one URL to think about; very common Flask pattern (cf. auth's
  `register` / `login`).
- Cons: `form_action` is the same as the page URL, which is fine in practice
  but ties the two concepts together; the POST handler also has to redirect on
  failure to itself (the GET) with the form re-rendered, which is one extra hop.

**Story-notes line 34 calls this out as a deliberate question.** The story
also wonders if multiple GET URLs could share a single POST (translated forms,
A/B variants). That argues for Option A — `form_action` becomes a function
of the page, not a function of how the form arrived. This also lines up with
the future-multi-language work flagged in §4.6.

### Q2 — How much to share with `edit_respondent_form.py`? **DECIDED → Option A**

The backoffice already has a per-schema dynamic-FlaskForm builder that handles
type coercion, choice options, and bool-or-none radios. The public side needs
_similar_ logic but with three differences:

| Concern                   | Backoffice edit form                  | Public registration form                                                             |
| ------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------ |
| Form HTML source          | System renders WTForms widgets        | Author wrote raw HTML — system never renders the inputs                              |
| Field naming              | `attr_<key>` prefix to avoid clashes  | Bare `<key>` (the author owns the `name=`)                                           |
| Required fields           | Mostly optional (mid-flow edits)      | Submission must satisfy the form's contract (whatever that turns out to be — see Q9) |
| Booleans                  | Radio values are `"true"` / `"false"` | Radio values are author-controlled, but the **starter** emits `"yes"` / `"no"`       |
| Multi-select / checkboxes | Not really used                       | Checkboxes for consent/stay_on_db — values vary by HTML                              |
| `external_id`             | Already exists (it's an edit)         | Has to be generated (UUID? hashed? — see Q6)                                         |

**Option A (chosen): build a new validator helper, share only the
field-type coercion primitives.**

Extract `radio_or_none_to_bool`, `radio_to_bool`, choice-option matching into a
small `domain/respondent_field_coercion.py` (or just leave them where they
are and import from there). The two consumers — backoffice edit form and
public submission validator — each call those primitives but otherwise stay
independent.

- Pros: each form has its own validation rules (the backoffice tolerates
  partial edits; the public form has to be stricter); changes on one side
  don't risk breaking the other.
- Cons: two implementations of "walk the schema, pull values per type".

**Option B: build a public WTForms FlaskForm dynamically (mirror of
`build_edit_respondent_form`).**

- Pros: validation is a one-liner (`form.validate_on_submit()`); WTForms gives
  us per-field error structure for free.
- Cons: the author writes raw HTML — we never _render_ the WTForms widgets,
  we only use them as validators. Setting up a `FlaskForm` purely to call
  `validate()` on it is a tax. And the bool/choice coercions differ from
  the backoffice's value conventions (yes/no vs true/false).

**Option C: a small ad-hoc validator that doesn't lean on WTForms at all.**

Just a function that walks the schema, pulls each `field_key` from the
`request.form` dict, coerces, accumulates errors, and returns.

- Pros: no FlaskForm scaffolding; structured errors look exactly how we want
  them; very testable in isolation.
- Cons: re-invents some bookkeeping; if WTForms grows new features (e.g.
  Hypothesis-style validation) we don't get them for free.

The same separation-of-concerns logic from §1.5 reinforces this: the future
form builder and Jinja-template-with-error-bits paths will _also_ call the
same validator helper. Forcing all three through a FlaskForm shaped around
the raw-HTML case would be the wrong abstraction.

### Q3 — How to surface validation failures (for the raw-HTML source)?

The structured-error contract is settled in §4.7 — `RegistrationSubmissionResult`
always carries per-field errors. This question is narrower: how does the **raw
HTML** path surface those errors to the user, given that the service has no
ability to inject markup inside the author's HTML?

(The form-builder and Jinja-template paths get inline per-field errors for
free — they own the markup.)

**Option A (recommended): a render-time summary block + an additive token.**

The wrapper template renders the error summary as a `<div>` above the
author's HTML by default. Authors who want to control placement can paste
`{{ form_errors_summary }}` somewhere in their form HTML; the renderer
substitutes it with the rendered summary (or empty string when there are no
errors). Mirrors the GOV.UK error-summary pattern.

- Pros: the author's HTML stays untouched; placement is controllable but not
  required; one new author-facing token to document.
- Cons: less ergonomic than per-field errors — but those are intentionally
  out of reach for the raw-HTML path. The user has to read the summary and
  scroll up to find each field.

**Option B: redirect on failure with the errors in the session.**

POST → 302 → GET → render with summary read from session.

- Pros: classic post/redirect/get pattern; refresh-friendly.
- Cons: more moving parts (session storage); errors can become stale; doesn't
  preserve the user's typed values unless we also stash those (more session
  bytes).

**Option C: render the form directly from the POST handler (no redirect).**

POST handler renders the same template the GET would, with errors in scope.
Re-populating typed values would need yet more substitution tokens
(`{{ value:first_name }}` and so on), which Q15 from 610 explicitly rejected.

- Pros: typed values are easy to preserve since we're still in the request.
- Cons: explodes the templating contract; against the spirit of Q15.

Personal lean: **Option A** — small, additive, fits the existing design, and
the structured-error contract from §4.7 means future form-builder /
Jinja-template paths can do better-than-summary error rendering without
disturbing the raw-HTML path.

**Open: do we preserve typed values across a re-render?** §6 — Q8.

### Q4 — Form wrapper template, or render the author's HTML as the whole page? **DECIDED → Option A**

The author's HTML is the contents of `<form>...</form>`, plus optionally a
heading / paragraph above it. It is **not** a full HTML document — there's no
`<head>`, no doctype, no CSP nonce wiring.

**Option A (chosen): wrap it.**

`templates/registration/page.html` is a thin Jinja template:

```jinja
{% extends "registration/base.html" %}
{% block body %}
{{ form_html | safe }}
{% endblock %}
```

where `registration/base.html` mirrors the rest of the app's `<head>`
(security headers, CSP nonce script, locale, base CSS). `form_html` is the
already-rendered author HTML with `{{ csrf_form_element }}` and `{{ form_action }}`
substituted.

- Pros: page chrome is consistent with the rest of the site; CSP nonce works;
  i18n locale is on `<html>`; we can ship a default stylesheet that styles
  the unstyled-starter output sanely.
- Cons: the author can't override the `<head>` (e.g. a custom theme).
  Probably fine — that's a feature to defer.

**Option B: return the author's HTML as the whole response body.**

- Pros: total author control.
- Cons: no `<head>`, no CSP, no JS module loader — the author would have to
  write all of that themselves, including `<script nonce="{{ csp_nonce }}">`
  tokens that we'd need to expose. Not v1.

### Q5 — Where does the redirect target for "thank you" live? **DECIDED → Option A**

**Option A (chosen): a separate path per page, `/register/<url_slug>/thank-you`.**

After a successful POST, redirect to this URL. The GET handler loads the page,
checks visibility (so a slug change doesn't strand the page mid-redirect), and
renders `page.thank_you_html` inside a wrapper template.

- Pros: bookmarkable; refreshable without re-submitting; identical pattern to
  the form GET; survives any future "share your registration" feature.
- Cons: needs visibility logic again (do we show the thank-you page if the
  registration page is now unpublished? — see Q11).

**Option B: render the thank-you HTML directly from the POST handler, no
redirect.**

- Pros: simpler.
- Cons: F5 re-submits the form; story-notes line 18 explicitly says
  "form success is HTTP 302 to thank-you URL", which makes this a non-starter.

### Q6 — How is `external_id` generated for a submission? **DECIDED → Option A**

Every `Respondent` needs an `external_id`. The constructor strips and rejects
empty values. Existing source types use:

- `CSV_IMPORT`: id column value from the CSV.
- `MANUAL_ENTRY`: chosen by an organiser.

For a public registration submission, no organiser is on the keyboard. Options:

**Option A (chosen): generate a UUID4 string at submission time.**

`external_id = str(uuid.uuid4())`. Unique by construction. Doesn't depend on
the form having an `email` field (which it might not — for an anonymous-style
form `email` is technically optional).

- Pros: zero ambiguity; collision-resistant; works regardless of what fields
  the form has.
- Cons: a UUID isn't human-meaningful — but `external_id` is _already_ a
  machine identifier, not a display field.

**Option B: use the submitted email, if present.**

- Pros: feels meaningful when scrolling the respondent list.
- Cons: emails can be reused (one person re-submits); the form may not
  collect email at all; collides with `get_by_external_id` semantics, which
  current code uses for de-dup on CSV import.

**Option C: a per-assembly auto-incrementing sequence.**

- Pros: short, memorable.
- Cons: needs a DB sequence; race conditions; doesn't really suit our UUID-PK
  philosophy.

**Email dedup — explicitly NOT done.** Multiple submissions with the same
email address are allowed and expected. The motivating case: an elderly couple
who share an email address can both register independently; other analogous
situations exist (a parent registering on behalf of a child, etc.). Each
submission creates a fresh `Respondent` with a fresh UUID `external_id`.

### Q7 — Do we set `email` / `eligible` / `can_attend` / `consent` / `stay_on_db` from the form, or treat them all as attributes? **DECIDED → Option A**

These five names are reserved top-level `Respondent` fields. The schema's
`IN_SCHEMA_FIXED_FIELDS` says they live in the schema with `is_fixed=True`
and have hardcoded `effective_field_type`s (EMAIL or BOOL_OR_NONE).

**Option A (chosen): submissions for those keys land in their top-level
columns; everything else lands in `attributes`.**

The validator maps `email` → `Respondent.email`, `eligible` → `Respondent.eligible`
(parsed yes/no → True/False/None), `can_attend` → same, `consent` → same,
`stay_on_db` → same. Other `name=`s become `attributes[key]`. This matches
`pop_normalised` + `validate_no_field_name_collisions` in the existing
domain layer.

- Pros: keeps the eligibility/consent flags queryable as first-class columns;
  matches how `import_respondents_from_csv` works today.
- Cons: requires the validator to know which keys are fixed.

**Option B: dump everything into `attributes`.**

- Pros: simpler validator.
- Cons: breaks the eligibility/consent query patterns; doesn't match CSV.

**Absent fixed fields are expected.** Not every form will collect every one
of those five keys — a simple "register interest" form might omit `eligible`,
`can_attend`, and `stay_on_db`, leaving only `email` and `consent`. The
validator must therefore treat a _missing_ fixed field as "leave the
`Respondent` column at its default (`None` for the booleans, `""` for email)"
rather than rejecting the submission. This dovetails with the lenient
validation stance in Q9, and connects to the proposed
`for_registration_page` schema flag in §6 — Q15: that flag would let the
validator know _which_ fields the schema author intended to collect on the
form, without requiring an `is_required` migration.

### Q8 — Preserve typed values across a re-render after a validation failure?

The author's HTML emits e.g. `<input type="text" name="first_name">`. After a
validation failure, do we want the user to see the value they typed
re-populated?

**Option A (recommended): no, not in v1.**

The first version surfaces an error summary (Q3) listing what went wrong; the
user has to re-enter. Cost is paid by the user; benefit is **massive
simplification** of the templating model — we don't have to introduce a
`{{ value:foo }}` token for every field, or post-process the author's HTML to
inject `value=` attributes.

- Pros: zero new substitution tokens; the author's HTML stays untouched; ships
  in v1 timeframe.
- Cons: poor UX for users with long forms.

**Option B: yes, re-populate.**

Either by extending the substitution scheme (back to a Jinja-like model, which
Q15 explicitly rejected) or by parsing the author's HTML after-the-fact and
injecting `value=` attributes. Either is a substantial new piece of work.

Personal lean: **Option A for v1, document the limitation, revisit later.**

### Q9 — How strict is the validation? Does the submitted form have to match the schema exactly?

The author writes the HTML, the schema is the source of truth, and the two can
drift. Five sub-questions inside this one — they're tied together:

1. **Missing fields:** schema has `email` but the form omits it. Validator
   behaviour?
2. **Extra fields:** form posts `name="favourite_colour"` but the schema has
   no such field. Drop, store, or reject?
3. **Required-ness:** the schema doesn't currently mark fields as required
   (the `_render_field` helper inspects a `required_field_keys` set passed by
   the caller, but the persistent schema doesn't store that). Where do
   per-field required flags come from?
4. **Choice values:** form posts `gender=Martian` for a choice field whose
   options are {Female, Male, Non-binary or other}. Reject or accept?
5. **Type errors:** integer field gets `"abc"`. Reject definitely. But
   user-visible message?

**Option A (recommended for v1): lenient — trust the schema for _what to
collect_, ignore extras, treat all fields as optional, validate types and
choice values strictly.**

- Missing fields: stored as `None` / empty string.
- Extras: silently dropped (not stored in `attributes`).
- Required-ness: not enforced server-side until we add a `is_required`
  column to `RespondentFieldDefinition`.
- Choice values: rejected.
- Type errors: rejected.

- Pros: ships now; doesn't depend on a schema migration; safer default
  (we'd rather accept a partially-filled submission than lose it).
- Cons: a half-filled submission gets stored as a half-filled `Respondent`;
  the author has no server-side enforcement of their own form.

**Option B: strict — the schema names exactly the fields the form must collect;
required vs optional comes from a new `is_required` column.**

- Pros: server-side enforcement; matches the user's mental model of "the
  form said this is required so the server should agree".
- Cons: requires a schema migration to add `is_required`; rejects perfectly
  reasonable submissions that the author intended to make optional.

**Option C: lenient where the form expressed nothing, strict where it did.**

E.g. the form HTML has `required` attribute on `<input name="first_name"
required>`. We _cannot_ read this from inside Python because we don't parse
the HTML. So this needs a different mechanism — perhaps a new optional
"required field keys" list on the `RegistrationPage` aggregate that the author
configures alongside the HTML.

- Pros: matches author intent.
- Cons: more state to maintain; more places for divergence.

Personal lean: **Option A for v1**, but call this out in the README so users
understand what they're getting. Revisit when we add `is_required` (and the
field-editing story owns that).

### Q10 — Does the `TEST_SUBMISSION` status need transitions in or out? **DECIDED → Option B**

`ALLOWED_SELECTION_STATUS_TRANSITIONS` currently doesn't include `TEST_SUBMISSION`
because it doesn't exist yet.

**Option A: no transitions in, no transitions out.**

A test submission is a frozen artefact for verifying the form worked. It can
be **deleted** (the GDPR delete path bypasses the transition map and just
flips status to `DELETED`), but you can't promote it to POOL.

- Pros: clean; matches the intent (tests are tests).
- Cons: an organiser who genuinely wants to "save" a test as a real
  respondent has to re-submit.

**Option B (chosen): allow `TEST_SUBMISSION` → POOL.**

Real people sometimes use the unpublished-with-token URL to register early,
or an organiser realises a test submission was actually a valid registration.
The transition is one-way (no POOL → TEST*SUBMISSION) and goes through the
existing `apply_status_transition` plumbing — which **requires a comment**
that lands in the Respondent Activity history, recording \_who* promoted the
submission and _why_. That audit trail removes the "is this real or staged"
concern that Option A's cons listed.

- Pros: handles the real-person-used-preview-link case without re-submission;
  audit trail is comment-driven, not enforced-by-rule.
- Cons: very slight cognitive load — organisers need to know the promotion
  is possible.

---

## 6. Open technical questions for the detailed plan

Lower-level questions that don't change the high-level shape but need answers
before code lands. Q1, Q2, Q4, Q5, Q6, Q7, Q11, Q12, Q13 are decided;
Q8 and Q10 are agreed as written. **Still open** (Doctor Chewie is talking to
the team about these): Q3 from §5 (raw-HTML error surface), Q8 from §5
(preserve typed values), Q9 from §5 (validation strictness), §6 Q14
(`is_required`), §6 Q15 (`for_registration_page` flag), §6 Q16 (blueprint
split).

### Q1 — Naming of the new status **DECIDED → `TEST_SUBMISSION`**

`RespondentStatus.TEST_SUBMISSION` (matches plan-data-service §8 and the
screaming-snake-case convention of `POOL`, `SELECTED`, etc.). Story-notes
line 8 used `RegistrationTest`; we're overriding that for consistency with
the rest of the enum.

### Q2 — Naming the new service module **DECIDED → `registration_submission_service.py`**

Lives next to `registration_page_service.py`, not inside it. (Matches Q11
reasoning from 610: form authoring and form submission are different
concerns.)

### Q3 — Dedup on email? On `external_id`? **SETTLED**

§5 Q6 settled this: **no dedup on email** (couples sharing an address is a
legitimate use case). `external_id` is a fresh UUID per submission so there's
nothing to dedupe there either. CSV import keeps its existing
`external_id`-based dedup; manual entry keeps its existing one. Registration-
form submissions just create a new row each time.

Open (not v1): do we want to _log_ when the same email submits twice, for
audit / spam-spotting? Useful, but not blocking.

### Q4 — `RegistrationPage.thank_you_html` rendering: through `|safe` directly, or via the `RegistrationPageHtml.render` mechanism? **DECIDED → `|safe`**

Use the `|safe` filter for now — cheap, easy to extend later if we decide
we need substitution. The thank-you HTML is plain text with no substitution
tokens in v1 (plan-data-service §5.3: `render_thank_you_html(page)` returns
`page.thank_you_html` verbatim). The route passes it to a template that
does `{{ thank_you_html | safe }}`.

The seam is already there in `render_thank_you_html` — once we add tokens
later (e.g. `{{ first_name }}` in the thank-you message after the form-submission
story), we extend that function. No route-layer change needed at that point.

### Q5 — What if the slug changed between form load and submission? **DECIDED → keep it simple**

YAGNI. Submission stays slug-based. If a user lands on
`POST /register/old-slug/submit` after the slug has changed (only possible
across an unpublish-edit-republish cycle — Q6 in 610 freezes slugs while
published), they get a friendly "this form has moved" page. No hidden
page-id field; no third render-time token.

### Q6 — Should TEST_SUBMISSION respondents show up in respondent lists? **DECIDED**

- **Default respondent list:** **yes, included** — same treatment as DELETED
  rows, which already appear. The existing status filter in the main view
  lets a user narrow to "only TEST_SUBMISSION" if they want to audit test
  data.
- **Counts:** **exclude both DELETED and TEST_SUBMISSION** from the
  headline count. Detailed plan should audit the existing count helpers to
  make sure both are excluded, and add comments alongside each one explaining
  the exclusion rule (so the next person to add a status doesn't trip over it).
- **Selection runs:** **not included.** Already correct by construction —
  `is_available_for_selection()` requires `selection_status == POOL`. Pin
  this with a unit test against TEST_SUBMISSION specifically.

### Q7 — Should the submission route be CSRF-exempt? **DECIDED → keep CSRF**

CSRF stays on for the submission route. The render-time `{{ csrf_form_element }}`
token already substitutes in a real token; no `@csrf.exempt` decorator.

This is a *public* form — anonymous user, no login — so Flask-WTF's CSRF
token rides the Flask session cookie. Detailed plan must verify and pin:

- Anonymous requests get a session cookie that pins the CSRF token (the
  default when `CSRFProtect` is enabled; `generate_csrf` sets one).
- Token survives back/forward navigation.
- Token TTL behaviour (see Q10 below).

### Q8 — Rate-limiting **AGREED**

Out of scope for 613 itself, but the detailed plan must name where the hook
will go: a public POST endpoint that creates DB rows is a juicy DoS target.
`login_rate_limit_service` (Redis counters per email/IP) is the pattern to
follow; a decorator on the POST route is the most likely shape. Reserve the
seam now so the follow-up story doesn't have to retrofit it.

### Q9 — Translations

The "registration closed" template, the fallback thank-you content, and the
error-summary strings all need gettext. Pattern is well-established
(`_()` / `_l()` / `just translate-regen`). Nothing tricky here.

### Q10 — How does the GET form route handle Flask-WTF CSRF for anonymous users? **AGREED**

The form HTML the author wrote has `{{ csrf_form_element }}` substituted at
render time. The Flask-WTF CSRF middleware accepts the token from either
`csrf_token` form field or `X-CSRFToken` header. Detailed plan must verify
and pin:

1. Anonymous users get a session cookie that pins the CSRF token.
2. The token survives back/forward navigation.
3. CSRF tokens have a TTL (default 3600s in Flask-WTF) — when expired, we
   show the same form again with a friendly "your session timed out, please
   re-submit" message.

### Q11 — Visibility of `/register/<slug>/thank-you` **DECIDED → render anyway**

If the page is unpublished by the time the user lands on the thank-you URL
(e.g. organiser unpublished immediately after the submission), render the
thank-you page anyway. The submission is a fact; the thank-you is
acknowledgement of that fact. Don't redirect to `/registration-closed` in
this scenario.

### Q12 — Sequencing relative to story 610's frontend **DECIDED → parallel**

Work on both stories in parallel. The public side (613) and the backoffice
side (610's `plan-frontend.md`) don't share much code; the backoffice tab
unblocks end-to-end testing of 613. Pull them together once both are green.

### Q13 — What does a TEST_SUBMISSION respondent look like in the database? **DECIDED → same shape as a real submission**

A test submission is a Respondent row with `selection_status=TEST_SUBMISSION`,
otherwise identical to a real submission:

- `email`/`eligible`/etc. landing logic still happens (top-level columns
  populated when the corresponding form field was submitted).
- Auto-generated `CREATE` comment that explicitly says it was created via the
  preview-token URL — e.g. "Created via test submission (preview token)".
  Makes the test-ness unambiguous in the activity log, separately from the
  status field.
- `RespondentSourceType.REGISTRATION_FORM` (no separate source type — the
  status carries the test-ness).

### Q14 — Source of `RespondentFieldDefinition.is_required`

Currently, the schema has no `is_required` column. The `generate_starter_form_html`
helper takes a `required_field_keys` parameter that defaults to empty — i.e.
nothing is required in the starter today.

Options:

- Add `is_required: bool` to `RespondentFieldDefinition` (schema migration).
- Treat the four core fixed booleans (`eligible`, `can_attend`, `consent`,
  `stay_on_db`) as implicitly required and everything else as optional.
- Leave required-ness to the author's HTML (`<input required>`) and not
  enforce server-side.

This intersects with Q9 (lenient vs strict) and Q15 (`for_registration_page`
flag). Tied to the field-editing story (out of scope here). My lean: do
**not** add `is_required` in 613; accept lenient validation; punt to a
follow-up.

### Q15 — Add a `for_registration_page` flag (or scope enum) to `RespondentFieldDefinition`?

Suggested in §1.5. Concrete options:

- **A bool: `for_registration_page: bool`.** Simple; tells the validator
  "these are the keys you should expect on a submission" and tells a future
  form builder "these are the keys to offer as components". Anything not
  flagged is implicitly derived/back-office-only.
- **An enum: `field_scope: registration_page | derived_target |
confirmation_call_only | back_office_only | ...`** Richer; lets us tag
  e.g. confirmation-call fields so they don't pollute the registration form
  builder's component list.

If we ship neither, the validator falls back to the lenient behaviour in Q9
Option A (every schema field is collected if present in the form, otherwise
left empty).

Open: do we add this in 613 (it directly informs the validator), or punt to
the form-builder story and let 613 stay lenient? My lean: **add the bool now**
(cheap migration, immediately useful to the validator's error messages — we
can say "field `x` is expected but not in the form" only for flagged fields),
and let the enum evolve later. Tied to Q9 — if we want any kind of "your
form is missing a required field" check, this flag is the cleanest place to
hang it.

### Q16 — Separate blueprint for the `/r/` short-URL redirect?

Per §4.4. Two cleanly-separated blueprints (`registration_public` at
`/register/`, `redirects` at `/r/`) vs one combined blueprint.

The combined option is simpler today; the split option earns its keep if we
ever add more short-link patterns (invite codes already have short codes;
share-this-page links might want them). My lean: **one combined blueprint
for now**, split later if pressure builds. Document the URL prefix on the
single blueprint comment so a future split is mechanical.

---

## 7. Recommended overall shape (TL;DR)

Pulled together from the §5 decisions (Q1, Q2, Q4, Q5, Q6, Q7, Q10), the
§6 decisions (Q1, Q2, Q4, Q5, Q6, Q7, Q11, Q12, Q13), and the additional
context in §1.5 / §4.7. Six questions remain genuinely open and parked for
team discussion — see §6 intro.

- **New routes** on a single `registration_public_bp` blueprint (§6 Q16
  unresolved — lean: combined):
  - `GET /register/<url_slug>` — render form (or 302 to `/registration-closed`).
  - `GET /r/<short_url_slug>` — 302 to canonical.
  - `POST /register/<url_slug>/submit` — validate, create Respondent, 302 to thank-you.
    Slug-mid-flight cliff: friendly "this form has moved" page if the slug
    changed (no hidden page-id field — YAGNI).
  - `GET /register/<url_slug>/thank-you` — render `thank_you_html` in a
    wrapper. Renders even if the page has since been unpublished — the
    submission is a fact.
  - `GET /registration-closed` — static page.
- **CSRF stays on** for the submission route — anonymous session cookie
  carries the token. Detailed plan verifies anonymous-session token
  lifecycle and adds a friendly "session timed out" path for expired tokens.
- **New status** `RespondentStatus.TEST_SUBMISSION`. **No inbound
  transitions; outbound TEST_SUBMISSION → POOL is allowed** (audit via the
  required transition comment).
- **TEST_SUBMISSION row shape:** same fields as a real submission
  (top-level `email`/`eligible`/etc. land normally), `source_type =
  REGISTRATION_FORM`, plus an auto-generated `CREATE` comment that says
  "Created via test submission (preview token)" so the test-ness is visible
  in the activity log.
- **Respondent list behaviour:** TEST_SUBMISSION rows show in the default
  list (alongside DELETED), counts exclude **both** DELETED and
  TEST_SUBMISSION. Selection runs already exclude TEST_SUBMISSION by
  construction — pin with a test.
- **New service** `registration_submission_service.py` returning a
  **structured `RegistrationSubmissionResult`** (per-field `FieldError` list +
  form-level errors + `Respondent | None`). Presentation-agnostic — raw HTML
  v1 turns it into a summary, future form-builder and Jinja-template paths
  attach inline errors. See §4.7.
- **Schema-driven validator** as a pure helper (no Flask, no WTForms),
  called by the service. Strictness model is **§5 Q9 still open**; the
  current lean is lenient (missing fields → empty values; extras →
  dropped; type / choice violations → rejected). Fixed-field keys land on
  `Respondent` top-level; rest in `attributes`. **Missing fixed fields are
  accepted** — not every form will collect every fixed key.
- **`external_id`** = freshly-generated UUID per submission. **No email
  dedup** — shared-email submissions are explicit valid usage.
- **Errors** surface for the raw-HTML path is **§5 Q3 still open** —
  current lean is a server-rendered summary block injectable via an
  additive render-time token (`{{ form_errors_summary }}`).
- **Typed values across re-render** is **§5 Q8 still open** — current
  lean is "not preserved in v1".
- **Thank-you HTML rendering:** via Jinja `{{ thank_you_html | safe }}` for
  now (no substitution tokens in v1; the existing `render_thank_you_html`
  seam stays).
- **Feature-flag gate** (`FF_REGISTRATION_PAGE`) at the top of every route.
- **Wrapper templates** for form page, thank-you page, closed page —
  consistent `<head>`, CSP nonce, locale, base CSS.
- **Rate-limiting:** out of scope for 613, but the detailed plan reserves
  the seam (decorator on the POST route) so the follow-up doesn't have to
  retrofit.
- **Sequencing:** developed in parallel with 610's `plan-frontend.md`
  backoffice tab; integrated end-to-end once both are green.
- **Future-proofing:** validator + structured errors are designed for two
  more form sources (form builder, Jinja-template-for-LLM) that will land
  after 613. Multi-language registration forms will reuse the same service
  and validator, keyed off `RegistrationPage` rather than assembly.

Schema-side **still open** (§6 Q14, Q15): whether to add an `is_required`
column and/or a `for_registration_page` flag to `RespondentFieldDefinition`.
Decisions here change the validator's strictness story (§5 Q9).

Estimated rough size: ~400 LOC of new src code (route + service + validator
+ structured-error value object + status enum + possibly the schema flag),
~700 LOC of tests, three new templates, one domain enum addition, possibly
one schema migration. Note: `RespondentStatus` is stored via `EnumAsString`
(confirmed in `domain/value_objects.py` + ORM code), so **adding the new
status value does NOT need a column-type migration** — it's just a code
change. Any schema-flag migration (§6 Q15) would be the only DB change in
play.

---

## 8. References

- `docs/agent/613-registration-page-accept/story-notes.md`
- `docs/agent/610-registration-page-html/plan-data-service.md`
- `docs/agent/610-registration-page-html/plan-data-service-detailed.md`
- `docs/agent/610-registration-page-html/plan-frontend.md`
- `docs/agent/610-registration-page-html/deltas-to-fix.md`
- `docs/agent/610-registration-page-html/example-form-a-raw-html.html`
- `docs/architecture.md`
- `src/opendlp/domain/registration_page.py`
- `src/opendlp/domain/respondents.py`
- `src/opendlp/domain/respondent_field_schema.py`
- `src/opendlp/domain/value_objects.py` (`RespondentStatus`, `RespondentSourceType`)
- `src/opendlp/service_layer/registration_page_service.py`
- `src/opendlp/service_layer/respondent_service.py`
- `src/opendlp/entrypoints/edit_respondent_form.py` (parallel pattern for
  schema-driven form building)
- `src/opendlp/entrypoints/blueprints/respondents.py` (`edit_respondent`
  route — coercion + validation flow)
- `src/opendlp/entrypoints/blueprints/wellknown.py` (parallel pattern for
  a public, anonymous blueprint)
- `src/opendlp/feature_flags.py`
- `src/opendlp/entrypoints/extensions.py` (CSRF setup)
