# 609 — Templated Emails: Implementation Plan

> **Status:** Plan for review — not yet started.
> **Date:** 2026-06-16
> **Companion doc:** [`research.md`](research.md) holds the design decisions; this
> doc turns them into an ordered, file-by-file build plan. Where this plan and the
> research doc disagree, the research doc's **DECISION** blocks win — flag it.
> **Scope (this round):** domain + persistence + service layers for creating,
> updating and sending templated emails, plus the **registration auto-reply** as
> the first consumer, a minimal **respondent send record**, a per-assembly
> **reply-to address**, and a new `reply_to` parameter on the email adapter.
> **Out of scope (this round):** add/edit UI, preview UI, mass email, mass SMS,
> `UserEmailSendRecord`, storing rendered bodies on send records.

---

## 0. Established facts from the codebase (verified)

These drove the plan; they correct a couple of stale notes in `research.md`.

- **Current single Alembic head is `974f13035459`** (verified via `uv run alembic
heads`), _not_ `28ad0135cfe8` as `research.md` §2 says. Base the new migration
  on `974f13035459`.
- **DB-stored template bodies are rendered in the domain**, not via the
  `FlaskTemplateRenderer`. `RegistrationPageHtml.render()` is the precedent: a
  module-level `SandboxedEnvironment` renders the author string directly
  (`domain/registration_page.py:26,320`). The `TemplateRenderer` adapter is only
  for _file_ templates (`emails/*.txt|.html`) and is **not needed** for the
  template body. So no `template_renderer` dependency on the new send path.
- **Email file templates live at repo-root `templates/emails/`** (e.g.
  `email_confirmation.{txt,html}`). We do **not** add files there for the template
  body (it comes from the DB), but we _may_ want a small wrapper layout later
  (deferred — see open questions).
- **`EmailAdapter.send_email(to, subject, text_body, html_body=None,
from_email=None) -> bool`** already takes both bodies and returns a bool
  (`adapters/email.py:18`). The auto-reply maps straight onto it.
- **Respondent attributes** are a JSON dict of assembly-specific keys
  (`domain/respondents.py`). `Respondent.display_name(field_names)` +
  `Assembly.name_fields` give the best-effort name; `name_fields` reads
  `respondents[0].attributes`, so for a freshly-submitted respondent we derive
  name keys from **that respondent's own `attributes`**, not via a loaded
  assembly (`domain/assembly.py:108`, `domain/respondents.py:333`).
- **`submit_registration(uow, *, url_slug, form_data)`** returns a
  `RegistrationSubmissionResult` with a **detached** `respondent`, `is_test`, and
  `is_valid` (`service_layer/registration_submission_service.py:191`). It runs
  inside `with uow:` and currently takes **no** email dependency.
- **Email-send precedent**: `send_confirmation_email(email_adapter,
template_renderer, url_generator, user, token, …)` — dependencies are **injected
  positionally**, the function takes no `uow`, and the blueprint orchestrates
  create-then-send (`service_layer/email_confirmation_service.py:87`). Blueprints
  obtain adapters via `bootstrap.get_email_adapter()` etc.
- **Tests for email services** mock the email adapter with `MagicMock`
  (no `FakeEmailAdapter` exists) and use `FakeTemplateRenderer` / `FakeURLGenerator`
  from `tests/fakes.py` (`tests/unit/test_email_confirmation_service.py:156`).

### Deliberate divergences from the `RegistrationPage` precedent

1. **One table, not two.** `RegistrationPage` splits into `registration_pages` +
   `registration_page_html_sources`. `EmailTemplate` keeps `subject` + `body_html`
   in a **single `email_templates` table** (per `research.md` §7). Simpler; no
   sibling repo/mapper.
2. **Recording-lenient undefined, not strict.** The registration renderer uses
   `StrictUndefined`. The email renderer renders leniently but **records** missed
   variables (`research.md` §4.3). New mechanism — see §2.1.

---

## 1. Build order (each numbered item ≈ one commit)

Layered bottom-up so each phase is independently testable. Tests ship **in the
same commit** as the code they cover (unit + contract per phase; integration and
e2e/BDD in their own later phase).

