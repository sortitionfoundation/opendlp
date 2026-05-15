# Registration Page — Detailed TDD Implementation Plan (data + service layer)

**Branch:** `610-registration-page-html`
**Date:** 2026-05-14
**Companion to:** `plan-data-service.md` (the design) — this doc is the _build order_.
**Status:** For review before implementation starts.

---

## 0. Scope and decisions baked in

This plan implements **only** `domain/`, `adapters/` and `service_layer/`. Everything under
`entrypoints/` (the backoffice tab, the public `/register/` + `/r/` routes, the feature-flag
gate, WTForms) is a colleague's work and is **out of scope here**.

### 0.1 Q15 — using Option A (two minimal tokens)

Per Doctor Chewie's instruction: **Q15 = Option A**. The author pastes a complete HTML form into
the textarea; at render time we do **flat string substitution** of exactly two tokens:

- `{{ csrf_form_element }}` — the hidden CSRF input
- `{{ form_url }}` — the URL the form POSTs to

No Jinja, no sandbox — `str.replace` on two known tokens (`plan-data-service.md` §5.3). This
keeps the design from `plan-data-service.md` intact:

| `plan-data-service.md` element       | This implementation                                                                                        |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `RenderContext` dataclass (§5.3)     | **kept** — carries `csrf_form_element` and `form_url`, lives in `domain/registration_page.py`              |
| `REQUIRED_TOKENS` / token scan       | **kept** — `("csrf_form_element", "form_url")`; readiness checks both are present in the HTML              |
| `RegistrationPageHtml.render(ctx)`   | **kept** — substitutes the two tokens via `str.replace`; unknown `{{ … }}` left untouched                  |
| `render_thank_you_html()` service fn | **kept** — returns `thank_you_html` verbatim (no substitutable tokens in v1), exists as a seam             |
| CSRF / `form_url` injection          | the blueprint builds `RenderContext` and passes it in (`plan-data-service.md` §5.5) — entrypoints' concern |

Everything else in `plan-data-service.md` stands.

### 0.2 Assumptions worth a second look before we start

These are judgement calls. Flag any you disagree with on review:

1. **`render(ctx)` does the two-token substitution** and is the stable seam the public route
   calls. The `HtmlSource` protocol is the whole point of the child-table design, so this seam
   stays meaningful. _(Confirmed on review — keep it, with the two minimal tokens.)_

2. **The `Assembly.registration_page` ORM relationship is NOT added.** `plan-data-service.md` §4.2
   suggested it, but to keep this story decoupled from the existing `Assembly` aggregate we skip
   it: no `Assembly.__init__` change, no back-relation. The `registration_pages.assembly_id` FK
   keeps `ondelete="CASCADE"` so DB-level cleanup still works, and the repo's `get_by_assembly_id`
   is the access path. We add a short comment in `domain/assembly.py` noting that a
   `registration_page` relationship could be added later if wanted. _(Confirmed on review.)_

3. **`UrlSlugValidator` raises `ValueError`** (a domain validator), _not_ `wtforms.ValidationError`
   like the existing `GoogleSpreadsheetURLValidator`. The domain layer must not depend on WTForms.
   _(Confirmed on review.)_

4. **Open questions left open.** Q8 is subsumed by Q15 (settled). Nothing else in
   `plan-data-service.md` §8 ("punted to form-submission story") is touched here.

### 0.3 TDD discipline

Every step below is a **red → green → refactor** cycle:

1. **Red:** write the test(s) named in the step, run them, watch them fail for the _expected_
   reason (import error / assertion). A test that fails for the wrong reason is not a red.
2. **Green:** write the _minimum_ production code to pass. No speculative extras.
3. **Refactor:** tidy with tests green.

Run scoped tests as you go (`uv run pytest <path> -q`); run `CI=true just test` and `just check`
before the final commit of each phase. Bottom-up order — domain, then adapters, then service —
so each layer's tests run against already-green code beneath it.

### 0.4 Commit strategy

Per Doctor Chewie's standing preference, **plan/spec docs commit separately from code**. This
doc and `plan-data-service.md` are already (or will be) committed on their own. Suggested code
commits, one per phase, each green + linted:

- `feat(registration): add RegistrationPage domain model` (Phase 1)
- `feat(registration): add registration page tables, mapping and repositories` (Phase 2)
- `feat(registration): add registration page HTML size-limit config` (Phase 3)
- `feat(registration): add registration page service layer` (Phase 4, may absorb the Phase 3 config)

---

## Phase 1 — Domain layer ✅ COMPLETE

New file: `src/opendlp/domain/registration_page.py` (with the 2-line `ABOUTME:` header).
New test file: `tests/unit/domain/test_registration_page.py`.
Slug validator tests go in the existing `tests/unit/test_validators.py`.

Pure Python — no Flask, no SQLAlchemy, no DB. These tests are fast and need no fixtures.

### 1.1 `RegistrationPageSource` enum

- **Red:** `test_registration_page_source_has_html_member` — `RegistrationPageSource.HTML.value == "html"`.
- **Green:** `class RegistrationPageSource(Enum): HTML = "html"`.

### 1.2 `UrlSlugValidator` + `RESERVED_SLUGS` — in `domain/validators.py`

Tests in `tests/unit/test_validators.py` (new `TestUrlSlugValidator` class).

- **Red:** parametrised accept cases (`"my-assembly"`, `"abc"`, `"a1-b2"`) and reject cases:
  empty string handling (note: empty is _allowed_ by the domain as "unset" — see 1.3 — so the
  validator itself should be called only on non-empty values; decide whether the validator
  rejects `""` or the caller guards. Recommendation: **validator rejects `""`**, `RegistrationPage`
  only calls it when the slug is non-empty), uppercase, leading/trailing hyphen, spaces,
  underscores, non-ASCII, >100 chars, and each value in `RESERVED_SLUGS`.
- **Green:** `RESERVED_SLUGS = frozenset({"preview", "submit", "admin", "static", "assets"})`
  and `UrlSlugValidator` with a `validate(value: str) -> str` method (returns the value on
  success, raises `ValueError` with a friendly message on failure). Regex:
  `^[a-z0-9]+(-[a-z0-9]+)*$`, length 1–100, lowercased input compared, reserved set checked.

### 1.3 `RegistrationPage.__init__`

- **Red:**
  - `test_init_sets_id_when_not_given` / `test_init_keeps_given_id`
  - `test_init_defaults` — `is_published is False`, `source_type is HTML`,
    `url_slug == ""`, `short_url_slug == ""`, `thank_you_html == ""`
  - `test_init_autogenerates_preview_token` — non-empty, and two instances differ
  - `test_init_keeps_given_preview_token`
  - `test_init_sets_created_and_updated_at`
  - `test_init_validates_url_slug` / `test_init_validates_short_url_slug` — a bad slug raises
    `ValueError`; an empty slug does **not** (empty = unset)
