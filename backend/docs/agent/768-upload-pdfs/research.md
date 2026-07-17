<!-- ABOUTME: Research and options for adding PDF uploads (download links) to registration pages. -->
<!-- ABOUTME: Revisits the 672 image-storage decision for large files; covers storage, serving, security, GDPR. -->

# PDF uploads for registration pages — research

**Issue:** 768 · **Status:** decided — **Option A (`bytea`)**; see `domain-service-plan.md` · **Date:** 2026-07-16 (decision 2026-07-17)

## 0. TL;DR

We already ship image uploads for registration pages, storing re-encoded image
bytes in Postgres (`registration_images.data BYTEA`). The new requirement is to
let organisers attach **PDFs** to a registration page, and "some PDFs can be
quite big". This document asks whether PDFs should follow the same `bytea` path
or diverge to filesystem storage.

Two of the 672 decision's load-bearing premises do **not** transfer to PDFs:

1. **Size.** 672 explicitly scoped `bytea` to blobs "under ~256 KB–1 MB" — its
   own quantitative case. "Quite big" PDFs land on the wrong side of that line.
2. **The re-encode disarm step.** 672's keystone security control was
   re-encoding every image through Pillow to strip active content. **You cannot
   safely re-encode a PDF that way** — PDFs are active-content-capable.

The second point is **healed for free** by a product decision already taken:
PDFs are consumed as a **download link**, not an inline embed. Serving them as
`Content-Disposition: attachment` means they never render as active content in
our origin, so the security story collapses back to "cheap validation + forced
download" and neither re-encoding nor a separate origin is required.

> **DECIDED (2026-07-17): Option A — Postgres `bytea`.** The team confirmed the
> PDFs are **all under 1 MB, at most 3 per assembly, and often zero.** That is
> comfortably inside the ~256 KB–1 MB parity band the 672 research cited, so the
> two costs that would have pushed us to on-disk storage — memory-per-download
> and dump bloat — are negligible at this size and volume. We therefore **mirror
> the shipped image feature**: bytea in a new `registration_documents` table,
> served by an app route with `Content-Disposition: attachment`. Option B
> (on-disk) stays on record below as the fallback if the size/volume assumption
> ever breaks. Implementation is specified in `domain-service-plan.md`.

## 1. What we are trying to do

Organisers author the HTML for an assembly's public registration page
(`registration_page_html_sources.form_html`). Today they can upload images and
paste a ready-made `<img>` snippet into that HTML (issue 672, shipped). The new
requirement: let an organiser upload a **PDF** — an information pack, agenda,
privacy notice, terms — and reference it from their form HTML as a **download
link**, e.g. `<a href="/register/<slug>/documents/<id>.pdf">Information pack
(PDF)</a>`.

Decided so far (with Doctor Chewie, 2026-07-16):

- **Consumption model: download link.** Not an inline/embedded viewer. This is
  the decision that simplifies security (see §5).
- **Intended use: public documents** (info pack, agenda, etc.), not registrant
  personal data. Makes GDPR neutral for the content (see §6).
- **Size/volume: all under 1 MB, ≤3 per assembly, often zero** (team, 2026-07-17).
  This resolves the storage pivot (§3) in favour of **Option A (`bytea`)**.

## 2. What we already have (from issue 672)

The image feature is built and merged; the PDF feature should mirror its shape
wherever the two genuinely rhyme, and diverge only where PDFs differ.

- **Storage:** `registration_images` table, `data` column is `LargeBinary`
  (Postgres `bytea`), FK to `registration_pages` with `ondelete="CASCADE"`, plus
  `byte_size`, `width`, `height`, `sha256`, `alt`, `original_filename`,
  `created_by`, `created_at`, and a unique `(registration_page_id, sha256)`
  index. See `adapters/orm.py:666`.
- **Service boundary:** `service_layer/registration_image_service.py` (validate,
  store, list, delete, resolve-for-serving) and
  `service_layer/image_processing.py` (the Pillow re-encode/resize). Clean
  service/repository seam — a PDF feature can sit alongside it as
  `registration_document_service.py` without disturbing images.
