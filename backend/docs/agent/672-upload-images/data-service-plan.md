<!-- ABOUTME: TDD implementation plan for the data/domain/adapters + service layers of registration image uploads. -->
<!-- ABOUTME: Covers storage, image processing, repositories, serving, and skeleton <img> generation; excludes upload routes/templates. -->

# Registration image uploads — data + service layer plan (red/green TDD)

**Issue:** 672 · **Companion:** [research.md](research.md) · **Date:** 2026-06-11
**Branch:** `672-upload-images`

## 1. Scope

This plan covers the **data/domain/adapters layer**, the **service layer**, the
**generation of skeleton `<img>` HTML**, and **serving images that live in the
database**.

**In scope**

- Domain: a `RegistrationImage` entity, a `ProcessedImage` value object, image
  validation rules/exceptions, and pure `<img>`-snippet generation.
- Image processing (validate → re-encode → resize → hash) via Pillow.
- Adapters: a `registration_images` table (`bytea` storage), imperative mapper,
  Alembic migration, repository (abstract + SQLAlchemy + fake), UoW wiring.
- Service layer: add / list / delete / quota, and a public "resolve image for
  serving" function, plus the skeleton-`<img>` service entry point.
- A **GET serving route** that streams an image from the DB with correct
  security/cache headers (this is the one entrypoint deliberately included —
  "serving images that are in the database").
- Config getters, conftest cleanup, i18n, and the full test pyramid for the
  above.

**Out of scope (another person is doing this)**

- The **upload route** (POST) and any upload/management **templates** or UI.
- Wiring an upload form into the backoffice registration editor.

We design a clean service seam (`add_registration_image(...)`) that the upload
route will call, so the two work-streams meet at a well-defined function
boundary and nothing here blocks the other person.

## 2. Architecture decisions (carried from research.md)

- **Storage:** PostgreSQL `bytea` in a new `registration_images` table, tied to
  `registration_pages.id` with `ON DELETE CASCADE`. No filesystem, no GDPR
  blanking logic (logos on public pages — not personal data).
- **Identity / dedup / cache:** images are content-addressed by the **sha256 of
  the re-encoded bytes**; `UNIQUE (registration_page_id, sha256)`.
- **Serving:** main domain, `GET /register/<url_slug>/assets/<sha>.png`; serve
  only when the page is publicly loadable (TEST or PUBLISHED), else 404 —
  mirrors `RegistrationPage.is_publicly_loadable()` / `resolve_visibility`.
- **Validation/processing (keystone):** size cap → cheap Pillow header gate
  (format + dimensions) → full decode + re-encode + downscale + hash. Input
  PNG/JPEG/WebP; **reject SVG/GIF/animated**; **always output PNG** (preserving
  transparency) — one code path, maximum compatibility.
- **Limits:** 10 MB upload cap; max long edge ~2048 px (banner width); **10
  images per registration page**.

### Where each piece lives (layering)

| Concern                                                                   | Layer / file                                                                                              | Why                                                                                                                  |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `RegistrationImage` entity, `ProcessedImage` VO, exceptions, `<img>` HTML | `domain/registration_image.py`                                                                            | Plain Python, no Pillow/Flask/SQLAlchemy — mirrors `domain/registration_page.py` (which already builds HTML strings) |
| Pillow pipeline (`process_image(...)`)                                    | `service_layer/image_processing.py`                                                                       | Wraps a library with pure functions — mirrors `service_layer/security.py` wrapping `werkzeug.security`               |
| Table + mapper                                                            | `adapters/orm.py` + `adapters/database.py`                                                                | Imperative mapping convention                                                                                        |
| Repository                                                                | `service_layer/repositories.py` (abstract) + `adapters/sql_repository.py` (SQL) + `tests/fakes.py` (fake) | Existing repository pattern                                                                                          |
| Orchestration (add/list/delete/serve/snippet)                             | `service_layer/registration_image_service.py`                                                             | New service module beside `registration_page_service.py`                                                             |
| GET serving route                                                         | `entrypoints/blueprints/registration.py`                                                                  | Public, already `@require_feature("registration_page")`                                                              |

