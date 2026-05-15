# Registration Page — Data and Service Layer Plan

**Branch:** `610-registration-page-html`
**Date:** 2026-05-13
**Status:** Updated 2026-05-15 — all open questions now resolved. Q15 settled on Option A (system-generated starter HTML, two render-time tokens only). Render-time tokens are `{{ csrf_form_element }}` and `{{ form_action }}` (renamed from `form_url` per `deltas-to-fix.md` §4). Preview query parameter is `?token=<preview_token>` (per `deltas-to-fix.md` §3). All cross-plan deltas are recorded in `deltas-to-fix.md`; `plan-frontend.md` still needs to absorb their implications.

## 1. Scope

This plan covers ONLY:

- The **domain layer**: a `RegistrationPage` aggregate per assembly, plus child `RegistrationPageHtml` row that supplies the form HTML.
- The **adapters layer**: ORM tables, mappings, migration, repository implementations.
- The **service layer**: functions for creating/editing/publishing the page in the backoffice, plus the public-facing lookup-and-render path.

This plan deliberately does NOT cover:

- Blueprint routes (backoffice tab nor the public `/register/<url_slug>` and `/r/<short_url_slug>` routes)
- Templates / HTML / UI
- WTForms classes
- The form-submission endpoint or `Respondent` creation from a submission (next story)
- QR-code generation (presentation concern; uses `qrcode` already pulled in for TOTP)
- Bot protection, image upload, rich text editor, NB sync, auto publish/unpublish on dates (all out of story scope)

Where a question in the plan depends on the design of form submission (next story), it is flagged with **🔮 Depends on form-submission story**.

---

## 2. Big-picture shape

```
Assembly (1) ──── (0..1) RegistrationPage
                              │   ├── url_slug          (globally unique under /r/)
                              │   ├── short_url_slug    (globally unique under /r/)
                              │   ├── is_published
                              │   ├── preview_token
                              │   ├── source_type       (enum: HTML for now)
                              │   ├── thank_you_html
                              │   └── created_at / updated_at
                              │
                              └─(1)── one of these "HTML source" siblings,
                                       picked by source_type
                                       │
                                       └── RegistrationPageHtml
                                            ├── form_html
                                            └── created_at / updated_at

                                       # Future source types (out of scope):
                                       # └── RegistrationPageTemplate (drag-and-drop builder)
                                       # └── ... (translations, A/B variants, ...)
```

Per Q1, the form HTML lives in a **child table** keyed off `registration_page_id`, not on the main `RegistrationPage` row. This is because we anticipate alternative ways to _produce_ the form HTML (a templated drag-and-drop builder, later versions/translations/A-B variants), and the alternative producers will need different schemas. The `source_type` field on `RegistrationPage` says which child table holds the active source. All source-type domain models implement a common `HtmlSource` protocol (see §3.4).

The thank-you HTML stays on the main `RegistrationPage` row for now (one column, no alternative producers). When translations land it will need to be split out — same pressure exists on the form-HTML side, so the split there is the leading edge of this change. See Q13.

### Public URL shape

Aligned with `plan-frontend.md`: the long and short slugs live under **separate path prefixes**.

- Canonical (long) form: `/register/<url_slug>`
- Short form: `/r/<short_url_slug>` — issues a **302** (temporary) redirect to the canonical `/register/<url_slug>` URL (so QR-code scans always land on the canonical address). 302 not 301: short slugs may be cleared and reused later, and a cached permanent redirect would misroute. See Q3.
- Preview of an unpublished page: `/register/<url_slug>?token=<preview_token>`

Because the two slug types live in different namespaces, a string can be a `url_slug` for one page and a `short_url_slug` for another without colliding as URLs. Each slug column therefore only needs to be unique **within its own column**, across all assemblies — no cross-column uniqueness check is required (this simplifies §4.1, §4.4, §5.1 versus the earlier "both under /r/" design). See Q3.

### Module system

`docs/agent/module_design.md` describes a future "modules" system in which a `registration_page` module would own this configuration via a generic `ModuleConfig` JSON blob. Per Q9, ignore the module system for now and build first-class tables. Migrate later if/when the module system lands and the registration page's shape has stabilised.

---

## 3. Domain layer

New file: `src/opendlp/domain/registration_page.py`

### 3.1 `RegistrationPage` aggregate root