- **Serving:** public route `serve_registration_image` in
  `entrypoints/blueprints/registration.py:346`. It loads the **whole blob into
  app memory** and returns it: `Response(served.data, mimetype=...)` then
  `response.make_conditional(request)`. Every byte served passes through
  Gunicorn's memory. Fine for a ~200 KB re-encoded image; the crux of the PDF
  problem (§3). Note this is a property of serving from `bytea` (a `BytesIO`
  has no file descriptor), **not** a limitation of our stack: WhiteNoise already
  serves the build-time `static/` dir efficiently via the OS `sendfile` syscall
  (`wsgi.file_wrapper`, no bytes through Python — see ADR 0008), and Flask's
  `send_file(<path>)` gets the same treatment under Gunicorn. That efficient
  path is available to **on-disk** documents (Option B), never to `bytea`
  (Option A). WhiteNoise itself, though, scans its root **at startup**, so it is
  the wrong tool for files uploaded at runtime — an on-disk PDF is served by the
  app via `send_file` or by the proxy directly (§4), not by our WhiteNoise
  instance.
- **Config knobs** (`config.py`): `MAX_IMAGE_UPLOAD_MB` (default 10, clamped
  1–25), `REGISTRATION_IMAGE_MAX_EDGE_PX`, `MAX_IMAGES_PER_REGISTRATION_PAGE`
  (default 10). A PDF feature wants its own parallel `MAX_PDF_UPLOAD_MB` etc.
- **Test-data teardown:** any new table must be added to
  `_delete_all_test_data()` in `tests/conftest.py` and
  `delete_all_except_standard_users()` in `tests/bdd/conftest.py`
  (child-before-parent FK ordering), per CLAUDE.md.

## 3. The storage decision — spelled out in full

The 672 research chose `bytea` **because the files were small and re-encoded**.
Read literally, it bracketed its own conclusion:

- §3 Option A: "Research puts the DB at parity-or-better for blobs **under ~256
  KB–1 MB**, which is exactly our target after optimisation."
- §3 cons: dump bloat is negligible "_at our scale_ (tens of images ×
  low-hundreds-of-KB)".
- §7: "No X-Accel-Redirect… with bytea we stream from the DB. **At our
  size/volume that's fine.**"

PDFs are 10–100× the per-file size and are **not** shrunk by any re-encode step,
so each of those three caveats is exactly what changes. Below are the two real
options, in detail. (672's Option C — Redis only — remains a "no": Redis is
`allkeys-lru`, capped, ephemeral; documents must persist for the life of the
page. Redis stays right only for a short-TTL upload preview/staging copy.)

### Option A — PostgreSQL `bytea` (mirror the image feature)

Store the validated PDF bytes in a new `registration_documents` table:
`id`, `registration_page_id` FK (`ondelete="CASCADE"`), `content_type`
(`application/pdf`), `byte_size`, `sha256`, `data BYTEA`, `original_filename`,
`created_by`, `created_at`, unique `(registration_page_id, sha256)`.

**Pros**

- **Zero new infrastructure.** No volume to provision, mount, or add to every
  compose variant; no second backup pipeline. Documents ride inside the one
  `pg_dump`/snapshot we already take.
- **Transactional, no orphans.** Insert/delete of the document is atomic with
  its owning row; FK + cascade cleans up when a page is deleted. No
  DB-vs-filesystem reconciliation, no crash-between-writes orphaned files.
- **Consistent with what's shipped.** Same table shape, same service/repository
  pattern, same serving route family as images — one mental model, less code to
  review, obvious for the next maintainer.
- **GDPR-friendly if documents ever contain personal data** (see §6): takedown
  is a trivial `UPDATE … SET data = NULL` blank-by-ID, no filesystem `unlink` to
  coordinate. This is the CLAUDE.md "findable and blankable by ID" strategy for
  free.
- **Content-addressed caching** works identically to images: address by the
  `sha256`, serve `Cache-Control: public, max-age=31536000, immutable`, set
  `ETag` from the hash.

**Cons**