- **Green:** constructor per `plan-data-service.md` §3.1. `preview_token` via
  `secrets.token_urlsafe(32)` when blank. Validate each slug only if non-empty. Use
  `datetime.now(UTC)` for timestamp defaults (matches `assembly.py` / `password_reset.py`).

### 1.4 `update_slugs`

- **Red:**
  - `test_update_slugs_changes_url_slug` / `..._short_url_slug` / both at once
  - `test_update_slugs_none_leaves_value_alone` (passing `None` is a no-op for that arg)
  - `test_update_slugs_empty_string_clears` (passing `""` clears — distinct from `None`)
  - `test_update_slugs_validates` — bad slug raises `ValueError`
  - `test_update_slugs_raises_when_published` — `is_published=True` → `ValueError` (Q6)
  - `test_update_slugs_bumps_updated_at`
- **Green:** implement per §3.1. Guard `is_published` first, then validate, then assign, then
  bump `updated_at`.

### 1.5 `update_thank_you_html`

- **Red:** `test_update_thank_you_html_sets_value`, `test_update_thank_you_html_bumps_updated_at`.
  (No size check here — that lives in the service layer, Phase 4.5.)
- **Green:** trivial setter + `updated_at` bump.

### 1.6 `RenderContext` + `REQUIRED_TOKENS`

Both live in `domain/registration_page.py` (per `plan-data-service.md` §10).

- **Red:** `test_render_context_holds_csrf_and_form_url` — a frozen dataclass with
  `csrf_form_element: str` and `form_url: str` fields.
- **Green:** `REQUIRED_TOKENS = ("csrf_form_element", "form_url")` as a module-level constant,
  and `@dataclass(frozen=True) class RenderContext` with the two `str` fields (§5.3).

### 1.7 `RegistrationPageHtml`

- **Red:**
  - `test_html_init_defaults` — `form_html == ""`, id generated, timestamps set
  - `test_html_init_keeps_given_id`
  - `test_update_html_sets_value_and_bumps_updated_at`
  - `test_render_substitutes_both_tokens` — `form_html` containing `{{ csrf_form_element }}` and
    `{{ form_url }}` → both replaced with the `RenderContext` values
  - `test_render_leaves_unknown_braces_untouched` — a literal `{{ something_else }}` (e.g. in
    author prose or CSS) survives unchanged
  - `test_render_with_no_tokens_returns_html_unchanged`
  - `test_readiness_problems_empty_when_html_ready` — non-empty HTML containing both tokens → `[]`
  - `test_readiness_problems_reports_empty_html` — whitespace-only `form_html` → non-empty list
  - `test_readiness_problems_reports_missing_token` — HTML missing `{{ form_url }}` (and/or
    `{{ csrf_form_element }}`) → list names the missing token(s)
  - `test_html_create_detached_copy`
- **Green:** implement `RegistrationPageHtml` per §3.3. `render(self, ctx: RenderContext) -> str`
  does `str.replace("{{ csrf_form_element }}", ctx.csrf_form_element)` then the same for
  `form_url`; tokens not in `REQUIRED_TOKENS` are left alone. `readiness_problems()` returns a
  message when `form_html.strip()` is falsy, plus one per missing required token.

### 1.8 `HtmlSource` protocol

- **Red:** `test_registration_page_html_is_an_html_source` —
  `isinstance(RegistrationPageHtml(...), HtmlSource)` is `True` (requires `@runtime_checkable`).
- **Green:** `@runtime_checkable class HtmlSource(Protocol)` with `render(self, ctx:
RenderContext) -> str` and `readiness_problems(self) -> list[str]`.

### 1.9 `publish` / `unpublish` / `readiness_problems`

`publish` and `readiness_problems` take the active `HtmlSource` as a parameter (§3.1). The
concrete `RegistrationPageHtml` is already built (1.7), so use a real one in these tests — or a
tiny `_StubSource` with a `readiness_problems()` method if you want to isolate the page logic.

- **Red:**
  - `test_readiness_problems_empty_when_ready` — non-empty `url_slug` + source with no problems
    → `[]`
  - `test_readiness_problems_reports_missing_url_slug` — empty `url_slug` → list contains a
    human-readable string about the URL slug
  - `test_readiness_problems_includes_source_problems` — source returns `["..."]` → those
    strings appear in the result
  - `test_publish_sets_is_published` — ready combo → `is_published is True`, `updated_at` bumped
  - `test_publish_raises_when_not_ready` — raises `RegistrationPageNotReady` (the **domain**
    exception — see note)
  - `test_unpublish_clears_is_published` — `updated_at` bumped; `preview_token` untouched (Q12)
- **Note on the exception (decided):** `RegistrationPageNotReady` is a **domain** exception
  defined in `domain/registration_page.py`, carrying `.problems: list[str]`, and **re-exported**
  from `service_layer/exceptions.py` for service-layer callers. This keeps the domain layer from
  importing the service layer.
- **Green:** implement `readiness_problems(source)`, `publish(source)`, `unpublish()`.

### 1.10 `is_visible_with` and `regenerate_preview_token`

- **Red:**
  - `test_is_visible_with_published_is_always_visible` — published → `True` for any token incl. `""`
  - `test_is_visible_with_unpublished_needs_matching_token` — unpublished + matching non-empty
    token → `True`; wrong token → `False`; empty token → `False`
  - `test_regenerate_preview_token_changes_token` — token differs, `updated_at` bumped
- **Green:** implement both.

### 1.11 `create_detached_copy`, `__eq__`, `__hash__`

- **Red:** `test_create_detached_copy_is_equal_independent_object` (equal by id, `is not` the
  original, all fields copied), `test_eq_by_id`, `test_hash_by_id`.
- **Green:** implement per the `Assembly` / `PasswordResetToken` pattern.

**End of Phase 1:** `uv run pytest tests/unit/domain/test_registration_page.py
tests/unit/test_validators.py -q` green; `just check` clean. Commit.

---

## Phase 2 — Adapters layer ✅ COMPLETE

### 2.1 ORM tables — `src/opendlp/adapters/orm.py`

Add `registration_pages` and `registration_page_html_sources` exactly as `plan-data-service.md`
§4.1 specifies (partial unique indexes on `url_slug` / `short_url_slug` via
`postgresql_where=text("...")`, `EnumAsString(RegistrationPageSource, 32)`, `TZAwareDatetime`,
`aware_utcnow` defaults).

No standalone test — exercised by 2.2 and 2.3. Run `uv run python -c "from opendlp.adapters
import orm"` to catch syntax/import errors immediately.

