# 609 — Templated Emails: Research & Design Options

> **Status:** Decisions largely settled (see the **DECISION** blocks); §8 and a
> few sub-points remain open.
> **Date:** 2026-06-12
> **Scope of this round:** domain/data + service layers for creating, updating
> and sending templated emails. Initial use case: registration auto-reply.
> **Explicitly out of scope this round:** the add/edit UI, mass-email
> implementation, and mass SMS (deferred — likely different enough to distort
> the design if forced in now).
>
> _How to use this doc:_ add your thinking inline. Decision points are marked
> **DECISION** with a `> _Notes:_` placeholder underneath. Open questions are
> marked **OPEN**.

---

## 1. Goal

Assembly managers need to author emails (subject + HTML body) whose templates
live in the **database** (not the repo), rendered per-recipient with a
documented context using Jinja syntax, e.g.:

```jinja
Dear {{ respondent.first_name }}

Thank you for registering for {{ assembly.title }} — if selected you will be
answering the question: {{ assembly.question }}

More info here ... {{ assembly.info_url }}

Yours
The Team
```

The text/plain alternative should be **generated from the HTML**, so authors
maintain only one body. The first consumer is the registration auto-reply;
mass emails to a group of respondents are coming "before too long".

---

## 2. Relevant existing architecture (what we have to build on)

Findings from the current codebase (`backend/src/opendlp/`):

- **DDD layering** (`docs/architecture.md`): plain-Python `domain/`, imperative
  SQLAlchemy mappings in `adapters/orm.py` + `adapters/database.py`, repositories
  - `UnitOfWork` in `service_layer/`, Flask blueprints as entrypoints.
- **Email sending already exists** — `adapters/email.py` defines
  `EmailAdapter` (abstract) with `ConsoleEmailAdapter` and `SMTPEmailAdapter`.
  Its `send_email(to, subject, text_body, html_body=None, from_email=None)`
  already takes **both** a text and an optional HTML body — so a "render to
  subject + text + html, then hand to the adapter" shape fits cleanly.
- **A repo-based templated email already exists** —
  `service_layer/email_confirmation_service.send_confirmation_email()` renders
  `emails/email_confirmation.{txt,html}` via a `TemplateRenderer` adapter. This
  is the _file-based_ precedent; our new work is the _database-stored_ analogue.
- **`bootstrap.get_email_adapter()`** selects console/SMTP from config; several
  blueprints already use it (`auth`, `admin`, `backoffice`, `main`).
- **Sandboxed Jinja is already used for author-supplied HTML** —
  `domain/registration_page.py::RegistrationPageHtml.render()` uses a
  `SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)` and
  validates author HTML via `meta.find_undeclared_variables` +
  `TemplateSyntaxError`. This is a strong precedent to mirror for safety.
- **Persistence patterns** (for a new aggregate, if we go that way):
  - Table in `orm.py`; `map_imperatively()` in `database.py`.
  - Abstract repo in `service_layer/repositories.py`; SQL impl in
    `adapters/sql_repository.py`; wired into `service_layer/unit_of_work.py`;
    fake in `tests/fakes.py` (the fake and SQL impl are kept honest against
    each other by the contract tests in `tests/contract/`).
  - Alembic migration (single current head: `28ad0135cfe8`). New tables also
    need a delete line in `tests/conftest.py::_delete_all_test_data` and
    `tests/bdd/conftest.py::delete_all_except_standard_users`.
- **Registration submission flow** —
  `service_layer/registration_submission_service.submit_registration()` creates
  a `Respondent` from validated form data and returns a detached copy; the
  blueprint `entrypoints/blueprints/registration.py` calls it. This service is
  the natural hook for "send the auto-reply after a successful live submission"
  — **the send belongs in the service layer, not the blueprint.** We keep
  business logic in the service layer as much as possible; where the send needs
  Flask-side knowledge (the email adapter, URL building), we pass those in as
  functions/objects from the entrypoint rather than lifting logic into the
  blueprint.