- **Memory per download.** Serving is `Response(bytes)` — the entire PDF is read
  into Postgres → SQLAlchemy → Python memory → the response, per request. A
  30 MB PDF × N concurrent downloads is real Gunicorn memory. This is the single
  biggest reason the option degrades with size, and we have **no** `X-Sendfile`
  offload today to relieve it.
- **Backup/dump bloat.** Every `pg_dump` carries every PDF byte. At
  hundreds-of-KB images this was "seconds, negligible" (672). At multi-MB PDFs ×
  many pages it grows backup size, backup time, and restore time. Mitigations
  exist (`STORAGE EXTERNAL` to skip pointless re-compression of already-
  compressed PDFs; `pg_dump --exclude-table-data` + a separate snapshot) but
  they're extra work and partly reinvent the filesystem split anyway.
- **TOAST overhead.** Postgres TOASTs large values out-of-line and tries to
  compress them; PDFs are already compressed, so the compression attempt is
  wasted CPU (mitigated by `STORAGE EXTERNAL`). Reads reassemble chunks. Works
  fine, but it's overhead that scales with size.

**Best when:** PDFs are modest (≈≤ 2 MB) and few per page. Then the memory and
dump costs stay in the noise and operational simplicity wins outright.

### Option B — Local filesystem + path/key in DB (672's documented fallback)

Write the validated PDF to a mounted Docker volume; store a server-generated
relative path (or content-hash key) plus metadata in a `registration_documents`
row (same columns as Option A, but `data BYTEA` becomes `storage_path String`).

**Pros**

- **Bytes leave Postgres.** DB stays small; backups/dumps stay fast regardless of
  document size or count.
