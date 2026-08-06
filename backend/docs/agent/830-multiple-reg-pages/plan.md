# Multiple registration pages per assembly — plan

**Issue:** 830
**Branch (proposed):** `830-multiple-reg-pages`
**Date:** 2026-08-06
**Status:** DRAFT — awaiting answers to the questions in §2

---

## 1. Goal and current state

### Goal

An assembly should be able to have **more than one registration page**, so that organisers can:

- run **A/B tests** of different page designs / copy, and
- offer the **same assembly in different languages**.

### What exists today

The model is `Assembly (1) —— (0..1) RegistrationPage`, and the "at most one" is
enforced in three places:

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

## 2. Questions for Chewie

> Please answer inline — add your answer under each question and I'll fold it into
> the plan. Where I have a recommendation it's marked **Rec:**.

### Q1 — Does the app do the A/B *split*, or do you just want two URLs? ⚠️ BIGGEST QUESTION

Two very different products:

**(a) Two independent URLs.** You get `/register/climate-a` and
`/register/climate-b`, print different QR codes on different flyers / put them in
different emails, and compare the numbers afterwards. The app never decides which
page a visitor sees.

**(b) The app splits traffic.** One entry URL, and OpenDLP randomly assigns each
visitor to variant A or B and keeps them there on refresh/resubmit.

(b) costs a lot more: an "entry point / campaign" concept above the pages, sticky
assignment, and — the killer — **sticky assignment needs a cookie or a
device-identifying signal**. `docs/personal-data.md` is explicit that OpenDLP's
"no cookie banner" conclusion rests on having exactly two consent-exempt cookies,
and that adding any cookie may invalidate it. An A/B assignment cookie is a
*measurement* cookie, which is the classic non-exempt category — it would likely
put a cookie banner on the public registration pages. A URL-parameter or
alternating-server-side scheme avoids the cookie but breaks on refresh/back-button
and skews the numbers.

**Rec: (a).** It delivers both stated use cases (A/B and languages), needs no
cookie, and doesn't touch the personal-data posture. If you want (b) later it can
be built on top of (a) — but it should be its own piece of work with its own
personal-data review.

**Answer:**

### Q2 — Should assets (images, PDFs) be shared across an assembly's pages?

Today `registration_images` and `registration_documents` are keyed by
`registration_page_id`, and public serving is
`/register/<url_slug>/assets/<sha>.png` → resolve slug → page → look up image
*on that page*. So with multiple pages, an image uploaded to the English page is
a 404 from the Spanish page's URL, and the organiser has to upload the logo twice.

- **(a) Keep page-scoped.** No migration on those tables. Every variant needs its
  own upload; snippet URLs differ per page; duplicate bytes stored per page.
- **(b) Move to assembly-scoped** (`assembly_id` FK, unique on
  `(assembly_id, sha256)`). Upload once, use from any variant. Serving keeps the
  same public URL shape but resolves `slug -> page -> assembly -> image`. Needs a
  data migration (backfill `assembly_id` from the page) and index changes.

**Rec: (b).** Language variants and A/B variants will almost always share the same
logo and the same "what is a citizens' assembly" PDF. Making an organiser upload
the same file per variant is exactly the friction this feature is supposed to
remove. The migration is mechanical (every existing page is the only page of its
assembly, so the backfill is unambiguous). It also keeps GDPR sweep surface flat —
one place per assembly rather than one per variant.

**Answer:**

### Q3 — Do we record which page each respondent registered through?

For A/B testing this is the *point* — without it you can't compare conversion.
`respondents` currently has `source_type = REGISTRATION_FORM` but no pointer to
the page.

**Rec: yes** — add a nullable `registration_page_id` FK on `respondents`
(`ON DELETE SET NULL`, so deleting a variant doesn't destroy respondent rows).
Nullable because CSV/GSheet/manual respondents have no page. It's a UUID, not PII,
so it changes nothing for erasure.

Follow-up: **how much reporting is in scope?** Options, cheapest first:
1. Just store it (a later story builds reporting).
2. Store it + show a per-page submission count on the registration page list.
3. Store it + a proper comparison view (counts, over time, completion).

**Rec: 2** — the count is a one-line query and makes the list page genuinely
useful; leave real analytics for later.

**Answer:**

### Q4 — Can variants differ in *which fields* they ask?

Field definitions (`respondent_field_definitions`) are assembly-scoped, and
`submit_registration` validates every submission against the assembly's schema.
So today, variants can differ in **layout, copy, styling and language**, but not
in the set of fields — and specifically, a variant that omits a
`YES_REQUIRED` field will fail validation for every visitor.

**Rec: keep it that way.** Same data, different presentation. It keeps the
respondent table coherent and keeps selection working. If you want per-variant
field sets, say so — it's a substantially bigger job (per-page field overrides,
and selection has to cope with respondents missing attributes).