```
P1 domain: EmailTemplate + RenderedEmail + renderer + html_to_text + context VOs
P2 persistence: orm + mapper + repos + uow + fakes + contract tests + migration + conftest
P3 service: email_template_service (CRUD + permissions)
P4 service: send path — RespondentEmailSendRecord + send_registration_auto_reply
P5 wiring: hook auto-reply into the registration submission flow
P6 integration + BDD/e2e coverage
```

---

## 2. Phase 1 — Domain layer ✅ DONE

All plain-Python, no Flask/SQLAlchemy. Mirror `domain/registration_page.py`
style (ABOUTME header, frozen dataclasses for value objects, `create_detached_copy`).

> **Implementation note:** `RenderedEmail` lives in `email_template_render.py`
> (not `email_template.py` as sketched) to avoid a circular import; the aggregate
> re-exports it. The body byte-cap (Q3) is enforced in the Phase 3 service via a
> config getter, mirroring the registration page's `_check_size` precedent, rather
> than in the pure-domain `validation_problems()`.

### 2.1 `domain/email_template_render.py` (new) — the rendering seam

The reusable "render a DB template string against a context" module. Kept
**separate** from the aggregate (the "C" seam) so mass email/SMS reuse it.

- Module-level `SandboxedEnvironment(autoescape=True, undefined=<recording>)` —
  autoescape on, **nothing marked `safe`** (the §4.6 escaping decision; respondent
  `<script>` renders inert).
- **Recording-lenient undefined.** A custom `Undefined` subclass that renders to
  empty string (lenient) but records each missed variable name so the caller can
  log them and attach them to the send record. **Decided (Q1): option (a)** — a
  fresh environment per render with a collector list bound via closure to the
  undefined factory. The rejected alternative was (b) a `RecordingUndefined`
  appending to a `contextvars.ContextVar` list for the duration of one render.
  Rationale for (a) — explicit, no global state; per-render env construction is cheap and
  matches "the aggregate stays thin, rendering is a seam".
- `render_template_string(subject: str, body_html: str, context: Mapping) ->
RenderedEmail` — renders subject + body together, returns subject, html body,
  derived text body (via §2.2), and the sorted list of missed variable names.
- `template_syntax_problems(subject: str, body_html: str) -> list[str]` — parse
  both with the sandbox env, return human-readable syntax errors (mirror
  `RegistrationPageHtml.readiness_problems()` shape at `registration_page.py:339`).
  Do **not** reject unknown variables.

> **Decision (Q2):** the subject is plain text and is rendered with **autoescape
> off** (a non-autoescaping render of the subject string), so `&`/`<`/`>` are not
> turned into HTML entities. The **body** keeps autoescape on. The recording
> undefined still applies to both.

### 2.2 `domain/html_to_text.py` (new) — stdlib HTML→text

Per §4.4 decision (stdlib, no new dependency). A small `HTMLParser` subclass that
handles the common email cases: paragraphs/`<br>` → newlines, `<a href>` →
`text (url)`, `<li>` → bullet lines, collapse whitespace. Public:
`html_to_text(html: str) -> str`. Pure, unit-tested against representative
snippets. Explicitly **not** aiming for perfect fidelity (most recipients never
see it).

### 2.3 `domain/email_template.py` (new) — the aggregate

- `@dataclass(frozen=True) RenderedEmail`: `subject: str`, `html_body: str`,
  `text_body: str`, `missing_variables: list[str]`.
- `class EmailTemplate` (plain class, UUID id, mirrors `RegistrationPage` ctor
  style):
  - fields: `assembly_id: uuid.UUID`, `name: str`, `subject: str`,
    `body_html: str`, `id`, `created_at`, `updated_at`.
  - `render(context: Mapping) -> RenderedEmail` — delegates to
    `email_template_render.render_template_string`.
  - `validation_problems() -> list[str]` — non-empty name/subject/body + delegate
    to `template_syntax_problems`; **add a generous body byte-cap** (Q3) via a
    module/config constant, mirroring the registration page's byte-cap approach,
    to prevent runaway templates.
  - `sample_context() -> dict` — sample assembly/respondent context for previews
    and tests (the preview UI is deferred, but the method is cheap and underpins
    a "validate against sample" test).
  - `update(...)` mutators bumping `updated_at` (mirror `update_html`).
  - `create_detached_copy()`, `__eq__`/`__hash__` on id.

