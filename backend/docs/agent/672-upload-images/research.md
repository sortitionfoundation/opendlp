<!-- ABOUTME: Research and options for adding image uploads to registration form pages. -->
<!-- ABOUTME: Covers storage, serving domain, validation, optimisation, and GDPR considerations. -->

# Image uploads for registration form pages — research

**Issue:** 672 · **Status:** research / pre-decision · **Date:** 2026-06-11

## 1. What we are trying to do

Organisers author the HTML for an assembly's public registration page (see
`registration_page_html_sources.form_html`). They want to embed images in that
HTML — a logo, a banner, an illustrative photo of the assembly venue, etc. We
need a way for an organiser to upload an image and reference it from their form
HTML by a stable URL.

This document lays out the options across the questions Doctor Chewie raised
(storage, serving domain, limits, scanning, optimisation) plus a few that fell
out of the research, with pros/cons and a recommendation for each. **No code has
been written** — this is to support a decision.

## 2. Relevant facts about the current system

These shape the options; sources are `file:line` in this repo unless noted.

- **No _file_ is persisted today, but we do accept untrusted input.** Two
  existing precedents matter:
  - **CSV uploads** (`entrypoints/blueprints/respondents.py:116`, `forms.py:591`)
    read the file into memory, validate it, stage the parsed rows in **Redis
    with a 30-minute TTL** (`service_layer/csv_upload_stash.py`), then on confirm
    write the _parsed contents_ (respondents) into the database. The CSV file
    itself is never stored — only its parsed data. So we have a precedent for
    _receiving, validating, and staging_ an upload.
  - **Author HTML** for registration pages is submitted as a form field and
    **persisted verbatim** in `registration_page_html_sources.form_html`, then
    rendered through a sandboxed Jinja env (see below). So we already accept and
    durably store large chunks of untrusted author content.
  - What's new for images is storing **opaque binary bytes** and serving them
    back — neither precedent covers that.
- **Static files are repo/build-time only.** Everything under `static/` comes
  from the repo or a one-time build step (e.g. Tailwind CSS at Docker image
  build), served by **WhiteNoise under Gunicorn** with a 1-year immutable cache
  (`entrypoints/extensions.py`). User-uploaded images are _dynamic content_ and
  **must not** go in `static/` — that directory is immutable per deploy and
  shared into the image, not a writable upload target.
- **CSP is set in `get_secure_headers()` in `flask_app.py`** via the `secure`
  library. Current `img-src` is `'self' data:`. Author form HTML is rendered in
  a **sandboxed Jinja environment** with the CSP nonce _deliberately withheld_
  (`service_layer/registration_page_service.py`) so authors cannot whitelist
  their own inline scripts. `default-src` is `'self'`; `object-src 'none'`;
  `frame-ancestors 'none'`.
- **Multi-container, no shared filesystem.** `app` (Gunicorn) and `app_celery`
  run the same image but are **separate containers with separate ephemeral
  filesystems** (see `system-architecture.md`). Anything written to a container
  FS is lost on restart and is invisible to the other container unless a Docker
  volume is mounted. Postgres and Redis are the only shared, persistent stores.
- **Pillow 12.2.0 is already a dependency** (transitive, in `uv.lock`). So
  re-encoding/resizing images needs **no new package**. `python-magic` is _not_
  present (would be a new dep + the `libmagic1` system lib).
- **Celery is already wired up** (`entrypoints/celery/`), so async processing is
  available if we want it — but see §6, we probably don't.
- **GDPR posture (CLAUDE.md / AGENTS.md):** every persistent copy of personal
  data must be findable and blankable by ID; we must _not_ keep long-term file
  copies that can't be easily found and blanked.

## 3. Issue: where to store the image bytes

Three realistic options given "no cloud service".

### Option A — PostgreSQL `bytea` column ⭐ decided

Store the (re-encoded) image bytes in a new table, e.g. `registration_images`
with `id`, `assembly_id`/`registration_page_id` FK, `content_type`, `byte_size`,
`width`, `height`, `sha256`, `data BYTEA`, `created_at`, `created_by`.