### 2.2 Imperative mapping — `src/opendlp/adapters/database.py` + `domain/assembly.py`

Per decision §0.2(2), the `Assembly` aggregate is **not** touched structurally — no relationship,
no `__init__` change.

- Add plain `map_imperatively` calls for `RegistrationPage` and `RegistrationPageHtml` (no
  `properties=`, no back-relation). They are mapped independently; the service layer resolves
  page ↔ source explicitly via `source_type`.
- In `domain/assembly.py`: add a short comment near the other sub-config attributes noting that a
  `registration_page` relationship could be hung off `Assembly` later if desired, but is
  deliberately decoupled for now (the FK + repo `get_by_assembly_id` are the access path).
- **Red:** add a round-trip test to `tests/integration/test_orm.py`:
  `test_registration_page_round_trips` — construct a `RegistrationPage` + `RegistrationPageHtml`,
  add to a session, commit, expire, reload by id, assert fields survive (incl. `source_type`
  enum and tz-aware datetimes).
- **Green:** the mapping.
- **Regression watch (low risk now).** Since `Assembly` is untouched, the blast radius is small,
  but still run `uv run pytest tests/integration/test_orm.py -q` to confirm the mapper registry
  is happy with the two new mappings.

### 2.3 Migration

```bash
uv run alembic revision --autogenerate -m "add registration pages"
```

Review the generated file by hand: confirm both tables, both **partial** unique indexes
(autogenerate sometimes misses `postgresql_where` — add it manually if so), FK `ondelete`
clauses, and that nothing unrelated was swept in. Then `uv run alembic upgrade head` against the
local DB and confirm it applies and `downgrade` is sane.

Also update the test-data cleanup (FK order — children before parents, both before `assemblies`):

- `tests/conftest.py` `_delete_all_test_data()` — add `DELETE FROM
registration_page_html_sources;` then `DELETE FROM registration_pages;`
- `tests/bdd/conftest.py` `delete_all_except_standard_users()` — same two deletes.

### 2.4 Abstract repositories — `src/opendlp/service_layer/repositories.py`

Add `RegistrationPageRepository` and `RegistrationPageHtmlRepository` ABCs per
`plan-data-service.md` §4.4 (`get_by_assembly_id`, `get_by_url_slug`, `get_by_short_url_slug`,
`delete` for the page; `get_by_page_id`, `delete` for the HTML source). No test — interfaces.

### 2.5 SQL repositories — `src/opendlp/adapters/sql_repository.py`

Implement `SqlAlchemyRegistrationPageRepository` and `SqlAlchemyRegistrationPageHtmlRepository`
(subclassing `SqlAlchemyRepository` like the others). Use `orm.registration_pages.c.*` column
references in filters, per CLAUDE.md mypy guidance. `get_by_url_slug` / `get_by_short_url_slug`
**short-circuit on empty input** (`return None` without a query) so an unset slug column can't
match.

### 2.6 Fake repositories — `tests/fakes.py`

Add `FakeRegistrationPageRepository` and `FakeRegistrationPageHtmlRepository` (subclass
`FakeRepository`), mirroring the SQL behaviour — including the empty-input short-circuit, so the
contract tests stay honest.

### 2.7 Wire the Unit of Work

- `service_layer/unit_of_work.py`: add `registration_pages` and `registration_page_html_sources`
  attrs to `AbstractUnitOfWork`; instantiate both in `SqlAlchemyUnitOfWork.__enter__`.
- `tests/fakes.py` `FakeUnitOfWork`: instantiate both fakes in `__init__` and clear them in
  `rollback()`.
- **Red/green:** add assertions to `tests/unit/test_unit_of_work.py` (if it checks repo wiring)
  that the two new repos are present on the UoW.

### 2.8 Contract tests

New files `tests/contract/test_registration_page_repo.py` and
`tests/contract/test_registration_page_html_repo.py`, following
`test_assembly_gsheet_repo.py`'s shape (a `_add_*` helper, test classes, the
`params=["fake","sql"]` backend fixture).

- In `tests/contract/conftest.py`: add `registration_page_backend` and
  `registration_page_html_backend` fixtures (fake + SQL variants), import the new SQL + fake repo
  classes. The HTML-source backend's tests need a parent `RegistrationPage` row first — add a
  `make_registration_page` helper to the backend (SQL variant persists it; fake variant just
  returns it), or build it inline in the per-test `_add_*` helper.
- **Red:** write the test bodies first (they fail to import the fixture / repo).
- **Green:** the fixtures + repos from 2.5/2.6 make them pass.
- Cover: `add` + `get`, `get` nonexistent → `None`, `all`, `get_by_assembly_id`,
  `get_by_url_slug` / `get_by_short_url_slug` (hit, miss, **empty input → None**),
  `get_by_page_id`, `delete`. Both backends must agree.

**End of Phase 2:** `CI=true uv run pytest tests/contract/test_registration_page_repo.py
tests/contract/test_registration_page_html_repo.py tests/integration/test_orm.py -q` green;
`just check` clean. Commit.

---

## Phase 3 — Config (size limits) ✅ COMPLETE

Done early — before the service layer — so the size checks in Phase 4 have a real config helper
to call rather than a stub.

- `src/opendlp/config.py`: add `get_registration_form_html_max_bytes()` and
  `get_registration_thank_you_html_max_bytes()`, modelled on `get_max_csv_upload_mb()` —
  read env var, default (`204800` / `51200`), clamp with a logged warning on bad/out-of-range
  input.
- **Red:** add cases to `tests/unit/test_config.py` — default when unset, override honoured,
  invalid value falls back to default with a warning.
- **Green:** implement.
- Document both vars in `env.example` and `docs/configuration.md`.

**End of Phase 3:** `CI=true uv run pytest tests/unit/test_config.py -q` green; `just check`
clean. Commit (or fold into the Phase 4 commit).

---

## Phase 4 — Service layer ✅ COMPLETE

New file: `src/opendlp/service_layer/registration_page_service.py` (its own file — **not**
appended to `assembly_service.py`, which is already flagged for splitting). New test file:
`tests/unit/test_registration_page_service.py`, using `FakeUnitOfWork` and the contract-conftest
`make_user` / `make_assembly` helpers (or the existing `tests/unit/test_assembly_service.py`
fixtures — match whatever that file does).

Each function follows the `assembly_service` pattern: load user (`uow.users.get(user_id)` →
`UserNotFoundError`), load assembly (`uow.assemblies.get(assembly_id)` → `AssemblyNotFoundError`),
permission check, do the work, `uow.commit()`, return a `create_detached_copy()`.

### 4.1 `RegistrationPageNotReady` exception