```python
class RegistrationPageSource(Enum):
    HTML = "html"
    # TEMPLATE = "template"   # future


class RegistrationPage:
    def __init__(
        self,
        assembly_id: uuid.UUID,
        url_slug: str = "",
        short_url_slug: str = "",
        is_published: bool = False,
        preview_token: str = "",          # auto-generated if blank
        source_type: RegistrationPageSource = RegistrationPageSource.HTML,
        thank_you_html: str = "",
        registration_page_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        # validate slugs (see UrlSlugValidator)
        # auto-generate preview_token if empty
        ...

    # mutation methods (all bump updated_at):
    def update_slugs(self, url_slug: str | None = None, short_url_slug: str | None = None) -> None:
        """Raise if is_published — slugs are frozen once published (Q6)."""
    def update_thank_you_html(self, thank_you_html: str) -> None: ...
    def publish(self, source: "HtmlSource") -> None:
        """Raise RegistrationPageNotReady if the combination of self + source
        isn't publishable. Sets is_published=True."""
    def unpublish(self) -> None: ...
    def regenerate_preview_token(self) -> None: ...

    # read helpers:
    def is_visible_with(self, token: str = "") -> bool:
        """True if published, or if `token` matches preview_token and is non-empty."""
    def readiness_problems(self, source: "HtmlSource") -> list[str]:
        """Human-readable reasons the (page, source) combo isn't publishable.
        Empty list = ready to publish."""

    def create_detached_copy(self) -> "RegistrationPage": ...
    # __eq__ / __hash__ by id, like other aggregates
```

Notes:

- `form_html` is NOT on this class. It's on `RegistrationPageHtml` (see §3.3). The aggregate root holds the cross-source metadata.
- `publish()` and `readiness_problems()` take the active `HtmlSource` as a parameter because publish-readiness depends on the source (e.g. the HTML source needs its required-template tokens present). Callers must load the source first; the service layer wraps this.
- `preview_token` is generated with `secrets.token_urlsafe(32)` — same approach as `password_reset.py`. Stored plaintext (low-stakes: worst case is preview access to draft form HTML; no PII, no write).
- Empty slug strings mean "not set yet". Uniqueness enforced at DB level via partial unique indexes on `WHERE slug != ''` (Q2 confirmed).
- Per Q6, `update_slugs` raises while `is_published=True`. Caller must unpublish first.

### 3.2 Readiness rules

A `(page, source)` combo is publishable iff:

- `page.url_slug` is non-empty.
- `source.readiness_problems()` returns an empty list. For `RegistrationPageHtml`, that means:
  - `form_html` non-empty (after strip)
  - `form_html` contains both `{{ csrf_form_element }}` and `{{ form_action }}`

`thank_you_html` is NOT required to publish (Q5 confirmed). If empty at submit time, the form-submission route falls back to a Jinja template owned by the public blueprint.

🔮 **Depends on form-submission story:** the canonical list of required template tokens may grow (honeypot, version pin, schema fields). Keep `REQUIRED_TOKENS` as a module-level constant easy to extend.

### 3.3 `RegistrationPageHtml`

```python
class RegistrationPageHtml:
    """The HTML source-of-truth when RegistrationPage.source_type == HTML."""

    def __init__(
        self,
        registration_page_id: uuid.UUID,
        form_html: str = "",
        html_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        ...

    def update_html(self, form_html: str) -> None: ...

    # Conforms to HtmlSource protocol:
    def render(self, ctx: "RenderContext") -> str:
        """Substitute {{ token }} placeholders in form_html."""
    def readiness_problems(self) -> list[str]:
        """Returns missing-requirement strings for publishing."""

    def create_detached_copy(self) -> "RegistrationPageHtml": ...
```

### 3.4 `HtmlSource` protocol

```python
class HtmlSource(Protocol):
    """All registration-page source-type models conform to this."""
    def render(self, ctx: "RenderContext") -> str: ...
    def readiness_problems(self) -> list[str]: ...
```

Using `typing.Protocol` (structural) rather than an ABC. Reason: the source classes live in different files and have different storage shapes; we don't want to force inheritance just for two methods. Protocol works for both mypy and for `isinstance` checks (with `runtime_checkable`). See Q14.

### 3.5 Slug validator

```python
# In opendlp.domain.validators (existing module)
class UrlSlugValidator:
    """lowercase ASCII alphanumerics + hyphens, 1–100 chars, no leading/trailing hyphen.

    Rejects values in RESERVED_SLUGS."""
```

`RESERVED_SLUGS = frozenset({"preview", "submit", "admin", "static", "assets"})` — disallow list applied to both `url_slug` and `short_url_slug` (same validator), guarding against collisions with reserved sub-paths we might mount under `/register/` or `/r/`.

Uniqueness is per-column only: `url_slug` unique among `url_slug`s, `short_url_slug` unique among `short_url_slug`s (see §4.1). The two columns are independent namespaces, so no cross-column check is needed. Within one page, `url_slug` and `short_url_slug` may legitimately differ or even be unset independently.

### 3.6 No `RespondentSourceType` change needed

`RespondentSourceType.REGISTRATION_FORM` already exists — used by the form-submission story, not by this one.

---

## 4. Adapters layer

### 4.1 ORM tables

In `src/opendlp/adapters/orm.py`:

```python
registration_pages = Table(
    "registration_pages",
    metadata,
    Column("id", PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "assembly_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("assemblies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,             # one registration page per assembly
    ),
    Column("url_slug", String(100), nullable=False, default=""),
    Column("short_url_slug", String(30), nullable=False, default=""),
    Column("is_published", Boolean, nullable=False, default=False, index=True),
    Column("preview_token", String(64), nullable=False),
    Column("source_type", EnumAsString(RegistrationPageSource, 32), nullable=False),
    Column("thank_you_html", Text, nullable=False, default=""),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("updated_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    # Partial unique indexes — only enforce uniqueness when the slug is set:
    Index("ix_registration_pages_url_slug_unique",
          "url_slug", unique=True,
          postgresql_where=text("url_slug != ''")),
    Index("ix_registration_pages_short_url_slug_unique",
          "short_url_slug", unique=True,
          postgresql_where=text("short_url_slug != ''")),
)

registration_page_html_sources = Table(
    "registration_page_html_sources",
    metadata,
    Column("id", PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "registration_page_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("registration_pages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,             # one HTML source per page
    ),
    Column("form_html", Text, nullable=False, default=""),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Column("updated_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
)
```

Sizing: 100 chars for `url_slug`, 30 chars for `short_url_slug`. HTML stored as `Text`. Per Q4, size limits are enforced at the **service layer** (so we can give a friendly error) and are **configurable via env vars** — see §5.6.

**Slug uniqueness:** the two partial unique indexes above each cover one column. Because `/register/<url_slug>` and `/r/<short_url_slug>` are separate path namespaces (see §2), per-column uniqueness is sufficient — there is no cross-column constraint to enforce. The DB partial unique indexes are the real guard; the service layer adds a pre-flush check only to turn an `IntegrityError` into a friendly message.

### 4.2 Imperative mapping

In `src/opendlp/adapters/database.py`, alongside other `map_imperatively` calls:

- Map `RegistrationPage` ↔ `registration_pages` with a `relationship` to `Assembly` (back-populated as `Assembly.registration_page`, `uselist=False`).
- Map `RegistrationPageHtml` ↔ `registration_page_html_sources` (no relationship back to RegistrationPage needed — the service layer resolves it explicitly via `source_type`).
- Update the `Assembly` mapping to add `registration_page: relationship(..., uselist=False, cascade="all, delete-orphan")`.
- Update `Assembly.__init__` and `Assembly.create_detached_copy()` to know about the new attribute.

### 4.3 Migration

`migrations/versions/XXXX_add_registration_pages.py`:

1. Create `registration_pages` table.
2. Create the two partial unique indexes on `url_slug` and `short_url_slug`.
3. Create `registration_page_html_sources` table.

No backfill — pages and source rows are created explicitly via the backoffice (Q11).

Also: add `DELETE FROM registration_page_html_sources` and `DELETE FROM registration_pages` to `_delete_all_test_data()` in `tests/conftest.py` and `delete_all_except_standard_users()` in `tests/bdd/conftest.py` (in that order, before `DELETE FROM assemblies`).

### 4.4 Repositories

Two new abstract repos in `service_layer/repositories.py`:

```python
class RegistrationPageRepository(AbstractRepository):
    @abc.abstractmethod
    def get_by_assembly_id(self, assembly_id: uuid.UUID) -> RegistrationPage | None: ...
    @abc.abstractmethod
    def get_by_url_slug(self, url_slug: str) -> RegistrationPage | None: ...
    @abc.abstractmethod
    def get_by_short_url_slug(self, short_url_slug: str) -> RegistrationPage | None: ...
    @abc.abstractmethod
    def delete(self, item: RegistrationPage) -> None: ...


class RegistrationPageHtmlRepository(AbstractRepository):
    @abc.abstractmethod
    def get_by_page_id(self, registration_page_id: uuid.UUID) -> RegistrationPageHtml | None: ...
    @abc.abstractmethod
    def delete(self, item: RegistrationPageHtml) -> None: ...
```

`get_by_url_slug` and `get_by_short_url_slug` short-circuit on empty input (return None without a query) so an unset slug column can't accidentally match.

SQL implementations in `adapters/sql_repository.py` (use `orm.registration_pages.c.*` for filters per CLAUDE.md mypy guidance).

### 4.5 Unit of work

Add to `AbstractUnitOfWork`:

```python
registration_pages: RegistrationPageRepository
registration_page_html_sources: RegistrationPageHtmlRepository
```

Wire both in `SqlAlchemyUnitOfWork.__enter__`.

---

## 5. Service layer

New file: `src/opendlp/service_layer/registration_page_service.py`

### 5.1 Management functions

All take `uow`, `user_id`, `assembly_id`, follow the existing `assembly_service` pattern. All require `can_manage_assembly` per §6.

