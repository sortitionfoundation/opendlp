<!-- ABOUTME: Implementation plan for the data/domain, service, and download layers of PDF uploads (issue 768). -->
<!-- ABOUTME: Mirrors the shipped registration-image feature; the upload/management blueprints are deferred. -->

# PDF uploads — domain, service & download plan

**Issue:** 768 · **Depends on:** `research.md` (storage = Postgres `bytea`, decided) · **Date:** 2026-07-17

## 0. Scope of this plan

The `research.md` decision is settled: store PDFs as `bytea`, serve them from an
app route as `Content-Disposition: attachment` downloads, mirroring the shipped
registration-**image** feature wherever the two rhyme.

**This plan covers, end to end:**

1. **Data / domain layer** — `RegistrationDocument` domain object, the
   `registration_documents` ORM table + migration, repository, UoW wiring.
2. **Service layer** — PDF validation, and the full set of service functions
   (`add` / `list` / `delete` / snippet-generation / `get…for_serving`), plus
   config and exceptions.
3. **Download endpoint** — the public `GET` route that streams a stored PDF.
4. **Tests** for all of the above.

**This plan deliberately excludes** (deferred to a later `blueprint-plan.md`):

- The backoffice **blueprint routes** and **templates** that let an organiser
  upload, list, and delete documents and copy the `<a>` snippet into their form
  HTML.
- The organiser-journey **BDD** scenario for that UI.

Note the split is clean: the service-layer functions the upload/management UI
will call (`add_registration_document`, `list_registration_documents`,
`delete_registration_document`, `list_document_snippets`) **are built and tested
here** — only their web entrypoints are deferred. The download path
(`get_registration_document_for_serving` + the public route) is fully wired in
this plan. See §9.10 for the testing-policy implication of deferring the
organiser-journey BDD.

## 1. Reference: the feature we are mirroring

The registration-image feature is the template. Key files and the parallel we'll
build:

| Image feature (existing)                                            | Document feature (this plan)                                        |
| ------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `domain/registration_image.py`                                      | `domain/registration_document.py`                                   |
| `service_layer/image_processing.py`                                 | `service_layer/document_processing.py`                              |
| `service_layer/registration_image_service.py`                       | `service_layer/registration_document_service.py`                    |
| `orm.py` `registration_images` table                                | `registration_documents` table                                      |
| `SqlAlchemyRegistrationImageRepository`                             | `SqlAlchemyRegistrationDocumentRepository`                          |
| route `serve_registration_image` (`/register/<slug>/assets/<name>`) | `serve_registration_document` (`/register/<slug>/documents/<name>`) |

The document feature is **simpler** than images in one important way: there is
**no re-encode / resize / pixel pipeline**. PDFs are stored as-uploaded after a
cheap validation gate (size + `%PDF-` magic bytes). So there is no analogue of
`width`/`height`, `max_edge_px`, `ProcessedImage.thumbnail`, or Pillow.

## 2. Data / domain layer

### 2.1 `domain/registration_document.py`

A plain-Python domain object mirroring `RegistrationImage`, minus the image-only
fields. ABOUTME header as per CLAUDE.md.

**Module constants**

```python
PDF_CONTENT_TYPE = "application/pdf"
PDF_FILE_EXTENSION = "pdf"
PDF_MAGIC = b"%PDF-"                      # every valid PDF starts with this
MAX_ORIGINAL_FILENAME_LENGTH = 255
```