### 2.4 `domain/email_context.py` (new) — context view-objects

Plain view-objects built from real domain models, so the sandbox never sees raw
aggregates (per §5).

- `@dataclass(frozen=True) AssemblyContext`: `title`, `question`,
  `first_assembly_date` (ISO string or ""), `number_to_select`. **No `info_url`**
  (§5.1 decision — illustrative only).
- `class RespondentContext` (§5.2 decision — wraps a respondent):
  - `email`.
  - best-effort `first_name` / `last_name` / `full_name`, derived by matching
    normalised attribute keys (reuse `normalise_field_name` + the
    `Assembly.name_fields` precedence; derive from the respondent's own
    `attributes` so it works for a fresh submission).
  - `first_name_or_friend` convenience fallback (§4.3) → first name or "Friend".
  - `attributes` — the raw submitted dict, so authors can reference any field key.
- `build_context(assembly_context, respondent_context) -> dict` → `{"assembly":
..., "respondent": ...}`. The mapping from real `Assembly`/`Respondent` →
  these VOs lives in the **service layer** (it needs the loaded assembly); the VOs
  themselves stay in domain.

**Phase 1 tests** (`tests/unit/`): `test_email_template.py` (render happy path,
missing-variable recording, validation_problems, detached copy, escaping of a
`<script>` name), `test_html_to_text.py` (snippet table), `test_email_context.py`
(name derivation across firstname/lastname, surname, fullname, name, and the
`_or_friend` fallback; raw attributes passthrough).

---

## 3. Phase 2 — Persistence

Follow the `RegistrationPage` persistence checklist exactly, adapted to one table

- the send-record table + the FK column. Touch points (all verified above):

### 3.1 `adapters/orm.py`

- `email_templates` Table: `id` UUID PK; `assembly_id` FK → `assemblies.id`
  `ondelete="CASCADE"` (assembly-scoped, GDPR-local — §4.1); `name` String;
  `subject` Text; `body_html` Text; `created_at`/`updated_at` `TZAwareDatetime`
  default `aware_utcnow`. (No `unique` on assembly_id — many templates per
  assembly.)
- `respondent_email_send_records` Table: `id` UUID PK; `respondent_id` FK →
  `respondents.id` (FK enables one-pass GDPR blanking — §6); `email_template_id`
  nullable FK → `email_templates.id` `ondelete="SET NULL"`; `to_email` String;
  `from_email` String; `subject` Text; `outcome` `EnumAsString` (see §4.2);
  `missing_variables` JSON (list of strings); `created_at` `TZAwareDatetime`.
  **No body column this round** (§6 decision; note it as a future add).
- Import the new domain enums (e.g. `EmailSendOutcome`) at the top, as the
  registration enums are imported (`orm.py:11-37`).
- **`assemblies` table — add `reply_to_name` + `reply_to_email` columns** (Q7/Q10):
  two empty-default String columns on the existing `assemblies` Table, so an
  assembly's auto-reply (and later mass email) carry a Reply-To pointing back at the
  team. Also add the matching fields to the `Assembly` domain model
  (`domain/assembly.py`), its constructor/`create_detached_copy`, and the assembly
  repo/service update path. Follow the project's empty-string-default convention.
  **Validate `reply_to_email` on save** via `validate_email()`
  (`domain/validators.py:145`) — empty is allowed (reply-to optional), a non-empty
  value must be a valid address.

### 3.2 `adapters/database.py`

- Add `email_template`, (send-record domain module) to the import block; add
  `map_imperatively(...)` calls in `start_mappers()`. Map independently, **no ORM
  relationship** (matches the RegistrationPage comment at `database.py:210`).

### 3.3 `service_layer/repositories.py` (abstract)

- `EmailTemplateRepository(AbstractRepository)`: `add`, `get`,
  `list_by_assembly(assembly_id) -> list[EmailTemplate]`, `delete`.