**Answer:**

### Q5 — Should a page carry a `language` code?

For the translation use case a `language` column (e.g. `en`, `es`, `cy`) would
let us label pages meaningfully and, later, cross-link variants ("Ver en español")
or honour `Accept-Language`.

**Rec: add the column now** (optional, default `""`), use it only as a label in
this piece of work. It's cheap to add and expensive to retrofit. **Do not** build
`Accept-Language` auto-redirect now — that's a behaviour change on public URLs
that deserves its own think.

**Answer:**

### Q6 — What should the backoffice URL / UI shape be?

Today: `/assembly/<id>/registration` renders a 3-step stepper (form → auto-reply
email → preview and publish) for the one page. The template is ~1950 lines.

- **(a) A list page, then a per-page editor.**
  `/assembly/<id>/registration` becomes a list of the assembly's pages (name,
  language, slug, status, submission count, actions). The existing stepper moves
  to `/assembly/<id>/registration/<page_id>` essentially unchanged.
- **(b) Keep one URL, add a page-picker dropdown** at the top of the existing
  page, with `?page=<uuid>`.

**Rec: (a).** The stepper template barely changes (it just gains `page` in its
url_for calls), the list is a new small template, and "which page am I editing"
is unambiguous in the URL — which matters when someone bookmarks or shares a link
to a variant. (b) makes every existing route implicitly stateful.

**Answer:**

### Q7 — Is there a "primary" page?

The Assembly **Details** tab currently shows *the* registration URL + QR code.
With N pages it has to show something else.

- **(a) List them all** (name, URL, QR link) — no primary concept, no extra column.
- **(b) Add `is_primary`** and show that one, with "and 2 others".

**Rec: (a).** A primary flag is a rule you then have to maintain (what happens
when the primary is closed? deleted?) for very little gain. Listing 2–3 pages on
the Details tab is fine.

**Answer:**

### Q8 — Deleting a registration page

There's no delete today (a page is created once and lives forever). With
variants, organisers will create a test variant and want it gone.

**Rec:** allow delete **only while the page has never been published**
(`has_ever_been_published() == False`) **and has no respondents**. Once published,
its slug is in the world and its submissions are in the pool — offer `close`
instead. This mirrors the existing slug-freeze reasoning.

**Answer:**

### Q9 — Anything to say about how many pages? Any cap?

**Rec:** no hard cap in the domain; the practical limit is the image/document
quotas which are already per-page (and become per-assembly if Q2 = (b)). Happy to
add a soft cap if you'd rather.

**Answer:**

---

## 3. Proposed design (assuming the recommended answers)

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

Assembly (1) ──── (0..N) RegistrationImage      MOVED from page to assembly (Q2b)
Assembly (1) ──── (0..N) RegistrationDocument   MOVED from page to assembly (Q2b)
Assembly (1) ──── (0..N) RespondentFieldDefinition   unchanged, shared by all pages
Assembly (1) ──── (0..N) EmailTemplate               unchanged; assignment is per page

