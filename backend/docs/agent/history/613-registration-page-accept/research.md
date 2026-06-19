# Story 613 — Accept Registration Form Submissions

**Branch:** `613-registration-page-accept`
**Date:** 2026-05-18
**Status:** Research only — open for review before a detailed plan is written.

**Updated 2026-05-22** — realigned against the now-evolved 610 work. Since this
doc was first drafted, 610 (a) replaced `is_published`/`preview_token` with a
`RegistrationPageStatus` enum (`TEST / PUBLISHED / CLOSED`) and retired the
preview token completely (610 Q17), (b) moved form rendering to a **Jinja
sandbox** with a helper API (`value` / `checked` / `selected` / `field_errors` /
`form_errors`), and (c) **took over the public GET routes** (form render,
short-URL redirect, `/registration-closed`). The Doctor Chewie review comments
that drove this revision are folded in: Q3 and Q8 are now settled on the Jinja
round-trip; Q9 leans strict (Option B); Q14 adds `is_required`; Q15 adds the
`for_registration_page` bool; §6 Q16 (blueprint split) is out of scope.

**Updated 2026-06-02** — §5 Q1 (POST URL shape) flipped from Option A
(`/register/<slug>/submit`) to **Option B** (method-dispatched on
`/register/<slug>`) to match what landed during implementation. See Q1 for the
rationale; `form_action` is still an explicit substitution so a future story
can re-introduce a separate submit URL if multi-language / A/B variants need
it.

**Updated 2026-06-08** — §6 Q14/Q15 revised. The two-boolean plan
(`is_required` + `for_registration_page`) is replaced by a **single
`FieldOnRegistrationPage` enum** (`NO` / `YES_OPTIONAL` / `YES_REQUIRED`) on
`RespondentFieldDefinition`, which makes the illegal combination "not on the
form but required" unrepresentable. Bool fields on the public form render as
**checkboxes** (`YES_REQUIRED` → must be checked, e.g. `consent`/`eligible`;
`YES_OPTIONAL` → optional, e.g. `stay_on_db`), so a form submission never
produces `None` for them. The **back-office edit-registrant form is unchanged**
— it keeps full True/False/None handling for bool fields, because off-form
fields and rows from CSV upload / manual entry can legitimately be `None`. The
never-None behaviour is specific to the public registration form, not to the
domain field. See Q14 for the full rationale.

This document captures what's already in place from story 610, what story 613 actually
adds, the main implementation options for each meaty decision, and the open technical
questions that need answering before a detailed plan can be cut.

---

## 1. What's already in place (from story 610)

### 1.1 Domain layer

`src/opendlp/domain/registration_page.py`:

- `RegistrationPage` aggregate per assembly with `url_slug`, `short_url_slug`,
  `status` (`RegistrationPageStatus`: `TEST` / `PUBLISHED` / `CLOSED`),
  `source_type` (HTML only for now), `thank_you_html`, and an append-only
  `activity` audit log (`list[RegistrationPageActivity]`). Slugs freeze once the
  page has _ever_ been published — `slugs_frozen` ← `has_ever_been_published()`,
  derived from the activity log (610 Q6/Q16). Status transitions are `publish`
  (TEST→PUBLISHED), `unpublish` (PUBLISHED→TEST), `close` (PUBLISHED→CLOSED) and
  `reopen` (CLOSED→PUBLISHED); each appends a matching activity entry.
- **No preview token.** A `TEST` page loads publicly at its slug with **no
  token** — the `preview_token`, the `?token=` link, the `PREVIEW` visibility
  state and the `REGENERATE_TOKEN` action were all retired (610 Q17).
  `is_publicly_loadable()` is True for `TEST` and `PUBLISHED` with a non-empty
  `url_slug`, False for `CLOSED` and slugless pages.
- `RegistrationPageHtml` child holding the author's HTML. `render(RenderContext)`
  runs the HTML through a **Jinja sandbox** (`SandboxedEnvironment`, `autoescape`,
  `StrictUndefined`) exposing a small helper API (below). `readiness_problems()`
  parses the template and insists both `{{ csrf_form_element }}` and
  `{{ form_action }}` are referenced. (This replaced the original flat
  two-token string substitution.)
- `RenderContext` carries `csrf_form_element` and `form_action` plus the
  **validation-round-trip state**: `values` (re-populate inputs), `errors`
  (per-field messages keyed by `field_key`), and `form_level_errors`
  (cross-field). All three default to empty, so a fresh GET renders the form
  unchanged and a failed POST re-renders it with values + errors in place.
- Render helpers exposed to author HTML (see `RegistrationPageHtml.render`):
  `value(key)`, `checked(key, val)`, `selected(key, val)`, `field_errors(key)`,
  `has_error(key)`, `first_error(key)`, `form_errors()`. **This helper API is the
  seam story 613 feeds its validation results into** — the canonical shape is
  `docs/agent/610-registration-page-html/example-form-d-jinja-helpers.html`. See
  §4.7 and §5 — Q3.
- `HtmlSource` protocol so future source types (form builder, A/B variants,
  translations) plug in without touching the page aggregate.
- `generate_starter_form_html(fields, required_field_keys=())` — pure helper that
  emits an unstyled HTML form from the assembly's `RespondentFieldDefinition` set,
  **with the Jinja helper calls already wired in** (`value(...)` on inputs,
  `checked(...)`/`selected(...)` on options, `field_errors(...)` after each field,
  `form_errors()` at the top). `name=` attributes match `field_key`; choice fields
  are emitted as radios/select; the boolean fixed fields (`eligible`,
  `can_attend`, `consent`, `stay_on_db`) become yes/no radios via
  `effective_field_type`.