> **Design note — domain stays Pillow-free.** The entity and `<img>` generation
> are pure; only `service_layer/image_processing.py` imports Pillow. This keeps
> domain unit-testable without Pillow and matches how `security.py` isolates
> `werkzeug`.

## 3. Prerequisite — Pillow as a direct dependency ✅ done

Pillow 12.2.0 was already installed transitively; Doctor Chewie has run
`uv add pillow` to record it as a **direct** dependency (so a direct import
satisfies `deptry` / `just check`). **Not yet committed** — it will go in as the
first commit of the implementation (§12). **No other new deps**
(`python-magic`/`libmagic1` avoided — Pillow does the format gate; no ClamAV).

## 4. Config additions (`src/opendlp/config.py`)

Follow the existing `get_max_csv_upload_*` / `get_registration_*_max_bytes`
patterns (env override, clamp, warn-on-out-of-range). Add getters:

- `get_max_image_upload_bytes()` → default **10 MB**, env `MAX_IMAGE_UPLOAD_MB`,
  clamped (e.g. `[1, 25]` MB).
- `get_registration_image_max_edge_px()` → default **2048**, env
  `REGISTRATION_IMAGE_MAX_EDGE_PX`, clamped (e.g. `[256, 4096]`).
- `get_max_images_per_registration_page()` → default **10**, env
  `MAX_IMAGES_PER_REGISTRATION_PAGE`, clamped (e.g. `[1, 50]`).

> **MAX_CONTENT_LENGTH caveat (research §10).** `MAX_CONTENT_LENGTH` is currently
> app-global (`= get_max_csv_upload_bytes()`, 50 MB). The image **upload route**
> (out of scope) will enforce the 10 MB image cap at route level; our service
> `process_image()` also enforces it defensively on the raw bytes. We do **not**
> change the global here.

**TDD:** `tests/unit/test_config.py` (or the existing config test module) — one
test per getter: default, env override, below-min clamp + warning, above-max
clamp + warning. _(Red: assert getter exists/returns default → Green: implement.)_

## 5. Phase 1 — Domain (`domain/registration_image.py`)

All pure Python. Unit tests in `tests/unit/domain/test_registration_image.py`
(mirrors `tests/unit/domain/test_registration_page.py`).

### 5.1 `ProcessedImage` value object

Frozen dataclass: `data: bytes`, `width: int`, `height: int`, `sha256: str`,
`byte_size: int`. Output is **always PNG**, so `content_type` is fixed
(`image/png`) and the extension is always `.png` — expose these as constants
(`IMAGE_CONTENT_TYPE = "image/png"`) rather than computing per instance.

- **Red:** `test_processed_image_carries_dimensions_and_hash`.
- **Green:** implement dataclass.

### 5.2 `RegistrationImage` entity

Constructor like `RegistrationPageHtml`: `registration_page_id: uuid.UUID`,
`byte_size`, `width`, `height`, `sha256`, `data: bytes`,
`created_by: uuid.UUID | None = None`, `image_id: uuid.UUID | None = None`,
`created_at: datetime | None = None`. No `content_type` field — output is always
PNG (§5.1), served via the `IMAGE_CONTENT_TYPE` constant. Provide
`create_detached_copy()`, `__eq__`/`__hash__` on `id`, and a `classmethod
from_processed(page_id, processed, created_by)`.

- **Red:** `test_from_processed_copies_fields`, `test_detached_copy_equal_by_id`.
- **Green:** implement.

### 5.3 Validation exceptions + policy constants

In domain (mirrors `SlugError`/`RegistrationPageNotReady`):
`ALLOWED_INPUT_FORMATS = {"PNG", "JPEG", "WEBP"}` (input only), the single
`IMAGE_CONTENT_TYPE = "image/png"` output constant, and an
`ImageValidationError(reason: str, message: str)` (i18n `_l()` messages). Reasons
e.g. `too_large`, `unsupported_format`, `too_many_pixels`, `decode_failed`.

