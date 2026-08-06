# Code review findings — 768-pdf-upload-ui (PR #225)

Reviewed: `git diff origin/main...768-pdf-upload-ui` (3 commits), 2026-07-29, high effort.
Scope: document upload/relabel/delete routes in `backoffice_registration.py`, Assets panel
Documents subsection + modals + Alpine JS in `assembly_registration.html`, component tests,
and the service-docs error-token fixes. Excluded per agreement: the pre-existing
`test_2fa_flow.py::test_login_with_2fa_backup_code` failure on main, and the undefined
info/success/warning token family (handled on branch `797-undefined-design-token-references`).

## Verdict

**No correctness, security, or CSP findings.** The implementation mirrors the image-asset
pattern closely, and the places where that pattern carries risk were checked and cleared
(see "Verified non-issues"). The findings below are minor consistency and coverage notes,
none blocking merge.

## Findings (most severe first — all low)

### 1. Snippet text diverges from the service-layer snippet helper (cosmetic)

`_document_to_dict` builds the `<a>` snippet text from `display_name` (label → original
filename → short-sha fallback), while `registration_document_service._snippet_text` uses
`document.label` directly. For a document whose label is blank — only creatable through the
dev service-docs tab, since the product routes default the label to the filename and reject
blank labels on PATCH — the dev tab's snippet renders as ` (PDF, 123 KB)` with empty link
text while the product UI shows the filename. Suggest aligning `_snippet_text` to the same
fallback chain. File: `src/opendlp/service_layer/registration_document_service.py:153`.

### 2. Route tests omitted the error branches (test coverage) — RESOLVED

This finding originally understated the problem as "inherited parity, optional follow-up".
In fact `codecov/patch` failed on the PR at 84.5% with **34 uncovered new lines** — all of
them error-handling branches of the three new routes (upload read-failure/quota/no-page/
403/404/500; PATCH and DELETE 404/403/500 variants). Parity with the image routes' gaps
did not help, because the patch check measures only the diff's new lines.

**Resolved 2026-07-29**: 15 error-branch tests added (`TestUploadErrorBranches` plus PATCH/
DELETE branch tests) using a non-manager user for 403s, a monkeypatched document quota for
the 400, assemblies without a registration page for those 404s, and monkeypatched service
raises for the 500 handlers. Full component-suite coverage now shows **no uncovered lines
in any code added by this branch**; the file's remaining uncovered lines (image/email error
branches) are inherited from main.

### 3. Native `confirm()` for list-row deletion (UX consistency, inherited)

`deleteDocument()` uses the browser-native `confirm()` dialog, copied from `deleteImage()`.
The app's own destructive flows (close registration, discard changes) use styled modal
dialogs. Kept for parity with images; if it changes, change both together.

### 4. File input `accept` could include the extension fallback (nit)

`accept="application/pdf"` works in current browsers, but `accept="application/pdf,.pdf"`
is more robust on some OS file-picker combinations where the MIME association is missing.
Server-side validation (magic-bytes check) is the real gate either way.

## Verified non-issues

- **Oversized uploads**: Flask `MAX_CONTENT_LENGTH` is set globally (`config.py:492`), so a
  multi-GB body is rejected before `upload.read()`; `validate_pdf` enforces the 5 MB PDF cap
  after that.
- **Label length**: the `registration_documents.label` column is an unbounded Postgres
  `String` — no silent truncation or 500 on long labels.
- **CSRF**: all three fetch verbs send `X-CSRFToken`; routes are `@login_required` and the
  service layer enforces `can_manage_assembly`.
- **CSP-safe Alpine**: flat `x-model` props only; `@click` passes identifiers (`doc`,
  `editingDocument`), never string literals; clipboard copy for the file name uses the
  `data-copy-text` attribute pattern.
- **i18n**: every new user-facing string (routes, template, JS toasts, aria-labels) is
  wrapped in `_()`; Hungarian catalog regenerated. Aria-labels are built server-side with
  `%(name)s` placeholders so word order is translatable.
- **Logging/PII**: new log lines carry only assembly/document UUIDs and error strings via
  structlog — no filenames or user PII.
- **XSS**: snippet HTML is built by `generate_document_html`, which HTML-escapes href and
  text; `documents|tojson` in the script block uses Flask's script-safe JSON encoding.
- **Template gating**: document modals and JS live inside the same
  `{% if has_registration_page %}` blocks as the image ones; the view always passes
  `documents` (empty list when no page), so `x-data` seeding cannot KeyError.
- **Dedup re-upload**: server returns the existing row (with the caller's label applied);
  the JS replaces the matching row in place instead of duplicating it.
- **mypy strict / prek**: both clean; component suite 709 passed (single failure is the
  excluded pre-existing 2FA test).