- **Respondent data is dynamic** — `Respondent.attributes` is a JSON dict keyed
  by assembly-specific field keys. There is _no fixed first/last-name column_.
  `Assembly.name_fields` heuristically picks name keys
  (firstname+lastname / firstname+surname / fullname / name) for display.
- **`Assembly` fields today:** `title`, `question`, `first_assembly_date`,
  `number_to_select`, `status`. **There is no `info_url`** (the example uses it).
- **No html→text dependency present** (`jinja2`, `markupsafe` only; no
  `html2text`/`beautifulsoup`). Generating text from HTML means either a small
  stdlib converter or adding a dependency.

---

## 3. The core fork — how to shape the domain

### Option A — library + data on the consumer

No template table. Provide reusable render/library code; the **registration
page stores its own auto-reply subject + HTML** (extra columns or a sibling
table). Send at submission.

- **Pros:** smallest footprint now; data sits next to its only consumer; no
  template-management surface to build.
- **Cons:** when mass email arrives there is no home for ad-hoc templates, so we
  either add the table _then_ and migrate the page's inline data into it, or
  duplicate the render/validate/context plumbing onto a second owner — both are
  rework. Rendering/validation/context-docs become ownerless helpers.

### Option B — first-class `EmailTemplate` aggregate

A template table (scoped to an assembly). The registration page gets a
**nullable FK** to its auto-reply template. Mass email later creates templates
the same way and sends to a respondent group.

- **Pros:** one owner for subject/body/render/validate/context; auto-reply and
  mass email share the **exact same model**, so mass email becomes "recipient
  selection + a sender" on top; optional auto-reply is just a null FK; clean CRUD
  surface for the eventual UI.