Per the decision in 1.9, `RegistrationPageNotReady` is defined in
`domain/registration_page.py`. **Re-export** it from `service_layer/exceptions.py` so
service-layer callers import it from the usual place. One test that it carries the `.problems`
list.

### 4.2 `create_registration_page`

- **Red:**
  - `test_create_makes_page_and_html_source` — returns a `RegistrationPage`, and a matching
    `RegistrationPageHtml` row exists for it; `source_type == HTML`
  - `test_create_raises_if_already_exists` (Q11)
  - `test_create_requires_manage_permission` — a view-only user → `InsufficientPermissions`
  - `test_create_raises_assembly_not_found`
  - `test_create_raises_user_not_found`
- **Green:** create the page row + the HTML child row in one transaction.

### 4.3 `get_registration_page` / `get_registration_page_with_source`

- **Red:** returns `None` when not created; returns the page (and the loaded source, by
  `source_type`) when it exists; permission checks (`can_view_assembly` — read-only members may
  read, per Q10 / §6); not-found errors.
- **Green:** implement.

### 4.4 `update_registration_page` (slugs only — thank-you split out per the agreed deltas #2)

- **Red:**
  - `test_update_slugs_happy_path`
  - `test_update_slug_rejects_duplicate` — another page already owns the `url_slug` → `ValueError`
    (pre-flush per-column check; same for `short_url_slug`)
  - `test_update_slug_allows_same_page_keeping_its_own_slug` (clash check excludes `self`)
  - `test_update_slug_rejected_when_published` (Q6) → `ValueError`
  - permission + not-found cases
- **Green:** implement with the per-column uniqueness check from §5.1.

### 4.5 `update_thank_you_html`

- **Red:** happy path; **size-limit rejection** (`> get_registration_thank_you_html_max_bytes()`
  from the Phase 3 config helper → `ValueError` with a friendly message); permission +
  not-found cases.
- **Green:** implement; size check before mutate.

### 4.6 `update_registration_page_html`

- **Red:** happy path; **size-limit rejection** (`get_registration_form_html_max_bytes()`, the
  Phase 3 config helper); `test_rejects_when_source_type_not_html` (defensive — only HTML source
  supported in v1); page-not-created → appropriate error; permission + not-found cases.
- **Green:** implement.

### 4.7 `publish_registration_page` / `unpublish_registration_page`

- **Red:**
  - `test_publish_happy_path` — ready page → `is_published True`
  - `test_publish_raises_not_ready_with_problems` — empty `url_slug`, empty `form_html`, or HTML
    missing a required token → `RegistrationPageNotReady`, `.problems` lists the reasons
  - `test_unpublish_happy_path`
  - permission + not-found cases
- **Green:** load page + source via `get_registration_page_with_source`, delegate to the domain
  `publish(source)` / `unpublish()`.

### 4.8 `regenerate_preview_token`

- **Red:** token changes and is persisted; permission + not-found cases.
- **Green:** implement.

### 4.9 Public lookup + visibility (no `user_id`, no auth — §5.2)

- **Red:**
  - `test_find_by_url_slug` hit / miss / empty input → `None`
  - `test_find_by_short_url_slug` hit / miss / empty input → `None`
  - `resolve_visibility` (pure function) truth table: not found → not visible; published →
    visible, `is_preview False`; unpublished + matching token → visible, `is_preview True`;
    unpublished + wrong/empty token → not visible
  - `get_page_and_source_for_render` returns the source matching `source_type`
- **Green:** implement `find_registration_page_by_url_slug`,
  `find_registration_page_by_short_url_slug`, `RegistrationPageVisibility` dataclass,
  `resolve_visibility`, `get_page_and_source_for_render`.

### 4.10 `render_thank_you_html`

- **Red:** `test_render_thank_you_html_returns_verbatim` — returns `page.thank_you_html`
  unchanged (no substitutable tokens in v1; the function exists as a seam for the
  form-submission story to add `{{ respondent_name }}` etc.).
- **Green:** implement the one-liner per `plan-data-service.md` §5.3.

**End of Phase 4:** `CI=true uv run pytest tests/unit/test_registration_page_service.py -q`
green; `just check` clean.

---

## Phase 5 — Full verification ✅ COMPLETE

1. `CI=true uv run pytest --ignore=tests/bdd` — full non-BDD suite green (2732 passed). The BDD
   browser suite could not be run in this environment: Playwright browsers are not installed
   (`playwright install` needed) — a pre-existing environment limitation unrelated to this work.
2. `just check` — prek, mypy, deptry all clean.
3. `uv run alembic upgrade head` then `downgrade -1` then `upgrade head` on the local DB — the
   migration applies and is reversible.
4. Confirmed no `entrypoints/` or `templates/` file was touched by this work.

---

## File-by-file summary

### New files

| Path                                                     | Phase |
| -------------------------------------------------------- | ----- |
| `src/opendlp/domain/registration_page.py`                | 1     |
| `tests/unit/domain/test_registration_page.py`            | 1     |
| `src/opendlp/service_layer/registration_page_service.py` | 4     |
| `tests/unit/test_registration_page_service.py`           | 4     |
| `tests/contract/test_registration_page_repo.py`          | 2     |
| `tests/contract/test_registration_page_html_repo.py`     | 2     |
| `migrations/versions/XXXX_add_registration_pages.py`     | 2     |

### Modified files

| Path                                        | Change                                                                      | Phase |
| ------------------------------------------- | --------------------------------------------------------------------------- | ----- |
| `src/opendlp/domain/validators.py`          | `UrlSlugValidator`, `RESERVED_SLUGS`                                        | 1     |
| `tests/unit/test_validators.py`             | slug validator tests                                                        | 1     |
| `src/opendlp/domain/assembly.py`            | comment only — note a `registration_page` relationship could be added later | 2     |
| `src/opendlp/adapters/orm.py`               | two new tables                                                              | 2     |
| `src/opendlp/adapters/database.py`          | two plain `map_imperatively` calls (no Assembly relationship)               | 2     |
| `src/opendlp/adapters/sql_repository.py`    | two SQL repos                                                               | 2     |
| `src/opendlp/service_layer/repositories.py` | two repo ABCs                                                               | 2     |
| `src/opendlp/service_layer/unit_of_work.py` | wire two repos                                                              | 2     |
| `src/opendlp/service_layer/exceptions.py`   | re-export `RegistrationPageNotReady` from the domain                        | 4     |
| `tests/fakes.py`                            | two fake repos + `FakeUnitOfWork` wiring                                    | 2     |
| `tests/contract/conftest.py`                | two backend fixtures + `make_registration_page` helper                      | 2     |
| `tests/integration/test_orm.py`             | round-trip test                                                             | 2     |
| `tests/unit/test_unit_of_work.py`           | repo-wiring assertions                                                      | 2     |
| `tests/conftest.py`                         | two `DELETE` statements                                                     | 2     |
| `tests/bdd/conftest.py`                     | two `DELETE` statements                                                     | 2     |
| `src/opendlp/config.py`                     | two size-limit helpers                                                      | 3     |
| `tests/unit/test_config.py`                 | size-limit tests                                                            | 3     |
| `env.example`, `docs/configuration.md`      | document two env vars                                                       | 3     |