- **Red:** `test_image_validation_error_carries_reason`.
- **Green:** implement.

### 5.4 Skeleton `<img>` HTML generation (pure, URL-agnostic)

**Decided: the asset URL/path lives in exactly one place — the Flask serving
route (§9).** The domain does **not** know or construct the path. So there is no
`image_asset_path` helper; the domain only assembles an `<img>` tag from a
**src URL it is given**:

```python
def generate_image_html(src_url: str, alt: str = "") -> str:
    # '<img src="<src_url>" alt="...">'  — both attributes html-escaped
```

Whoever needs a snippet builds the URL with `url_for("registration.serve_registration_image", ...)`
(the route is the single source of truth) and passes the result in. This removes
the duplicated-path drift risk entirely — and so the Phase 5 "parity test" is no
longer needed (there is nothing to keep in sync).

For a **service-layer** snippet list (so the upload UI doesn't have to loop
itself), the service function takes a URL-builder **callable** injected by the
Flask caller — see §8.4. This keeps the path in Flask while letting us unit-test
snippet assembly with a fake builder.

- **Red:** `test_generate_image_html_escapes_alt`,
  `test_generate_image_html_escapes_src`, `test_generate_image_html_structure`.
- **Green:** implement.

## 6. Phase 2 — Image processing (`service_layer/image_processing.py`)

The keystone. One public function; **real images in tests** (generate with
Pillow — no mocks, per project rules). Tests:
`tests/unit/test_image_processing.py`.

```python
def process_image(raw: bytes, *, max_bytes: int, max_edge_px: int) -> ProcessedImage:
    """Validate, re-encode, downscale, hash. Raises ImageValidationError."""
```

Pipeline (research §5/§6):