- **Cons:** more upfront (table, repo, UoW wiring, service, migration); mild
  over-engineering risk _if_ mass email never lands (but it's expected to).

### Option C — Option B, with deliberate seams (recommended framing)

Same as B, but the **rendering logic**, the **context contract**, and the
**HTML→text conversion** are decoupled modules that the thin aggregate calls —
so mass email (and any later SMS channel) reuse the rendering library without
inheriting auto-reply assumptions.

**Recommendation:** **B, structured as C.** Given mass email is coming, deferring
the table mostly buys a migration later for little saving, and B is literally
"the templated email domain model" requested. The aggregate stays thin; the
reusable bits are separate.

> **DECISION — domain shape (A vs B/C): B, structured as C** (agreed). A
> first-class `EmailTemplate` aggregate, with rendering, the context contract,
> and HTML→text conversion factored into separate seams the thin aggregate
> calls.

---

## 4. Sub-decisions

### 4.1 Template scope

- **Assembly-scoped** (`assembly_id` FK) — simplest; matches "everything hangs
  off an assembly"; aids GDPR locality (cleaned up with the assembly).
- **Org/global house-style templates** reusable across assemblies — adds a
  sharing + permissions dimension.

_Lean: assembly-scoped now; revisit shared templates on demand._

> **DECISION — scope: assembly-scoped** (`assembly_id` FK). Later we add the
> ability to **copy a template from another assembly** (gated by permissions),
> which delivers much of what org/global house-style templates would have,
> without the upfront sharing/permissions dimension.

### 4.2 How the registration auto-reply links to a template

- **FK on the page** (`registration_pages.auto_reply_email_template_id`,
  nullable, `ON DELETE SET NULL`) — template stays purpose-agnostic and
  reusable; auto-reply trivially optional; page owns its choice.
- **`kind`/`purpose` enum on the template** (AUTO_REPLY / MASS / GENERAL) +
  "look up the AUTO_REPLY template for this assembly" — self-describing; easy to
  enforce one-auto-reply-per-assembly; UI can categorise.
- Not exclusive: FK for wiring now + an optional `kind` _label_ later for UI
  grouping.

_Lean: FK for wiring now._

> **DECISION — auto-reply wiring: nullable FK on the page**
> (`registration_pages.auto_reply_email_template_id`, `ON DELETE SET NULL`). The
> `kind`/`purpose` enum is **YAGNI** until we have a stronger need — don't add
> it now.

### 4.3 Undefined-variable policy at render time

The two poles:

- **Lenient** (missing var → empty string) — a send never hard-fails because one
  optional respondent field is blank; pair with **save-time syntax validation**
  and an **editor preview against sample data**. Downside: silent typos.
- **Strict** (`StrictUndefined`, like the registration form HTML) — catches
  typos at validation, but risks runtime send failures on real-data variability
  (e.g. an optional attribute absent for one respondent).

Neither pole is forced on us — Jinja and our own context builder give us a few
ways to keep lenient rendering while still making fallbacks explicit and misses
observable:

- **Jinja `default` filter** — authors write `{{ respondent.first_name |
default('Friend') }}`. Lightweight and self-documenting in the template.
  Caveat: the bare filter only fires on _undefined_, not on an empty string; to
  also catch blanks you need the boolean form `default('Friend', true)`. Easy to
  get subtly wrong, so it's a nice-to-have rather than the primary safety net.
- **Computed convenience fields on the context** — bake the common fallbacks
  into the view-objects so authors don't have to remember filter syntax, e.g.
  `respondent.first_name_or_friend` returns the derived first name or `"Friend"`.
  We control the logic in one place, document it, and it composes with the
  best-effort name derivation in §5.2. This is the friendliest option for the
  registration-greeting case.
- **Required vs optional variables** — mark some context fields as required
  (fail validation / fail the send if absent) and the rest as optional (lenient).
  More machinery and a new concept for authors; feels like over-engineering
  until we see a real need, so park it.
- **Recording-lenient render** — render leniently, but use a custom `Undefined`
  subclass that **records every undefined access** (rather than `StrictUndefined`
  which raises, or plain `Undefined` which silently swallows). Each send then
  knows exactly which variables resolved to nothing, so we can **log the misses**
  and later **surface them on the send record** (§6) for review.

_Lean: **lenient over strict**, implemented as recording-lenient so misses are
never silent — log them, and once the send record exists, store the list of
undefined variables there. Provide convenience fields (e.g.
`first_name_or_friend`) for the friendly cases; keep the `default` filter
available to authors but don't rely on it. (Note: this differs from the
registration-page renderer, which is strict — a conscious, documented choice.)_

> **DECISION — undefined policy: recording-lenient render + convenience
> fields.** Lenient so a single blank field never aborts a send; a recording
> `Undefined` so every miss is logged now and attached to the send record once
> we build it; convenience fallbacks (`first_name_or_friend`-style) in the
> context for greetings; `default(...)` filter available but not the load-bearing
> mechanism. Required/optional marking is deferred (YAGNI for now).

### 4.4 Text-body generation

Derive text from the rendered HTML. Options:

- **Stdlib converter** (`html.parser`) — dependency-free, keeps domain pure;
  handles the common email cases (paragraphs, breaks, links as `text (url)`,
  list bullets). Less polished on complex HTML.
- **Add `html2text`** — battle-tested, Markdown-ish output; one new dependency.

_Lean: stdlib now; trivial to swap to `html2text` if output quality matters._

> **DECISION — text generation: stdlib converter for now.** Most recipients
> never see the text/plain alternative, so polish isn't worth a new dependency.
> Trivial to swap to `html2text` later if output quality ever matters.

### 4.5 Validation — what and when

Mirror `RegistrationPageHtml.readiness_problems()`: at save time, check
non-empty name/subject/body and valid Jinja syntax for subject + body. Do **not**
reject "unknown" variables (the respondent attribute set is dynamic per
assembly). Optionally also size-limit the body (the registration page enforces
byte caps via config).

> **DECISION — save-time validation:** as described above. Mirror
> `RegistrationPageHtml.readiness_problems()` — non-empty name/subject/body and
> valid Jinja syntax for subject + body; do **not** reject unknown variables (the
> respondent attribute set is dynamic per assembly); optionally size-limit the
> body via config. No further checks needed for this round.