- `RespondentEmailSendRecordRepository(AbstractRepository)`: `add`, `get`,
  `list_by_respondent(respondent_id) -> list[...]`.

### 3.4 `adapters/sql_repository.py`

- `SqlAlchemyEmailTemplateRepository` and
  `SqlAlchemyRespondentEmailSendRecordRepository`, querying the mapped class with
  `filter_by` (the simple RegistrationPage pattern, `sql_repository.py:455`).

### 3.5 `service_layer/unit_of_work.py`

- Imports (SQL + abstract), type annotations on `AbstractUnitOfWork`, and
  instantiation lines in `SqlAlchemyUnitOfWork.__enter__` (mirror
  `unit_of_work.py:66,134`).

### 3.6 `tests/fakes.py`

- `FakeEmailTemplateRepository`, `FakeRespondentEmailSendRecordRepository`; wire
  into `FakeUnitOfWork.__init__` (dual-assign) and `rollback()` (`fakes.py:775,810`).

### 3.7 `tests/contract/`

- Add `make_email_template` helper + parameterized `*_backend` fixtures in
  `tests/contract/conftest.py`; new `test_email_template_repo.py` and
  `test_respondent_email_send_record_repo.py` with class-grouped tests **including
  a JSON round-trip** for `missing_variables` (mirror
  `test_registration_page_repo.py`).

### 3.8 Migration — base on head `974f13035459`

- `uv run alembic revision --autogenerate -m "add email templates and send records"`.
- `upgrade()`: create `email_templates` (FK CASCADE to assemblies); create
  `respondent_email_send_records` (FK to respondents, nullable SET NULL FK to
  `email_templates`); `op.add_column("registration_pages",
auto_reply_email_template_id …)` nullable FK → `email_templates.id`
  `ondelete="SET NULL"` (lands **this round** — Q4); `op.add_column("assemblies",
reply_to_email …)` (Q7). Use `orm.TZAwareDatetime`/`orm.EnumAsString` for custom
  types (precedent: `migrations/versions/6c832644862b_*`).
- `downgrade()`: reverse order — drop the assemblies column, drop the FK column,
  then send-records, then templates. **Review the autogenerated migration by hand**
  (autogenerate misses custom type imports and SET NULL nuances).

### 3.9 conftest delete lines (both files, FK ordering)

- `tests/conftest.py::_delete_all_test_data` **and**
  `tests/bdd/conftest.py::delete_all_except_standard_users`:
  - `respondent_email_send_records` — delete **before** `respondents` and before
    `email_templates`.
  - `email_templates` — delete after `registration_pages` (the
    `auto_reply_email_template_id` FK is `SET NULL`, but deleting the templates
    while clearing everything is simplest after the pages are gone), and before
    `assemblies`.

**Note (Q4 — confirmed this round):** the new `auto_reply_email_template_id`
column on `registration_pages` is added in this round, which means also adding the
field to the `RegistrationPage` aggregate (`domain/registration_page.py` ctor +
`create_detached_copy`), the ORM mapping, and a setter on the page (plus the
service path that assigns/clears it). This is the deliberate scope widening flagged
in the original Q4.

---

## 4. Phase 3 — `service_layer/email_template_service.py` (CRUD + permissions)

Mirror `assembly_service`/`respondent_service` patterns (permission checks via
`service_layer/permissions.py`, operate through `uow`, return detached copies).

### 4.1 CRUD

- `create_email_template(uow, *, actor, assembly_id, name, subject, body_html)` —
  `can_manage_assembly` check; validate via `EmailTemplate.validation_problems()`
  (raise a service exception listing problems); add + commit; return detached.
- `update_email_template(uow, *, actor, template_id, …)` — manage check + validate.
- `get_email_template` / `list_email_templates(assembly_id)` — `can_view_assembly`.
- `delete_email_template` — manage check; rely on `SET NULL` to detach any
  registration page that referenced it.

### 4.2 `EmailSendOutcome` enum (domain)

