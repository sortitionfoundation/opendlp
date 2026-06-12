# 609 — Templated Emails: Research & Design Options

> **Status:** Design discussion — nothing decided yet.
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
  + `UnitOfWork` in `service_layer/`, Flask blueprints as entrypoints.
- **Email sending already exists** — `adapters/email.py` defines
  `EmailAdapter` (abstract) with `ConsoleEmailAdapter` and `SMTPEmailAdapter`.
  Its `send_email(to, subject, text_body, html_body=None, from_email=None)`
  already takes **both** a text and an optional HTML body — so a "render to
  subject + text + html, then hand to the adapter" shape fits cleanly.
- **A repo-based templated email already exists** —
  `service_layer/email_confirmation_service.send_confirmation_email()` renders
  `emails/email_confirmation.{txt,html}` via a `TemplateRenderer` adapter. This
  is the *file-based* precedent; our new work is the *database-stored* analogue.
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
    fake in `tests/fakes.py`.
  - Alembic migration (single current head: `28ad0135cfe8`). New tables also
    need a delete line in `tests/conftest.py::_delete_all_test_data` and
    `tests/bdd/conftest.py::delete_all_except_standard_users`.
- **Registration submission flow** —
  `service_layer/registration_submission_service.submit_registration()` creates
  a `Respondent` from validated form data and returns a detached copy; the
  blueprint `entrypoints/blueprints/registration.py` calls it. This is the
  natural hook for "send the auto-reply after a successful live submission".
- **Respondent data is dynamic** — `Respondent.attributes` is a JSON dict keyed
  by assembly-specific field keys. There is *no fixed first/last-name column*.
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
  either add the table *then* and migrate the page's inline data into it, or
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
  over-engineering risk *if* mass email never lands (but it's expected to).

### Option C — Option B, with deliberate seams (recommended framing)

Same as B, but the **rendering logic**, the **context contract**, and the
**HTML→text conversion** are decoupled modules that the thin aggregate calls —
so mass email (and any later SMS channel) reuse the rendering library without
inheriting auto-reply assumptions.

**Recommendation:** **B, structured as C.** Given mass email is coming, deferring
the table mostly buys a migration later for little saving, and B is literally
"the templated email domain model" requested. The aggregate stays thin; the
reusable bits are separate.

> **DECISION — domain shape (A vs B/C):**
>
> > _Notes:_

---

## 4. Sub-decisions

### 4.1 Template scope

- **Assembly-scoped** (`assembly_id` FK) — simplest; matches "everything hangs
  off an assembly"; aids GDPR locality (cleaned up with the assembly).
- **Org/global house-style templates** reusable across assemblies — adds a
  sharing + permissions dimension.

_Lean: assembly-scoped now; revisit shared templates on demand._

> **DECISION — scope:**
>
> > _Notes:_

### 4.2 How the registration auto-reply links to a template

- **FK on the page** (`registration_pages.auto_reply_email_template_id`,
  nullable, `ON DELETE SET NULL`) — template stays purpose-agnostic and
  reusable; auto-reply trivially optional; page owns its choice.
- **`kind`/`purpose` enum on the template** (AUTO_REPLY / MASS / GENERAL) +
  "look up the AUTO_REPLY template for this assembly" — self-describing; easy to
  enforce one-auto-reply-per-assembly; UI can categorise.
- Not exclusive: FK for wiring now + an optional `kind` *label* later for UI
  grouping.

_Lean: FK for wiring now._

> **DECISION — auto-reply wiring:**
>
> > _Notes:_

### 4.3 Undefined-variable policy at render time

- **Lenient** (missing var → empty string) — a send never hard-fails because one
  optional respondent field is blank; pair with **save-time syntax validation**
  and an **editor preview against sample data**. Downside: silent typos.
- **Strict** (`StrictUndefined`, like the registration form HTML) — catches
  typos at validation, but risks runtime send failures on real-data variability
  (e.g. an optional attribute absent for one respondent).

_Lean: lenient render + syntax validation + preview. (Note: this differs from
the registration-page renderer, which is strict — worth a conscious choice.)_

> **DECISION — undefined policy:**
>
> > _Notes:_

### 4.4 Text-body generation

Derive text from the rendered HTML. Options:

- **Stdlib converter** (`html.parser`) — dependency-free, keeps domain pure;
  handles the common email cases (paragraphs, breaks, links as `text (url)`,
  list bullets). Less polished on complex HTML.
- **Add `html2text`** — battle-tested, Markdown-ish output; one new dependency.

_Lean: stdlib now; trivial to swap to `html2text` if output quality matters._

> **DECISION — text generation:**
>
> > _Notes:_

### 4.5 Validation — what and when

Mirror `RegistrationPageHtml.readiness_problems()`: at save time, check
non-empty name/subject/body and valid Jinja syntax for subject + body. Do **not**
reject "unknown" variables (the respondent attribute set is dynamic per
assembly). Optionally also size-limit the body (the registration page enforces
byte caps via config).

> **OPEN — anything else to validate at save time?**
>
> > _Notes:_

---

## 5. The context contract (the part needing most thought)

Templates render against a **documented, explicit context** built from plain
view-objects rather than raw domain models — so the sandbox stays safe, the
contract is stable, and we can document it for authors. Reliability differs by
field because respondent data is dynamic.

### 5.1 `assembly.*`

| Variable               | Source                         | Reliability                          |
| ---------------------- | ------------------------------ | ------------------------------------ |
| `assembly.title`       | `Assembly.title`               | Solid                                |
| `assembly.question`    | `Assembly.question`            | Solid                                |
| `assembly.first_assembly_date` | `Assembly.first_assembly_date` | Solid (ISO string, or empty) |
| `assembly.number_to_select`    | `Assembly.number_to_select`    | Solid                        |
| `assembly.info_url`    | **does not exist yet**         | See decision below                   |

> **DECISION — `assembly.info_url`:** add a real field to `Assembly` (small
> migration); or stub it empty (renders blank, not broken); or omit until there
> is a field to back it.
>
> > _Notes:_

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

> **DECISION — respondent name/context strategy:**
>
> > _Notes:_

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
- **Sent-email records / audit (out of scope, flagged):** the template is **not**
  a record of what was *sent*. Mass email will eventually want an
  `EmailSendRecord` (rendered body, recipient, timestamp, outcome). That
  intersects **GDPR** — rendered bodies contain PII and must be findable/blankable
  per the "right to be forgotten" strategy. Design B leaves room; we don't build
  it now.
- **SMS-later** — different body/channel; not forced into this design.

> **OPEN — do we want a minimal "sent" record even for auto-reply now (audit /
> debugging), or strictly defer?**
>
> > _Notes:_

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
  `registration_pages.auto_reply_email_template_id` FK (`SET NULL`); repo + UoW +
  fake; Alembic migration; conftest delete lines.
- Hook: registration blueprint sends the auto-reply after a successful **live**
  (non-test) submission — best-effort, never blocking the redirect.

> **OPEN — naming, field set, and whether to include `name`/a `kind` label:**
>
> > _Notes:_

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
