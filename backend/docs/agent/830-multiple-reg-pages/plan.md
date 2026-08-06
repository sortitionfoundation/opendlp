# Multiple registration pages per assembly — plan

**Issue:** 830
**Branch:** `830-multiple-reg-pages`
**Date:** 2026-08-06
**Status:** All decisions recorded (§2). Backend phases 1–5 and 7 are fully
specified and ready to build. Phase 6 (backoffice UI) is **blocked** on Q6/Q7 only,
which Chewie is taking to the team — no other open questions.

---

## 1. Goal and current state

### Goal

An assembly should be able to have **more than one registration page**, so that organisers can:

- run **A/B tests** of different page designs / copy (typically driven by different
  printed invite materials, each carrying its own URL and QR code), and
- offer the **same assembly in different languages** — up to 20+ pages for
  EU-wide jobs, all feeding a single pool of respondents.

### What exists today

The model is `Assembly (1) —— (0..1) RegistrationPage`, and the "at most one" is
enforced in four places:

| Layer | Where | What enforces one-per-assembly |
|---|---|---|
| DB | `orm.py:601` `registration_pages` | `assembly_id` column has `unique=True` |
| Repository | `repositories.py:572` / `sql_repository.py:506` | `get_by_assembly_id() -> RegistrationPage \| None` |
| Service | `registration_page_service.py` | every function takes `assembly_id` and resolves it to *the* page; `create_*` raises `ValueError` if a page exists |
| Routes | `backoffice_registration.py` | every backoffice route is `/assembly/<uuid:assembly_id>/registration/...` |

Everything hanging off a page is already **page-scoped**, which is good news —
these need no schema change:

- `registration_page_html_sources.registration_page_id` (the form HTML)
- `registration_pages.thank_you_html`
- `registration_pages.auto_reply_email_template_id`
- `registration_pages.url_slug` / `short_url_slug` / `status` / `activity`

Everything **assembly-scoped** stays shared across pages:

- `respondent_field_definitions` (the field schema — what data is collected)
- `email_templates` (the pool of templates; the *assignment* is per page)

The **public routes are already slug-scoped**
(`/register/<url_slug>`, `/r/<short_url_slug>`), so multiple live pages fall out
almost for free once the DB constraint goes. The public path resolves
`slug -> page -> page.assembly_id`, which is exactly the direction we want.

The real work is: the backoffice (which assumes a single page everywhere), asset
scoping, respondent provenance, and the auto-reply lookup.

---

## 2. Decisions

### 2.1 Settled

| # | Question | Decision |
|---|---|---|
| Q1 | Does the app split A/B traffic? | **No — independent URLs.** Each variant gets its own URL and QR code, printed on different invite materials. A future single-URL splitter would be a separate redirect-only page; explicitly out of scope. |
| Q2 | Are images/PDFs shared across pages? | **Yes — move assets to assembly scope.** Logos are the same for every variant; re-uploading per variant is unacceptable friction. |
| Q3 | Record which page a respondent came through? | **Yes** — nullable `registration_page_id` FK on `respondents`. Reporting scope: **submission count per page on the list view**; leave real analytics for later. |
| Q4 | Can variants differ in which fields they ask? | **No.** Field schema stays assembly-scoped. Variants differ in layout, copy, styling and language only. |
| Q5 | `language` column on a page? | **Yes**, optional, default `""`, used as a label in this work. **No** `Accept-Language` auto-redirect — separate story. |
| Q8 | Deleting a page? | **Allowed only while never-published and with no respondents.** Otherwise offer `close`. |
| Q9 | Cap on pages per assembly? | **No cap.** 20+ happens (EU-wide jobs), but is rare — under 5% of assemblies will exceed 3 pages. Support it; don't optimise the UI for it. |
| Q10 | Auto-reply template on duplicate? | **Deep-copy the template**, so each variant gets its own editable copy ready to translate. Seed a default template only for an assembly's *first* page. |
| Q11 | Bulk state change over mixed states? | **Best-effort with a report.** Move every page that can move, skip the rest, and tell the organiser exactly what happened and why. Never all-or-nothing. |

Consequences of Q1 worth stating plainly: **no new cookie, no change to
`docs/personal-data.md`.** The A/B measurement is the `registration_page_id` on
the respondent row, which is server-side and carries no device identifier.