Respondent.registration_page_id  NEW, nullable — which page it came in through
```

Several pages of one assembly may be `PUBLISHED` at the same time — that is the
whole point, and no code currently assumes otherwise once the lookups are fixed.

### 3.2 Naming and slugs

- `name` is required and unique within the assembly (a human handle for the
  editor UI; never shown publicly).
- Slug auto-generation changes from `slugify(assembly.title)` to
  `slugify(assembly.title + "-" + page.name)`, still passed through
  `generate_unique_url_slug` for the `-2`, `-3` fallback. So the Spanish variant
  of "Climate Assembly" defaults to `climate-assembly-espanol` rather than
  `climate-assembly-2`.
- Slug freeze rules are unchanged and remain per page.

### 3.3 What stays exactly as it is

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

## 4. Implementation phases

Each phase should be independently testable and leave `just test` and `just check`
green. Phases 1–5 are backend and can land before any UI change; the app keeps
working with exactly one page per assembly throughout.

### Phase 1 — Domain and data layer

**Domain** (`domain/registration_page.py`)

- Add `name: str` (required, non-empty, validated in `__init__`) and
  `language: str = ""` to `RegistrationPage.__init__`, `create_detached_copy()`,
  and add `rename()` / `set_language()` mutators that touch `updated_at`.
- Add `can_be_deleted()` → `not has_ever_been_published()` (the respondent check
  lives in the service, which has repository access).
- Update the module docstring comment in `domain/assembly.py:72-75` which says
  "An assembly may have a RegistrationPage".

**ORM** (`adapters/orm.py`)

- `registration_pages.assembly_id`: drop `unique=True`, add `index=True`.
- Add `name` (`String(100)`, not null) and `language` (`String(20)`, not null,
  default `""`) columns.
- Add `Index("ix_registration_pages_assembly_name", "assembly_id", "name", unique=True)`.
- Add `registration_page_id` to `respondents` (nullable UUID FK,
  `ondelete="SET NULL"`, indexed).

**Repositories** (`service_layer/repositories.py`, `adapters/sql_repository.py`)

- Replace `get_by_assembly_id() -> RegistrationPage | None` with
  `list_by_assembly_id() -> list[RegistrationPage]` (ordered by `created_at`).
- Keep a `get_by_assembly_id_and_name()` if useful for slug generation; otherwise
  don't keep a "the one page" accessor at all — its existence is what invites
  single-page assumptions back in.
- Remember: filter/order with ORM table columns (`orm.registration_pages.c.…`),
  not domain attributes, per CLAUDE.md.

**Migration**

```
uv run alembic revision --autogenerate -m "allow multiple registration pages per assembly"
```

then hand-edit to add the backfill:

- drop the unique constraint on `registration_pages.assembly_id`
- add `name` nullable → `UPDATE registration_pages SET name = 'Registration page'`
  → alter to not null (or backfill from the assembly title — decide when writing)
- add `language` with server default `''`
- add `respondents.registration_page_id` (nullable, no backfill needed:
  existing registration-form respondents predate variants and we can't reliably
  attribute them — leaving NULL is honest)

**Tests:** `tests/contract/test_registration_page_repo.py` gains
`list_by_assembly_id` coverage including "two pages, both returned, ordered";
unit tests for the new domain fields and `can_be_deleted()`.

### Phase 2 — Service layer: page-id addressing

`service_layer/registration_page_service.py` — the bulk of the change. Every
function currently shaped `(uow, user_id, assembly_id, …)` splits into one of:

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

The page-id functions need a permission helper that goes
`page_id -> page.assembly_id -> assembly -> can_manage_assembly(user, assembly)`
and raises `RegistrationPageNotFoundError` for a bad id — note this must not leak
existence across assemblies, so "page belongs to an assembly you can't manage"
should look the same as "no such page".

New:

- `duplicate_registration_page(uow, user_id, source_page_id, name, language)` —
  copies `form_html`, `thank_you_html` and the auto-reply template *assignment*
  into a fresh TEST page with fresh generated slugs and a `CREATE` activity entry
  saying what it was copied from. This is the feature that makes variants and
  translations actually pleasant, and it is cheap.
- `delete_registration_page(uow, user_id, page_id)` — refuses if
  `has_ever_been_published()` or if any respondent references it.

### Phase 3 — Assets: assembly-scoping (if Q2 = b)

- `orm.py`: `registration_images.registration_page_id` → `assembly_id`;
  same for `registration_documents`. Unique index becomes
  `(assembly_id, sha256)`.
- Migration backfills `assembly_id` from
  `registration_pages.assembly_id` via the existing FK, then drops the old column.
- `domain/registration_image.py` / `registration_document.py`: rename the field,
  update `from_processed` and `create_detached_copy`.
- Repositories: `get_by_page_and_sha` → `get_by_assembly_and_sha`,
  `list_by_page_id` → `list_by_assembly_id`, ditto `count_by_*`.
- `registration_image_service.get_registration_image_for_serving(uow, url_slug, name)`:
  keep the signature; internally resolve `slug -> page`, check
  `page.is_publicly_loadable()`, then look the image up **by
  `page.assembly_id`**. So any live page of the assembly can serve any of the
  assembly's images, which is what shared assets means.
- The `page.record_edit(...)` calls in the image/document services currently
  attribute asset changes to the single page's activity log. With assembly-scoped
  assets there is no single page to attribute to — drop those `record_edit` calls
  (asset changes are not page edits any more). Worth noting in the story: it is a
  small loss of audit detail. If we care, an assembly-level activity log is a
  separate story.
- Quotas (`get_max_images_per_registration_page`) become per assembly — rename the
  config accessor and env var, or keep the name and document the change. Prefer
  renaming: `REGISTRATION_MAX_IMAGES_PER_ASSEMBLY`, keeping the old env var
  readable as a fallback for one release.

### Phase 4 — Respondent provenance and the auto-reply

- `domain/respondents.py`: `Respondent.__init__` gains
  `registration_page_id: uuid.UUID | None = None`; add it to `__slots__`-ish
  attribute list at line 84ff and to `create_detached_copy()`.
- `registration_submission_service._create_and_save_respondent` gains the page id;
  `submit_registration` already has the `page` in hand, so it just passes
  `page.id` through. `submit_registration_by_assembly_id` (dev/service-docs)
  passes `None`.
- **`email_send_service.send_registration_auto_reply` must change.** It currently
  does `uow.registration_pages.get_by_assembly_id(assembly_id)` to find the
  template — with N pages that's ambiguous and would send the wrong language's
  auto-reply. Change its signature to take `registration_page_id` (the caller,
  `registration.py:_send_registration_auto_reply`, has the respondent, which now
  carries it). If the respondent has no page id, skip (no auto-reply for
  CSV-imported respondents, which is already effectively true).
- `email_template_service.assign_auto_reply_template(…, assembly_id, template_id)`
  → takes `page_id`. `auto_reply_readiness_problems` stays assembly-scoped
  (it checks reply-to address etc.).

Repository addition: `respondents.count_by_registration_page_id(page_id)` for
the list-page submission counts (Q3 rec 2) and the delete guard.

### Phase 5 — Public routes

Almost nothing. Verify and cover with tests:

- Two published pages of one assembly both resolve and both submit into the same
  pool, tagged with different `registration_page_id`s.
- A TEST variant alongside a PUBLISHED variant: the TEST one still produces
  `TEST_SUBMISSION` respondents.
- Asset URLs work from either page's slug (Phase 3).
- The `after_request` noindex header is blueprint-wide, so it already covers all
  variants.

### Phase 6 — Backoffice: list page + per-page editor

Routes in `entrypoints/blueprints/backoffice_registration.py`:

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
     …/images…, …/documents…  → stay assembly-scoped (Phase 3), no page_id
```