- `RegistrationPageActivity` — frozen dataclass (`text`, `author_id`,
  `created_at`, `action`) serialised as a JSON list on the page row.
- `SlugError(field, reason, message)` carries structured info so a UI can attach
  the right error to the right slug input.
- `RegistrationPageNotReady` carries a `.problems: list[str]`.

### 1.2 Service layer

`src/opendlp/service_layer/registration_page_service.py` exposes:

- **Management** (all require `can_manage_assembly`): `create_registration_page`,
  `get_registration_page`, `get_registration_page_with_source`,
  `update_registration_page` (slugs), `update_thank_you_html`,
  `update_registration_page_html`, `publish_registration_page`,
  `unpublish_registration_page`, `close_registration_page`,
  `reopen_registration_page`, `generate_starter_form_html`.
- **Public, unauthenticated**: `find_registration_page_by_url_slug`,
  `find_registration_page_by_short_url_slug`, `resolve_visibility(page)`
  → `RegistrationPageVisibility(page, state)` where `state` is a
  `RegistrationPageVisibilityState` (`LIVE` / `TEST` / `CLOSED` / `NOT_FOUND`);
  `.is_visible` is True for `LIVE` and `TEST`, `.is_test` True only for `TEST`.
  Plus `get_page_and_source_for_render(uow, page)` and `render_thank_you_html(page)`.

The public functions are intentionally read-only seams for the route layer to plug
into. `resolve_visibility` is pure — no token argument, no DB hit; it dispatches on
`page.status`. **Story 613 reads `visibility.is_test` (equivalently `page.status`)
to decide whether a submission becomes `TEST_SUBMISSION` or `POOL`.**

### 1.3 Adapters + tests

ORM tables `registration_pages` and `registration_page_html_sources` exist;
migration is applied; repositories (`RegistrationPageRepository`,
`RegistrationPageHtmlRepository`) live on `AbstractUnitOfWork`; full contract
tests and unit tests are green (last verified 2026-05-15: 2764 passed).

### 1.4 What's NOT in place yet (the gap 613 sits in)

- The **public GET side is now 610's**, not 613's: the `GET /register/<url_slug>`
  form-render route, the `GET /r/<short_url_slug>` redirect, visibility
  resolution, and the canonical `/registration-closed` page are delivered by
  610's frontend work (see COMMENT in §2). 613 no longer owns the read path.
- No **POST** submission route, no submission service, no schema-driven validator
  turning a POST body into a `Respondent`. **This is the bulk of 613.**
- No "thank-you" page route rendering `page.thank_you_html` after a successful POST.
- `RespondentStatus.TEST_SUBMISSION` doesn't exist yet. Currently the enum has
  POOL / SELECTED / CONFIRMED / WITHDRAWN / DELETED.
- `RespondentSourceType.REGISTRATION_FORM` **does** exist already.
- `FF_REGISTRATION_PAGE` is gated by 610's public routes; 613's new POST and
  thank-you routes must gate the same way. The service layer intentionally
  doesn't check the flag — it stays a route-layer concern.
- No `FieldOnRegistrationPage` enum on `RespondentFieldDefinition` yet (proposed
  here — see §6 Q14; supersedes the earlier two-bool `is_required` /
  `for_registration_page` plan).

### 1.5 The bigger picture — the HTML source is just the first source type

The HTML authoring path that 610 ships is only the **first** way users will
create registration forms. Note that what 610 actually shipped is **not** raw,
inert HTML: the author's HTML is run through a Jinja sandbox and the generated
starter already wires in the helper API (`value`, `checked`, `selected`,
`field_errors`, `form_errors`). So the "author-edits-Jinja-with-error-bits"
path described in early drafts as a _future_ option is, in effect, the **v1**
path — a styling pass (by hand or via an LLM) round-trips because the
"Jinja-ness" is confined to attribute values and one-liner helper calls, not
block structure.

One further path is still anticipated, and 613's submission handler is intended
to support it too:

- **A form builder** — expected to be the most common option. A library of
  components (text input, radio group, dropdown, consent checkbox, ...) keyed
  off the fields the user said they need for targets and for contacting
  respondents. The author orders elements, groups them into sections, adds an
  introduction. The system writes most of the HTML and provides default
  styling. Because the system owns the markup, the form builder can show
  errors **next to** the relevant inputs.

Implications for story 613:

- The submission service **must return structured validation results** — a data
  shape any presentation layer can consume (the v1 Jinja path renders them via
  `field_errors(key)` / `form_errors()`; a future form builder attaches them to
  its rendered widgets). Don't pre-bake HTML inside the service. See §4.7.
- The respondent field schema grows a `FieldOnRegistrationPage` enum (`NO` /
  `YES_OPTIONAL` / `YES_REQUIRED`) so the validator and the form builder both
  know which fields belong on a registration form (anything `!= NO`) and which
  are required. A richer *scope* enum (`registration_page`, `derived_target`,
  `confirmation_call_only`, ...) for the non-form contexts remains a separate,
  later axis. See §6 — Q14 (**decided: add the enum**) and Q15.

---

## 2. What story 613 actually has to do

Boiled down from `story-notes.md`, and trimmed for the fact that **610 now owns
the public GET routes** (the form render, the short-URL redirect, visibility
resolution and `/registration-closed` — these were originally listed here but
moved to 610; see the COMMENT below). What is left for 613:

1. **POST** to the form action (`POST /register/<url_slug>` — same URL as the
   GET, dispatched by method) — validate
   the body against the assembly's `RespondentFieldDefinition` set. On success:
   - Create a `Respondent` with `source_type=REGISTRATION_FORM`.
   - Status is **POOL** when the page is `PUBLISHED`, or the new
     **TEST_SUBMISSION** value when the page is in `TEST` status (read off
     `page.status` / `visibility.is_test` — there is no preview token any more).
   - **302 redirect** to a "thank you" page that renders `page.thank_you_html`
     (or a Jinja fallback if it's blank).
   - On failure → re-render the form through the **Jinja sandbox** with the
     submitted values and per-field errors carried in `RenderContext` (settled
     in §5 — Q3/Q8). No bespoke error-injection mechanism.
2. **GET** `/register/<url_slug>/thank-you` — render `page.thank_you_html` in a
   wrapper after a successful submission.
3. **Feature flag** 613's new routes behind `FF_REGISTRATION_PAGE`, matching the
   gate 610 already applies to the GET routes.

> **COMMENT (resolved):** the GET routes — `GET /register/<url_slug>` and
> `GET /r/<short_url_slug>`, together with visibility resolution and the
> `/registration-closed` page — are now being done in the 610 story, so they are
> no longer 613's responsibility. The original full-list version of this section
> is preserved in git history. 613 picks up at the POST.

The status-driven render itself (PUBLISHED → form, TEST → form + test banner,
CLOSED → 302 to `/registration-closed`) is 610's `resolve_visibility` dispatch
(plan-data-service §5.4). 613 only consumes the `is_test` outcome at submit time.

Out of scope per the story notes:

- Bot protection.
- Field editing inside the registration page.
- Date-based publish/unpublish.
- QR code rendering.

Out of scope per `plan-data-service.md` §8 (still relevant):

- Rate-limiting.
- Thank-you page substitution (e.g. `{{ respondent_name }}`).
- What happens to submissions when a page is unpublished and republished after a
  slug change (mitigated by the "slugs frozen once ever published" rule).

---

## 3. Big-picture shape

```
# delivered by 610:
GET  /register/<url_slug>            → render form HTML (or 302 closed)
GET  /r/<short_url_slug>             → 302 to /register/<url_slug>
GET  /registration-closed            → static "closed" page

# delivered by 613:
POST /register/<url_slug>            → create Respondent, 302 to thank-you
GET  /register/<url_slug>/thank-you  → render thank_you_html
```

The POST shares the GET URL and is dispatched by method (§5 — Q1, Option B). The
author's HTML still emits `<form action="{{ form_action }}" method="post">` so
`form_action` stays an explicit substitution — if a future translation/A/B
variant story needs multiple GET URLs sharing one POST, the seam is preserved
and we can re-point `form_action` without disturbing author HTML.

The thank-you URL needs to be sticky enough that the redirect target works even
after a slug change — see §6 — Q5.

---

## 4. New code expected (rough sketch, subject to the open questions)

### 4.1 Domain

- Add `RespondentStatus.TEST_SUBMISSION` to `domain/value_objects.py`. Update
  `ALLOWED_SELECTION_STATUS_TRANSITIONS`: no **inbound** transitions
  (TEST_SUBMISSION rows are only created from the form), but **outbound
  TEST_SUBMISSION → POOL is allowed** so an organiser can promote a real
  person who submitted while the page was in `TEST` status. The transition
  requires a comment (the existing rule) so the activity history records who
  promoted it and why. See §5 — Q10.
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
) -> RegistrationSubmissionResult:
    """Validate the submission against the assembly's field schema, create a
    Respondent if valid (status from page.status — POOL when PUBLISHED,
    TEST_SUBMISSION when TEST), and return a RegistrationSubmissionResult the
    route can either redirect on (success) or re-render the form with (errors +
    submitted values)."""
```

No `preview_token` argument — the token was retired (610 Q17); the service reads
`page.status` to decide POOL vs TEST_SUBMISSION. No `user_id` argument: the public
route is anonymous. The return shape is in §4.7; on failure the route feeds
`result.values` + `result.errors` straight into a `RenderContext` (§5 — Q3).

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

610 already added the public blueprint hosting the GET routes
(`/register/<url_slug>`, `/r/<short_url_slug>`, `/registration-closed`). 613
adds the two new routes to the **same** blueprint: `POST
/register/<url_slug>` (method-dispatched on the GET URL) and
`GET /register/<url_slug>/thank-you`. No
`@login_required`. CSRF is on by default (global `CSRFProtect`), so the form
needs the real token from `flask_wtf.csrf.generate_csrf()` substituted in via
`RenderContext.csrf_form_element` (610 already does this for the GET render; the
re-render after a failed POST does the same).

Feature-flag gate at the top of the new routes: `if not
has_feature("registration_page"): abort(404)` — matching the gate 610 applies to
its GET routes.

(The earlier "split the short-URL redirect into its own blueprint?" question —
§6 Q16 — is **out of scope**: see the COMMENT there.)

### 4.5 Templates

610 owns the GET-side templates — the "registration is closed" page and the
form wrapper (`<head>`, doctype, CSP nonce, locale, base CSS around the
rendered author HTML). 613 **re-uses the form wrapper** for the failed-POST
re-render (same template, now with `values`/`errors` populated in the
`RenderContext`), and adds one new template:

- `templates/registration/thank_you.html` — the **wrapper** for the thank-you
  page. The author's `thank_you_html` is inserted as a body block via `|safe`.
  If the author's HTML is empty, the wrapper falls back to a default thank-you
  message (gettext'd). See §6 — Q4.

(Q4 in §5 — "wrap the author's HTML vs render it as the whole page" — was decided
Option A and is now realised by 610's form wrapper.)

### 4.6 Where the i18n boundary sits

The author's HTML is **not** gettext'd — it's user content. The wrapper, closed
page, and fallback thank-you message all are. Same rule as the rest of the codebase.

**Future-proofing note:** a later iteration will add the ability to have
**multiple registration forms in different languages** per assembly, with
workflows for adding the translations. That work isn't in 613, but the service
layer should not assume one form per assembly. The Jinja render mechanism,
the submission handler, the error contract — all should be keyed off the
`RegistrationPage` (or a future `RegistrationPageTranslation` row) that produced
the form HTML, not off the assembly. The current public-lookup seams
(`find_registration_page_by_url_slug`) already lean this way; the submission
handler should follow the same pattern.

### 4.7 Structured-error contract (for current and future form sources)

The validator's output has to be consumable by:

- The v1 Jinja path — `RenderContext.errors` (per-field, keyed by `field_key`)
  drives `field_errors(key)`; `RenderContext.form_level_errors` drives
  `form_errors()`; `RenderContext.values` drives `value`/`checked`/`selected`.
  **This already exists in 610's `RenderContext` and helper API** — the
  submission service just has to populate it.
- The future form-builder — needs per-field errors keyed by `field_key` so it
  can attach them next to each rendered widget. Same `field_key`-keyed shape.

Suggested service-layer return shape (concrete enough to be useful, not so
concrete that we commit to wire format) — note it carries the **submitted
values** as well as errors, so the route can re-populate the form on failure
(see §5 — Q8):

```python
@dataclass
class FieldError:
    field_key: str           # matches RespondentFieldDefinition.field_key
    reason: str              # "invalid_choice" | "wrong_type" | "missing" | ...
    message: str             # human-readable, already gettext'd