**Pros**

- **Solves the multi-container problem for free.** Both `app` and `app_celery`
  reach Postgres by service name; no shared volume to provision or back up
  separately.
- **One consistent backup/restore.** Images travel in the same `pg_dump` /
  snapshot as the rows that reference them — no second file-backup pipeline to
  keep in sync.
- **Transactional.** Insert/update/delete of the image is atomic with its
  owning row. No orphaned-file reconciliation, no crash-between-write problem.
- **Trivially blankable** if a takedown is ever needed: `UPDATE … SET data = NULL`
  keeps the ID row, no filesystem `unlink` to coordinate. (A nice-to-have, not a
  driver — see the decided note below.)
- **Size range is ideal.** Postgres TOASTs large values out-of-line
  automatically; `bytea` caps at 1 GB (irrelevant). Research (Microsoft "To BLOB
  or Not To BLOB", SQLite `fasterthanfs`) puts the DB at parity-or-better for
  blobs under ~256 KB-1 MB, which is exactly our target after optimisation.

> **Decided:** the images are organisation logos on public pages, so there is
> **no GDPR concern for the image content**, and that is not expected to change.
> This removes GDPR-blanking as a deciding factor — it was one of the two main
> original arguments for `bytea`. (Registrant personal data is unaffected; these
> images are not personal data.)

**Cons**

- **Dump bloat** if volume ever grew to _gigabytes_ of imagery — at our scale
  (tens of images × low-hundreds-of-KB) it's seconds, negligible. Mitigations
  exist later (`STORAGE EXTERNAL` to skip pointless re-compression of JPEG/WebP;
  `pg_dump --exclude-table-data` + separate snapshot) but are not day-one work.
- Slightly more code than dropping a file on disk — but _less_ than doing
  on-disk storage _correctly_ (see Option B cons).
- Must serve via an app route (can't let WhiteNoise/proxy serve it) — but we
  want an app route anyway for access control and correct headers (§5, §7).

### Option B — Local filesystem + path in DB

Write files to a mounted Docker volume; store the path/filename in the DB.

**Pros**

- Conventional advice for media; cheap to serve via `X-Accel-Redirect` /
  `X-Sendfile`; keeps the DB small.

**Cons (these are the deciding factors against it here)**

- **Needs a shared writable volume** mounted into _both_ `app` and `app_celery`,
  or images written by one are invisible to the other. New infra in every
  compose file + deploy doc.
- **No ACID across DB+FS** — crashes leave orphaned files or dangling rows;
  robust designs end up reinventing two-phase commit.
- **GDPR deletion becomes a two-system operation** (blank row _and_ unlink file);
  orphaned files are a standing compliance risk — exactly what our GDPR note
  tells us to avoid ("must not keep long-term file copies that can't be easily
  found and blanked").
- The "filesystem wins" performance argument is about multi-GB, high-throughput
  media — it doesn't apply at our size/volume.

> **Decided:** only the `app` container handles images — they're uploaded to and
> served by `app`; **no other container needs access** (celery never touches
> them). This **weakens** the filesystem cons above: a volume need only be
> mounted into one container, not shared. So "cross-container sharing" — the
> _other_ main `bytea` driver — also largely falls away. A single-container
> bind mount / named volume becomes a realistic option.

### Option C — Redis only (transient, like the CSV stash)

**Verdict: no.** Redis is `allkeys-lru`, 450 MB capped, "ephemeral by design"
(sessions and queued tasks are lost on restart). Registration-page images must
persist for the life of the page. Redis is right for the _upload preview /
staging_ step (mirroring the existing CSV stash) but not for the durable copy.

### Recommendation

The two clarifications above (no GDPR concern, single-container) remove the two
_strongest_ original arguments for `bytea`, so the decision is **closer than the
first draft implied**. On the remaining merits, **`bytea` still edges it**:

- **No volume to provision or back up.** Even a single-container volume is new
  infra — a mount in every compose variant (`compose.production*.yaml`), plus a
  separate backup path. `bytea` keeps images inside the one Postgres backup we
  already take.
- **Transactional + no orphans.** Image rows live and die with their owning
  registration page (FK + cascade); no reconcile job, no crash-between-writes
  orphaned files.
- **Volumes are small** (≤10 images/page × low-hundreds-of-KB), so dump bloat is
  a non-issue.

Filesystem-on-a-single-container (Option B) is a reasonable alternative that
would lean on `X-Sendfile` / direct static serving.

> **Decided: store the images in the database (`bytea`, Option A).** We accept
> the closer-than-first-thought trade-off in favour of operational simplicity —
> one store, one backup, no volume. **Option B is kept on record above** as the
> fallback to return to if image volume ever grows into multi-GB territory or we
> otherwise want bytes out of Postgres.

## 4. Issue: serve from the main domain or a separate `files.xyz` domain?

### The security rationale for a separate origin

Big platforms (GitHub `githubusercontent.com`, Google `googleusercontent.com`)
serve user content from a **separate registrable domain** so that if a file ever
executes as active content, it runs in an origin with **no cookies, no session,
no access** to the main app. It must be a separate _registrable domain_, not a
subdomain — cookies and `document.domain` leak across subdomains, and CSP can't
restrict cookie scope. The threat it defends against is **stored XSS via
uploaded files** (SVG with `<script>`, HTML polyglots, MIME-sniffed responses)
leading to session/token theft and account takeover.

### Why it is likely overkill _for us_

That pattern exists because those platforms serve **arbitrary attacker-controlled
file types at scale**. Our case is narrow: **raster images embedded inline in a
registration page**. If we control the pipeline — reject SVG, re-encode every
image through Pillow, send `nosniff` — the residual risk the separate domain
defends against is **eliminated at the source**. Re-encoding is the keystone
control (§5): it discards everything that isn't pixel data, so a polyglot or
embedded script cannot survive.

A second registrable domain also has real operational cost for a small
self-hosted civic app: extra DNS, a second TLS cert, separate vhost/routing, and
CSP/`form-action` adjustments — disproportionate to the residual risk once
images are raster-only and re-encoded.

### Options

| Option                                              | What                                                                                                                | Verdict                                                                                                 |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **A. Main domain, app route** ⭐                    | Serve via `/…/images/<id>` from the Flask app, raster-only + re-encode + `nosniff` + `Content-Type` set server-side | Recommended. Safe for an image-only pipeline; no new infra.                                             |
| B. Separate registrable domain                      | `opendlpusercontent.org` (or similar), cookie-less, restrictive CSP/sandbox                                         | Defensible but disproportionate now. Reconsider **only** if we ever accept SVG or arbitrary file types. |
| C. `Content-Disposition: attachment` on main domain | Forces download, neutralises inline script                                                                          | **Rejected** — incompatible with the whole point (inline embedding).                                    |

### CSP implications (small, either way)

- `img-src` is currently `'self' data:`. Serving from the **main domain** needs
  **no CSP change** — `'self'` already covers it. (We could drop `data:` if we
  decide author HTML should reference uploaded images by URL only, not inline
  base64 — worth considering, see open questions.)
- A **separate domain** would require adding that origin to `img-src` and
  reviewing `default-src`.
- Independent of domain choice, we should keep `object-src 'none'` and serve
  images with `X-Content-Type-Options: nosniff` and a correct server-set
  `Content-Type`. The author-HTML sandbox already withholds the CSP nonce, so
  authors can't introduce inline script regardless.

### Recommendation

**Option A — main domain, served by a dedicated app route**, relying on
raster-only + mandatory re-encode + `nosniff` as the real controls. Record the
separate-domain option as the documented fallback if the accepted-types policy
ever broadens.

> **Decided:** main domain, dedicated app route (agreed). The separate-domain
> option is parked as the documented fallback.

## 5. Issue: validation, limits, and how much scanning

**Threat model (decided):** only **assembly managers** can upload today, but we
may allow self-signup in future, so we treat uploads as **fully untrusted** and
build to be proof against malicious files regardless of who is uploading. We do
not lean on "the uploader is trusted" as a control.

Defence-in-depth; no single check is sufficient. Ordered cheapest gate first so
we **reject bad files fast, before any expensive pixel decode**:

1. **Byte-size cap before anything is read.** Set a cap so oversized bodies get a
   413 before we buffer them. This is currently app-global via `MAX_CSV_UPLOAD_MB`
   (default 50 MB) in `config.py` — the image route wants its own, smaller cap
   (route-level guard on `request.content_length`, or a dedicated config value;
   `MAX_CONTENT_LENGTH` is app-wide). **Decided: 10 MB** — phone photos can
   exceed 5 MB, and we downscale afterwards anyway.
2. **Cheap format gate at open time — and yes, Pillow gives us this.** Answering
   the question directly: `Image.open()` is **lazy**. It reads only the file
   header to identify the format and dimensions; it does **not** decode pixel
   data until `.load()` (or an op that triggers a load). So immediately after
   `open()` we can read `img.format` and `img.size` cheaply and **reject before
   the expensive decode**:
   - `img.format not in {"PNG", "JPEG", "WEBP"}` → reject (no SVG — it isn't even
     a raster format Pillow opens as an image — no GIF/animated).
   - `img.size` over our pixel/dimension ceiling → reject (decompression-bomb
     guard; Pillow already raises `DecompressionBombError` past 2× its
     `MAX_IMAGE_PIXELS`, which we promote from warning to error).
     This is content-based detection — we never trust the client `Content-Type` or
     the file extension, both trivially spoofed — and it needs **no `python-magic`
     / `libmagic1`**, just Pillow which is already a dependency.
3. **Re-encode every surviving image through Pillow — the keystone.** Only now,
   for allowed formats within limits, do we force a full decode and write a
   brand-new file. This is OWASP's "image rewriting" (Content Disarm &
   Reconstruction): it discards appended payloads, polyglot trailers, embedded
   scripts, and EXIF/GPS in one step. Sketch (preserving transparency for logos —
   see §6 on output format):
   ```python
   from PIL import Image, ImageOps
   img = Image.open(upload.stream)
   if img.format not in {"PNG", "JPEG", "WEBP"}:   # cheap gate, header only
       reject()
   img = ImageOps.exif_transpose(img)              # bake in rotation, drop EXIF
   img.load()                                       # force full decode now
   img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)  # downscale (§6)
   # save to an in-memory buffer as PNG (if it has alpha) else JPEG; store bytes
   ```
   This single step makes same-origin serving genuinely safe and doubles as
   EXIF/GPS stripping.
4. **Server-generated identifiers.** Store under a content hash (the sha256 of
   the re-encoded bytes — see §7); never reflect the user's filename into a path
   or header (avoids path traversal and the CRLF/`Content-Disposition`
   header-injection bypass). `secure_filename()` only if we ever surface the
   original name in the UI.

**ClamAV / antivirus:** **skip it.** It targets known-malware signatures and is
resource-hungry; it adds little over re-encoding for a raster-only pipeline.
Worth it only if we later accept un-re-encodable types (PDF, Office) or have a
compliance mandate.

**How much scanning before we agree to serve?** For raster images the honest
answer is: **size cap → format/dimension gate → re-encode** _is_ the scan. If an
image survives a full Pillow decode + re-encode within the size and dimension
limits, it's safe to serve with `nosniff`. No further scanning needed at our
scale — and this holds even if uploaders become untrusted self-signups.

## 6. Issue: image optimisation

**Yes, optimise — synchronously, in the request, with plain Pillow.** It's free
(Pillow is already a dep) and folds into the mandatory re-encode.

- **Library:** plain **Pillow**. `pillow-simd` (x86-only, pinned to old Pillow
  9.5/Py≤3.11, lagging) and `pyvips` (native libvips dep) are **overkill** —
  reach for them only if we ever batch-process large images.
- **Resize:** `thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)` — preserves aspect
  ratio, never upscales. **Decided: support banner width**, so `MAX_EDGE` ≈
  **1600-2048 px** on the long edge (enough for a full-width banner on a
  high-DPI screen; downscale anything larger).
- **Format/quality (decided: PNG/JPEG, not WebP).** Maximum compatibility and
  accessibility beat marginal byte savings here. Output **PNG** when the source
  has transparency (logos/line art — lossless, universal) and **JPEG**
  (`quality≈82, optimize=True`) for photographs without alpha. **Skip WebP as the
  output format**: its ~96% support means a small slice of visitors would get a
  broken image, and per the decision below that must never be a barrier to
  signing up.
- **Resilience: a broken image must never block signup (decided).** The logo is
  decorative — the form and its text carry the real content. So: always provide
  meaningful/empty `alt` text, never gate form submission on image loading, and
  keep the layout intact if the image 404s (see §7 — a missing/closed image
  returns 404 cleanly rather than erroring the page).
- **Sync, not Celery.** Resizing one small image is tens of milliseconds — well
  within request time. Celery would add broker/worker/status plumbing for no
  gain. We _have_ Celery if volume ever explodes, but don't pre-build it.
- **Responsive `srcset`/`<picture>`: skip.** Overkill for a few-hundred-KB image
  shown at roughly one size. A single optimised image is fine.
- **AVIF / WebP: skip.** Marginal gain, slower/less-universal — not worth it for
  a decorative logo where compatibility matters most.

## 7. Serving mechanics & caching

- **Serve via a Flask route under the `/register/` path (decided).** Mirror the
  registration form's own URL space:
  `GET /register/<url_slug>/assets/<imagename>.png` (where `<imagename>` is the
  sha256 from §5/below). Rationale:
  - `<url_slug>` is already globally unique per registration page, so this **side-
    steps filename collisions between assemblies** for free — no cross-assembly
    namespace to manage.
  - It lets us **return 404 when registration is closed**, exactly as the form
    route already does — the assets share the form's lifecycle and visibility.
  - It keeps the whole feature **scoped to registration** (see §11 decisions),
    rather than a generic `/public/<assembly_id>/image/...` space that would also
    force a public/private visibility decision we don't need yet (YAGNI).
    The route returns the `bytea` via `send_file`/a `Response`; an app route is
    required anyway because the bytes live in Postgres and we want to set headers.
- **Headers:** `Content-Type` set server-side from the stored value;
  `X-Content-Type-Options: nosniff`; `Cache-Control`.
- **Content-addressed caching.** Store and address images by the **sha256 of
  their (re-encoded) bytes**. The hash _is_ a content fingerprint, so a changed
  image gets a new URL and we can serve `Cache-Control: public, max-age=31536000,
immutable` with no staleness risk. The hash also gives free dedup and
  eliminates user-controlled filenames entirely (kills filename/path-traversal
  concerns — we only ever handle our own hex strings). This is the single
  highest-leverage serving choice and is cheap.
- **ETag caveat with `bytea`.** Flask's `send_file` auto-generates ETag/304 for
  real _file paths_ but **not** for in-memory `BytesIO`. Since we stream from the
  DB, set the `ETag` ourselves (use the stored `sha256`), `last_modified`, and
  call `response.make_conditional(request)` to get 304s — or just rely on the
  `immutable` long-cache above, which sidesteps revalidation entirely.
- **Access control:** images embedded in a _public_ registration page are
  themselves public, so the GET route is likely unauthenticated — but the
  **upload** route must be behind the same assembly-manager permission used for
  editing the registration page (`backoffice_registration.py`).
- **No `X-Accel-Redirect`/`X-Sendfile`** — those are for filesystem storage;
  with `bytea` we stream from the DB. At our size/volume that's fine.

## 8. How images plug into the registration form feature

This is the part that makes it concrete and is worth deciding early.

- Author HTML lives in `registration_page_html_sources.form_html` and is
  rendered in a **sandboxed Jinja env** with no CSP nonce. Authors reference an
  image by URL, e.g.
  `<img src="/register/<url_slug>/assets/<sha>.png" alt="…">`.
- **Workflow now (decided): paste a pre-made `<img>` tag.** The backoffice
  registration editor (`backoffice_registration.py` / `templates/backoffice/...`)
  gets an upload UI that lists an assembly's uploaded images and, for each, offers
  a **ready-to-paste `<img>` snippet** (correct URL + an `alt` placeholder) plus
  a delete action. The author pastes the snippet into their form HTML.
- **Workflow later (don't build now, don't block): a richer media-picker.** A
  future GUI form-builder will want a proper media-picker rather than
  copy-paste. We are **not** building that in this story, but we should avoid
  decisions that make it harder — e.g. keep the upload + storage + serving as a
  clean service/repository boundary the future picker can reuse, and don't bake
  assumptions that only hand-written HTML will ever reference these images.
- **Linking images to a page's lifecycle:** when a registration page is deleted
  (`ondelete="CASCADE"` on the page tables), its images should cascade too. Tie
  `registration_images` to the registration page (and/or `assembly_id`) so the
  FK + cascade handles cleanup. The serving route resolves `<url_slug>` →
  page → its images, so closed/deleted pages naturally 404 their assets.
- **`_delete_all_test_data()` in `tests/conftest.py`** and
  `delete_all_except_standard_users()` in `tests/bdd/conftest.py` must learn
  about the new table (child-before-parent FK ordering), per CLAUDE.md.
- **Migration:** `uv run alembic revision --autogenerate -m "add registration images"`.

## 9. GDPR considerations

- **Decided: no GDPR concern for the image content** — these are organisation
  logos on public pages, not registrant personal data. So GDPR is **not** a
  driver for the design (it was downgraded as a storage tie-breaker in §3).
- We still get the good hygiene for free: the mandatory re-encode (§5) strips
  EXIF/GPS, and `bytea` keeps any future takedown a trivial `SET data = NULL`
  blank-by-ID — but neither is load-bearing for this feature.
- **Don't** keep transient originals anywhere long-lived: do the re-encode in
  memory, persist only the optimised result, and let any preview/staging copy
  live in the Redis stash with a short TTL (mirroring the CSV pattern). This is
  general good practice, not a GDPR requirement here.

## 10. What else to think about (raised by the research)

- **Per-route size cap vs the global `MAX_CONTENT_LENGTH`.** It's currently
  app-global and tied to the 50 MB CSV cap. We need a smaller effective cap for
  images without shrinking the CSV path — decide the mechanism (route guard vs
  reconfiguring). New env var `MAX_IMAGE_UPLOAD_MB` following the existing
  `get_max_csv_upload_mb()` pattern in `config.py`.
- **Quota (decided): 10 images per registration page.** A simple count cap;
  prevents a compromised/malicious account bloating the DB. Enforce on upload.
- **Rate limiting** on the upload route (we already have rate-limit machinery in
  Redis for login).
- **Whether to allow `data:` URIs at all — pending team discussion.** If authors
  reference images by our URL, we could **drop `data:` from `img-src`** and
  disallow inline base64 in author HTML — smaller attack surface, forces
  everything through the validated pipeline. Trade-off: less author flexibility.
  Doctor Chewie is raising this with the team; **left open** for now.
- **Content moderation.** Organisers are trusted-ish, but there's no review step
  on what they upload to a public page. Probably acceptable; note it.
- **i18n** on all new user-facing strings (`_()` / `_l()`), per CLAUDE.md.
- **Test pyramid:** unit (validation/re-encode/repository), integration (upload
  → store → serve round-trip), and BDD/e2e (organiser uploads, references in
  form, public page renders). CLAUDE.md's no-skip testing policy applies.
- **Accessibility:** the upload UI and any inserted `<img>` need alt-text
  guidance (component accessibility guide) — and per §6, a broken image must
  never block signup.

## 11. Recommended approach (summary)

| Question               | Decision                                                                        |
| ---------------------- | ------------------------------------------------------------------------------- |
| Scope                  | **Registration pages only** (YAGNI on a generic media store)                    |
| Storage                | **Postgres `bytea`** in a new `registration_images` table (Option B = fallback) |
| Serving domain / route | **Main domain**, `GET /register/<url_slug>/assets/<sha>.png`; 404 when closed   |
| Container access       | **`app` only** — celery never touches images                                    |
| Transient/staging copy | Redis stash with short TTL (reuse CSV pattern), in-memory processing            |
| Accepted (input)       | **PNG, JPEG, WebP — reject SVG**, skip GIF/animated; untrusted threat model     |
| Served (output)        | **PNG (alpha) / JPEG (photo)** — not WebP, for max compatibility                |
| Size limit             | **10 MB** upload cap, then downscale                                            |
| Validation             | size cap → cheap Pillow format/dimension gate → **mandatory re-encode**         |
| AV scanning            | **None** (re-encode is the disarm step)                                         |
| Optimisation           | **Pillow, synchronous**, `thumbnail` LANCZOS to ~1600-2048 px (banner width)    |
| Quota                  | **10 images per registration page**                                             |
| Referencing model      | **Paste a pre-made `<img>` tag** now; keep clean boundary for a future picker   |
| Serving headers        | server-set `Content-Type`, `nosniff`, content-hash `Cache-Control`/`ETag`       |
| New dependencies       | **None** (Pillow already present; no `python-magic`, no ClamAV)                 |
| CSP change             | **None needed** for main-domain `'self'`; `data:` drop pending team discussion  |

## 12. Decisions and remaining open question

Resolved with Doctor Chewie (all reflected above):

1. **Referencing model** — paste a pre-made `<img>` tag for now; keep a clean
   service/repository boundary so a future GUI form-builder media-picker can
   reuse it. Don't build the picker in this story; don't block it either.
2. **Display size** — support **banner width**; `MAX_EDGE` ≈ 1600-2048 px.
3. **Quota** — **10 images per registration page**.
4. **Format policy** — **reject SVG** (confirmed); input PNG/JPEG/WebP, serve
   PNG/JPEG.
5. **Scope** — **registration pages only**; YAGNI on a generic media store, add
   a parallel implementation if/when another use case appears.
6. **Storage** — **store images in the database (`bytea`)**; Option B
   (single-container filesystem) kept on record in §3 as the fallback.

Still open (but **does not block the build**):

- **`data:` URIs in `img-src`** — keep allowing inline base64 in author HTML, or
  drop `data:` to force everything through the validated upload pipeline. Decided
  that we **build the happy path with `<img src="<url>">` regardless**, so this
  is purely a **CSP-header policy decision** with no effect on what we
  implement. Doctor Chewie is settling the policy with the team.

---

### Sources

Storage: PostgreSQL wiki _BinaryFilesInDB_; Microsoft Research _To BLOB or Not To
BLOB_; SQLite _fasterthanfs_; CYBERTEC binary-data-performance; Docker storage
docs. Serving-domain & XSS: OWASP File Upload / CSP cheat sheets; OWASP
Unrestricted File Upload; w3c/webappsec#432; CSP-cookies; eliranturgeman uploads
attack surface; markitzeroday Content-Disposition bypass; Tenable TRA-2026-25;
GitHub usercontent rationale (rgrove/rawgit#197). Validation: OWASP File Upload
Cheat Sheet; python-magic; Pillow `verify`/`MAX_IMAGE_PIXELS` docs; OPSWAT
polyglot; SVG XSS advisories (Plane, Traccar, SVGMagic CVE-2024-4270). Limits &
optimisation: Flask file-uploads / web-security docs; Werkzeug request_data
(`MAX_FORM_MEMORY_SIZE`/`MAX_FORM_PARTS`); Pillow image-file-formats; caniuse
WebP/AVIF; testdriven Flask+Celery. Full URLs retained in the issue-672 research
notes.