**Reuse, don't duplicate, `sanitise_original_filename` (decided — §9.6).** The
image module already has `sanitise_original_filename` and
`MAX_ORIGINAL_FILENAME_LENGTH`. **Lift both into a shared `domain/uploads.py`**
and import from the image and document modules. This is a small, safe refactor of
shipped code (the image module's import changes; behaviour is unchanged) — flag
it in review. The two tiny *service* helpers (`_load_user_and_assembly` /
`_load_page`) are **not** shared — they're duplicated so the service modules stay
independent (§6).

**`DocumentValidationError`** — mirror `ImageValidationError` exactly (a
`reason` slug + a translated `message`), so the future upload blueprint can map
`reason` → a field error the way the image UI does.

**`ValidatedDocument`** value object — the analogue of `ProcessedImage`, but with
no pixel fields:

```python
@dataclass(frozen=True)
class ValidatedDocument:
    data: bytes
    sha256: str
    byte_size: int
```

**`RegistrationDocument`** — mirror `RegistrationImage`'s shape and helpers:

- `__init__(registration_page_id, byte_size, sha256, data, original_filename="",
label="", created_by=None, document_id=None, created_at=None)`
  - `id = document_id or uuid.uuid4()`; `created_at = created_at or datetime.now(UTC)`.
  - **`label`** replaces the image's `alt` — the human-visible link text for the
    `<a>` snippet, defaulting to the filename and editable later (decided —
    §9.2).
- `from_validated(cls, registration_page_id, validated, created_by=None,
original_filename="", label="")` — analogue of `from_processed`.
- `create_detached_copy(self)` — **required**, same reason as images: the service
  returns domain objects after the UoW/session closes, so it hands back a
  detached copy to avoid `DetachedInstanceError`.
- `__eq__` / `__hash__` on `id`, identical to images.

**`generate_document_html(href, label)`** — analogue of `generate_image_html`.
Returns an escaped anchor, e.g.:

```python
def generate_document_html(href: str, text: str) -> str:
    href_attr = html_lib.escape(href, quote=True)
    text_attr = html_lib.escape(text, quote=True)
    return f'<a href="{href_attr}">{text_attr}</a>'
```

`generate_document_html` stays a thin href+text escaper — **no `download`
attribute** (the `attachment` header already forces the download). The visible
`(PDF, {human size})` suffix that the accessibility guide wants is **composed by
`list_document_snippets`** (§6), which passes `f"{label} (PDF, {size})"` as the
link text. (Decided — §9.1.)

### 2.2 ORM table — `orm.py` `registration_documents`

Mirror `registration_images` (`orm.py:666`) minus `width`/`height`/`alt`, add
`label`:

```python
registration_documents = Table(
    "registration_documents",
    metadata,
    Column("id", PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "registration_page_id",
        PostgresUUID(as_uuid=True),
        ForeignKey("registration_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("byte_size", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),
    Column("label", String, nullable=False, server_default=""),
    Column("original_filename", String(255), nullable=False, server_default=""),
    Column("created_by", PostgresUUID(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Index("ix_registration_documents_page_sha_unique", "registration_page_id", "sha256", unique=True),
)
```

Notes:

- **No `content_type` column** (decided — §9.7) — every row is `application/pdf`,
  so we hardcode the constant on serving exactly as images hardcode `image/png`.
- The unique `(registration_page_id, sha256)` index gives us content-addressed
  dedup for free, same as images.
- **Skip `STORAGE EXTERNAL`** on the `data` column (decided — §9.5): the tuning
  to avoid Postgres re-compressing already-compressed PDFs is negligible at
  < 1 MB and not worth the non-default DDL.

### 2.3 Mapping — `adapters/database.py`

Add next to the image mapping (`database.py:225`):

```python
orm.mapper_registry.map_imperatively(registration_document.RegistrationDocument, orm.registration_documents)
```

### 2.4 Migration

`uv run alembic revision --autogenerate -m "add registration documents"`. Review
the autogenerated migration by hand (the project's standard practice). Verify the
FK `ondelete="CASCADE"` and the unique index are emitted.

### 2.5 Test-data teardown (CLAUDE.md requirement)

- `tests/conftest.py` `_delete_all_test_data()` — add
  `session.execute(orm.registration_documents.delete())` **before**
  `registration_pages` and alongside `registration_images` (child-before-parent;
  see the existing block at `conftest.py:291`).
- `tests/bdd/conftest.py` `delete_all_except_standard_users()` — the equivalent
  addition.

## 3. Repository & Unit of Work

### 3.1 Abstract repository — `service_layer/repositories.py`

Mirror `RegistrationImageRepository` (`repositories.py:602`):

```python
class RegistrationDocumentRepository(AbstractRepository):
    """Repository interface for RegistrationDocument domain objects."""

    @abc.abstractmethod
    def get_by_page_and_sha(self, registration_page_id: uuid.UUID, sha256: str) -> RegistrationDocument | None: ...

    @abc.abstractmethod
    def list_by_page_id(self, registration_page_id: uuid.UUID) -> list[RegistrationDocument]: ...

    @abc.abstractmethod
    def count_by_page_id(self, registration_page_id: uuid.UUID) -> int: ...

    @abc.abstractmethod
    def delete(self, item: RegistrationDocument) -> None: ...
```

`add` / `get` / `all` come from `AbstractRepository`.

### 3.2 SQLAlchemy implementation — `adapters/sql_repository.py`

Mirror `SqlAlchemyRegistrationImageRepository` (`sql_repository.py:547`). Per
CLAUDE.md's imperative-mapping rule, filter/order using **ORM table columns**,
not domain attributes:

- `list_by_page_id` → `.order_by(orm.registration_documents.c.created_at)`
  (oldest first, matching images).
- `count_by_page_id` → `filter_by(registration_page_id=...).count()`.
- `get_by_page_and_sha` → filter on
  `orm.registration_documents.c.registration_page_id` and `.c.sha256`.

### 3.3 Unit of Work — `service_layer/unit_of_work.py`

- Add `registration_documents: RegistrationDocumentRepository` to the abstract
  UoW (alongside `registration_images` at `unit_of_work.py:77`).
- Wire `self.registration_documents = SqlAlchemyRegistrationDocumentRepository(self.session)`
  in the SQLAlchemy UoW (`unit_of_work.py:160`).
- If there is a fake/in-memory UoW used in tests, add the parallel fake repo.

## 4. Config — `config.py`

Mirror the image knobs (`config.py:280`+):

```python
def get_max_pdf_upload_mb() -> int:
    """Max size for an uploaded registration PDF, in MB. Default 5, bounded [1, 25].
    Env: MAX_PDF_UPLOAD_MB."""
    return _clamped_int_env("MAX_PDF_UPLOAD_MB", 5, 1, 25)

def get_max_pdf_upload_bytes() -> int:
    return get_max_pdf_upload_mb() * 1024 * 1024

def get_max_documents_per_registration_page() -> int:
    """Max PDFs per registration page. Default 5, bounded [1, 20].
    Env: MAX_DOCUMENTS_PER_REGISTRATION_PAGE."""
    return _clamped_int_env("MAX_DOCUMENTS_PER_REGISTRATION_PAGE", 5, 1, 20)
```

**Must-do:** add `get_max_pdf_upload_bytes` to the `_UPLOAD_SIZE_CONTRIBUTORS`
list (`config.py`) so Flask's global `MAX_CONTENT_LENGTH` grows to admit PDF
uploads. Missing this makes the WSGI gateway reject uploads before the route
sees them.

Defaults are **5 MB / 5 docs** (decided — §9.3): generous headroom over the real
data (< 1 MB, ≤ 3) without inviting abuse.

## 5. PDF validation — `service_layer/document_processing.py`

The analogue of `image_processing.py`, but there is **no transform** — we
validate and hash the original bytes:

```python
def validate_pdf(raw: bytes, *, max_bytes: int) -> ValidatedDocument:
    if len(raw) > max_bytes:
        raise DocumentValidationError("too_large", _("The PDF file is too large"))
    if not raw.startswith(PDF_MAGIC):
        raise DocumentValidationError("unsupported_format", _("The file must be a PDF"))
    return ValidatedDocument(
        data=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
    )
```

Rationale (all from `research.md` §5): cheapest gate first (size), then the
`%PDF-` magic-byte check — we never trust the client `Content-Type` or the
`.pdf` extension. **No re-encode, no ClamAV, no deep structure parse** — magic
+ size only (decided — §9.8): no trailer `%%EOF` or `/Encrypt` checks. Safety
comes from serving as an attachment download (§7), not from sanitising the bytes.

## 6. Service layer — `service_layer/registration_document_service.py`

Mirror `registration_image_service.py` structure, including its own copies of the
private helpers `_load_user_and_assembly` and `_load_page` (duplicated, not
shared — decided §9.6). Permission checks reuse `can_manage_assembly` /
`can_view_assembly`. Every
function follows the `with uow:` … `uow.commit()` … `return
domain.create_detached_copy()` pattern.

**New exceptions in `service_layer/exceptions.py`** (mirror the image ones):

- `DocumentQuotaExceeded(ServiceLayerError)` — like `ImageQuotaExceeded`, message
  "This registration page already has the maximum of %(limit)s documents".
- `RegistrationDocumentNotFoundError(NotFoundError)` — like
  `RegistrationImageNotFoundError`. Add both to `__all__`.
- Reuse `UserNotFoundError`, `AssemblyNotFoundError`,
  `RegistrationPageNotFoundError`, `InsufficientPermissions`.

**Functions** (the first four are the ones the deferred upload/management UI will
call; they are still built and tested here):

- `add_registration_document(uow, user_id, assembly_id, raw, original_filename="",
label="") -> RegistrationDocument`
  - permission: `can_manage_assembly` else `InsufficientPermissions`.
  - load page; `validate_pdf(raw, max_bytes=get_max_pdf_upload_bytes())`.
  - **content-addressed dedup:** `get_by_page_and_sha(page.id, sha256)`; if it
    exists, update `label` if changed (`page.record_edit(...)`, commit) and
    return the detached copy — exactly the image dedup branch.
  - **quota:** if `count_by_page_id(page.id) >= get_max_documents_per_registration_page()`
    raise `DocumentQuotaExceeded(limit)`.
  - build via `from_validated`, `sanitise_original_filename(original_filename)`,
    `add`, `page.record_edit(user.id, "Added a registration document")`, commit,
    return detached copy.
- `list_registration_documents(uow, user_id, assembly_id) -> list[RegistrationDocument]`
  - permission: `can_view_assembly`. Returns `[]` if the page doesn't exist
    (matches the image service). Detached copies.
- `delete_registration_document(uow, user_id, assembly_id, document_id) -> None`
  - permission: `can_manage_assembly`; verify the document belongs to this
    page's id else `RegistrationDocumentNotFoundError`;
    `page.record_edit(..., "Deleted a registration document")`.
- `set_registration_document_label(uow, user_id, assembly_id, document_id, label)
  -> RegistrationDocument` — analogue of `set_registration_image_alt`. **Kept**
  (we have an editable `label` — decided §9.2).
- `list_document_snippets(uow, user_id, assembly_id, url_for_document) ->
  list[tuple[RegistrationDocument, str]]` — analogue of `list_image_snippets`;
  pairs each document with `generate_document_html(url_for_document(doc),
  f"{doc.label} (PDF, {human_size(doc.byte_size)})")`. The `(PDF, {size})` suffix
  is composed **here** (decided §9.1), keeping `generate_document_html` a thin
  escaper. Needs a small `human_size` helper (e.g. "312 KB") — put it in the
  shared `domain/uploads.py` alongside `sanitise_original_filename`. Used later by
  the (deferred) editor UI; built and unit-tested now.
- `get_registration_document_for_serving(uow, url_slug, document_name) ->
RegistrationDocument | None` — analogue of `get_registration_image_for_serving`:
  - parse the sha from `document_name` via `rsplit(".", 1)[0]`;
  - load page by `url_slug`; return `None` unless `page.is_publicly_loadable()`;
  - `get_by_page_and_sha(page.id, sha)`; detached copy or `None`.
    This is the function the download endpoint (§7) calls.

## 7. Download endpoint — `entrypoints/blueprints/registration.py`

Add a public route mirroring `serve_registration_image`
(`registration.py:344`). It rides the **same feature flag**
(`@require_feature("registration_page")`) since documents are part of the
registration page (decided — §9.9).

```python
@registration_bp.route("/register/<url_slug>/documents/<document_name>", methods=["GET"])
@require_feature("registration_page")
def serve_registration_document(url_slug: str, document_name: str) -> ResponseReturnValue:
    """Serve a registration page PDF from the database (public, attachment download)."""
    uow = bootstrap.get_flask_uow()
    served = get_registration_document_for_serving(uow, url_slug, document_name)
    if served is None:
        abort(404)

    response = Response(served.data, mimetype=PDF_CONTENT_TYPE)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = _content_disposition(served)   # attachment; see below
    response.set_etag(served.sha256)
    return response.make_conditional(request)
```

Details:

- **`Content-Disposition: attachment` is the load-bearing security header**
  (`research.md` §5): it forces a download instead of inline rendering, so any
  active content in the PDF never executes in our origin. This is the one place
  the document route intentionally diverges from the image route (images are
  served for inline `<img>` display and set no `Content-Disposition`).
- **Filename in the header** (decided — §9.4) — a helper
  `_content_disposition(served)` builds `attachment; filename="…"` using the
  organiser's `original_filename` when present, else `<sha>.pdf`. It must avoid
  header injection: the name is already sanitised at storage (control chars
  stripped), and for non-ASCII names we emit RFC 5987 `filename*=UTF-8''…` with an
  ASCII `filename=` fallback. Prefer Werkzeug's built-in
  (`werkzeug.datastructures` / `send_file(download_name=…)` uses
  `werkzeug.utils.send_file`'s header builder) rather than hand-rolling the
  encoding.
- **Caching** (decided — §9.5) — `set_etag(sha256)` + `make_conditional` gives
  304s (matching images), **and** we add `Cache-Control: public,
  max-age=31536000, immutable`, which is safe because the URL is
  content-addressed.
- Import `PDF_CONTENT_TYPE` from `domain/registration_document.py` (parallel to
  the existing `IMAGE_CONTENT_TYPE` import at `registration.py:13`).

## 8. Testing

Following the CLAUDE.md test pyramid and no-skip policy, all for the scope of
this plan:

- **Unit**
  - `domain/registration_document.py`: `RegistrationDocument` construction /
    `from_validated` / `create_detached_copy` / equality; `generate_document_html`
    escaping; shared `sanitise_original_filename` behaviour.
  - `document_processing.validate_pdf`: a valid `%PDF-` sample passes and hashes;
    oversized → `too_large`; non-PDF bytes → `unsupported_format`; empty input.
- **Integration / contract**
  - `SqlAlchemyRegistrationDocumentRepository` round-trip: add → get →
    get_by_page_and_sha → list_by_page_id (ordering) → count → delete; the unique
    `(page, sha)` constraint.
  - Service functions against a real session/UoW: add happy path; **dedup**
    (same bytes twice → one row, label update); **quota** boundary
    (`DocumentQuotaExceeded`); permission failures for view/manage;
    `get_registration_document_for_serving` returns `None` when the page is not
    `is_publicly_loadable()` and the document when it is; cascade-delete when the
    owning page is deleted.
- **End-to-end (public download route)**
  - `GET /register/<slug>/documents/<sha>.pdf` returns 200, `application/pdf`,
    `Content-Disposition: attachment`, `nosniff`, correct bytes, and a working
    ETag/304 on conditional re-request; 404 for unknown sha, closed page, and
    when the feature flag is off. This gives us a genuine e2e surface **without**
    the deferred upload UI (fixtures insert a document via the service/repo).

The **organiser upload-journey BDD** (upload via the backoffice form, see it
listed, paste the snippet, load the public page) belongs with the deferred
blueprint plan because it exercises UI that doesn't exist yet — see §9.10.

## 9. Decisions (resolved with Doctor Chewie, 2026-07-17)

All ten open questions were reviewed and the proposed answers accepted. They are
recorded here as decisions and folded into the body of the plan above.

1. **Link snippet format / accessibility.** The pasted snippet is
   `<a href="…">{label} (PDF, {size})</a>` — the `(PDF, {human size})` suffix
   signals file type and size per the accessibility guide. **No `download`
   attribute** — `Content-Disposition: attachment` already forces the download.
   The `(PDF, {size})` suffix is composed at snippet-generation time (§6
   `list_document_snippets`), so `generate_document_html` stays a thin
   href+text escaper (§2.1).
2. **Editable `label`.** Keep a dedicated `label`, defaulting to the filename;
   the future editor lets organisers change it. So we keep the `label` column
   and the `set_registration_document_label` service function (§2, §6).
3. **Default limits.** `MAX_PDF_UPLOAD_MB=5`, `MAX_DOCUMENTS_PER_REGISTRATION_PAGE=5`
   — headroom over the real data (< 1 MB, ≤ 3) without inviting DB bloat (§4).
4. **`Content-Disposition` filename.** Serve under the organiser's original
   filename when present (RFC 5987 `filename*` encoded, with an ASCII `filename=`
   fallback), else `<sha>.pdf` (§7).
5. **Caching / storage tuning.** (a) **Add** `Cache-Control: public,
   max-age=31536000, immutable` on the download route — safe because the URL is
   content-addressed (§7). (b) **Skip** `STORAGE EXTERNAL` on `data` — negligible
   at < 1 MB (§2.2).
6. **Shared vs duplicated helpers.** **Lift** `sanitise_original_filename` (and
   `MAX_ORIGINAL_FILENAME_LENGTH`) into a shared `domain/uploads.py`, imported by
   both the image and document modules; **duplicate** the tiny service helpers
   (`_load_user_and_assembly` / `_load_page`) so the two service modules stay
   independent (§2.1, §6).
7. **`content_type` column.** **Hardcode** the `application/pdf` constant on
   serving (as images hardcode PNG); no column. Add one only if/when a second
   document type appears (§2.2).
8. **Validation depth.** **Magic-only** — size cap + `%PDF-` prefix, no trailer
   or `/Encrypt` parsing. The attachment download makes deeper parsing low-value
   (`research.md` §5, §5 here).
9. **Feature flag.** Documents **reuse** the existing
   `require_feature("registration_page")` flag (§7).
10. **Deferred BDD is acceptable.** This plan ships unit + integration + e2e for
    the download path; the organiser upload-journey BDD defers with the upload
    blueprint (it drives UI that doesn't exist yet). Nothing in this plan's scope
    ships untested (§8).

## 10. Build order

1. ✅ Domain object + shared filename helper + constants + `ValidatedDocument` +
   `DocumentValidationError` (+ unit tests).
2. ✅ `document_processing.validate_pdf` (+ unit tests).
3. ✅ ORM table + mapping + migration + conftest teardown entries.
4. ✅ Repository (abstract + SQLAlchemy) + UoW wiring (+ contract tests).
5. ✅ Config knobs + `_UPLOAD_SIZE_CONTRIBUTORS` entry.
6. ✅ Exceptions + `registration_document_service.py` (+ service tests).
7. Download route (+ e2e tests).
8. `just check` + `just test` green; `just translate-regen` for new strings.

> **Implementation note (during build):** the immutable `Cache-Control` is not
> set inline in the route (the plan's §7 sketch showed it inline). The codebase
> applies it centrally in `flask_app.py` via `PUBLIC_IMMUTABLE_ASSET_ENDPOINTS`;
> the document serving endpoint is added to that frozenset, mirroring how
> `registration.serve_registration_image` gets its immutable cache header.

Deferred to `blueprint-plan.md`: backoffice upload/list/delete routes and
templates, the snippet-copy UI, and the organiser-journey BDD.