**New requirement (from Chewie's comment on Phase 6):** the UI needs controls to
move **all** of an assembly's registration pages between states (test / publish /
close) in one action. Semantics settled by Q11; design in §3.4.

### 2.2 Deferred — Chewie is discussing with the team

These block **Phase 6 only**. Every backend phase is agnostic to the outcome:
both UI shapes need page-id-addressed services, so Phases 1–5 and 7 can be built
and merged before these land.

**Q6 — backoffice URL / UI shape.**
(a) a list page at `/assembly/<id>/registration` plus a per-page editor at
`/assembly/<id>/registration/<page_id>`, versus (b) keep one URL with a
page-picker and `?page=<uuid>`.

> **Note:** I briefly argued that 20+ pages made (a)'s list view need sorting and
> filtering. Chewie's follow-up settles it — under 5% of assemblies exceed 3 pages,
> and the 20-page case is allowed to be a bit awkward. So design the list for 2–3
> rows: a plain table, no filtering, no grouping. It just has to stay *usable*
> rather than pleasant at 20, which a plain table is. That also keeps (b)'s
> dropdown viable, so the choice between (a) and (b) is back to being about URL
> shape and bookmarkability, not scale.
>
> The one thing that does change with page count is the **bulk state controls**
> (§3.4) — those matter most precisely when there are 20 pages to close.

**Q7 — does the Assembly Details tab show a "primary" page?**

> **Note:** my original recommendation was (a) "just list them all", on the grounds
> that listing 2–3 pages is fine. Chewie's 5% figure confirms 2–3 is the normal
> case, so **(a) stands** — I withdraw the intermediate worry that 20 pages made it
> untenable. All it needs is a graceful cap: list them all, and if there are more
> than ~5, show the first few plus "and N more" linking to the registration tab.
> That costs nothing and needs no `is_primary` column. Choosing `is_primary` later
> is one small migration, so there is still no penalty for deferring — do not add
> the column speculatively.

### 2.3 Q11 in detail — bulk state changes are best-effort

Worth recording *why*, because the implementation has to resist the temptation to
simplify it back into all-or-nothing.

An assembly's pages will routinely sit at different points: some TEST, some
PUBLISHED, one half-built with no URL slug. Two of the three transitions are also
**not single operations** — reaching PUBLISHED means `publish()` from TEST but
`reopen()` from CLOSED, and both run the readiness check, which a half-built page
will fail. So a mixed set is the normal case, not an edge case.

Best-effort means: move every page that can move, skip the rest, and report
per page — *"4 published, 1 already published, 1 not published: the Welsh page has
no URL slug."* One unfinished draft must never block the other nineteen from going
live on launch day.

The guard rails are unaffected: no page skips its state machine, no page publishes
while failing readiness, and each moved page records its own activity entry noting
it was part of a bulk action.

Two consequences that follow directly, and are easy to get wrong:

- **The flash message must be a real summary**, naming the pages that didn't move
  and why. A generic "Done" would be actively harmful here: the organiser would
  believe registration is fully open when one language is still dark.
- **No wrapping transaction rollback on partial failure.** The successes commit.
  That is the point of best-effort, and it means the service function must not
  raise on the first page that can't move.

---

## 3. Design

### 3.1 Shape

```
Assembly (1) ──── (0..N) RegistrationPage
                            ├── name              NEW  (e.g. "English", "Variant A")
                            ├── language          NEW  (e.g. "en", "es"; optional label)
                            ├── url_slug          unique under /register/  (unchanged)
                            ├── short_url_slug    unique under /r/         (unchanged)
                            ├── status            TEST / PUBLISHED / CLOSED (per page)
                            ├── thank_you_html                             (per page)
                            ├── auto_reply_email_template_id               (per page)
                            ├── activity                                   (per page)
                            └─(1)── RegistrationPageHtml (form_html)       (per page)

Assembly (1) ──── (0..N) RegistrationImage      MOVED from page to assembly (Q2)
Assembly (1) ──── (0..N) RegistrationDocument   MOVED from page to assembly (Q2)
Assembly (1) ──── (0..N) RespondentFieldDefinition   unchanged, shared by all pages
Assembly (1) ──── (0..N) EmailTemplate               unchanged; assignment is per page

Respondent.registration_page_id  NEW, nullable — which page it came in through
```