Keeping `assembly_id` in the path alongside `page_id` is redundant but keeps the
breadcrumb/nav code and the permission helper unchanged, and lets us 404 cleanly
on a page/assembly mismatch. Worth doing.

Templates:

- New `templates/backoffice/assembly_registration_list.html` — a table of pages
  (name, language, slug, status tag, submission count, Edit / Duplicate /
  Delete), plus "Add a page" and "Duplicate" entry points. Follow
  `docs/agent/govuk_components.md` and the accessibility guide; status uses the
  existing status-tag component.
- `assembly_registration.html` (1950 lines) stays as the per-page editor. The
  change is mechanical: every `url_for(..., assembly_id=assembly.id)` in it gains
  `page_id=registration_page.id`, and the breadcrumb gains a "Registration pages"
  level. The Assets subsections lose their page association in copy ("images for
  this assembly" rather than "for this page") if Q2 = (b).
- `assembly_details.html:107-170`: the single-page block becomes a loop over
  `registration_pages`, and the "create" CTA stays but says "Add a registration
  page".

Alpine.js: the assets panels use `x-model` flat-property and no-string-argument
constraints (`templates/backoffice/patterns.html`) — the list page's delete
confirmation must follow the same CSP-safe patterns. No new inline JS.

### Phase 7 — Dev / service-docs, docs, i18n

- `entrypoints/blueprints/dev.py` — `_handle_create_registration_page`,
  `_handle_get_registration_page`, and the two direct
  `registration_pages.get_by_assembly_id` calls at lines 1030 and 1196 need
  page-aware equivalents.
- `entrypoints/blueprints/backoffice.py:134,194` — assembly details and edit both
  call `get_registration_page_with_source(…, assembly_id)`; switch to
  `list_registration_pages`.
- Docs: update `docs/personal-data.md` if Q1 = (b) (it won't be if we take the
  recommendation), `docs/configuration.md` for any renamed quota env var, and
  `CLAUDE.md`'s core-entities list.
- `just translate-regen` after all new user-facing strings are in.
- `tests/conftest.py::_delete_all_test_data` and
  `tests/bdd/conftest.py::delete_all_except_standard_users` — no new tables, but
  the delete order for images/documents changes if they move to assembly scope
  (they'd then be siblings of `registration_pages`, not children).
- Regenerate `../.secrets.baseline` if test line numbers shift.

### Phase 8 — Tests

Per the no-exceptions policy, all three levels plus the existing contract/BDD
tiers:

**Unit** (`tests/unit/test_registration_page_service.py` and new files)
- name required / unique-per-assembly, language optional
- `duplicate_registration_page` copies HTML, thank-you and template assignment,
  generates fresh slugs, starts in TEST
- `delete_registration_page` refuses when published, refuses when respondents
  exist, succeeds otherwise
- page-id permission helper: cross-assembly page id behaves as not-found
- slug generation from assembly title + page name

**Contract** (`tests/contract/test_registration_page_repo.py`)
- `list_by_assembly_id` with 0 / 1 / 3 pages, ordering
- two pages of the same assembly can both be PUBLISHED
- respondent `registration_page_id` round-trips; `ON DELETE SET NULL` behaviour

**Integration** (`tests/integration/`)
- submit through variant A and variant B of one assembly → two respondents in the
  same pool with different `registration_page_id`
- auto-reply picks the *submitting page's* template, not another variant's
  (this is the regression the change to `send_registration_auto_reply` prevents —
  test it explicitly)

**Component** (`tests/component/`)
- list route renders N pages with correct statuses and counts
- create / duplicate / delete routes: happy path, permission denial, guard rails
- per-page editor routes 404 on a page id from another assembly

**E2E** (`tests/e2e/`)
- full journey: create assembly → add English page → duplicate as Spanish →
  publish both → submit to each → both respondents present and attributed

**BDD** (`tests/bdd/`)
- a feature for the organiser-facing journey, matching the existing registration
  feature style

Run order per CLAUDE.md: never concurrently — `just test`, or
`just test-nobdd && just test-bdd-headless`.

---

## 5. Risks and things I'd watch

1. **The auto-reply lookup is the sharpest edge.** Until Phase 4 lands,
   `send_registration_auto_reply(assembly_id)` will pick an arbitrary page's
   template. If Phases 1–2 ship before Phase 4, a Spanish registrant can get an
   English auto-reply. Either ship 1–4 together or keep the DB constraint until
   Phase 4 is done.
2. **`assembly_registration.html` is 1950 lines** and threads `assembly.id`
   through dozens of `url_for` calls. The change is mechanical but wide; it's the
   most likely place for a missed link. Worth a grep-based sweep plus the
   component tests above.
3. **Slug freeze across variants.** Nothing changes structurally, but organisers
   will now hit "I published variant B by accident and can't rename its slug" more
   often. The delete-while-unpublished rule (Q8) is the escape hatch; make sure
   the UI says so.
4. **Asset migration is one-way.** Phase 3's backfill is unambiguous today
   (one page per assembly) but becomes ambiguous the moment a second page exists.
   So Phase 3 must land *before* anyone creates a second page in production —
   i.e. before Phase 6 ships the UI, and ideally in the same release as Phase 1.
5. **Respondent attribution is not retroactive.** Existing registration-form
   respondents get `registration_page_id = NULL`. Any per-page count will
   under-report for assemblies that were live before this lands. Say so in the UI
   rather than pretending the number is complete.
6. **`external_id` prefix.** Submissions get `reg-<hex>`; consider whether A/B
   analysis wants the variant encoded there too. **Rec: no** — the FK is the
   right place, and `external_id` is user-visible in exports.

---

## 6. Rough sizing

| Phase | Size | Notes |
|---|---|---|
| 1 Domain + data + migration | M | mechanical, but the migration needs care |
| 2 Service layer | L | ~15 function signatures, plus duplicate/delete |
| 3 Asset re-scoping | M | only if Q2 = (b) |
| 4 Respondent provenance + auto-reply | M | small code, important correctness |
| 5 Public routes | S | mostly tests |
| 6 Backoffice UI | L | one new template, one wide mechanical edit |
| 7 Dev/docs/i18n | S | |
| 8 Tests | L | spread across all phases, not a separate block |

Phases 1, 2, 4 and 5 are the minimum viable "two URLs work". 3 and 6 are what
make it usable.
