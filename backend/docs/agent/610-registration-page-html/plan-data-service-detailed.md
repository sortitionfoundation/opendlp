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

## Phase 5 — Full verification

1. `CI=true just test` — whole suite green, output pristine (CLAUDE.md: no stray errors/warnings).
2. `just check` — mypy, deptry, ruff all clean.
3. `uv run alembic upgrade head` then `downgrade -1` then `upgrade head` on the local DB — the
   migration is reversible.
4. Sanity-grep that no `entrypoints/` file was touched.

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