### 4.6 Output escaping

We render with **standard Jinja autoescaping on** (matching the registration-page
renderer's `SandboxedEnvironment(autoescape=True, ...)`), and **no context value
is ever marked `safe`/`Markup`**. Every interpolated value — assembly fields and
respondent-supplied data alike — is HTML-escaped on output. So a respondent whose
name is `<script>badThing();</script>` renders as inert, escaped text, never
executable markup. Authors supply the trusted template structure; all
interpolated data is treated as untrusted.

> **DECISION — escaping: autoescape on, nothing marked safe.** Respondent and
> assembly values are always escaped; no opt-out for this round.

---

## 5. The context contract (the part needing most thought)

Templates render against a **documented, explicit context** built from plain
view-objects rather than raw domain models — so the sandbox stays safe, the
contract is stable, and we can document it for authors. Reliability differs by
field because respondent data is dynamic.

### 5.1 `assembly.*`

| Variable                       | Source                         | Reliability                  |
| ------------------------------ | ------------------------------ | ---------------------------- |
| `assembly.title`               | `Assembly.title`               | Solid                        |
| `assembly.question`            | `Assembly.question`            | Solid                        |
| `assembly.first_assembly_date` | `Assembly.first_assembly_date` | Solid (ISO string, or empty) |
| `assembly.number_to_select`    | `Assembly.number_to_select`    | Solid                        |
| `assembly.info_url`            | **illustrative example only**  | Not part of the context      |

> **DECISION — `assembly.info_url`: don't define it.** It was only an
> illustrative example in the goal sketch (§1), not a required field. We omit it
> for now; it stands as an example of the kind of `assembly.*` field that could
> be added later if a real need appears.

### 5.2 `respondent.*`

- `respondent.email` — solid.
- **Names are the hard part.** No guaranteed first/last name field exists.
  Options:
  1. **Best-effort derive** `first_name`/`last_name`/`full_name` by matching
     field keys (firstname/lastname/surname/fullname/name), **and** expose the
     raw submitted `attributes.<field_key>` so authors can reference whatever the
     assembly actually collects. Friendly for `Dear {{ respondent.first_name }}`,
     documented fallbacks, no new config.
  2. **Designated name fields** — assemblies explicitly map which schema field is
     first/last/full name. Reliable, but needs new schema config (and eventually
     UI) before usable.
  3. **Raw attributes + email only** — no name conveniences; most honest about
     the dynamic data, least friendly for greetings.

_Lean: (1) best-effort + raw attributes now; consider (2) later if managers want
guarantees._

> **DECISION — respondent name/context strategy: (1) best-effort + raw
> attributes.** A `RespondentContext` view-object wraps the respondent and
> exposes defined best-effort `first_name`/`last_name`/`full_name` (derived by
> matching field keys, reusing the `Assembly.name_fields` heuristic), the
> convenience fallbacks from §4.3 (e.g. `first_name_or_friend`), and the raw
> `attributes.<field_key>` values so authors can reference whatever the assembly
> actually collects. Designated name fields (option 2) can come later if managers
> want guarantees.

### 5.3 Timing note (why this works for both consumers)

At registration submission we have exactly the submitted attributes (great for
names/fields). Mass email later runs against stored respondents — **same context
shape**, so one contract serves both. SMS-later would likely need a different
(plain-text) body and channel, which is why it's deliberately excluded now.

---

## 6. Forward-compatibility check (does the shape hold?)

- **Mass email** = (select recipient respondents) + (pick an `EmailTemplate`) +
  (loop `render` → `send_email` per respondent context), probably with Celery
  batching. The aggregate, context builder, renderer and send helper all already
  serve it; the genuinely-new pieces are recipient selection + batching.
- **Sent-email records / audit:** the template is **not** a record of what was
  _sent_. We build a **minimal** send record this round (see decision below) to
  capture render errors/warnings; the **rendered body is deferred**. When the
  body is added it intersects **GDPR** — rendered bodies contain PII and must be
  findable/blankable per the "right to be forgotten" strategy, which is exactly
  why the record carries a respondent FK.
- **SMS-later** — different body/channel; not forced into this design.

> **DECISION — yes, build a minimal sent record now.** Even for the auto-reply
> alone we want a record so we can capture **render errors/warnings** (the
> undefined-variable misses from §4.3) for review later.
>
> Shape: **split by recipient type** into two tables rather than one polymorphic
> table:
>
> - **`UserEmailSendRecord`** — emails to system users (assembly managers,
>   organisers, etc.).
> - **`RespondentEmailSendRecord`** — emails to respondents, with an **FK to the
>   respondent**.
>
> The split is driven by **GDPR**: when a respondent asks to be forgotten we find
> every `RespondentEmailSendRecord` by that FK and blank the PII fields in one
> pass. We **cannot** rely on `ON DELETE CASCADE` here — our strategy is to blank
> fields and keep the row (stable ID), not delete it — so a clean, queryable FK
> is what makes the blanking tractable.
>
> **Body storage — skip for now.** Whether to store the full rendered body is
> still under discussion with the team. For this round we store **subject +
> metadata only** (to/from, timestamp, outcome, and the undefined-variable list
> from §4.3), which also keeps the GDPR surface smaller. **Note for later:** we
> may want to add the rendered body for audit/debugging once the team decides.
>
> **Outcome field — keep it simple for now.** Today we hand off to a local SMTP
> relay that forwards the mail, so we only observe whether the **initial handoff**
> succeeded, not later delivery steps. Record just that. Later, if we send via a
> transactional email provider's API, we may get richer outcome data (delivered /
> bounced / etc.) worth modelling — not designed now.

