# Multiple registration pages — frontend (Phase 6) plan

**Branch:** `830-multiple-reg-pages-frontend` (PR #239, stacked on PR #235)
**Figma:** list view `node 3187:2883`, row contextual menu `node 3187:2904`
(file `WaG38I99ccF8RMy1655fA2`). Metadata browsing of the file is restricted, so
these two frames are the design inputs; everything else follows existing app
conventions.
**Status:** plan agreed with Gergő 2026-08-11; not yet implemented.

## 1. What the design shows

**List view (3187:2883)** — a "Registration" heading with a "Create HTML page"
primary button on the right, above a bordered table. Columns in the frame:
*Status* (pill chip, e.g. green "● Published"), *Date of publish*, and a
right-aligned kebab (`more_vert`) per row.

**Row contextual menu (3187:2904)** — a dropdown with three items:
- 👁 *See assembly details*
- ⊗ *Close registration*
- ✎ *Edit registration*

**Agreed deviations / clarifications:**

- The frame shows one anonymous row; we add a **Name column** (with the
  language code shown alongside when set) as the first column, since multiple
  pages must be distinguishable.
- **Do not touch the app navigation** (top nav / assembly nav), even where the
  Figma frame differs from the code.
- The frame's "Create HTML page" button is rendered grey/disabled; in the app
  it is an active primary button (disabled styling in the frame is just the
  captured state).

## 2. Routing changes

Today every backoffice registration route is assembly-addressed and acts on
the assembly's oldest page (`_sole_page` in `backoffice_registration.py:90`).
New scheme — the page's **url_slug** joins the URL, as agreed
(e.g. `/backoffice/assembly/<id>/registration/test-pt`):

| Route | Becomes |
|---|---|
| `GET  /assembly/<id>/registration` | **List view** (new template) |
| — | `GET /assembly/<id>/registration/<slug>` — the page editor (current `assembly_registration.html`) |
| `POST /assembly/<id>/registration/save` | `POST /assembly/<id>/registration/<slug>/save` |
| `POST .../registration/email/save` | `POST .../registration/<slug>/email/save` |
| `GET  .../registration/skeleton` | `GET .../registration/<slug>/skeleton` |
| `GET  .../registration/form-preview` | `GET .../registration/<slug>/form-preview` |
| `GET  .../registration/qr-code.png` | `GET .../registration/<slug>/qr-code.png` |
| `POST/PATCH/DELETE .../registration/images...` | unchanged (images/documents are **assembly-scoped** since phase 3) |
| `POST .../registration/create` | unchanged (assembly-scoped; creates page then redirects to its editor) |

Implementation notes:

- Backoffice-created pages always get a slug (`create_registration_page_with_slugs`),
  so a slug is always available. Slugs are **globally** unique; the loader must
  still verify the resolved page belongs to `<id>` (404 otherwise).
- Slugs are editable while in TEST: after a save that changes the slug,
  **redirect** to the new URL. As a safety net, resolving an unknown slug
  redirects to the list view with a flash rather than a bare 404.
- Flask matches static segments (`create`) before converters, so route order is
  safe; a page whose slug collides with a reserved word is prevented by keeping
  `create` in the reserved-slug check when saving slugs.
- Replace `_sole_page`/`_require_page`/`_page_with_source` with a
  slug-addressed `_load_page(assembly_id, slug)` helper. Other pages that
  deep-link to "the registration tab" (dashboard, details tab, email step
  URLs in `_email_section_url`) now link to the list or to a specific page's
  editor as appropriate.

## 3. List view (new)

`GET /assembly/<id>/registration` renders the Figma table:

- **Columns:** Name (+ language chip when set) · Links (full and short URL, each
  with a copy button) · QR code (thumbnail of the short URL's code, downloading
  the full-size PNG) · Status chip (existing status chip styling: TEST amber /
  PUBLISHED green / CLOSED red) · Date of publish · kebab menu.
- **Date of publish** = timestamp of the page's most recent PUBLISH activity
  entry (`page.activity`), blank for never-published pages. Format with the
  babel date filter (no `.strftime` in templates).
- **Row kebab menu** (CSP-safe Alpine dropdown per `templates/backoffice/patterns.html`;
  WAI-ARIA menu semantics per the component accessibility guide):
  - *See assembly details* → assembly details tab.
  - *Close registration* → POST to the page's close action; only shown for
    PUBLISHED pages (lifecycle: TEST ⇄ PUBLISHED ⇄ CLOSED, no CLOSED → TEST).
  - *Edit registration* → the page's editor URL.
  - *Delete registration page* → arms a confirmation dialog that POSTs to
    `.../registration/<slug>/delete`; only shown where the delete would be
    allowed (see §6).
- Row click (name cell) also opens the editor.
- **Create registration page** button → existing `POST .../registration/create`,
  which must now (a) stop rejecting a second page, and (b) generate a unique
  default name ("Registration page", "Registration page 2", …). It redirects
  to the new page's editor where the name can be changed. Once the assembly has
  a page the label reads "Create another registration page".
- Empty state: the table shows a single explanatory row + the create button
  (replaces the old details-tab create CTA).

## 4. Editor changes (`assembly_registration.html`)

- The static heading **"Registration Form HTML"** (line ~140) becomes the
  **page name**: display text in read-only mode, a text input in edit mode
  (`?edit=1`), saved with the existing save action.
- Service: extend `update_registration_page()` with an optional `name`
  parameter running `_validated_name` (unique within assembly); the save route
  passes it. Activity entry records the rename.
- **Slug editing moves here** from the Edit Assembly form (see §5): the page
  URL panel in the editor gains editable slug fields in edit mode, frozen once
  published (existing `slugs_frozen` behaviour and messaging).
- Breadcrumb/back link: editor links back to the list view.

## 5. Assembly details tab & Edit Assembly decoupling (agreed)

`backoffice.py` / `assembly_details.html` / `edit_assembly.html`:

- The **"Registration Page Details" section of the details tab becomes
  read-only**: a list of all the assembly's registration pages — name, status,
  registration URL and short URL with the existing copy-to-clipboard
  component (QR stays on the page editor only).
- The section keeps a **permanent link with explanation** pointing to the
  Registration tab — for creating the first page, editing existing ones, or
  adding more. The old "Create Registration Page" CTA on the details tab is
  removed in favour of that link.
- **Edit Assembly no longer touches registration settings**: remove the
  "Registration URLs" section from `edit_assembly.html` and the
  `url_slug`/`short_url_slug` handling + `update_registration_page` call from
  `backoffice.edit_assembly` (`backoffice.py:196-225`). The section stays
  read-only even in editing mode.

## 6. Out of scope / open questions

- **Duplicate rows:** the service exists (`duplicate_registration_page`) but the
  Figma menu doesn't include it. Not built; it slots naturally into the same
  kebab menu once designed.
- **Delete rows:** built after review feedback. The kebab offers *Delete
  registration page* only for pages `delete_registration_page` would accept —
  never published, no registrations — behind a confirmation dialog. It is a hard
  delete: no archive, no soft delete, no undelete.
- Bulk "close all pages" — service exists, no design; deferred.
- Navigation redesign visible in Figma — explicitly untouched.

## 7. Tests & mechanics

- **Component** (`tests/component/test_backoffice_registration_*`): update for
  slug-addressed URLs; new tests for the list view (two pages listed, close
  from the menu, wrong-assembly slug 404s), the create-second-page flow, the
  rename save, and the details/edit-assembly decoupling (posting slugs to
  edit_assembly changes nothing).
- **E2E / BDD**: `tests/e2e/test_backoffice_registration.py` and
  `features/backoffice-registration-editor.feature` follow the plan.md §4.6
  journey: create → duplicate (via service until UI exists) → publish both →
  submit to each → attribution. BDD steps already address pages by id; step
  URL builders switch to slugs.
- CSP: no inline JS; Alpine flat `x-model`, no string args in `@click`.
- i18n: wrap new strings, `just translate-regen`.
- TDD order: (1) routing + loaders red/green, (2) list view, (3) editor
  name/slug editing, (4) details/edit-assembly decoupling, (5) e2e + BDD.