```python
def create_registration_page(
    uow, user_id, assembly_id,
    *,
    source_type: RegistrationPageSource = RegistrationPageSource.HTML,
) -> RegistrationPage:
    """Explicit create (Q11). Raises if the assembly already has one.
    Creates the page row AND the matching source-type child row in the same
    transaction. Initial source for v1: HTML only.

    Seeds `thank_you_html` with `DEFAULT_THANK_YOU_HTML` so the author has
    something to edit (see §5.8). The form-HTML child row is created empty —
    authors generate a starter via `generate_starter_form_html` (§5.9) and
    paste the result in."""

def get_registration_page(uow, user_id, assembly_id) -> RegistrationPage | None:
    """Returns None if the page hasn't been created yet (Q11)."""

def get_registration_page_with_source(
    uow, user_id, assembly_id,
) -> tuple[RegistrationPage, HtmlSource] | None:
    """Convenience: loads page + the right child row by source_type. None if
    page doesn't exist. Used by backoffice edit view and by publish flow."""

def update_registration_page(
    uow, user_id, assembly_id,
    *,
    url_slug: str | None = None,        # None = leave alone, "" = clear
    short_url_slug: str | None = None,
) -> RegistrationPage:
    """Partial update to the aggregate root's slugs. Per Q6, raises ValueError
    if the page is published and a slug change is attempted. Performs a
    per-column slug uniqueness check before flush so we raise a clean
    ValueError instead of an IntegrityError."""

def update_thank_you_html(
    uow, user_id, assembly_id, thank_you_html: str,
) -> RegistrationPage:
    """Update the thank-you HTML on the aggregate root. Separate from
    update_registration_page so the backoffice can save the thank-you content
    independently of the slug fields. Enforces size limit (§5.6)."""

def update_registration_page_html(
    uow, user_id, assembly_id, form_html: str,
) -> RegistrationPageHtml:
    """Update the form HTML. Enforces size limit (§5.6). Page must already
    exist AND have source_type=HTML."""

def publish_registration_page(uow, user_id, assembly_id) -> RegistrationPage:
    """Loads page + active source, checks readiness, raises
    RegistrationPageNotReady with the list of problems if not ready."""

def unpublish_registration_page(uow, user_id, assembly_id) -> RegistrationPage: ...

def regenerate_preview_token(uow, user_id, assembly_id) -> RegistrationPage: ...
```

`RegistrationPageNotReady` is a new exception in `service_layer/exceptions.py`. It carries the list of problem strings:

```python
class RegistrationPageNotReady(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))
```

**Slug uniqueness check pattern** (per-column, using the existing `get_by_url_slug` / `get_by_short_url_slug` repo methods):

```python
new = url_slug.strip()
if new:
    clash = uow.registration_pages.get_by_url_slug(new)
    if clash and clash.id != page.id:
        raise ValueError(f"The slug {new!r} is already in use by another registration page")
```

Same shape for `short_url_slug` via `get_by_short_url_slug`. The DB partial unique indexes are the real guard; this check just produces a friendly error. No cross-column check — the two slug namespaces are independent (see §2, §4.1).

**Slug-error specificity** (per `deltas-to-fix.md` §12): exceptions raised for slug problems must carry enough information for the UI to attach the error to the correct field — i.e. the message / exception identifies *which* slug column is at fault (`url_slug` vs `short_url_slug`) and *what kind* of failure (taken / reserved / malformed). Implementation can use distinct exception subclasses or a structured attribute on the raised error; pick during implementation. The validator (`UrlSlugValidator`, §3.5) similarly raises with enough detail to distinguish reserved vs malformed.

### 5.2 Public lookup functions

These do **not** take a `user_id` and do **not** check Flask-Login — the public route is anonymous.

The long and short slugs are served by different routes (`/register/<url_slug>` and `/r/<short_url_slug>` — see §2), so each route does an unambiguous single-column lookup. There is no "try one then the other" dispatch.

```python
def find_registration_page_by_url_slug(uow, url_slug: str) -> RegistrationPage | None:
    """For the canonical /register/<url_slug> route. None if not found."""

def find_registration_page_by_short_url_slug(uow, short_url_slug: str) -> RegistrationPage | None:
    """For the /r/<short_url_slug> route. The route 302-redirects to
    /register/<page.url_slug> on a hit. None if not found."""

@dataclass
class RegistrationPageVisibility:
    page: RegistrationPage | None
    is_visible: bool
    is_preview: bool       # True iff visible only because of preview token

def resolve_visibility(
    page: RegistrationPage | None,
    preview_token: str = "",
) -> RegistrationPageVisibility:
    """Pure function. Encodes: not found → not visible; published → visible;
    unpublished + non-empty token matching page.preview_token → visible as preview;
    otherwise not visible."""
```

`resolve_visibility` is pure (no uow) so it's trivially unit-testable and the blueprint stays thin.

For rendering, the route also needs the active source:

```python
def get_page_and_source_for_render(
    uow, page: RegistrationPage,
) -> HtmlSource:
    """Loads the child row matching page.source_type. Used by the public route
    after visibility is resolved as is_visible=True."""
```

### 5.3 Templating / rendering

Q15 settled on **Option A** (system-generated starter HTML, minimal substitution at render time). The user's HTML is author-controlled but trusted (assembly managers are vetted). Rendering is **flat string substitution** — not Jinja, not sandboxed Jinja.

```python
REQUIRED_TOKENS = ("csrf_form_element", "form_action")
OPTIONAL_TOKENS: tuple[str, ...] = ()  # extensible — see form-submission plan

@dataclass(frozen=True)
class RenderContext:
    csrf_form_element: str   # full `<input type="hidden" name="csrf_token" value="...">` HTML
    form_action: str         # absolute or root-relative URL to POST to (lands in `action=`)
```

`RegistrationPageHtml.render(ctx)` does the substitution. Tokens not in `REQUIRED_TOKENS|OPTIONAL_TOKENS` are left untouched (literal `{{ ... }}` in the user's prose stays as-is).

For the thank-you page:

```python
def render_thank_you_html(page: RegistrationPage) -> str:
    """Returns thank_you_html verbatim (no substitutable tokens in v1 — see
    `deltas-to-fix.md` §7). Exists so the route always goes through the
    service, leaving a hook for {{ respondent_name }} etc. once the
    form-submission story lands."""
```

Why string substitution rather than `jinja2.sandbox.SandboxedEnvironment`?

- Sandbox is overkill for two known placeholders.
- `{` and `}` are common in user CSS (`<style>`); Jinja's parser would error on unmatched braces unless we asked users to escape, which is hostile.
- Trivial to extend by adding entries to the substitution dict.

Brace-collision risk: literal `{{` in HTML body that isn't a recognised token won't be touched. CSS uses single braces, no collision.

🔮 **Depends on form-submission story:** the canonical list of substitution tokens may grow (e.g. honeypot field name, version pin). New entries plug into `OPTIONAL_TOKENS` and `RenderContext` without changing the substitution mechanics.

### 5.4 The "registration closed" page

When an unpublished page is hit without a valid preview token, the route 302-redirects (Q7) to a single canonical `/registration-closed` URL served by the public blueprint. The closed page is a regular Jinja template — **not** the user's HTML. No service-layer involvement.

### 5.5 CSRF and dependency injection

The service layer must not import Flask. `csrf_form_element` and `form_action` in `RenderContext` are built by the blueprint (`flask_wtf.csrf.generate_csrf()` and `url_for(...)`) and passed in. Same pattern as `bootstrap.get_template_renderer` / `bootstrap.get_url_generator`.

### 5.6 Size limits (Q4)

Two env vars added to `opendlp.config`, with the defaults below if unset:

| Var                                     | Default       | Applies to                        |
| --------------------------------------- | ------------- | --------------------------------- |
| `REGISTRATION_FORM_HTML_MAX_BYTES`      | 204800 (200K) | `RegistrationPageHtml.form_html`  |
| `REGISTRATION_THANK_YOU_HTML_MAX_BYTES` | 51200 (50K)   | `RegistrationPage.thank_you_html` |

Enforced in `update_registration_page_html` and `update_thank_you_html` respectively, raising `ValueError` with a friendly message ("HTML must be ≤ N bytes; got M"). Document both in `env.example` and `docs/configuration.md`.

### 5.7 Where the service file lives

New file `service_layer/registration_page_service.py`. Not added to `assembly_service.py` — that file is already flagged for splitting in `docs/architecture.md` (line 360).

### 5.8 Default thank-you HTML

Per `deltas-to-fix.md` §7, the thank-you HTML has no placeholders in this round, but `create_registration_page` seeds a starter so the author has something to edit (rather than a blank textarea).

```python
# In src/opendlp/domain/registration_page.py
DEFAULT_THANK_YOU_HTML = (
    "<h1>Thank you for registering</h1>\n"
    "<p>Your registration has been received. We'll be in touch.</p>\n"
)
```

Wrap the `<h1>` and `<p>` strings in `lazy_gettext` if/when this default is moved into a Jinja template owned by the public blueprint (the per-CLAUDE.md i18n rule). For the seeded value stored in the DB we keep plain text — once written, it's user-editable content, not a translation source.

Lifecycle:

- `create_registration_page` writes `DEFAULT_THANK_YOU_HTML` into the new `RegistrationPage.thank_you_html` field at create time.
- `update_thank_you_html` may overwrite it freely (including with the empty string — see Q5: `thank_you_html` is not required to publish, and the public blueprint's fallback Jinja template covers the empty case at submission time).

### 5.9 Generating a starter form HTML

Per `deltas-to-fix.md` §1, authors get a system-generated starter from the assembly's `RespondentFieldDefinition` set. A new service function returns the HTML on demand (it is **not** auto-seeded into `form_html`):

```python
def generate_starter_form_html(uow, user_id, assembly_id) -> str:
    """Generate a plain, unstyled HTML starter form from the assembly's
    respondent field schema (`assembly.respondent_field_schema` — i.e. the
    `RespondentFieldDefinition` set, including `ChoiceOption` lists for choice
    fields). The result includes:

    - A `<form action="{{ form_action }}" method="post">` wrapper.
    - `{{ csrf_form_element }}` immediately inside the form.
    - One labelled control per field, with the schema's `field_key` as the
      `name=` attribute, and explicit per-option markup for choice fields
      (radio / select option lists are written out — no loops, since this is
      Option A).
    - A submit button.

    Required-field markers and input types follow `RespondentFieldDefinition`
    (`is_required`, `effective_field_type`).

    The intended workflow: author calls this, optionally pastes the result into
    an LLM for styling, then pastes the styled HTML back into the textarea.
    Nothing is auto-written to the database — the UI displays the result and
    the author copies it.

    Permission: `can_manage_assembly` (same as the rest of §5.1)."""
```

Where it lives: a pure helper in `domain/registration_page.py` (e.g. `generate_starter_form_html(schema: RespondentFieldSchema) -> str`) does the actual HTML construction; the service function above loads the assembly's schema and delegates. This keeps the HTML generator unit-testable without a database.

The canonical reference for what the output looks like is `610-registration-page-html/example-form-a-raw-html.html` — the generator should produce HTML in the same shape (modulo whitespace / heading copy / section grouping, which are author concerns).

🔮 **Depends on form-submission story:** the precise mapping between `RespondentFieldDefinition` and rendered widget (e.g. how textarea-vs-input is chosen for free-text fields, how multi-select choice fields render). Treat the v1 generator as a starter — authors can hand-edit the output before publishing.

---

## 6. Permissions

- **Management (read+write the page config):** `can_manage_assembly` (i.e. assembly-manager, global-organiser, admin). Same as gsheet config.
- **Viewing the registration tab as read-only:** `can_view_assembly` (any assembly role). Per Q10, read-only members CAN see the tab — useful for "what URL was set?". The blueprint hides write controls.
- **Public route:** no auth.

---

## 7. Feature flag

Story explicitly: "behind a feature flag". Existing pattern is `FF_*` env vars handled by `opendlp.feature_flags`.

Suggested name: **`FF_REGISTRATION_PAGE`** (checked via `has_feature("registration_page")`).

Gates:

- The "Registration" tab in the backoffice (route layer).
- The public `/register/<url_slug>` and `/r/<short_url_slug>` routes (return 404 if flag is off).

The service layer itself does NOT check the flag — it stays pure. The flag is a presentation-layer gate.

---

## 8. Things explicitly punted to the form-submission story

1. The `Respondent` creation path. Already supported by `RespondentSourceType.REGISTRATION_FORM`.
2. The `RespondentStatus.TEST_SUBMISSION` state from story-notes line 109 — adding the enum value, transitions, filters.
3. Mapping submitted form values → respondent fields. Q15 settles that the author writes `<input name="<field_key>">` themselves (Option A reading of Q8); the form-submission story owns turning a POST body into a `Respondent` via the assembly's `RespondentFieldDefinition` set.
4. Rate-limiting / bot protection.
5. Thank-you page substitution context (e.g. `{{ respondent_name }}`) — see `deltas-to-fix.md` §7. v1 has no thank-you placeholders.
6. How to handle slug change after submissions have arrived via the old slug. (Mitigated by Q6: slug is frozen while published. Open: what happens on unpublish-edit-republish — are previously-submitted respondents still associated?)
7. Refinements to the starter HTML generator (§5.9): widget-type selection for ambiguous field types (free-text input vs textarea), multi-select choice rendering, ordering / grouping conventions. v1 ships a basic generator; the form-submission story drives any improvements.

---

## 9. Testing outline

- **Unit tests** for `domain/registration_page.py`:
  - `RegistrationPage.__init__` validation, `update_slugs` rejection when published, `publish`/`unpublish`, `is_visible_with`, `readiness_problems` returning a list of strings, `regenerate_preview_token`.
  - `RegistrationPageHtml.render` substitution behaviour (both `{{ csrf_form_element }}` and `{{ form_action }}`), `readiness_problems`.
  - `UrlSlugValidator` accept/reject cases including reserved values, with errors that distinguish reserved vs malformed (per `deltas-to-fix.md` §12).
  - `generate_starter_form_html` (pure helper): produces a `<form action="{{ form_action }}">` wrapper, includes `{{ csrf_form_element }}`, emits one labelled control per `RespondentFieldDefinition`, expands `ChoiceOption` lists into per-option HTML.
  - `DEFAULT_THANK_YOU_HTML` constant non-empty and contains `<h1>` and `<p>`.
- **Contract tests** for `RegistrationPageRepository` and `RegistrationPageHtmlRepository` against SqlAlchemy (plus an in-memory fake if we use the existing fake repo pattern).
- **Service-level tests** for each `registration_page_service` function: permission failures, explicit create (Q11) including "already exists" rejection, `create_registration_page` seeds `DEFAULT_THANK_YOU_HTML` and leaves `form_html` empty, per-column slug uniqueness, slug-error specificity (errors identify which slug column and which failure type — `deltas-to-fix.md` §12), slug change while published rejected, publish-without-required-fields → `RegistrationPageNotReady` carrying problems, preview-token rotation, public lookup by url_slug and by short_url_slug, render-context substitution, size-limit rejection (Q4), env-var override of size limits, `generate_starter_form_html` wrapper loads the assembly's schema and delegates.
- **BDD** deferred to the route-level plan.

---

## 10. Files to create / modify (data + service scope only)

### New

| Path                                                         | Why                                                                                                                                                              |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/opendlp/domain/registration_page.py`                    | `RegistrationPage`, `RegistrationPageHtml`, `HtmlSource` protocol, `RenderContext`, `RegistrationPageSource`, `DEFAULT_THANK_YOU_HTML`, `generate_starter_form_html` (pure helper, takes a schema) |
| `src/opendlp/service_layer/registration_page_service.py`     | Service functions, including `generate_starter_form_html` wrapper that loads the assembly schema and delegates to the domain helper                              |
| `migrations/versions/XXXX_add_registration_pages.py`         | Two tables + partial unique indexes                                                                                                                              |
| `tests/unit/domain/test_registration_page.py`                | Domain tests, including `generate_starter_form_html` output shape against a known `RespondentFieldSchema`                                                        |
| `tests/unit/service_layer/test_registration_page_service.py` | Service tests, including the starter-HTML generator wrapper and the `DEFAULT_THANK_YOU_HTML` seeding on create                                                   |
| `tests/contract/test_registration_page_repository.py`        | Repo contract tests (both repos)                                                                                                                                 |

### Modified

| Path                                        | Change                                                                                    |
| ------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `src/opendlp/adapters/orm.py`               | Add `registration_pages` and `registration_page_html_sources` tables                      |
| `src/opendlp/adapters/database.py`          | Map `RegistrationPage` + `RegistrationPageHtml`; add Assembly relationship                |
| `src/opendlp/adapters/sql_repository.py`    | `SqlAlchemyRegistrationPageRepository`, `SqlAlchemyRegistrationPageHtmlRepository`        |
| `src/opendlp/service_layer/repositories.py` | Both repository ABCs                                                                      |
| `src/opendlp/service_layer/unit_of_work.py` | Wire both repos                                                                           |
| `src/opendlp/service_layer/exceptions.py`   | `RegistrationPageNotReady`                                                                |
| `src/opendlp/domain/assembly.py`            | Add `registration_page` attribute; `create_detached_copy()` handles it                    |
| `src/opendlp/domain/validators.py`          | `UrlSlugValidator` and `RESERVED_SLUGS`                                                   |
| `src/opendlp/config.py`                     | Read `REGISTRATION_FORM_HTML_MAX_BYTES`, `REGISTRATION_THANK_YOU_HTML_MAX_BYTES` env vars |
| `env.example`                               | Document the two new env vars                                                             |
| `docs/configuration.md`                     | Document the two new env vars                                                             |
| `tests/conftest.py`                         | DELETE from `registration_page_html_sources`, then `registration_pages`                   |
| `tests/bdd/conftest.py`                     | Same DELETE additions                                                                     |

---

## 11. Open questions

### Q1 — One table or three? **RESOLVED**

HTML goes in a **child table** (`registration_page_html_sources`). RegistrationPage gets a `source_type` field; future source types (templated builder, A/B variants, translations) add their own child tables. All source types implement the `HtmlSource` protocol. Thank-you HTML stays on the main page row for now (see Q13).

### Q2 — Empty string or NULL for unset slugs? **RESOLVED**

Empty string with partial unique index on `WHERE slug != ''`.

### Q3 — Reserved slug values? **RESOLVED**

Confirmed reserved list: `preview`, `submit`, `admin`, `static`, `assets`.

URL structure aligned with `plan-frontend.md`: the canonical (long) form lives at `/register/<url_slug>` and the short form at `/r/<short_url_slug>`. They are **separate path namespaces**, so each route does a single-column lookup — no "try one then the other" dispatch, and no cross-column uniqueness needed.

The `/r/<short_url_slug>` route redirects to the canonical `/register/<url_slug>` URL using a **302 (temporary) redirect**, not 301. A short slug may be cleared and reused by a different assembly later; a 301 would be cached by browsers and intermediaries and would keep pointing at the old target. Everywhere in this doc that describes the short-URL redirect uses 302.

### Q4 — HTML size cap? **RESOLVED**

200 KB form HTML, 50 KB thank-you HTML — both configurable via env vars `REGISTRATION_FORM_HTML_MAX_BYTES` and `REGISTRATION_THANK_YOU_HTML_MAX_BYTES`. Documented in `env.example` and `docs/configuration.md`. See §5.6.

### Q5 — Is `thank_you_html` required to publish? **RESOLVED**

No. Publish without it; the form-submission route serves a generic fallback from a Jinja template.

### Q6 — Can `url_slug` be changed after publishing? **RESOLVED**

No. Slug changes (both `url_slug` and `short_url_slug`) are forbidden while `is_published=True`. `update_registration_page` raises `ValueError`. User must unpublish first, edit slug, republish.

### Q7 — Unpublished page: redirect or render in place? **RESOLVED**

302-redirect to a canonical `/registration-closed` URL.

### Q8 — Required-input-fields templating **RESOLVED (via Q15)**

Settled by Q15 below: Q15 Option A implies the (a) reading — authors write `<input name="...">` themselves, with `name` matching the `RespondentFieldDefinition.field_key`. Render-time tokens are limited to `csrf_form_element` and `form_action`. Validation that the right input names are present is owned by the form-submission story (per §8), not by this plan.

### Q9 — Pre-empt or ignore the module system? **RESOLVED**

Ignore for now. Build first-class tables. Revisit when the module system shape settles.

### Q10 — Read-only access for non-managers? **RESOLVED**

Read-only assembly members CAN see the registration tab; write controls hidden by the blueprint.

### Q11 — Lazy create vs explicit create? **RESOLVED**

Explicit create. `create_registration_page` is a named action; `get_registration_page` returns `None` if not yet created. Future "choice of HTML vs template" plugs into the `source_type` parameter on create.

### Q12 — Preview-token rotation triggers **RESOLVED**

Option (b): token is generated when the page is first created and persists across publish/unpublish cycles. Only `regenerate_preview_token` rotates it. Already consistent with §3.1 and §5.1 — `unpublish()` does not touch the token.

### Q13 — Should `thank_you_html` ALSO be split into a child table for parity? **RESOLVED**

Option (a): keep `thank_you_html` on the main `RegistrationPage` row. Split out when translation work drives the same change for the form HTML. The plan already reflects this in §2 and §4.1.

### Q14 — `HtmlSource` as Protocol or ABC? **RESOLVED**

Option (a): `typing.Protocol`, marked `@runtime_checkable`. Already consistent with §3.4. `RegistrationPageHtml` conforms structurally — no explicit subclassing required.

### Q15 — Templating engine and form-authoring model **RESOLVED**

**Decision:** Option A — system-generated starter form; minimal substitution at render time.

- The backoffice generates a complete, unstyled HTML form from the per-assembly respondent field schema (every field's `<input>`/`<select>`/`<label>`, including option lists for choice fields, with correct `name=` attributes — all hand-rendered, no loops, since this is Option A). The intended workflow is that the author pastes that into an LLM for styling and pastes the styled HTML back into the textarea.
- At render time the **only** substitutions are `{{ csrf_form_element }}` and `{{ form_action }}`.
- The starter is exposed via `generate_starter_form_html` (§5.9) — generated on demand, not auto-seeded into `form_html`. The author calls it explicitly (typically a "Generate starter HTML" button in the UI).
- Canonical example: `610-registration-page-html/example-form-a-raw-html.html`.
- Trade-off accepted: schema changes after authoring don't auto-propagate. If a `RespondentFieldDefinition` is added later, the author must hand-edit the HTML (or regenerate a starter and merge). Publish-readiness can warn about missing fields but cannot fix them.

This decision settles Q8 — see Q8 above. Q15 is recorded here in detail; the day-to-day mechanics live in §5.3 (rendering) and §5.9 (starter generator).

#### Worked examples (kept for reference)

Three concrete example forms remain in this directory, all built from the real
16-field schema of assembly `c8f833a8-a712-4457-b564-b1736cdf5222` and all
converging on the **same** rendered output:

| File | Approach | Author writes |
| --- | --- | --- |
| `example-form-a-raw-html.html` | **Option A — chosen** — raw HTML | everything; only `{{ csrf_form_element }}` / `{{ form_action }}` are tokens |
| `example-form-b-input-attrs.html` | Option C (rejected) — attributes injected | all structural HTML + `{% for %}` loops; `{{ }}` for system-owned attrs/options |
| `example-form-c-field-tags.html` | another option (rejected) — what `plan-frontend.md` assumed | page chrome only; one `{{ field('x') }}` per field |

Examples B and C are kept as historical context for the decision; only A reflects the agreed direction.