---

## 7. Proposed shape if we go with B/C (for reference, not committed)

Sketch only — concrete names/fields up for discussion:

- `domain/email_template.py` — `EmailTemplate` aggregate (`assembly_id`, `name`,
  `subject`, `body_html`, timestamps); `render(context) -> RenderedEmail`;
  `validation_problems()`; `sample_context()` for previews; detached-copy.
- `domain/html_to_text.py` — pure HTML→text helper (or a dependency).
- Context view-objects (`AssemblyContext`, `RespondentContext`) + a service-layer
  builder mapping real `Assembly`/`Respondent` → context.
- `service_layer/email_template_service.py` — CRUD (create/update/get/list/
  delete with `can_manage_assembly`/`can_view_assembly` checks), auto-reply
  assignment, `send_templated_email`, `send_registration_auto_reply`.
- Persistence: `email_templates` table; nullable
  `registration_pages.auto_reply_email_template_id` FK (`SET NULL`); a minimal
  `respondent_email_send_records` table (respondent FK, subject + metadata +
  undefined-variable list, no body for now — see §6) and its `user_…` sibling
  if/when needed; repo + UoW + fake; Alembic migration; conftest delete lines.
- Hook: the **submission service** sends the auto-reply after a successful
  **live** (non-test) submission — best-effort, never blocking the redirect.
  Flask-side dependencies (email adapter, URL building) are passed in from the
  blueprint so the logic stays in the service layer (see §2).

> **OPEN — naming and field set.** The `kind`/`purpose` label is **YAGNI** (see
> §4.2) — don't include it. Concrete table/field/attribute names and the exact
> field set are still open for discussion.

---

## 8. A WIP code spike exists (for reference only)

An exploratory implementation of the B/C shape was drafted, then set aside for
this design session. It lives on branch **`claude/youthful-carson-tkv0al`** as a
single WIP commit (not reviewed, not final, may be reworked or discarded). It can
be used to sanity-check feasibility but is **not** the proposal — this document
is. Decisions here drive whatever gets built.

> **OPEN — anything above you want to reframe, or options I've missed?**
>
> > _Notes:_