---

## Open questions carried from `plan-data-service.md`

None block this build. For the record:

- **Q15** — settled as Option A: two-token flat substitution (§0.1).
- **Q8** — subsumed by Q15.
- `plan-data-service.md` §8 items (`Respondent` creation, `TEST_SUBMISSION` status, field
  mapping, rate-limiting, thank-you substitution context, slug-change-after-submission) are all
  the form-submission story — untouched here.

---

## Phase 6 — Align with updated plan after the 2026-05-15 decisions — TODO

**Why this phase exists.** Phases 1–5 above shipped the data + service layer per
`plan-data-service.md` _as it stood on 2026-05-14_. Since then `plan-data-service.md` has been
updated to record four decisions captured in `deltas-to-fix.md`:

1. The render-time placeholder previously called `{{ form_url }}` is now `{{ form_action }}`
   (deltas §4).
2. `create_registration_page` should seed `RegistrationPage.thank_you_html` with a default
   `<h1>` + `<p>` so the author has something to edit (deltas §7, plan §5.8).
3. Slug-related exceptions must carry enough information for the UI to attribute the error to
   the right field (deltas §12, plan §5.1 "Slug-error specificity").
4. A new `generate_starter_form_html` function (pure helper in the domain layer + service
   wrapper) generates an unstyled HTML form from the assembly's `RespondentFieldDefinition`
   set. **Not** auto-seeded into `form_html`: the UI calls it explicitly and shows the result
   for the author to copy / paste / hand off to an LLM and paste back (deltas §1, plan §5.9).

The route layer is also adopting `?token=<preview_token>` instead of `?preview=<token>` for the
preview URL (deltas §3, plan §2). That is a route-layer concern only — the service-layer
function `resolve_visibility(page, preview_token=...)` already takes a token argument under that
name, so no service- or domain-layer change is needed for it. Nothing to do in this phase for §3.

Same TDD discipline as the rest of this plan (§0.3): red → green → refactor, scoped pytest as
you go, `CI=true just test` and `just check` before each commit. **One commit per sub-phase**
keeps the diffs reviewable; the four sub-phases below are independent and can land in any
order, though 6.4 is the only meaty one.

### 6.1 Rename render token `form_url` → `form_action` ✅ COMPLETE

**Scope.** Pure rename across domain, tests, and existing fixture HTML. No behaviour change.

**Affected files (search the working tree to confirm before editing — there may be more than
the list below by the time this phase starts):**

| File                                                         | What changes                                                                            |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| `src/opendlp/domain/registration_page.py`                    | `REQUIRED_TOKENS` tuple, `RenderContext.form_url` → `form_action`, the `replace()` call |
| `tests/unit/domain/test_registration_page.py`                | `READY_HTML` fixture, two test names (`*_form_url`), all `form_url=` kwargs and asserts |
| `tests/unit/test_registration_page_service.py`               | `READY_HTML` fixture, any `form_url=` kwargs                                            |
| `tests/integration/test_orm.py`                              | The two `form_html` fixture strings around line 1111/1133                               |

**TDD shape.** Search-and-replace at this scale is one mechanical edit; a single failing test
isn't useful here. Approach:

1. **Rename in the production code** (`registration_page.py` only).
2. Run `CI=true uv run pytest tests/unit/domain/test_registration_page.py
   tests/unit/test_registration_page_service.py tests/integration/test_orm.py -q`. Watch the
   `form_url` tests fail (expected — they reference the old token).
3. **Rename in the tests / fixtures** to match.
4. Re-run the same scoped pytest. Green.
5. `CI=true just test` to confirm nothing else in the suite was relying on the old name; `just
check` for the lint/type pass. Commit.

**Suggested commit message:**
`refactor(registration): rename render-time token form_url to form_action`

### 6.2 Default thank-you HTML on create ✅ COMPLETE

**Scope.** New module-level constant + a one-line change in `create_registration_page`.

#### 6.2.1 `DEFAULT_THANK_YOU_HTML` constant

`src/opendlp/domain/registration_page.py`:

```python
DEFAULT_THANK_YOU_HTML = (
    "<h1>Thank you for registering</h1>\n"
    "<p>Your registration has been received. We'll be in touch.</p>\n"
)
```

- **Red:** `test_default_thank_you_html_has_h1_and_p` in
  `tests/unit/domain/test_registration_page.py` — asserts the constant is non-empty, contains
  `<h1>` and `<p>`. (Trivial, but it's the spec — if a future PR shrinks the default to a bare
  string, the test surfaces it.)
- **Green:** add the constant.

#### 6.2.2 `create_registration_page` seeds it

- **Red:** add `test_create_seeds_default_thank_you_html` to
  `tests/unit/test_registration_page_service.py` — call `create_registration_page`, fetch the
  returned page, assert `page.thank_you_html == DEFAULT_THANK_YOU_HTML`. Also assert
  `RegistrationPageHtml.form_html == ""` (no auto-seeding of the form HTML — that contract
  matters for 6.4).
- **Green:** in `registration_page_service.create_registration_page`, change

  ```python
  page = RegistrationPage(assembly_id=assembly_id, source_type=source_type)
  ```

  to

  ```python
  page = RegistrationPage(
      assembly_id=assembly_id,
      source_type=source_type,
      thank_you_html=DEFAULT_THANK_YOU_HTML,
  )
  ```

  (import the constant from `opendlp.domain.registration_page`).

**Existing tests to update.** Any service-layer test that asserts `thank_you_html == ""` after
`create_registration_page` becomes wrong. Grep for `thank_you_html` in the test files and adjust
the small number of spots — switch to `DEFAULT_THANK_YOU_HTML` or set thank-you HTML
explicitly via `update_thank_you_html`.

**Suggested commit message:** `feat(registration): seed default thank-you HTML on create`

### 6.3 Slug-error specificity ✅ COMPLETE

**Scope.** Make slug failures distinguishable by (a) which slug column and (b) what kind of
failure, so the UI can attach errors to the right field. Per `plan-data-service.md` §5.1, the
chosen mechanism (distinct exception subclasses vs. an attribute on the raised error) is left
to the implementation.