1. `len(raw) > max_bytes` → `ImageValidationError("too_large")`.
2. `img = Image.open(BytesIO(raw))` — lazy header read.
3. `img.format not in ALLOWED_INPUT_FORMATS` → `unsupported_format` (covers
   SVG/GIF — SVG won't even open as a raster).
4. Promote `Image.DecompressionBombWarning` to error; oversized pixel count →
   `too_many_pixels` (Pillow's `DecompressionBombError` caught + re-raised as
   our error).
5. `ImageOps.exif_transpose(img)` (bake rotation, drop EXIF) → `img.load()`
   (full decode; wrap decode failure → `decode_failed`).
6. `img.thumbnail((max_edge, max_edge), Image.LANCZOS)` (never upscales).
7. **Output is always PNG** (decided — crispness, fewer code paths). Save to a
   buffer as PNG with `optimize=True`, preserving the mode so logos keep their
   transparency (no `convert("RGB")`, no JPEG branch). One path for every input.
8. Compute `sha256(out_bytes)`, dimensions, `byte_size` → return `ProcessedImage`
   (content type is the fixed `image/png`).

**TDD cycles (each red→green):**

- `test_reencodes_valid_png_returns_png` (build a real PNG).
- `test_jpeg_input_returns_png` (output always PNG).
- `test_webp_input_returns_png`.
- `test_transparent_png_keeps_alpha`.
- `test_downscales_oversized_image` (e.g. 4000px → ≤ max_edge).
- `test_small_image_not_upscaled`.
- `test_rejects_oversized_bytes` (`raw` > max_bytes).
- `test_rejects_non_image_bytes` (`b"not an image"` → `decode_failed`/`unsupported_format`).
- `test_rejects_svg_bytes` (SVG XML → `unsupported_format`).
- `test_rejects_decompression_bomb` (a tiny image with a huge declared size, or
  set a low `max_edge`/monkeypatch `MAX_IMAGE_PIXELS` to assert the guard fires).
- `test_strips_exif` (input with EXIF → output has none).
- `test_same_input_same_sha` and `test_different_input_different_sha`.

## 7. Phase 3 — Adapters (storage)

### 7.1 ORM table (`adapters/orm.py`)

Add after `registration_page_html_sources` (and add `LargeBinary` to the
`sqlalchemy` import — currently absent):

```python
registration_images = Table(
    "registration_images",
    metadata,
    Column("id", PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("registration_page_id", PostgresUUID(as_uuid=True),
           ForeignKey("registration_pages.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("byte_size", Integer, nullable=False),
    Column("width", Integer, nullable=False),
    Column("height", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),     # bytea
    # Users are disabled, not deleted, so the audit reference always resolves —
    # a plain FK with no ON DELETE behaviour. Nullable only to allow a future
    # system/script upload with no human author.
    Column("created_by", PostgresUUID(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("created_at", TZAwareDatetime(), nullable=False, default=aware_utcnow),
    Index("ix_registration_images_page_sha_unique", "registration_page_id", "sha256", unique=True),
)
```

No `content_type` column — output is always PNG (§5.1); serving uses the
`IMAGE_CONTENT_TYPE` constant. (Re-adding it is a migration if formats ever
expand.)

### 7.2 Mapper (`adapters/database.py`)

Beside the registration mappers:
`orm.mapper_registry.map_imperatively(registration_image.RegistrationImage, orm.registration_images)`.

> Imperative-mapping note (CLAUDE.md): in the SQL repo, filter/order via ORM
> table columns (`orm.registration_images.c.sha256`), not domain attributes.

### 7.3 Migration

`uv run alembic revision --autogenerate -m "add registration images"`; review the
generated file (uses `sa.LargeBinary`, `orm.TZAwareDatetime()`); confirm the FK
cascade and the unique index are present. Run `uv run alembic upgrade head`
against the dev DB.

### 7.4 Repository — abstract + SQL + fake

- `service_layer/repositories.py`: `RegistrationImageRepository(AbstractRepository)`
  with `get(id)`, `add`, `all`, plus:
  - `get_by_page_and_sha(page_id, sha256) -> RegistrationImage | None`
  - `list_by_page_id(page_id) -> list[RegistrationImage]`
  - `count_by_page_id(page_id) -> int`
  - `delete(item)`
- `adapters/sql_repository.py`: `SqlAlchemyRegistrationImageRepository` (mirror
  `SqlAlchemyRegistrationPageHtmlRepository`).
- `tests/fakes.py`: `FakeRegistrationImageRepository` + add to `FakeUnitOfWork`.

### 7.5 UoW wiring

`service_layer/unit_of_work.py`: add `registration_images: RegistrationImageRepository`
to `AbstractUnitOfWork`; instantiate in `SqlAlchemyUnitOfWork.__enter__`.

### 7.6 Contract tests (parameterized fake + sql)

`tests/contract/test_registration_image_repo.py` mirroring
`test_registration_page_html_repo.py`; add a `registration_image_backend`
fixture to `tests/contract/conftest.py` (FakeContractBackend / SqlContractBackend).

**TDD cycles (each red→green):** round-trip add+get (bytes survive intact);
`get_by_page_and_sha` hit/miss; `list_by_page_id` ordering; `count_by_page_id`;
`delete`; **unique-constraint** behaviour on duplicate `(page, sha)`; **cascade**
— deleting the parent `registration_pages` row removes its images (SQL backend).

### 7.7 conftest cleanup (both)

Insert `orm.registration_images.delete()` **before**
`orm.registration_page_html_sources.delete()` (child-first) in:

- `tests/conftest.py::_delete_all_test_data`
- `tests/bdd/conftest.py::delete_all_except_standard_users`

## 8. Phase 4 — Service layer (`service_layer/registration_image_service.py`)

Mirrors `registration_page_service.py` (uses `with uow:`, `can_manage_assembly`,
`create_detached_copy()`, raises from `service_layer/exceptions.py`). Tests use
`FakeUnitOfWork` in `tests/unit/test_registration_image_service.py`.

### 8.1 `add_registration_image(uow, user_id, assembly_id, raw, created_by=...) -> RegistrationImage`

- Load user+assembly; `can_manage_assembly` else `InsufficientPermissions`.
- Resolve the assembly's registration page (else `RegistrationPageNotFoundError`).
- `process_image(raw, max_bytes=..., max_edge_px=...)` (config) — propagates
  `ImageValidationError`.
- **Dedup:** if `get_by_page_and_sha` already exists, return it (idempotent; no
  new row, no new activity entry).
- **Quota:** else if `count_by_page_id >= get_max_images_per_registration_page()`
  → raise `ImageQuotaExceeded`.
- Build `RegistrationImage.from_processed(...)`, `add`; **append a
  `RegistrationPageActivity` (EDIT) entry** to the page via `page.record_edit(
  user.id, "Added a registration image")` so uploads show in the audit log like
  HTML edits; `commit`, return detached.

**TDD:** happy path stores + returns + **records an activity entry**; permission
denied; no page; invalid image propagates; **dedup returns existing without
incrementing count or adding an activity entry**; **quota at limit raises**;
quota check happens _after_ dedup (re-uploading an existing image at the limit
still succeeds).

### 8.2 `list_registration_images(uow, user_id, assembly_id) -> list[RegistrationImage]`

`can_view_assembly` (matches page service read methods); returns detached copies.
**TDD:** lists only that page's images; permission denied.

### 8.3 `delete_registration_image(uow, user_id, assembly_id, image_id) -> None`

`can_manage_assembly`; 404 if image absent or belongs to another page. Deletes
the image and **appends a `RegistrationPageActivity` (EDIT) entry** to the page
(`"Deleted a registration image"`).
**TDD:** deletes + **records an activity entry**; permission denied; wrong-page
image → not found.

### 8.4 `list_image_snippets(uow, user_id, assembly_id, url_for_image) -> list[tuple[RegistrationImage, str]]`

The "skeleton `<img>` HTML" deliverable, built with the **URL kept in Flask**.
`url_for_image: Callable[[RegistrationImage], str]` is injected by the (out-of-
scope) caller — it will be
`lambda img: url_for("registration.serve_registration_image", url_slug=slug, image_name=f"{img.sha256}.png")`.
The service loads the page's images (`can_view_assembly`) and, per image, returns
`(image, generate_image_html(url_for_image(image), alt=""))`. No path knowledge
in the service or domain.
**TDD (with a fake builder, e.g. `lambda img: f"/x/{img.sha256}.png"`):** one
snippet per image; snippet contains the builder's URL; permission denied.
*(A bare `build_image_snippet(image, src_url, alt)` is just `generate_image_html`
— covered by the domain test in §5.4; no separate service wrapper needed.)*

### 8.5 `get_registration_image_for_serving(uow, url_slug, image_name) -> RegistrationImage | None`

Public, **no auth**. Resolve `url_slug → page`; if not `is_publicly_loadable()`
→ return `None` (route 404s). Strip the `.png` extension from `image_name` to get
the sha; `get_by_page_and_sha`; return the (detached) `RegistrationImage` or
`None`. Content type is the fixed `IMAGE_CONTENT_TYPE` at serve time.
**TDD:** serves for TEST and PUBLISHED; `None` for CLOSED; `None` for unknown
slug; `None` for unknown sha; ignores a mismatched extension gracefully.

## 9. Phase 5 — Serving route (`entrypoints/blueprints/registration.py`)

The single in-scope entrypoint. Public GET, `@require_feature("registration_page")`.

```python
@registration_bp.route("/register/<url_slug>/assets/<image_name>", methods=["GET"])
@require_feature("registration_page")
def serve_registration_image(url_slug, image_name) -> ResponseReturnValue:
    uow = bootstrap.bootstrap()
    served = get_registration_image_for_serving(uow, url_slug, image_name)
    if served is None:
        abort(404)
    resp = Response(served.data, mimetype=IMAGE_CONTENT_TYPE)   # always image/png
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    resp.set_etag(served.sha256)
    return resp.make_conditional(request)   # 304 support for in-memory bytes
```

- **Single source of truth for the path:** this route *is* the only place the
  asset URL is defined. Snippet generation (§8.4) is handed the URL via
  `url_for("registration.serve_registration_image", ...)`, so there is nothing to
  drift and **no parity test is needed**.
- **Headers:** `nosniff`, content-addressed `immutable` cache, ETag = sha (the
  `make_conditional` call is required because Flask does _not_ auto-ETag in-memory
  bodies — research §7).

**TDD (integration, Flask test client):**
`tests/integration/.../test_registration_image_route.py` (or e2e, see §10) —
seed page + image directly in the DB, then:

- 200 + correct `Content-Type` + bytes for a PUBLISHED page.
- 200 for TEST.
- 404 for CLOSED / unknown slug / unknown sha.
- `nosniff` + `Cache-Control: immutable` present.
- `If-None-Match: <sha>` → 304.
- Route 404s when `FF_registration_page` is off.

## 10. Test pyramid (CLAUDE.md no-skip policy)

| Type                     | What                                                                                                                                                                                             | Where                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| **Unit**                 | domain entity/VO/`<img>` gen; image processing with real images; service logic on `FakeUnitOfWork`; config getters                                                                               | `tests/unit/...`                              |
| **Contract/Integration** | repository round-trip incl. real `bytea`, unique constraint, cascade (real Postgres); serving route via Flask test client                                                                        | `tests/contract/...`, `tests/integration/...` |
| **E2E**                  | **serving an image from the DB through the public route** end-to-end (seed image in DB → GET `/register/<slug>/assets/<sha>.png` → bytes back). This is fully exercisable without the upload UI. | `tests/integration` or `tests/bdd`            |

> **Note on the upload journey:** a browser-level e2e of _uploading and then
> displaying_ an image needs the upload route + templates, which are **out of
> scope** (other person). Our e2e covers the **serve-from-DB** path, which is
> the half we own. The upload-and-display BDD should be authored alongside the
> upload route; flag this for coordination — **not** marking any test type N/A,
> just locating the upload e2e with the work-stream that owns the route.

## 11. Definition of done

- `just test` green (coverage ≥ 90% as configured).
- `just check` green (mypy strict, ruff, deptry — Pillow now a direct dep).
- New strings wrapped in `_()` / `_l()`; `just translate-regen` run if any added.
- Alembic migration applies cleanly and round-trips (`upgrade`/`downgrade`).
- `_delete_all_test_data` and `delete_all_except_standard_users` updated.
- Two ABOUTME comment lines at the top of every new file.

## 12. Suggested commit sequence (small, reviewable)

1. `build(deps): add pillow as a direct dependency` _(after approval)_
2. `feat(config): image upload size, dimension, and per-page quota limits`
3. `feat(domain): RegistrationImage, ProcessedImage and <img> snippet generation`
4. `feat(service): image processing pipeline (validate, re-encode, downscale)`
5. `feat(adapters): registration_images table, mapper, repository + migration`
6. `feat(service): add/list/delete registration images with quota and dedup`
7. `feat(registration): serve registration images from the database`

(Docs/spec already committed separately per project convention.)

## 13. Decisions (resolved with Doctor Chewie)

All previously-open questions are now settled and folded into the plan above:

1. **Pillow** — `uv add pillow` done (§3); committed first in the sequence.
2. **Output format** — **always PNG**. Chosen for logo crispness and fewer code
   paths: no JPEG branch, content type is always `image/png`, the asset
   extension is always `.png` (§5.1, §6).
3. **`MAX_EDGE`** — **2048 px** confirmed (banner width) (§4, §6).
4. **Audit trail** — **yes**: adding and deleting an image appends a
   `RegistrationPageActivity` entry to the page, like HTML edits (§8.1, §8.3).
5. **`created_by`** — users are **disabled, not deleted**, so audit references
   stay intact. `created_by` is therefore a plain non-cascading FK to `users`
   (no `ON DELETE SET NULL`); nullable only so a future system/script upload has
   a home (§7.1).