Many pages of one assembly may be `PUBLISHED` at the same time — that is the
whole point, and no code assumes otherwise once the lookups are fixed.

### 3.2 Naming and slugs

- `name` is required and unique within the assembly (a human handle for the
  editor UI; never shown publicly).
- Slug auto-generation changes from `slugify(assembly.title)` to
  `slugify(assembly.title) + "-" + suffix`, still passed through
  `generate_unique_url_slug` for the `-2`, `-3` fallback.
- **The suffix should be the `language` code when set, falling back to the
  slugified `name`.** `_slugify` strips everything outside `[a-z0-9-]`, so
  non-ASCII page names mangle badly — "Español" → `espaol`, "Čeština" → `etina`.
  With 20+ EU language variants that is not a corner case, it is the normal
  path. `climate-assembly-cs` beats `climate-assembly-etina`.
- Slug freeze rules are unchanged and remain per page.

### 3.3 How many pages to design for

**Design for 2–3 pages. Support 20 without falling over.** Under 5% of assemblies
will exceed three registration pages, so the 20-page EU case is allowed to be a
bit awkward in the UI — it must work, not delight.

Concretely, that means:

- **No** sorting, filtering or grouping controls on the page list. A plain table.
- **No** pagination anywhere. Twenty rows on one page is fine.
- **Do** use a single grouped query for the submission counts —
  `count_by_registration_page(assembly_id) -> dict[UUID, int]` — rather than a
  per-page count in a loop. Not for performance at three pages; because it is the
  same amount of code either way, and the loop version is the kind of N+1 that
  quietly survives into a report screen later.
- **Do** make duplicate prominent. Not because 20 pages demand it, but because
  even the 2–3 page case is almost always "the same page again, tweaked" — an A/B
  variant or a translation. It is the natural creation path for this feature.
- Bulk state controls (§3.4) are the one thing that genuinely earns its keep at
  high page counts, and they're cheap at low ones too.

### 3.4 Bulk lifecycle controls