**Recommendation.** Use a single new exception class with structured attributes — fewer types
to import and remember, and the route layer only needs `except SlugError: ...` once.

```python
# In src/opendlp/service_layer/exceptions.py (or domain/registration_page.py if we want to
# keep slug rules in the domain — pick one place; service_layer/exceptions.py matches where
# RegistrationPageNotReady is re-exported from today, so callers have a consistent import path)

class SlugError(ValueError):
    """A registration-page slug failed validation or uniqueness.

    `field` is one of {"url_slug", "short_url_slug"}.
    `reason` is one of {"taken", "reserved", "malformed", "too_long", "empty"}.
    """
    def __init__(self, field: str, reason: str, message: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(message)
```

Subclassing `ValueError` keeps backwards compatibility with any existing `except ValueError:`
clauses (there shouldn't be any — but it costs nothing).

#### 6.3.1 Validator changes

`src/opendlp/domain/validators.py` — `UrlSlugValidator.validate` currently raises bare
`ValueError`s. The validator doesn't know which column the value is for, so it can't set
`.field` itself; the caller has to. Two options:

- **(a)** Validator raises a new `InvalidSlug(reason: str, message: str)` (no `field`); the
  caller catches it and re-raises as `SlugError(field=..., reason=..., message=...)`.
- **(b)** Validator stays as-is (bare `ValueError`); the caller maps to `SlugError`.

Recommendation: **(a)**. It carries the kind-of-failure (reserved vs malformed vs too-long
vs empty) up to the caller without reparsing the message string, and keeps the validator
deterministic about its own classifications.

- **Red:** add tests to `tests/unit/test_validators.py`: each rejection case (empty,
  >100 chars, malformed, reserved) raises `InvalidSlug` with the expected `.reason` value.
- **Green:** add `InvalidSlug` to `domain/validators.py` (or co-locate with `SlugError`), make
  `UrlSlugValidator.validate` raise it.

#### 6.3.2 Service changes

`src/opendlp/service_layer/registration_page_service.py` — three call sites raise on slug
problems today:

- The `if clash` blocks for `url_slug` and `short_url_slug` in `update_registration_page`
  (lines 122–129).
- `RegistrationPage.__init__` / `update_slugs` propagate `ValueError` from the validator.

Wrap these so the exception always carries `field` and `reason`:

- The clash blocks raise `SlugError(field="url_slug", reason="taken", message=...)` /
  `SlugError(field="short_url_slug", reason="taken", message=...)`.
- The validator-call sites (in `_validated_slug` inside `domain/registration_page.py`, and any
  service-level slug strip / validate paths) catch `InvalidSlug` and re-raise as
  `SlugError(field=<which-column>, reason=e.reason, message=str(e))`. The domain helper
  `_validated_slug` doesn't know the column name — push the wrapping up to
  `RegistrationPage.__init__` / `update_slugs`, where the column _is_ known (one wrap per
  column), or add a `field` parameter to `_validated_slug`.

Recommendation: add a `field: str` parameter to `_validated_slug` and have it do the wrap.
Smallest delta, one place to change.

- **Red:** add tests to `tests/unit/test_registration_page_service.py`:
  - `test_update_slug_raises_slug_error_on_clash_for_url_slug` — `.field == "url_slug"`,
    `.reason == "taken"`.
  - `test_update_slug_raises_slug_error_on_clash_for_short_url_slug` — `.field ==
    "short_url_slug"`, `.reason == "taken"`.
  - `test_update_slug_raises_slug_error_on_reserved_value` — `.field == "url_slug"`,
    `.reason == "reserved"`.
  - `test_update_slug_raises_slug_error_on_malformed_value` — `.field == "url_slug"`,
    `.reason == "malformed"`.
  - One mirror test for `RegistrationPage(..., url_slug="ADMIN")` (the constructor path).
- **Green:** wire the wrap as described.

**Note on `RegistrationPageNotReady`.** That exception (Phase 1.9 / §3.1) already carries a
`.problems` list of human-readable strings. It is _not_ slug-specific and stays as-is.

**Suggested commit message:** `feat(registration): structured SlugError for UI field-specific errors`

### 6.4 Starter HTML form generator (the meaty bit) ✅ COMPLETE

This is the largest piece of the alignment work. Two parts:

- a **pure domain helper** that takes a list of `RespondentFieldDefinition` and returns HTML;
- a **service wrapper** that loads the assembly's schema and delegates.

The pure helper is the heart of it; the wrapper is six lines of permission + load + delegate.
Tests live where the logic does — most of the test surface is on the pure helper.

#### 6.4.1 Where the code lives

- `src/opendlp/domain/registration_page.py` — `generate_starter_form_html(fields:
list[RespondentFieldDefinition]) -> str`. Pure, no `uow`, no I/O. Importable from tests
  without any DB or fake-repo machinery.
- `src/opendlp/service_layer/registration_page_service.py` — `generate_starter_form_html(uow,
user_id, assembly_id) -> str`. Permission check (`can_manage_assembly` per §6 of
  `plan-data-service.md`), `uow.respondent_field_definitions.list_by_assembly(assembly_id)`,
  delegate to the domain helper, return.

Two functions with the same name in different modules — disambiguate by import alias if a test
file ever needs both:

```python
from opendlp.domain.registration_page import generate_starter_form_html as build_starter_html
from opendlp.service_layer.registration_page_service import generate_starter_form_html
```

#### 6.4.2 Output contract (what the helper must produce)

The canonical reference is `docs/agent/610-registration-page-html/example-form-a-raw-html.html`
(now using `{{ form_action }}` post-6.1). A starter for any 16-field schema should produce HTML
in the same shape — not byte-identical to the example, but in the same _shape_:

- A single `<form action="{{ form_action }}" method="post">` wrapper, closed at the end.
- `{{ csrf_form_element }}` immediately inside the form (line 32 in the example).
- Fields grouped under `<h2>{{ group label }}</h2>` headings, in `GROUP_DISPLAY_ORDER`. Skip
  groups with no fields (no empty `<h2>` + nothing).
- Within a group, fields ordered by `RespondentFieldDefinition.sort_order`.
- A `<button type="submit">Register</button>` immediately before `</form>`.

Per-field rendering, keyed off `RespondentFieldDefinition.effective_field_type`:

| `effective_field_type` | Rendered as |
| --- | --- |
| `TEXT`     | `<label for="K">L</label>\n<input type="text" id="K" name="K">` |
| `EMAIL`    | `<label for="K">L</label>\n<input type="email" id="K" name="K">` |
| `LONGTEXT` | `<label for="K">L</label>\n<textarea id="K" name="K"></textarea>` |
| `INTEGER`  | `<label for="K">L</label>\n<input type="number" id="K" name="K">` |
| `BOOL`     | `<fieldset><legend>L</legend>\n<label><input type="radio" name="K" value="yes"> Yes</label>\n<label><input type="radio" name="K" value="no"> No</label>\n</fieldset>` |
| `BOOL_OR_NONE` | same as `BOOL` (yes/no radios). The "not set" state is encoded by the absence of any selection in the submitted form — no third radio. _(Matches example-form-a, lines 41–48.)_ |
| `CHOICE_RADIO` | `<fieldset><legend>L</legend>` + one `<label><input type="radio" name="K" value="V"> V</label>` per `ChoiceOption`, in declaration order, then `</fieldset>`. _(Example-form-a lines 81–86.)_ |
| `CHOICE_DROPDOWN` | `<label for="K">L</label>\n<select id="K" name="K">` + `<option value="V">V</option>` per `ChoiceOption` + `</select>`. **Open question:** include the placeholder `<option value="">— Please choose —</option>` first as the example does (line 99)? Recommendation: **yes**, only when the field is not required, so author has a way to express "no answer" in a select widget. Otherwise required-attribute on the `<select>` covers it. |

Where `K` = `field_key`, `L` = `label`, `V` = `ChoiceOption.value`. Required fields get a
`required` attribute on the input/select (or on _all_ radios in the group? HTML5 says
`required` on any radio in a group makes the group required, which is fine).

**Helpers worth extracting** (private, in the same module): `_render_field`,
`_render_choice_options`, `_render_group`. Keep them small and pass `RespondentFieldDefinition`
in directly so they're easy to unit-test if it ever pays off. Don't over-abstract — these are
internal.

**Things deliberately out of scope** (for v1):

- HTML-escaping of label/value text. `RespondentFieldDefinition.label` and `ChoiceOption.value`
  are author-controlled strings entered via the schema editor — they're trusted. **However**
  they may legitimately contain `<` / `>` / `&` (e.g. "AT&T"). Use `html.escape` on label and
  value text on output. _(Cheap insurance — any author-supplied string lands in HTML; escape it.)_
- `ChoiceOption.help_text` — not rendered. Authors can add it back when they style the form;
  the starter stays minimal.
- Accessibility extras (`aria-describedby`, `<fieldset>` for input groups beyond radio
  choices, etc.) — author concern.
- Any styling: no `class=`, no `<div>` wrappers, no inline styles. The starter is unstyled by
  design (the LLM-styling step is what adds those).
- Internationalisation: the literal strings (`"Yes"`, `"No"`, `"— Please choose —"`,
  `"Register"`) are part of the generated _content_ that the author edits — they're not UI
  chrome the system owns at runtime. Plain English in v1 (the constants are easily reachable
  for a future i18n pass if needed).

#### 6.4.3 TDD breakdown — domain helper

New tests in `tests/unit/domain/test_registration_page.py`. They take a hand-rolled
`list[RespondentFieldDefinition]` directly (no UoW, no fake repo, no DB) — fastest possible.
Group them in a new `class TestGenerateStarterFormHtml:` block.

A small fixture that mints a `RespondentFieldDefinition` with sensible defaults and overridable
kwargs makes the tests readable:

```python
def _field(field_key, group, sort_order, *, label=None, field_type=FieldType.TEXT,
           options=None, is_fixed=False) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=ASSEMBLY_ID,
        field_key=field_key,
        label=label or humanise_field_key(field_key),
        group=group,
        sort_order=sort_order,
        is_fixed=is_fixed,
        field_type=field_type,
        options=options,
    )
```

Tests (one assertion per test where reasonable; a couple of "shape" tests near the end):

1. **Wrapper structure.** Empty schema → output starts with `<form action="{{ form_action }}"
method="post">`, contains `{{ csrf_form_element }}`, ends with `<button
type="submit">Register</button>` followed by `</form>`. (`test_empty_schema_minimal_form`.)
2. **TEXT field.** Single TEXT field → output contains `<label for="x">X</label>` and `<input
type="text" id="x" name="x">`. (`test_text_field_renders_input`.)
3. **EMAIL field.** As above with `type="email"`.
4. **LONGTEXT field.** Renders `<textarea id="K" name="K"></textarea>`.
5. **INTEGER field.** `type="number"`.
6. **BOOL.** `<fieldset><legend>...` + two radios `yes` / `no` in that order; verify exact
   text labels.
7. **BOOL_OR_NONE.** Same shape as BOOL — _no_ third "Not set" radio (per the table above);
   pin this so it doesn't drift.
8. **CHOICE_RADIO with two options.** `<fieldset><legend>` + one radio per option, in
   declaration order; values match `ChoiceOption.value` exactly.
9. **CHOICE_DROPDOWN with two options, not required.** Includes the leading placeholder
   `<option value="">…</option>`; one `<option value="V">V</option>` per option afterwards.
10. **CHOICE_DROPDOWN required.** Placeholder `<option value="">…</option>` _omitted_;
    `required` on the `<select>`.
11. **`is_required`** on a TEXT field → `required` attribute on the `<input>`.
12. **HTML escaping.** A field with `label="AT&T"` → output contains `AT&amp;T`; a
    `ChoiceOption(value="<x>")` → output contains `&lt;x&gt;` in both `value=` and label
    positions.
13. **Group ordering.** Fields in `ABOUT_YOU` (sort_order 0) and `ELIGIBILITY` (sort_order 0)
    → in the output, the `ELIGIBILITY` `<h2>` appears before the `ABOUT_YOU` `<h2>`
    (`GROUP_DISPLAY_ORDER`).
14. **Sort order within group.** Two fields in the same group with sort_order 20 then 10 →
    sort_order 10's input appears first in the output.
15. **Empty groups suppressed.** Single field in `OTHER` → `<h2>Eligibility</h2>` does **not**
    appear in the output.
16. **Group label.** A field in `NAME_AND_CONTACT` → the heading text matches
    `GROUP_LABELS[NAME_AND_CONTACT]` (which is a `lazy_gettext` proxy — `str(label)` to compare).
17. **`effective_field_type` honoured for fixed fields.** A field with
    `field_key="eligible"`, `field_type=FieldType.TEXT`, `is_fixed=True` → still rendered as
    BOOL_OR_NONE (radios), per `effective_field_type`. (Pin the override path so a future
    refactor doesn't quietly bypass it.)
18. **Token round-trip.** Render the generated HTML through
    `RegistrationPageHtml(form_html=generated).render(RenderContext(csrf_form_element="C",
form_action="A"))` → `C` and `A` end up in the right places (`<form action="A">` and where
    `{{ csrf_form_element }}` was). One end-to-end smoke test that proves the generator's
    output is valid input for the renderer — the contract that ties this story together.
19. **Readiness round-trip.** The generated HTML satisfies
    `RegistrationPageHtml(form_html=generated).readiness_problems() == []` (i.e. it includes
    both required tokens and is non-empty). This is the test that catches a future regression
    where someone changes `REQUIRED_TOKENS` but forgets the generator.
20. **Realistic 16-field schema (shape test).** Build the same 16 fields as
    `example-form-a-raw-html.html` (the assembly used to seed it) — assert: every `field_key`
    appears as a `name=` somewhere; every `ChoiceOption.value` appears as a `value=`
    somewhere; the order of `<h2>` headings matches the four groups in the example. Don't
    byte-compare to the example file — author tweaks would diverge — but pin the structural
    properties.

#### 6.4.4 TDD breakdown — service wrapper

New tests in `tests/unit/test_registration_page_service.py` using `FakeUnitOfWork`. Per the
prompt: this is where the FakeRepository test-speed payoff lives — no DB session, no real
SQLAlchemy, just `FakeRespondentFieldDefinitionRepository` populated via `add()`.

A helper to add a fixture schema to the fake repo (similar to the `_add_*` helpers in the
contract tests):

```python
def _populate_schema(uow: FakeUnitOfWork, assembly_id: uuid.UUID,
                    fields: list[RespondentFieldDefinition]) -> None:
    for f in fields:
        uow.respondent_field_definitions.add(f)
```

Tests:

1. **Happy path.** Populate the fake schema with two text fields for the assembly. Call
   `generate_starter_form_html(uow, manager.id, assembly.id)` → returns a string that contains
   both `name="<field_key>"` substrings. (Don't re-test the rendering details here — that's
   §6.4.3's job; assert just enough to prove the wrapper called the helper with the right
   schema.)
2. **Permission failure.** A view-only user → `InsufficientPermissions` (matches every other
   manage-only function in this service file).
3. **Assembly not found.** Unknown `assembly_id` → `AssemblyNotFoundError`.
4. **User not found.** Unknown `user_id` → `UserNotFoundError`.
5. **Empty schema.** Assembly exists but has no fields registered → returns the minimal-form
   string (still contains `{{ csrf_form_element }}` and `{{ form_action }}` and the submit
   button). Pin this — the wrapper must not crash on an empty schema.
6. **Schema for a different assembly is excluded.** Populate fields for `assembly_id_a` _and_
   `assembly_id_b`; call for `assembly_id_a` → output contains only `assembly_a`'s field keys.
   This pins the `list_by_assembly` filter on the wrapper side.
7. **No commit.** This is a read-only operation — `uow.committed` should be `False` after the
   call. (Mirrors the `get_registration_page` test, if there is one; otherwise skip.)

#### 6.4.5 Wiring

- `src/opendlp/service_layer/registration_page_service.py` — import the domain helper, add
  the wrapper.
- No new repository, no new fake — `FakeRespondentFieldDefinitionRepository` already lives on
  `FakeUnitOfWork` (per `tests/fakes.py:746`).
- `tests/unit/test_registration_page_service.py` — top of the file, import
  `FakeUnitOfWork`, `RespondentFieldDefinition`, `RespondentFieldGroup`, `FieldType` (most
  already imported by the existing tests).

#### 6.4.6 Smoke test

Once 6.4.1–6.4.5 are green, do an interactive sanity check via `flask shell`:

```python
from opendlp.bootstrap import bootstrap
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.registration_page_service import generate_starter_form_html

bootstrap()
uow = SqlAlchemyUnitOfWork()
print(generate_starter_form_html(uow, my_user_id, "c8f833a8-...assembly id from example-form-a..."))
```

Diff visually against `example-form-a-raw-html.html`. They won't match exactly (the example has
hand-edited copy and a placeholder option for the dropdown only when the field is not
required), but the shape should match. Any structural surprise here points back at a missing
test in §6.4.3 — add it, fix the helper, repeat.

**Suggested commit message:**
`feat(registration): generate starter HTML form from respondent field schema`

(One commit covering all of 6.4 is fine — the helper and wrapper land together, the tests are
the "review surface".)

### 6.5 Documentation sweep

After 6.1–6.4 are merged, do a final pass:

- `docs/agent/610-registration-page-html/plan-data-service.md` — already aligned (see the
  2026-05-15 status line). No change.
- This file (`plan-data-service-detailed.md`) — mark the four sub-phases above as `✅ COMPLETE`
  as they land, and update the file-by-file summary below.
- `docs/agent/610-registration-page-html/example-form-a-raw-html.html` — already updated to
  use `{{ form_action }}`. No further change.
- Spot-check `docs/configuration.md` and `env.example` — they should still reference
  `REGISTRATION_FORM_HTML_MAX_BYTES` and `REGISTRATION_THANK_YOU_HTML_MAX_BYTES` (Phase 3
  added them); nothing in this phase changes those.

### 6.6 Final verification

`CI=true uv run pytest --ignore=tests/bdd -q` and `just check` clean before the final commit.
The migration is unchanged in this phase, so no Alembic dance needed.

---

## Phase 6 file-by-file summary (additive)

### Modified files

| Path                                                         | Change                                                                                        | Sub-phase |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | --------- |
| `src/opendlp/domain/registration_page.py`                    | Token rename; `DEFAULT_THANK_YOU_HTML`; `generate_starter_form_html` helper                   | 6.1, 6.2.1, 6.4 |
| `src/opendlp/service_layer/registration_page_service.py`     | Seed default thank-you HTML on create; `SlugError` raises; new `generate_starter_form_html` wrapper | 6.2.2, 6.3.2, 6.4 |
| `src/opendlp/service_layer/exceptions.py`                    | New `SlugError` class                                                                         | 6.3       |
| `src/opendlp/domain/validators.py`                           | New `InvalidSlug` exception, `UrlSlugValidator.validate` raises it                            | 6.3.1     |
| `tests/unit/domain/test_registration_page.py`                | Token rename in fixtures; `DEFAULT_THANK_YOU_HTML` test; `TestGenerateStarterFormHtml`        | 6.1, 6.2.1, 6.4.3 |
| `tests/unit/test_registration_page_service.py`               | Token rename; default-thank-you-HTML test; `SlugError` tests; service wrapper tests           | 6.1, 6.2.2, 6.3.2, 6.4.4 |
| `tests/unit/test_validators.py`                              | `InvalidSlug` reason-code tests                                                               | 6.3.1     |
| `tests/integration/test_orm.py`                              | Token rename in fixture HTML strings                                                          | 6.1       |

### No new files in Phase 6

Everything in Phase 6 lands in files that already exist after Phases 1–5.