@dataclass
class RegistrationSubmissionResult:
    respondent: Respondent | None   # set on success
    values: dict[str, str]          # submitted values, for re-population
    errors: list[FieldError]        # empty on success; per-field
    form_errors: list[str]          # non-field-level (CSRF expiry, etc.)
    is_test: bool                   # True iff page.status == TEST
```

On a failed POST the route maps `result.values` → `RenderContext.values`,
groups `result.errors` by `field_key` → `RenderContext.errors`, and
`result.form_errors` → `RenderContext.form_level_errors`, then re-renders the
**same** form HTML through the Jinja sandbox. **The service layer's job ends at
populating `RegistrationSubmissionResult`** — it never produces HTML.

Putting `field_key` on `FieldError` (rather than a label or position) keeps the
data source-agnostic — the Jinja helpers re-resolve the key, and a future form
builder can resolve it to a slot index or component id.

> **QUESTION (Doctor Chewie):** `RenderContext.errors` is typed
> `dict[str, list[str]]` (a field can have several messages), whereas
> `RegistrationSubmissionResult.errors` is a flat `list[FieldError]`. The route
> bridges the two by grouping on `field_key`. Are you happy with that two-shape
> split (flat list out of the service, grouped dict into the renderer), or would
> you rather the service hand back the grouped `dict[str, list[str]]` directly so
> the route is a pure pass-through? The flat list keeps `reason` codes around for
> logging/i18n; the dict is less to translate at the boundary.

---

## 5. Main implementation options

Each subsection is a real fork in the road. The recommended option is listed first.

### Q1 — Where does the POST live? **DECIDED → Option B** (as implemented)

**Option B (chosen): same URL, dispatch by method.**

`POST /register/<url_slug>` does the submission; GET still renders the form.
The author's HTML emits `<form action="{{ form_action }}" method="post">` and
`form_action` is filled in with the same `/register/<url_slug>` URL.

- Pros: one URL to think about; standard Flask pattern (cf. auth's `register` /
  `login`); failed-POST re-render happens in the POST handler itself with no
  redirect needed (matches the round-trip in §5 — Q3 / Q8).
- Cons: `form_action` is the same as the page URL, so a future
  multi-GET / shared-POST design (translations, A/B variants — §4.6) would
  need to either re-point `form_action` or introduce a separate submit URL at
  that point. The substitution seam is still there, so it's a one-edit change
  if/when that story lands.

**Option A: separate URL — `POST /register/<url_slug>/submit`.**

The GET URL stays a "view this page" URL; the POST URL is its own thing.

- Pros: `form_action` independent of the page URL up-front; multiple GET URLs
  sharing one POST works without re-pointing anything later; matches the
  original example in `plan-data-service.md` §5.3.
- Cons: two URLs to keep track of; nothing in v1 actually needs the
  decoupling, so YAGNI bites.

**Note:** earlier drafts of this research recommended Option A on
future-proofing grounds, and the colleague implementing 613 went with Option B
(simpler, no extra URL). After review (2026-06-02), we accepted the
implementation: the `form_action` substitution preserves enough of the seam
that the multi-language / A/B story can re-introduce a separate submit URL if
it actually needs one.

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

### Q3 — How to surface validation failures? **DECIDED → standard POST re-render through the Jinja helpers**

This question — originally framed around a "raw HTML can't carry inline errors"
constraint — is **settled by the Jinja-sandbox rendering 610 shipped**. The
author's form HTML is a Jinja template, and the generated starter already wires
in the per-field error and re-population helpers (see
`docs/agent/610-registration-page-html/example-form-d-jinja-helpers.html` and
`RegistrationPageHtml.render` in `domain/registration_page.py`):

- `field_errors(key)` renders a system-owned `<p class="error">…</p>` block per
  message next to the field.
- `form_errors()` renders cross-field / form-level errors (CSRF expiry, etc.).
- `value(key)`, `checked(key, val)`, `selected(key, val)` re-populate inputs,
  radios, checkboxes and `<select>`s.

**Approach (decided):** a plain server-side form round-trip — **no** redirect on
failure, **no** summary-token scheme, **no** session stash. On a failed POST the
handler builds a `RenderContext` from the submission result
(`values` + `errors` + `form_level_errors`) and re-renders the _same_ form HTML.
On a fresh GET every helper returns `""` / no-op, so the page is visually
identical to the unsubmitted form. This is the standard "redisplay with errors
and the submitted values" pattern.

This supersedes the earlier Option A/B/C analysis (render-time summary token /
session redirect / token-per-value), all of which existed only to work around
the assumption that the author's HTML was inert. It isn't — it's Jinja. The
earlier options are preserved in git history.

A GOV.UK-style error summary at the top of the form is still possible and
desirable (accessibility), but it's now just another helper/partial driven by
the same `errors` data — not a separate mechanism. Whether the v1 starter emits
a summary block is a frontend-polish call, not an architectural one.

Typed-value preservation is therefore **yes** in v1 — see §6 — Q8 (also settled
via these helpers).

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

**A fixed field that the form doesn't collect is expected.** Not every form
collects every one of those five keys — a simple "register interest" form might
omit `eligible`, `can_attend`, and `stay_on_db`, leaving only `email` and
`consent`. The validator uses `FieldOnRegistrationPage` (§6 — Q14) to know which
fields the form is meant to collect: a fixed field set to `NO` is simply not
expected, and its `Respondent` column keeps its default (`None` for the
booleans, `""` for email). The required/optional distinction is the same enum's
`YES_REQUIRED` vs `YES_OPTIONAL`. So `NO` → ignored; `YES_REQUIRED` → must be
present (non-bool) / checked (bool checkbox); `YES_OPTIONAL` (e.g. `stay_on_db`)
→ may be blank / left unchecked.

### Q8 — Preserve typed values across a re-render after a validation failure? **DECIDED → yes, via the Jinja helpers**

Yes — we re-populate. The premise of the original "Option A: no, not in v1"
(that re-population would need a new `{{ value:foo }}` token scheme or
after-the-fact HTML parsing) no longer holds: **610 ships exactly the helpers
that make this free.** The generated starter already emits
`value="{{ value('first_name') }}"`, `{{ checked('eligible', 'yes') }}`,
`{{ selected('geo_bucket', 'Glasgow') }}` etc., and `RenderContext.values`
carries the submitted values back into them on the re-render.

So the flow is the standard form round-trip from Q3: failed POST → re-render
the same form HTML with `RenderContext.values` populated → text/email/number/
textarea inputs show what the user typed, radios/checkboxes keep their
selection, `<select>` keeps its option. No new tokens, no HTML post-processing.

(This is what makes Q3 a plain redisplay rather than a post/redirect/get — the
submitted values are still in scope on the failed POST.)

### Q9 — How strict is the validation? **DECIDED → Option B (strict), backed by `FieldOnRegistrationPage`**

Doctor Chewie's steer: **Option B — almost all fields are required.** The only
standard exception is the "stay on database" checkbox. So the validator enforces
required-ness server-side, sourced from the new `FieldOnRegistrationPage` enum
added in §6 — Q14 (a field is required iff `YES_REQUIRED`), plus the
fixed-boolean checkbox rules captured there.

The author writes the HTML, the schema is the source of truth, and the two can
drift. Five sub-questions, now answered:

1. **Missing required field:** schema has `email` (or any `YES_REQUIRED` field)
   but the form omitted/blanked it → **reject** with a per-field "this is
   required" error. Missing `YES_OPTIONAL` field → stored as `None` / empty string.
2. **Extra fields:** form posts `name="favourite_colour"` with no matching
   schema field → **silently dropped** (not stored in `attributes`). The schema
   is the source of truth for what to collect.
3. **Required-ness:** comes from `RespondentFieldDefinition.on_registration_page`
   (§6 — Q14). A field is required iff `YES_REQUIRED`. For bool fields,
   `YES_REQUIRED` renders a **checkbox that must be checked** (so `eligible` /
   `can_attend` / `consent` must be truthy), while `YES_OPTIONAL` (e.g.
   `stay_on_db`) is an optional checkbox. A field set to `NO` is not on the form
   at all. See Q14.
4. **Choice values:** form posts `gender=Martian` for a choice field whose
   options are {Female, Male, Non-binary or other} → **rejected**.
5. **Type errors:** integer field gets `"abc"` → **rejected**, with a
   user-visible per-field message (rendered via `field_errors`).

This depends on the §6 Q14 schema addition (the `FieldOnRegistrationPage` enum),
which Doctor Chewie has approved adding in 613. The earlier "Option A lenient for
v1, defer the migration" lean is therefore **dropped** — we are doing the
migration in this story.

> **QUESTION (Doctor Chewie):** for a required _choice_ field that the visitor
> simply leaves unselected (no radio chosen, `<select>` left on the "— Please
> choose —" blank), I'll treat that the same as "missing required" → reject with
> the field's required-error. Sound right? (It's the obvious reading of "almost
> all fields required", just flagging because choice fields have a legitimate
> empty state in the generated dropdown.)

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

Real people sometimes register while the page is still in `TEST` status (it
loads publicly at its real slug), or an organiser realises a test submission was
actually a valid registration.
The transition is one-way (no POOL → TEST*SUBMISSION) and goes through the
existing `apply_status_transition` plumbing — which **requires a comment**
that lands in the Respondent Activity history, recording \_who* promoted the
submission and _why_. That audit trail removes the "is this real or staged"
concern that Option A's cons listed.

- Pros: handles the real-person-registered-during-TEST case without
  re-submission; audit trail is comment-driven, not enforced-by-rule.
- Cons: very slight cognitive load — organisers need to know the promotion
  is possible.

---

## 6. Open technical questions for the detailed plan

Lower-level questions that don't change the high-level shape but need answers
before code lands. As of the 2026-05-22 revision, the §5 questions that were
parked are now resolved: Q3 (errors surface via the Jinja helpers — standard
redisplay), Q8 (typed values re-populated via the same helpers), and Q9
(strict, Option B). In §6, Q1, Q2, Q4, Q5, Q6, Q7, Q11, Q12, Q13 are decided;
Q8 and Q10 are agreed as written; Q14 and Q15 are decided by Doctor Chewie's
comments — **revised 2026-06-08 to a single `FieldOnRegistrationPage` enum**
replacing the earlier two-bool (`is_required` + `for_registration_page`) plan;
Q16 (blueprint split) is **out of scope**. Nothing in §5/§6
remains genuinely open except the two clarifying questions flagged inline (in
§4.7 and §5 — Q9) and the dedicated **§9 — Questions for Doctor Chewie** at the
end of this doc.

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
`POST /register/old-slug` after the slug has changed (only possible before the
page has ever been published — Q6 in 610 freezes slugs permanently once any
PUBLISH has happened), they get a friendly "this form has moved" page. No
hidden page-id field; no extra render-time token.

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

This is a _public_ form — anonymous user, no login — so Flask-WTF's CSRF
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
- Auto-generated `CREATE` comment that explicitly says it was submitted while
  the page was in `TEST` status — e.g. "Created via test submission (page in
  TEST status)". Makes the test-ness unambiguous in the activity log, separately
  from the status field.
- `RespondentSourceType.REGISTRATION_FORM` (no separate source type — the
  status carries the test-ness).

### Q14 — How is "on the registration page" + "required" represented? **REVISED 2026-06-08 → single `FieldOnRegistrationPage` enum (supersedes the two-bool plan)**

The earlier decision (this question + Q15) was to add **two booleans** to
`RespondentFieldDefinition`: `is_required` (default `True`) and
`for_registration_page`. Doctor Chewie has since revised this: **replace both
booleans with a single enum**, so the illegal state "not on the form but
required" (`for_registration_page=False, is_required=True`) is unrepresentable.

**Decision: add `on_registration_page: FieldOnRegistrationPage` to
`RespondentFieldDefinition`** (schema change, done in 613). The enum:

- **`NO`** — not on the registration page at all. The validator neither expects
  nor stores it; a fixed boolean in this state keeps its `Respondent` default
  (`None` for the bools, `""` for email). `NO` is also the "is this fixed
  boolean even in use?" signal — `NO` means not in use, so the question that the
  old two-bool plan needed a second flag (or a separate mechanism) to answer is
  now answered by the single enum.
- **`YES_OPTIONAL`** — on the form, may be left unsatisfied.
  - non-bool field: rendered as its normal input, may be left blank.
  - bool field: rendered as a **checkbox**, may be left unchecked → records
    `True` if checked, `False` if not. This is the `stay_on_db` / "keep my
    details so you can contact me about future events" case.
- **`YES_REQUIRED`** — on the form, the user must actively satisfy it.
  - non-bool field: must have a value (blank → reject).
  - bool field: rendered as a **checkbox with `required`** — must be checked
    (i.e. must be `True`); unchecked is a validation failure, not a recorded
    `False`. This is the `eligible` / `can_attend` / `consent` ("I am eligible",
    "I consent to you keeping my data") case.

**Why an enum over two bools:**

- Removes the illegal `(for_registration_page=False, is_required=True)` state by
  construction.
- `YES_REQUIRED` maps cleanly onto the HTML `required` attribute for **both**
  text inputs (must fill) and checkboxes (browsers enforce "must be checked"),
  so one uniform rule — "the user must actively satisfy this field" — covers
  both rendering cases.
- "Must be checked" becomes a **per-field property** (`YES_REQUIRED` on any bool
  field) rather than a rule hardcoded into the validator for the three fixed
  consent fields. A custom "I agree to the code of conduct" checkbox just works
  with no special-casing.

**Render bool fields as checkboxes, not radios.** The current starter
(`_render_yes_no_radios` in `domain/registration_page.py`) renders bool fields
as yes/no radios with no enforcement — which cannot express "must be True" (a
required radio only forces *a* pick, allowing "No"). The starter generator must
route bool types to a **checkbox** renderer (with `required` when
`YES_REQUIRED`).

**Invariants that follow from checkbox rendering:**

- A bool field on the form is binary — it can **never** produce `None`. `None`
  survives only for fields set to `NO` (not on the form), where it correctly
  means "not collected / unknown".
- The "must be True-or-False, never None" case therefore collapses into
  `YES_OPTIONAL` for a checkbox — there is no separate state to model.
- The one case the enum cannot express — a bool that must be *answered* but
  where *either* answer is valid (a yes/no screening question feeding targets) —
  is modelled as a **`CHOICE_RADIO`** with explicit yes/no options, not a BOOL.
  Rule: **BOOL ⇒ checkbox; required-but-either-answer ⇒ CHOICE.**

**The back-office edit-registrant form is NOT changed.** It keeps full
True / False / None (three-state) handling for the bool fields. Fields that are
not on the registration form — and rows created by CSV upload or manual entry —
can legitimately be `None`, and the back-office must continue to represent and
edit that. The checkbox-only / never-None behaviour is specific to the **public
registration form**, not to the domain field or the back-office editor.

**Enforce server-side regardless of HTML.** The `required` attribute is a
browser hint only; the validator independently rejects an unchecked
`YES_REQUIRED` bool and a blank `YES_REQUIRED` non-bool.

**Defaults.** `is_derived=True` fields default to `NO` — they are computed,
never collected on the form. New custom fields default to `YES_REQUIRED` (most
are about-you target fields). `generate_starter_form_html` derives its
`required_field_keys` (and which fields to emit at all) from this enum rather
than taking a separately hand-maintained parameter.

(Enum name `FieldOnRegistrationPage` per Doctor Chewie's proposal; value set
`NO` / `YES_OPTIONAL` / `YES_REQUIRED`.)

### Q15 — A `for_registration_page` flag (or scope enum)? **REVISED 2026-06-08 → folded into the Q14 enum; richer scope enum still deferred**

The standalone `for_registration_page: bool` is **dropped**. Its job — "is this
field on the registration form, so the validator should expect it / the form
builder should offer it?" — is now carried by `on_registration_page != NO`
(Q14). One field, no redundancy, no illegal combinations.

The richer alternative floated earlier — a `field_scope` enum
(`registration_page | derived_target | confirmation_call_only |
back_office_only | ...`) — is still **not** done now. Note it addresses a
*different axis* from the Q14 enum: Q14 answers "on the registration form, and
required?"; a future `field_scope` would answer "which of several non-form
contexts does this field belong to?". The two can coexist later (a field is `NO`
on the registration form but `confirmation_call_only` for scope). Adding the
Q14 enum now does not block that.

### Q16 — Separate blueprint for the `/r/` short-URL redirect? **OUT OF SCOPE**

> **COMMENT (Doctor Chewie):** this is now out of scope. 610 already owns the
> public blueprint (including the `/r/` redirect), so there is no blueprint-split
> decision left for 613 — its new routes (the POST on `/register/<slug>` and the
> `/thank-you` GET) just join the existing blueprint. The earlier "one combined
> vs two blueprints" analysis is moot and kept only in git history.

---

## 7. Recommended overall shape (TL;DR)

Pulled together from the §5 decisions and the §6 decisions, as revised
2026-05-22 against the evolved 610 work. The previously-parked questions are now
settled; only the two inline questions (§4.7, §5 Q9) and §9 remain for Doctor
Chewie.

- **610 owns the public GET side** — `GET /register/<url_slug>` (form render),
  `GET /r/<short_url_slug>` (302 to canonical), visibility resolution, and
  `GET /registration-closed`. 613 adds **two routes to the same blueprint**:
  - `POST /register/<url_slug>` (method-dispatched on the GET URL, §5 Q1
    Option B) — validate, create Respondent, 302 to thank-you. On failure,
    re-render the same form HTML through the Jinja sandbox with submitted
    values + per-field errors. Slug-mid-flight cliff: friendly "this form
    has moved" page if the slug changed (only possible pre-first-publish;
    no hidden page-id field — YAGNI).
  - `GET /register/<url_slug>/thank-you` — render `thank_you_html` in a wrapper.
    Renders even if the page has since been unpublished/closed — the submission
    is a fact (Q11).
- **Submission status from `page.status`** — `PUBLISHED` → `POOL`, `TEST` →
  `TEST_SUBMISSION`. No preview token (retired by 610 Q17); 613 reads
  `visibility.is_test`.
- **CSRF stays on** for the submission route — anonymous session cookie carries
  the token. Detailed plan verifies anonymous-session token lifecycle and adds
  a friendly "session timed out" path for expired tokens.
- **New status** `RespondentStatus.TEST_SUBMISSION`. **No inbound transitions;
  outbound TEST_SUBMISSION → POOL is allowed** (audit via the required
  transition comment).
- **TEST_SUBMISSION row shape:** same fields as a real submission (top-level
  `email`/`eligible`/etc. land normally), `source_type = REGISTRATION_FORM`,
  plus an auto-generated `CREATE` comment saying it was submitted while the page
  was in `TEST` status, so the test-ness is visible in the activity log.
- **Respondent list behaviour:** TEST_SUBMISSION rows show in the default list
  (alongside DELETED), counts exclude **both** DELETED and TEST_SUBMISSION.
  Selection runs already exclude TEST_SUBMISSION by construction — pin with a
  test.
- **New service** `registration_submission_service.py` returning a **structured
  `RegistrationSubmissionResult`** (`Respondent | None` + submitted `values` +
  per-field `FieldError` list + form-level errors + `is_test`). Presentation-
  agnostic — the v1 Jinja path renders it via `field_errors()`/`form_errors()`/
  `value()`; a future form builder attaches errors to its widgets. See §4.7.
- **Schema-driven validator** as a pure helper (no Flask, no WTForms), called by
  the service. Strictness is **strict (§5 Q9, Option B)**: required-ness from
  the new `on_registration_page` enum (`YES_REQUIRED`); missing required →
  reject; extras → dropped; type / choice violations → rejected. Fixed-field
  keys land on `Respondent` top-level; rest in `attributes`. Bool fields render
  as checkboxes: a field set to `NO` is not expected; `YES_REQUIRED` bools
  (`eligible`/`can_attend`/`consent`) must be checked; `YES_OPTIONAL` bools
  (`stay_on_db`) may be left unchecked. A form checkbox never yields `None`
  (§6 Q14).
- **`external_id`** = freshly-generated UUID per submission. **No email dedup** —
  shared-email submissions are explicit valid usage.
- **Errors + typed-value round-trip** (§5 Q3, Q8) — standard server re-render
  through the Jinja sandbox: failed POST → `RenderContext` carries `values`,
  `errors`, `form_level_errors` → helpers re-populate inputs and render
  per-field/form errors. No summary token, no session stash, no PRG.
- **Thank-you HTML rendering:** via Jinja `{{ thank_you_html | safe }}` for now
  (no substitution tokens in v1; the existing `render_thank_you_html` seam
  stays).
- **Feature-flag gate** (`FF_REGISTRATION_PAGE`) on 613's new routes, matching
  610's gate on the GET routes.
- **Templates:** 610 owns the form wrapper and closed page (re-used by 613 for
  the failed-POST re-render); 613 adds the thank-you wrapper.
- **Schema additions in 613:** `RespondentFieldDefinition.on_registration_page`
  (a `FieldOnRegistrationPage` enum — `NO` / `YES_OPTIONAL` / `YES_REQUIRED`,
  §6 Q14), replacing the earlier two-bool plan. One schema migration. The
  back-office edit-registrant form is unchanged (still True/False/None for bool
  fields).
- **Rate-limiting:** out of scope for 613, but the detailed plan reserves the
  seam (decorator on the POST route) so the follow-up doesn't have to retrofit.
- **Sequencing:** developed in parallel with 610's `plan-frontend.md` backoffice
  tab; integrated end-to-end once both are green.
- **Future-proofing:** validator + structured errors are designed for the
  future form-builder source too. Multi-language registration forms will reuse
  the same service and validator, keyed off `RegistrationPage` rather than
  assembly.

Estimated rough size: ~400 LOC of new src code (route + service + validator +
structured-error value object + status enum + the `FieldOnRegistrationPage`
enum + schema field), ~700 LOC of tests, one new template (thank-you wrapper),
two domain enum additions (`RespondentStatus.TEST_SUBMISSION` and
`FieldOnRegistrationPage`), one schema migration (the `on_registration_page`
column). Note: `RespondentStatus` is stored via `EnumAsString` (confirmed in
`domain/value_objects.py` + ORM code), so **adding the new status value does NOT
need a column-type migration** — it's just a code change. The
`RespondentFieldDefinition.on_registration_page` column (Q14) is the DB change in
play.

---

## 8. References

- `docs/agent/613-registration-page-accept/story-notes.md`
- `docs/agent/610-registration-page-html/plan-data-service.md`
- `docs/agent/610-registration-page-html/plan-data-service-detailed.md`
- `docs/agent/610-registration-page-html/plan-frontend.md`
- `docs/agent/610-registration-page-html/deltas-to-fix.md`
- `docs/agent/610-registration-page-html/example-form-a-raw-html.html`
- `docs/agent/610-registration-page-html/example-form-d-jinja-helpers.html`
  (the shape 613's error/value round-trip renders through — see §5 Q3/Q8)
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

---

## 9. Questions for Doctor Chewie

Captured here (rather than asked in chat) per your request. Each is also flagged
inline at the relevant section.

1. **Error shape at the service/route boundary (§4.7).**
   `RegistrationSubmissionResult.errors` is a flat `list[FieldError]` (keeps
   `reason` codes for logging/i18n); `RenderContext.errors` is a grouped
   `dict[str, list[str]]`. The route bridges them by grouping on `field_key`.
   Happy with that split, or should the service hand back the grouped dict so
   the route is a pure pass-through?

I'm happy with that split.

2. **"Fixed boolean in use" mechanism (§6 Q14).** You said the fixed booleans
   need "some way to select whether they are actually used". My lean is to
   **reuse the new `for_registration_page` flag** (Q15) — a fixed boolean is
   "in use" iff it's flagged for the registration page — rather than add a
   separate per-field toggle. Agree, or do you want a dedicated mechanism?

**RESOLVED (2026-06-08):** subsumed by the single `FieldOnRegistrationPage`
enum (Q14). A fixed boolean is "in use" iff `on_registration_page != NO` — no
separate flag or mechanism needed.

3. **"Must be checked" enforcement (§6 Q14).** For `eligible`/`can_attend`/
   `consent` when in use, "must be checked" is stronger than an HTML `required`
   attribute gives for a single checkbox. I plan to enforce it in the
   **validator** (server-side reject) _and_ mark `required` in the generated
   HTML (browser hint). Sound right?

**RESOLVED (2026-06-08):** yes — these render as **checkboxes** (not radios), so
`YES_REQUIRED` → HTML `required` on the checkbox (which browsers enforce as
"must be checked") *and* a server-side validator reject. Doctor Chewie confirmed
the checkbox rendering for these fields; the back-office edit form keeps
True/False/None and is unchanged.

4. **Unselected required choice fields (§5 Q9).** A required radio with nothing
   chosen, or a `<select>` left on the blank "— Please choose —" option → I'll
   treat as "missing required" and reject. Confirm that's the intended reading
   of "almost all fields required".

5. **Scope sanity-check (§2, §4.4).** I've taken your "the GETs are now in 610"
   comment to mean 610 owns the form-render route, the `/r/` redirect, visibility
   resolution **and** the `/registration-closed` page — leaving 613 with the
   POST on `/register/<slug>` and `GET /register/<slug>/thank-you` plus the
   submission service / validator / `TEST_SUBMISSION` status / schema
   additions. If the thank-you route or the closed page actually landed in 610
   too, say so and I'll move them out of 613's scope.

The stories have been combined now, so all of 613's scope is now in 610.