Organisers need to move **all** of an assembly's registration pages between
states in one action (Chewie's requirement): everything live on launch day,
everything closed when registration ends.

Three bulk actions, mirroring the per-page ones:

| Bulk action | Per-page effect | Notes |
|---|---|---|
| Publish all | `publish()` from TEST, `reopen()` from CLOSED | both run the readiness check |
| Unpublish all | `unpublish()` from PUBLISHED | back to TEST |
| Close all | `close()` from PUBLISHED | |

Design constraints:

- **The domain state machine is not bypassed.** A bulk action is a loop over
  per-page domain calls, not a bulk `UPDATE`. A page that can't make the
  transition is skipped, never forced.
- **Readiness still applies.** Publishing a page with no URL slug fails for that
  page exactly as it does today.
- **Each page records its own activity entry**, with text marking it as part of a
  bulk action, so the audit trail stays per-page and doesn't lie about how the
  change was made.
- **Best-effort, never all-or-nothing** (Q11). The service function returns a
  per-page outcome and does not raise when a page can't move. Successes commit.

The return type is the load-bearing bit — get it right and the route and template
are trivial:

```python
class BulkStatusOutcome(Enum):
    MOVED = "MOVED"        # transitioned
    SKIPPED = "SKIPPED"    # already in the target state, or not in a source state for it
    FAILED = "FAILED"      # tried and refused — readiness problems

@dataclass(frozen=True)
class BulkStatusResult:
    page_id: uuid.UUID
    page_name: str          # so the caller can name it without a second lookup
    outcome: BulkStatusOutcome
    problems: list[str]     # readiness problems when FAILED, else empty
```

`page_name` is carried deliberately: the flash message has to name the pages that
didn't move, and making the route re-fetch them to build that sentence is how the
summary quietly degrades into "Done".

### 3.5 What stays exactly as it is

- The public route contract: `/register/<url_slug>`, `/r/<short>`,
  `/register/<slug>/thank-you`, `/registration-closed`.
- `resolve_visibility` / `RegistrationPageVisibility` — pure, page-level, no change.
- Bot protection, rate limiting, timing tokens, honeypot — all slug/IP/email
  based, no change. (Note: rate limits are per IP+email globally, so they apply
  across variants — correct behaviour, a bot doesn't get N× the budget by cycling
  variants.)
- The sandboxed Jinja render pipeline and `RenderContext`.
- The field schema and submission validation.

---

## 4. Implementation — red/green TDD

### 4.0 How we work

**Every phase is a sequence of red/green cycles. No production line is written
before a test that fails because it is missing.**

The cycle, per behaviour:

1. **RED** — write one test for the next smallest behaviour. Run it. **Watch it
   fail, and read the failure.** A test that passes first time, or fails with the
   wrong error (import error where you expected an assertion error), is not yet a
   red — fix the test until it fails for the reason you intend.
2. **GREEN** — write the least production code that makes it pass. Run the test.
   Not the whole suite; just the test and its file.
3. **REFACTOR** — tidy with the test green. Re-run.
4. Repeat. Run the phase's full test file at each cycle's end, and
   `just check` before the phase's final commit.

Discipline notes for this particular job:

- **Commit at green**, one commit per cycle or small group of cycles. That keeps
  the failing-first history visible in review.
- **Refactors of existing code get a characterisation test first.** Phase 2 and
  Phase 6 are mostly signature changes to code that already works — for those the
  red is "existing behaviour, expressed through the new signature, fails because
  the new signature doesn't exist yet". Do not change a signature and then fix the
  tests it broke; write the new-signature test first, watch it fail, then change
  the signature.
- **Never run two test invocations concurrently** (CLAUDE.md) — the non-BDD and
  BDD suites share a database. Use `just test`, or
  `just test-nobdd && just test-bdd-headless`.
- Pipe long runs to a file rather than filling the terminal.

Everything ships in one release (per Chewie's comment on risk 1), so phase order
is about keeping the tree green, not about what a partial deploy would do.

**One material simplification:** no one has used registration pages in production
yet. So the migrations below need to be *correct*, but they carry no real data —
no anxious backfill, no retroactive-attribution problem, and no risk that the
asset re-scoping hits an assembly that already has two pages.

### 4.1 Phase 1 — Domain and data layer

**RED first:**

- `tests/unit/test_registration_page_service.py` (or a new
  `test_registration_page_domain.py`): constructing a `RegistrationPage` without a
  `name` raises; `name` and `language` round-trip through `create_detached_copy()`;
  `can_be_deleted()` is False once a `PUBLISH` activity exists.
- `tests/contract/test_registration_page_repo.py`: **the key red** — add two pages
  to one assembly and assert `list_by_assembly_id` returns both in `created_at`
  order. This fails today at the DB level on the unique constraint, which is
  exactly the constraint we are removing.

**Then GREEN:**

*Domain* (`domain/registration_page.py`)

- Add `name: str` (required, non-empty, validated in `__init__`) and
  `language: str = ""` to `RegistrationPage.__init__` and `create_detached_copy()`;
  add `rename()` / `set_language()` mutators that touch `updated_at`.
- Add `can_be_deleted()` → `not has_ever_been_published()` (the respondent check
  lives in the service, which has repository access).
- Update the comment in `domain/assembly.py:72-75` which says "An assembly may
  have a RegistrationPage".

*ORM* (`adapters/orm.py`)

- `registration_pages.assembly_id`: drop `unique=True`, add `index=True`.
- Add `name` (`String(100)`, not null) and `language` (`String(20)`, not null,
  default `""`).
- Add `Index("ix_registration_pages_assembly_name", "assembly_id", "name", unique=True)`.
- Add `registration_page_id` to `respondents` (nullable UUID FK,
  `ondelete="SET NULL"`, indexed).

*Repositories* (`service_layer/repositories.py`, `adapters/sql_repository.py`)

- Replace `get_by_assembly_id() -> RegistrationPage | None` with
  `list_by_assembly_id() -> list[RegistrationPage]` (ordered by `created_at`).
- Do **not** keep a "the one page" accessor — its existence is what invites the
  single-page assumption back in.
- Filter/order with ORM table columns (`orm.registration_pages.c.…`), not domain
  attributes, per CLAUDE.md.

*Migration*

```
uv run alembic revision --autogenerate -m "allow multiple registration pages per assembly"
```

then hand-edit: drop the unique constraint on `assembly_id`; add `name` nullable →
`UPDATE registration_pages SET name = 'Registration page'` → alter to not null;
add `language` with server default `''`; add `respondents.registration_page_id`.
Verify by running the suite against a migrated DB, not just an
`metadata.create_all()` one.

### 4.2 Phase 2 — Service layer: page-id addressing

**RED first:** for each converted function, a unit test in
`tests/unit/test_registration_page_service.py` calling it with a **page id** —
red because the parameter doesn't exist yet. Then the two genuinely new
behaviours, which are the interesting reds:

- `duplicate_registration_page` copies form HTML and thank-you HTML into a new
  page that is TEST, has fresh unique slugs, and carries a `CREATE` activity entry
  naming its source.
- **Q10's red, and the sharpest one in this phase:** duplicate a page, edit the
  *copy's* auto-reply template, and assert the *original's* template content is
  unchanged. That fails against a shared assignment and passes only against a real
  deep copy. Also: the duplicate's `auto_reply_email_template_id` differs from its
  source's.
- `delete_registration_page` refuses a published page, refuses a page with
  respondents, and succeeds otherwise.
- Bulk, and the red that pins Q11 down: over an assembly with a TEST page, a
  PUBLISHED page and a slugless page, `publish_all` returns MOVED / SKIPPED /
  FAILED respectively, **does not raise**, and — the part that would break under an
  all-or-nothing implementation — the TEST page is *still PUBLISHED after the call
  returns*, despite a sibling having failed. Assert the commit, not just the
  return value. Each moved page carries its own activity entry.
- Security red: a `page_id` belonging to an assembly the user cannot manage raises
  `RegistrationPageNotFoundError` — **identical** to a nonexistent id, so existence
  doesn't leak across assemblies.

**Then GREEN.** `service_layer/registration_page_service.py` is the bulk of the
change:

| Current | Becomes |
|---|---|
| `get_registration_page(uow, user, assembly_id)` | `list_registration_pages(uow, user, assembly_id)` **and** `get_registration_page(uow, user, page_id)` |
| `get_registration_page_with_source(…, assembly_id)` | `get_registration_page_with_source(…, page_id)` |
| `update_registration_page(…, assembly_id, slugs)` | `…(…, page_id, slugs)` |
| `update_registration_page_html(…, assembly_id, html)` | `…(…, page_id, html)` |
| `update_thank_you_html(…, assembly_id, html)` | `…(…, page_id, html)` |
| `publish/unpublish/close/reopen(…, assembly_id)` | `…(…, page_id)` |
| `create_registration_page_with_slugs(…, assembly_id)` | `…(…, assembly_id, name, language)` — no longer raises when a page exists |
| `generate_starter_form_html(…, assembly_id)` | unchanged (schema is assembly-scoped) |
| `find_registration_page_by_*_slug` | unchanged |
| `render_registration_form` / `render_thank_you_html` | unchanged (already take a page) |

Plus a shared permission helper `page_id -> page.assembly_id -> assembly ->
can_manage_assembly(user, assembly)`, and these new functions:

- `duplicate_registration_page(uow, user_id, source_page_id, name, language)` —
  copies form HTML, thank-you HTML, and (per **Q10 = deep copy**) creates a *new*
  `EmailTemplate` row from the source's auto-reply content, assigning it to the new
  page. The two pages must share no mutable state.
- `delete_registration_page(uow, user_id, page_id)`.
- `publish_all` / `unpublish_all` / `close_all(uow, user_id, assembly_id)` —
  each loops the assembly's pages calling the existing per-page domain methods,
  dispatching on current status (§3.4), and returns `list[BulkStatusResult]`.
  Best-effort per Q11: a page that refuses is recorded as FAILED with its
  readiness problems and the loop continues. **The function must not raise on a
  refused page**, and the successes commit — that is the behaviour the red below
  pins down.

Also in this phase: **only seed a default auto-reply template for an assembly's
first page** (Q10), so duplicating doesn't manufacture N identical English
defaults. That's a change to `_create_default_auto_reply_template`'s caller in
`backoffice_registration.py`, guarded by a test that a second created page starts
with no template rather than a fresh default.

### 4.3 Phase 3 — Assets: assembly-scoping

**RED first:**

- `tests/contract/test_registration_image_repo.py` (and the document twin):
  `list_by_assembly_id` returns images stored against the assembly; the unique
  index is `(assembly_id, sha256)` so the same bytes dedupe once per assembly, not
  once per page.
- `tests/component/test_registration_image_serve.py`: **the behavioural red that
  justifies the whole phase** — upload an image, then fetch it through a *second*
  page's slug in the same assembly and expect 200. Today that is a 404.
- A negative to pin the boundary: fetching it through a slug belonging to a
  *different* assembly is 404.

**Then GREEN:**

- `orm.py`: `registration_images.registration_page_id` → `assembly_id`; same for
  `registration_documents`. Unique index becomes `(assembly_id, sha256)`.
- Migration backfills `assembly_id` from `registration_pages.assembly_id` via the
  existing FK, then drops the old column.
- `domain/registration_image.py` / `registration_document.py`: rename the field,
  update `from_processed` and `create_detached_copy`.
- Repositories: `get_by_page_and_sha` → `get_by_assembly_and_sha`,
  `list_by_page_id` → `list_by_assembly_id`, ditto `count_by_*`.
- `get_registration_image_for_serving(uow, url_slug, name)`: keep the signature;
  internally resolve `slug -> page`, check `page.is_publicly_loadable()`, then look
  the image up by `page.assembly_id`.
- Drop the `page.record_edit(...)` calls in the image/document services — with
  assembly-scoped assets there is no single page to attribute an asset change to.
  A small, deliberate loss of audit detail; an assembly-level activity log would be
  its own story.
- **Rename the quota config** (confirmed by Chewie):
  `get_max_images_per_registration_page` → `get_max_images_per_assembly`, env var
  `REGISTRATION_MAX_IMAGES_PER_ASSEMBLY`, keeping the old env var readable as a
  fallback for one release. Same for documents. Update `docs/configuration.md` and
  `env.example`.

### 4.4 Phase 4 — Respondent provenance and the auto-reply

**RED first:**

- `tests/unit/test_registration_submission_service.py`: a submission through a page
  produces a `Respondent` whose `registration_page_id` is that page's id.
- `tests/integration/test_registration_auto_reply_integration.py`: **the sharpest
  red in the whole plan** — an assembly with two pages, each with a *different*
  auto-reply template; submit through page B and assert the email sent is B's, not
  A's. This currently cannot even be expressed (one page per assembly), and once it
  can be, `send_registration_auto_reply(assembly_id)` fails it by picking
  arbitrarily. Write this before touching `email_send_service`.
- `tests/contract/test_respondent_repo.py`: `registration_page_id` round-trips, and
  deleting a page sets it to NULL rather than cascading.

**Then GREEN:**

- `domain/respondents.py`: `Respondent.__init__` gains
  `registration_page_id: uuid.UUID | None = None`; add it to the attribute list at
  line 84ff and to `create_detached_copy()`.
- `registration_submission_service._create_and_save_respondent` gains the page id;
  `submit_registration` already holds the `page`, so it passes `page.id` through.
  `submit_registration_by_assembly_id` (dev/service-docs) passes `None`.
- `email_send_service.send_registration_auto_reply` takes `registration_page_id`
  instead of resolving from `assembly_id`. If the respondent has no page id, skip.
- `email_template_service.assign_auto_reply_template(…, page_id, template_id)`.
  `auto_reply_readiness_problems` stays assembly-scoped (it checks reply-to etc.).
- Repository: a grouped `count_by_registration_page(assembly_id) ->
  dict[UUID, int]` (§3.3 — one query, not N) plus the single-page count the delete
  guard needs.

### 4.5 Phase 5 — Public routes

Almost no production code; this phase is mostly tests confirming that the
slug-scoped routes already do the right thing with N pages.

**RED first** (in `tests/component/test_registration_routes.py` and
`tests/integration/test_registration_submission_integration.py`):

- Two PUBLISHED pages of one assembly both render, and submissions through each
  land in the same pool tagged with different `registration_page_id`s.
- A TEST variant alongside a PUBLISHED variant still produces
  `TEST_SUBMISSION` respondents, and the published one still produces `POOL`.
- Each page's thank-you page and short URL resolve to *its own* content, not a
  sibling's.

**GREEN:** expect little or nothing to change here. If a test passes on first
write, that is a signal the behaviour was already covered — replace it with one
that actually distinguishes the variants rather than deleting the coverage.

### 4.6 Phase 6 — Backoffice: list page + per-page editor ⛔ BLOCKED on Q6/Q7

Do not start until the team decides. The sketch below assumes Q6=(a); if they pick
(b) the routes change but the service layer underneath does not.

**RED first:** component tests in
`tests/component/test_backoffice_registration_view.py` and
`…_actions.py` — the list route renders N pages with statuses and counts; create /
duplicate / delete each behave and refuse correctly; a per-page editor route 404s
on a page id from another assembly. Plus the bulk route: posting `close` with a
mix of PUBLISHED and TEST pages closes only the published ones and flashes a
summary that **names the pages that didn't move** — assert on the page name
appearing in the flash, not just on a 302, or the summary will quietly rot into
"Done". These are route-level reds; write them against the intended URLs before
the routes exist.

**Then GREEN.** Routes in `entrypoints/blueprints/backoffice_registration.py`:

```
GET  /assembly/<assembly_id>/registration                      → list of pages (NEW)
POST /assembly/<assembly_id>/registration/create               → create (gains name/language)
POST /assembly/<assembly_id>/registration/<page_id>/duplicate  → duplicate (NEW)
POST /assembly/<assembly_id>/registration/<page_id>/delete     → delete (NEW)
GET  /assembly/<assembly_id>/registration/<page_id>            → the existing stepper
POST /assembly/<assembly_id>/registration/<page_id>/save
GET  /assembly/<assembly_id>/registration/<page_id>/form-preview
GET  /assembly/<assembly_id>/registration/<page_id>/qr-code.png
POST /assembly/<assembly_id>/registration/<page_id>/email/save
POST /assembly/<assembly_id>/registration/bulk-status              → publish/unpublish/close all (NEW)
     …/images…, …/documents…  → stay assembly-scoped (Phase 3), no page_id
```

Keeping `assembly_id` in the path alongside `page_id` is redundant but keeps the
breadcrumb/nav code and the permission helper unchanged, and lets us 404 cleanly
on a page/assembly mismatch.

Templates:

- New `templates/backoffice/assembly_registration_list.html` — a plain table
  (name, language, slug, status tag, submission count, Edit / Duplicate / Delete),
  plus "Add a page" and the bulk status controls. **No filtering, sorting,
  grouping or pagination** (§3.3). Follow `docs/agent/govuk_components.md` and the
  accessibility guide; status uses the existing status-tag component.
- The bulk controls need a confirmation step — "close all" over 20 live pages is
  not an undo-able click — and the outcome summary from §3.4 rendered as a flash
  message, not swallowed into a generic "done".
- `assembly_registration.html` (1950 lines) stays as the per-page editor. The change
  is mechanical: every `url_for(..., assembly_id=assembly.id)` gains
  `page_id=registration_page.id`, and the breadcrumb gains a "Registration pages"
  level. The Assets subsections' copy changes to "images for this assembly".
- `assembly_details.html:107-170`: depends on **Q7**.

Alpine.js: the assets panels use `x-model` flat-property and no-string-argument
constraints (`templates/backoffice/patterns.html`) — the list page's delete
confirmation must follow the same CSP-safe patterns. No new inline JS.

**E2E and BDD land with this phase**, since both drive the UI:

- `tests/e2e/test_backoffice_registration.py`: create assembly → add English page →
  duplicate as Spanish → publish both → submit to each → both respondents present
  and attributed to the right page.
- `features/backoffice-registration-editor.feature` gains scenarios for the
  multi-page journey, including "close all registration pages at once". Write the
  Gherkin first — it is the natural red for the organiser journey.

### 4.7 Phase 7 — Dev / service-docs, docs, i18n

**RED first:** `tests/component/` coverage that the dev service-docs handlers
return page-aware results for an assembly with two pages — the existing handlers
silently pick one today.

**Then GREEN:**

- `entrypoints/blueprints/dev.py` — `_handle_create_registration_page`,
  `_handle_get_registration_page`, and the direct
  `registration_pages.get_by_assembly_id` calls at lines 1030 and 1196.
- `entrypoints/blueprints/backoffice.py:134,194` — switch to
  `list_registration_pages`.
- Docs: `docs/configuration.md` for the renamed quota env vars, `CLAUDE.md`'s
  core-entities list. `docs/personal-data.md` needs **no** change (Q1 = independent
  URLs, no new cookie) — but say so in the PR so the reviewer doesn't have to
  re-derive it.
- `just translate-regen` once all new user-facing strings are in.
- `tests/conftest.py::_delete_all_test_data` and
  `tests/bdd/conftest.py::delete_all_except_standard_users`: no new tables, but
  images/documents become siblings of `registration_pages` rather than children, so
  the delete order changes.
- Regenerate `../.secrets.baseline` if test line numbers shift.

### 4.8 Test tier coverage map

The no-exceptions policy needs every tier represented. Where each lands:

| Tier | Phases | Nothing new needed? |
|---|---|---|
| Unit | 1, 2, 4 | — |
| Contract (repo) | 1, 3, 4 | — |
| Integration | 4, 5 | — |
| Component (route) | 3, 5, 6, 7 | — |
| E2E | 6 | — |
| BDD | 6 | — |

Phases 1–5 and 7 can go green without Phase 6, but **E2E and BDD coverage for this
feature does not exist until Phase 6 lands**. Since everything ships together that
is fine — but it means the branch is not releasable before Phase 6, regardless of
how green the backend is.

---

## 5. Risks and things I'd watch

1. **The auto-reply picking the wrong page's template.** Everything ships together
   (per Chewie), so there's no partial-deploy window — but within the branch, keep
   Phase 4's integration test red-first so the wrong-template bug can never land
   quietly. This is the one behaviour where a bug reaches a member of the public in
   the wrong language.
2. **`assembly_registration.html` is 1950 lines** and threads `assembly.id` through
   dozens of `url_for` calls. Mechanical but wide, and the most likely place for a
   missed link. Grep-sweep plus the Phase 6 component tests.
3. **Slug freeze across variants.** Structurally unchanged, but organisers will now
   hit "I published variant B by accident and can't rename its slug" far more often
   with 20 pages than with one. The delete-while-unpublished rule (Q8) is the escape
   hatch; make sure the UI says so.
4. **Asset migration.** The Phase 3 backfill is only unambiguous while every
   assembly has at most one page. Nothing is in production, so the real constraint
   is just ordering *within* the branch: Phase 3 before anyone can create a second
   page through the UI (Phase 6).
5. **Bulk actions are the destructive ones.** "Close all" over 20 live pages is a
   single click that takes an assembly's entire registration offline, and there is
   no bulk undo (reopening runs the readiness check per page). Confirmation step,
   clear summary of what moved, and per-page activity entries so the audit trail
   can reconstruct it.
6. **Don't over-build for 20 pages.** The 5% figure means effort spent on
   filtering, sorting and pagination is effort wasted on the 95%. The one place
   page count genuinely bites is bulk state changes, which are now in scope.
7. **`external_id` prefix.** Submissions get `reg-<hex>`; A/B analysis does *not*
   need the variant encoded there — the FK is the right place, and `external_id` is
   user-visible in exports.

---

## 6. Rough sizing

| Phase | Size | Notes |
|---|---|---|
| 1 Domain + data + migration | M | mechanical; migration needs care but no live data |
| 2 Service layer | L | ~15 signatures, plus duplicate (with template deep-copy), delete, and three bulk actions |
| 3 Asset re-scoping | M | two tables, config rename, doc updates |
| 4 Respondent provenance + auto-reply | M | small code, highest-consequence correctness |
| 5 Public routes | S | almost entirely tests |
| 6 Backoffice UI | L | blocked; new list view + bulk controls + one wide mechanical edit; carries E2E + BDD |
| 7 Dev/docs/i18n | S | |

Tests are inside each phase, not a phase of their own.

Phases 1–5 and 7 are buildable today and deliver a working multi-page backend.
Phase 6 is what makes it usable, and is gated on Q6/Q7.