- Small enum for the send record: `SENT` (adapter returned True) / `FAILED`
  (adapter returned False or raised). **No `SKIPPED`** — per Q5 a skipped send
  writes no record at all, so the enum only describes attempted sends. Per §6
  "outcome field — keep it simple": only the **initial handoff** is observable
  today; richer delivered/bounced states deferred to a transactional provider later.

i18n: wrap any new user-facing service strings (validation summaries, flash
messages once UI exists) in `_l()`/`_()` per CLAUDE.md. The template **body** is
author-supplied and not translated.

**Phase 3 tests** (`tests/unit/test_email_template_service.py`): create/update
validation failures, permission denials, list/get scoping.

---

## 5. Phase 4 — Send path + send record

### 5.0 Extend the email adapter with `reply_to` (Q7)

`EmailAdapter.send_email` has no reply-to parameter today (`adapters/email.py:18`).
Add an optional `reply_to: str | tuple[str, str] | None = None` to the abstract
signature and both concrete adapters:

- `SMTPEmailAdapter`: set `msg["Reply-To"] = self._format_address(reply_to)` when
  provided (alongside the existing `From`/`To` handling, `email.py:178`).
- `ConsoleEmailAdapter`: include the reply-to in the logged output.
- Existing callers are unaffected (new arg defaults to `None`). Add unit tests for
  the header being set/omitted. This is a small, self-contained change that can be
  its own commit at the head of Phase 4 (it's a precondition for §5.2).

### 5.1 Context builder (service layer)

- `build_email_context(assembly, respondent) -> dict` in the service layer (or a
  small `email_context_service`), mapping real `Assembly`/`Respondent` → the §2.4
  VOs. Keep the heuristic name-key derivation here since it needs the assembly.

### 5.2 Generic send

- `send_templated_email(uow, email_adapter, *, template, assembly, respondent) ->
RespondentEmailSendRecord`:
  1. build context, `rendered = template.render(context)`.
  2. `ok = email_adapter.send_email(to=[respondent.email], subject=rendered.subject,
text_body=rendered.text_body, html_body=rendered.html_body,
reply_to=<reply_to>)` — passing the per-assembly Reply-To (Q7/Q10; the new adapter
     parameter from §5.0). `<reply_to>` is `(assembly.reply_to_name,
     assembly.reply_to_email)` when a name is set, else `assembly.reply_to_email`,
     else `None` when the assembly has no reply-to address.
  3. if `rendered.missing_variables`: `logger.warning(...)` (the §4.3 "log misses
     now" requirement).
  4. build + persist a `RespondentEmailSendRecord` (to/from, subject,
     `missing_variables`, outcome `SENT`/`FAILED`), `uow.commit()`.
  5. best-effort: never raise to the caller on send failure — record + return.

### 5.3 Auto-reply

- `send_registration_auto_reply(uow, email_adapter, *, respondent, assembly_id) ->
RespondentEmailSendRecord | None`:
  - **return `None` and write no record** (Q5) when: the page has no
    `auto_reply_email_template_id`, the respondent has no email, or the submission
    was a **test** submission.
  - else load assembly + template, call `send_templated_email`.

**Phase 4 tests** (`tests/unit/`): `MagicMock` email adapter (per existing
precedent — no `FakeEmailAdapter`), `FakeUnitOfWork`; assert `send_email` called
with `to=[respondent.email]`, a send record persisted with the right outcome and
`missing_variables`, and the skip paths (no template / test submission / no email).

---

## 6. Phase 5 — Wire into the registration submission flow

Per the §2 decision (send logic in the **service layer**, Flask-side deps passed
in from the blueprint). The existing precedent is blueprint-orchestrates
create-then-send; we keep all logic in services and let the blueprint only wire
the adapter.

**Decided shape (Q6 — two service calls):** keep `submit_registration` unchanged;
the blueprint, after `result.is_valid`, calls
`send_registration_auto_reply(uow, email_adapter, respondent=result.respondent,
assembly_id=…)`. The blueprint adds `from opendlp.bootstrap import
get_email_adapter` and builds the adapter (as `auth.py`/`main.py` do). No business
logic lands in the blueprint — only adapter construction + one service call.
Threading `email_adapter` into `submit_registration` was rejected to avoid
coupling submission to email.

- Transaction boundary: the respondent is already committed by
  `submit_registration` before the send runs, so a send/record failure can't roll
  back the registration. The send is best-effort and must **never block the
  redirect** to the thank-you page (`registration.py:158`).

**Phase 5 tests**: extend `tests/unit`/`tests/integration` for the blueprint
route — a valid live submission triggers exactly one auto-reply send; a test
submission triggers none.

---

## 7. Phase 6 — Integration + BDD/e2e

CLAUDE.md mandates unit **and** integration **and** e2e — no skipping.

- **Integration** (`tests/integration/`): real Postgres + `ConsoleEmailAdapter`;
  create a template, submit a live registration, assert a `RespondentEmailSendRecord`
  row exists with the right fields and `SENT` outcome, and the rendered body went
  through autoescape. Mirror `tests/integration/test_email_confirmation_integration.py`.
- **BDD/e2e** (`tests/bdd/`): a feature covering "assembly with an auto-reply
  template + a live registration → respondent receives the auto-reply; test
  submissions don't". Run headless with `CI=true` (per project memory). Update the
  BDD conftest delete function for the new tables (already in §3.9).

---

## 8. Testing & quality gates

- Per-phase: `CI=true uv run pytest` for the touched areas; full `just test`
  before the integration/BDD commits.
- `just check` (mypy, deptry, ruff) before every commit. Note: imperative-mapping
  mypy rule — filter/order on **ORM table columns** (`orm.email_templates.c.…`),
  not domain attributes (CLAUDE.md).
- No new runtime dependency (stdlib HTML→text keeps `deptry` clean).

## 9. Commit strategy

- This **plan doc commits separately** from code (project memory: docs/specs
  separate from code commits). It's already on branch `609-templated-emails`.
- Then one commit per phase P1–P6 (conventional commits, `feat(609): …` /
  `test(609): …`), each green on its own.

---

## 10. Resolved decisions (from review)

All previously-open questions are now settled; the plan body above reflects them.

1. **Recording-undefined mechanism (§2.1):** ✅ per-render environment with a
   closure-bound collector (the lean) — explicit, no global state.
2. **Subject rendering (§2.1):** ✅ option (a) — subject is plain text, rendered
   with **autoescape off**; no escaping required. Body keeps autoescape on.
3. **Body size cap (§2.3):** ✅ add a generous body byte-cap constant now.
4. **`registration_pages.auto_reply_email_template_id` FK (§3.8/§3.9):** ✅ lands
   **this round** — includes touching the `RegistrationPage` aggregate/ORM/repo and
   the assign/clear service path.
5. **Skip vs record on no-send (§5.3):** ✅ return `None` and write **no** record.
   The `EmailSendOutcome` enum therefore has only `SENT`/`FAILED` (no `SKIPPED`).
6. **One service call or two (§6):** ✅ two service calls — blueprint calls
   `submit_registration` then `send_registration_auto_reply`. No coupling of
   submission to email.
7. **Reply-To address (§3.1/§5.0/§5.2):** ✅ **in this round** — add per-assembly
   `reply_to_name` + `reply_to_email` to the `Assembly` object (domain + ORM +
   migration; see Q10 for the name + validation), extend `EmailAdapter.send_email`
   with a `reply_to` parameter, and pass it on the auto-reply send.
8. **Wrapper layout for the HTML body:** ✅ send the body **as-is** this round; no
   house-style HTML shell. Revisit with the UI.
9. **`UserEmailSendRecord`:** ✅ **deferred** — build only `RespondentEmailSendRecord`
   this round (no system-user email is sent yet).

10. **Reply-To name + validation (§3.1/§5.0/§5.2):** ✅ store **both**
    `reply_to_name` and `reply_to_email` on the assembly. **Validate the email on
    save** using the existing `validate_email()` in `domain/validators.py:145`
    (Django `EmailValidator`, raises `ValueError`); an empty address is allowed
    (reply-to is optional) but a non-empty one must be valid. The send path passes
    a `(reply_to_name, reply_to_email)` tuple when a name is set, otherwise the
    bare email (the adapter's `_format_address` already handles both shapes).

_No open questions remain — ready for your review of the plan as a whole._