- **Efficient serving is available — and needs no proxy trickery.** On-disk
  files can be served two ways, both cheap and both a natural fit for a
  _download link_ (and precisely what `bytea` can't do):
  1. **App serves via `send_file(<path>)`.** Under Gunicorn this uses
     `wsgi.file_wrapper` → the OS `sendfile` syscall, so the file streams from
     the kernel without being read into Python memory — the same mechanism
     WhiteNoise uses for `static/` (ADR 0008). We keep the app in the loop for
     access control and the 404-when-closed check (§4). **No nginx, no
     `X-Accel-Redirect` needed.**
  2. **Caddy serves the mounted folder directly.** If we mount the upload volume
     into the Caddy container, a `file_server` on the `/register/*/documents/*`
     prefix serves files without ever hitting the app — maximally efficient, but
     it bypasses app-level access control and page-lifecycle 404s, so we'd only
     use it for genuinely public documents (§6 says they are). Note Caddy has
     **no** `X-Accel-Redirect` / `X-Sendfile` equivalent — that header is
     nginx-specific — so the "app returns a redirect header, proxy streams the
     file" pattern is **not** available to us; it's option (1) or a direct
     `file_server`, not a hybrid.
- **Natural fit for large/unbounded files.** The "filesystem wins for big media"
  argument that didn't apply to images _does_ apply once files are multi-MB.

**Cons**

- **New infrastructure.** A writable volume mounted into the `app` container,
  added to every compose variant (`compose.production*.yaml`) and the deploy
  docs. (Note: the **multi-container** objection that counted against this for
  images is _dead here_ — 672 decided only `app` touches these assets; celery
  never does. A single-container volume suffices.)
- **Second backup pipeline.** The volume must be backed up separately from
  Postgres and kept consistent with it. This is the strongest single argument
  _against_ B and _for_ A.
- **No ACID across DB + filesystem.** A crash between the file write and the row
  commit (or between row delete and file unlink) leaves orphaned files or
  dangling rows. Robust designs end up reinventing two-phase commit or running a
  reconcile/sweep job.
- **GDPR deletion becomes two-system.** Blank/delete the row **and** unlink the
  file; an orphaned file is a standing compliance risk — the exact thing the
  CLAUDE.md GDPR note warns against ("no long-term copies of uploaded files on
  disk that can't be easily found and blanked"). Only a concern if PDFs can
  carry personal data (§6), but if they can, this counts against B.
- **The efficient serving path is _not_ WhiteNoise-for-free.** WhiteNoise is
  wired only to the build-time `static/` root and scans it at startup, so it
  won't pick up runtime uploads. Efficient serving comes from `send_file(<path>)`
  (which does use the sendfile syscall under Gunicorn) or from a Caddy
  `file_server` on a mounted volume — both are small, well-trodden bits of
  config, but they are work we don't do today. This is a con only in the sense
  of "a little wiring", not "needs nginx" — see the Pros for the mechanics.

**Best when:** PDFs are routinely 5 MB+ or numerous, or effectively unbounded.
Then A's memory-per-serve and dump-bloat costs dominate and justify the new
infra.

### Option C (noted, not recommended now) — S3-compatible object storage

If we're moving bytes out of Postgres anyway, self-hosted **MinIO** (or any
S3-compatible store) gives Option B's "key in DB" model while folding **backup**
and any future **multi-container** access back in, and offloads serving via
presigned URLs. **But** it is new infrastructure _and_ a new dependency, which
per our rules needs Doctor Chewie's explicit sign-off, and 672 carried a stated
"no cloud service" constraint. Recorded as the escalation path if volumes ever
get genuinely large; **not** proposed for this story.

### Storage recommendation (resolved)

The pending number came back **< 1 MB, ≤ 3 per assembly, often zero**, which
lands squarely in the first bullet below. **Decision: Option A (`bytea`).**

- **PDFs ≈ ≤ 2 MB and few → Option A (`bytea`). ← this is us.** Mirror the image
  feature: one store, one backup, transactional cascade, zero new infra,
  consistent code.
- **PDFs routinely 5 MB+ or many → Option B (single-container volume +
  on-disk serving).** Accept the backup split and orphan-management in exchange
  for bounded memory and lean dumps. 672 already sanctioned this as the fallback
  "if bytes get big" — kept on record if the size assumption ever breaks.
- **In between / genuinely unbounded → escalate** to Doctor Chewie; consider
  Option C.

We deliberately **do not** build a speculative storage abstraction to hedge
across A and B — that's the kind of premature generality 672's YAGNI stance
rejects. The existing service/repository seam is enough to swap backends later
if the size estimate proves wrong.

## 4. Serving mechanics

- **Route:** mirror the image route's URL space under the registration page, so
  closed/deleted pages 404 their documents for free and there's no cross-assembly
  filename namespace to manage: `GET /register/<url_slug>/documents/<id>.pdf`
  (or `<sha>.pdf`). Resolve `<url_slug>` → page → its documents.
- **Under Option A:** `Response(data, mimetype="application/pdf")` +
  `make_conditional`, exactly like images (bytes through app memory).
- **Under Option B:** the app serves the file with `send_file(<path>, ...)`,
  which under Gunicorn uses `wsgi.file_wrapper` → the OS `sendfile` syscall, so
  the file streams from the kernel with ~zero app memory while we still run the
  page-lifecycle/404 check first. **We are on Caddy, not nginx, so the nginx
  `X-Accel-Redirect` "let the proxy stream it" trick is not available** — Caddy
  has no equivalent header. The two viable shapes are therefore (a) app
  `send_file` as above, or (b) mount the volume into Caddy and let a
  `file_server` on the documents prefix serve them directly, bypassing the app
  (public docs only — no per-request access control or closed-page 404; see §6).

- **Headers (both options):**
  - `Content-Type: application/pdf` (server-set, never from the client).
  - `Content-Disposition: attachment; filename="…"` — **the key security
    header** (see §5). Use a `secure_filename()`-sanitised display name; never
    reflect the raw client filename into the header (CRLF/`Content-Disposition`
    injection).
  - `X-Content-Type-Options: nosniff`.
  - `Cache-Control: public, max-age=31536000, immutable` + content-hash `ETag`
    if we address by `sha256` (same as images).
- **Access control:** documents on a _public_ registration page are public, so
  the GET route is unauthenticated (like images), but the **upload/delete**
  routes sit behind the same assembly-manager permission used for editing the
  registration page (`backoffice_registration.py`).

## 5. Security — why "download link" makes this tractable

The image pipeline's keystone control was **re-encoding through Pillow**: it
discards everything that isn't pixel data, so a polyglot or embedded script
can't survive, which is what made _inline, same-origin_ serving safe.

**PDFs have no equivalent.** They are active-content-capable (embedded
JavaScript, launch actions, embedded files, external references). There is no
lossless "re-encode to something inert" that disarms a PDF while keeping it a
usable PDF. So the 672 chain "main domain is safe because we sanitise" does
**not** transfer.

What rescues us is the **download-link** decision:

- Serving with `Content-Disposition: attachment` means the browser **downloads**
  the file rather than rendering it in our origin. Active content in the PDF, if
  any, only ever executes in the user's local PDF viewer against a file on their
  own disk — never in a page that shares our cookies/session. This is the same
  reasoning 672 used to _reject_ `Content-Disposition: attachment` for images
  (it defeats inline embedding) — but for PDFs, download **is** the requirement,
  so the control and the feature align.
- Therefore we do **not** need the separate-origin (`usercontent`) fallback, and
  we do **not** need to re-encode/flatten the PDF (a rabbit hole with no payoff
  once it's an attachment).

Validation we **do** keep (defence in depth, cheapest gate first):

1. **Byte-size cap before buffering** — a dedicated `MAX_PDF_UPLOAD_MB`
   (the number depends on §3; likely larger than the 10 MB image cap). Reject
   oversized bodies with 413 before reading them.
2. **Magic-byte check** — the file must start with `%PDF-`. Reject anything that
   doesn't. We never trust the client `Content-Type` or the `.pdf` extension.
   This needs no new dependency (a few-byte header read), matching 672's
   "no `python-magic`/`libmagic1`" posture.
3. **Server-generated identifiers** — store and address by `id`/`sha256`; never
   reflect the client filename into a path. Keep the original filename only as a
   display label (sanitised) for the download.
4. **Quota** — a per-page count cap (parallel to
   `MAX_IMAGES_PER_REGISTRATION_PAGE`) to stop a compromised account bloating
   storage.

**Deliberately skipped:** deep PDF structure parsing / sanitising (e.g.
stripping JS from the PDF) and ClamAV. Once the file is an attachment-download
and not rendered in our origin, the marginal safety doesn't justify the
dependency and complexity. Revisit **only** if the consumption model ever
changes from download to inline preview — that would reopen the whole §5 threat
model and likely force the separate-origin serving 672 parked.

## 6. GDPR considerations

**Decided (with Doctor Chewie, 2026-07-16): the intended use is public
documents** — information pack, agenda, privacy notice, terms and the like — not
registrant personal data. So, as with the 672 images, **GDPR is neutral for the
document content** and is **not** a driver for the storage choice. This also
clears the way for the Caddy-direct serving option (§4), which only suits
genuinely public files.

- The storage decision therefore rests purely on the size/ops tradeoff in §3 —
  there is no GDPR thumb on the scale toward Option A.
- **Guardrail, not a blocker:** because a PDF is inherently more capable of
  carrying personal data than a logo is, the upload UI should make the
  public-only intent explicit to organisers (a short note by the upload control),
  and we should treat "someone uploads a personal-data-bearing PDF anyway" as an
  operational/moderation matter (§7 notes there's no review step), not a reason
  to re-architect storage now.
- **What would change the answer:** if the use ever officially broadens to
  documents that hold personal data, the CLAUDE.md "findable and blankable by ID"
  rule kicks in and pulls **back toward Option A (`bytea`)** — blank-by-ID is a
  trivial `SET data = NULL`, whereas Option B would then need a reliable
  delete-plus-unlink path and an orphan sweep, and the Caddy-direct serving
  option would be off the table. Revisit this section if that happens.
- Regardless of the above: don't keep transient originals anywhere long-lived —
  validate in memory, persist only the stored copy, and let any preview/staging
  copy live in the Redis stash with a short TTL (the CSV/image pattern).

## 7. How PDFs plug into the registration form feature

- **Referencing model:** mirror images — the backoffice registration editor
  (`backoffice_registration.py` + templates) grows an upload UI that lists a
  page's uploaded PDFs and, for each, offers a **ready-to-paste `<a>` snippet**
  (correct URL + a link-text placeholder) plus a delete action. The author
  pastes it into their form HTML. Keep the service/repository boundary clean so a
  future GUI form-builder media-picker can reuse it (don't build the picker now).
- **Lifecycle:** tie `registration_documents` to the registration page with FK +
  `ondelete="CASCADE"`, so documents die with their page and the serving route
  naturally 404s assets of closed/deleted pages.
- **Teardown:** add the new table to `_delete_all_test_data()`
  (`tests/conftest.py`) and `delete_all_except_standard_users()`
  (`tests/bdd/conftest.py`), child-before-parent ordering (CLAUDE.md).
- **Migration:** `uv run alembic revision --autogenerate -m "add registration
documents"`.
- **i18n:** wrap all new user-facing strings in `_()` / `_l()` (CLAUDE.md).
- **Accessibility:** the upload UI needs the usual treatment; the inserted `<a>`
  should carry clear link text and signal that it's a PDF download (type + size)
  per the component accessibility guide.
- **CSP:** a download link is a same-origin `<a href>`, so no `img-src`/
  `default-src` change is needed. (Contrast images, which touched `img-src`.)
- **Rate limiting** on the upload route (reuse the existing Redis rate-limit
  machinery).

## 8. Decision summary (what's settled vs pending)

| Question                            | Status      | Position                                                                     |
| ----------------------------------- | ----------- | ---------------------------------------------------------------------------- |
| Scope                               | Decided     | Registration pages only; sits alongside the image feature                    |
| Consumption model                   | Decided     | **Download link** (not inline embed)                                         |
| Serving domain                      | Decided     | **Main domain**, app route under `/register/<slug>/documents/…`              |
| Serving header                      | Decided     | **`Content-Disposition: attachment`** + `nosniff`, server-set `Content-Type` |
| Re-encode / sanitise PDF            | Decided     | **No** — attachment download makes it unnecessary                            |
| Separate origin / usercontent       | Decided     | **Not needed** (revisit only if we ever move to inline preview)              |
| AV scanning (ClamAV)                | Decided     | **None**                                                                     |
| Validation                          | Decided     | size cap → `%PDF-` magic-byte gate → server-generated ids → quota            |
| Referencing model                   | Decided     | Paste a ready-made `<a>` snippet; clean seam for a future picker             |
| New dependencies                    | Decided     | **None** expected (no `python-magic`, no ClamAV)                             |
| Personal data in PDFs               | Decided     | **No** — public docs (info pack, agenda); GDPR neutral (§6)                  |
| **Storage (bytea vs disk)**         | **Decided** | **Option A (`bytea`)** — files < 1 MB, ≤ 3 per assembly (team, 2026-07-17)   |

## 9. Resolved

The one open question — how big, and how many — came back from the team on
2026-07-17: **all PDFs are under 1 MB, at most 3 per assembly, and often zero.**
That settles the storage pivot (§3) in favour of **Option A (`bytea`)**, and
nothing else was blocking. Implementation is specified in the sibling
`domain-service-plan.md` (data/domain layer, service layer, and the public
download endpoint; the backoffice upload/management blueprints are deferred to a
later plan).

---

### Sources

Builds directly on `docs/agent/history/672-upload-images/research.md` (storage,
serving-domain, validation, GDPR analysis for the image feature) and the shipped
image implementation (`adapters/orm.py`, `service_layer/registration_image_service.py`,
`service_layer/image_processing.py`, `entrypoints/blueprints/registration.py`).
PDF-specific security: OWASP File Upload Cheat Sheet; `Content-Disposition`
attachment as an active-content mitigation; PDF active-content background
(embedded JS / launch actions). Storage size tradeoff: same sources as 672
(PostgreSQL wiki _BinaryFilesInDB_; Microsoft Research _To BLOB or Not To BLOB_).
Efficient on-disk serving: ADR 0008 (WhiteNoise + the OS `sendfile` syscall via
`wsgi.file_wrapper`); WhiteNoise docs (startup file scan); Caddy `file_server`
docs (and the absence of an `X-Accel-Redirect`/`X-Sendfile` equivalent in Caddy).
