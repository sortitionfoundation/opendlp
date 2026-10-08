# Tiptap visual editor for the registration intro

Branch: `767-rich-text-editor`. Follows decision D1 in
[wysiwyg-editor-options.md](wysiwyg-editor-options.md): a Tiptap editor on the
**intro** box, built to keep (production quality, full tests) and reverted if
it doesn't work out. The auto-reply email is a later piece of work. Step 8
applies GOV.UK classes at render time (decision D4 there).

**Status: in progress.** Completed steps are marked ✅. Two review rounds are folded in, and the
answers are recorded at the end. The only open question is Q6 (layout or
data tables), which affects step 10 only.

## Goal

When editing the intro, the author sees a visual editor with a toolbar
(headings, bold, italic, lists, links, images, undo/redo) and can switch to
the existing CodeMirror HTML view and back. `{{ vars }}` are highlighted.
Images can be dropped or pasted in, and are uploaded to the existing images
route. With JavaScript off, the page works as it does today: a plain
textarea.

Step 8: the page records a content style ("GOV.UK" or "plain"). For
GOV.UK, rendering the public page adds a default GOV.UK class to any intro
element that has no class.

## How it works today (what this touches)

| Layer                 | Where                                                    | Today                                                                                                                                                                                                                                                                                                                                  |
| --------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Template              | `templates/backoffice/registration/_step_intro.html`     | `textarea(name="intro_content", label="", rows=15, code_editor=true, …)`; `readonly` + `aria-readonly` outside edit mode. The form has `@input/@change="markEditDirty()"`, `@submit="allowLeave()"`. The Assets aside (edit mode only) lists images with "copy snippet".                                                               |
| Macro                 | `templates/backoffice/components/input.html:155`         | `code_editor=true` adds `data-code-editor`.                                                                                                                                                                                                                                                                                            |
| JS                    | `src/js/backoffice/html-editor.js`                       | IIFE entry `backoffice/js/dist/html-editor` (loaded by `_page_data.html:5-6`). Mounts CodeMirror on every `textarea[data-code-editor]`, including those added later (MutationObserver), and syncs to the textarea on change and submit. **No exports and no unit test**; covered only by BDD (`tests/bdd/test_backoffice.py:506-531`). |
| JS                    | `src/js/components/registration-images.js`               | Alpine slice: upload modal (`postFormData` with file + alt + CSRF from the `registration-page-data` JSON), image list, `copyImageSnippet()` → clipboard. Never touches an editor.                                                                                                                                                      |
| Route                 | `backoffice_registration.py:1025`                        | `POST …/registration/images` → 201 `{"image": {id, alt, public_url, img_snippet, …}}`. `public_url` is `""` while the page has no slug.                                                                                                                                                                                                |
| Domain                | `registration_page.py:376` `RegistrationPageHtml.render` | Renders intro and form separately in `_SANDBOX_ENV` (autoescape on) and concatenates them.                                                                                                                                                                                                                                             |
| Starter               | `generate_starter_intro_html[_govuk]()`                  | The GOV.UK one wraps the content in `<div class="govuk-grid-row"><div class="govuk-grid-column-two-thirds" style="…">` with `govuk-heading-xl` / `govuk-body`.                                                                                                                                                                         |
| Public                | `templates/register/form.html` via `base_public.html`    | Loads `css/application.css`, which includes govuk-frontend.                                                                                                                                                                                                                                                                            |
| Python HTML libraries | —                                                        | None besides stdlib `html.parser` (used in `domain/html_to_text.py`).                                                                                                                                                                                                                                                                  |

## Decisions

### E1 — New npm dependencies (approved)

`@tiptap/core`, `@tiptap/pm`, `@tiptap/starter-kit`,
`@tiptap/extension-image`, `@tiptap/extension-file-handler` (plus its peer
`@tiptap/extension-text-style`). All MIT, version 3.31.x, pinned like the
CodeMirror packages. No Python dependencies. Chewie approved these.

Table support after the slice (step 10) adds `@tiptap/extension-table` (MIT,
same version). Chewie approved this too (Q7).

### E2 — One bundle, split into modules

The registration page is the only page that loads `html-editor.js`, so we
keep that single entry point and don't create a second bundle (which would
ship CodeMirror twice):

- `src/js/backoffice/code-editor.js`: the CodeMirror code moved out of
  `html-editor.js`, exporting
  `mountCodeEditor(textarea, {container}) → {getValue, setValue, focus, destroy}`.
  Behaviour unchanged.
- `src/js/backoffice/rich-editor.js`: exports
  `mountRichEditor(textarea) → {getHTML, setHTML, destroy}` and the pure
  helpers below, so vitest can test them.
- `src/js/backoffice/html-editor.js`: stays the entry. It mounts
  `[data-code-editor]` exactly as now, **except** textareas that also carry
  `data-rich-editor`; those go to `mountRichEditor`, which owns both views.

### E3 — The textarea stays the source of truth

Both views write to the hidden textarea on every change, and resync on
submit. After each write we dispatch a bubbling `input` event on the
textarea, so `markEditDirty()` and the leave-page guard keep working when the
change came from a toolbar click (which fires no input event of its own).
The server sees exactly what it sees today: `intro_content`.

### E4 — Visual / HTML switch, guarded by a round-trip check

A two-button switch ("Visual" / "HTML", `aria-pressed`) sits above the
editor.

- Pure helper `roundTripsCleanly(html, schema) → boolean`. It parses the HTML
  through the Tiptap schema, serialises it again, and compares the two after
  normalising both through `DOMParser` (whitespace between block elements,
  attribute order, void-tag spelling, entity forms).
- On load: start in Visual if the content round-trips cleanly, otherwise
  start in HTML mode and show an inset message ("This HTML uses things the
  visual editor can't show, so it opens as HTML.").
- Switching HTML → Visual runs the same check. If it fails, the switch is
  refused, focus stays put, and the same message is announced through the
  existing toast's live region.
- Switching Visual → HTML can't lose anything.
- No preference is stored; the mode is worked out on each load (Q1).

### E5 — The schema is StarterKit cut down, plus attribute preservation

- **StarterKit**, with the extras it ships that have no toolbar button
  turned off (`underline`, `strike`, `code`, `codeBlock`, `blockquote`,
  `horizontalRule`). Otherwise keyboard shortcuts and markdown input rules
  could still create them. Headings are limited to levels 1–3. This cut-down
  set is **for the first slice only**: once we go forward, underline, strike,
  blockquote, horizontal rule and tables are added (step 10). Until then an
  intro that already contains any of them opens in HTML mode, so nothing is
  lost.

- **Link** (in StarterKit v3): `openOnClick: false`, and its default
  protocol checks kept. Set `HTMLAttributes: {target: null, rel: null}`.
  Tiptap's default stamps `target="_blank" rel="noopener noreferrer nofollow"`
  on **every** link, which would rewrite every link in the real intros and
  fail the round-trip check. Links parsed with a `target` or `rel` keep it.
  New links from the link dialog get none, so they open in the same tab,
  which is the GOV.UK default.
- **Image**: `inline: true` and `allowBase64: false`.
  - `inline: true` matters because Tiptap's default is block images, so an
    image inside a `<p>`, which is how all three real intros place their
    logos, would be lifted out of the paragraph.
  - `allowBase64: false` means pasted `data:` images are dropped rather than
    saved into the HTML.
  - `width` and `height` are already Image attributes in v3.
- **`addGlobalAttributes`**, driven by the real intros in
  `tests/fixtures/registration_intros/`:
  - `class`, `style` and `dir` on paragraph, heading, bulletList,
    orderedList, listItem, link and image;
  - `target` and `rel` on link.

  Without `style` and `dir`, **all three real intros** would open in HTML mode
  for reasons the author can't see. They use `style` on `<p>`, `<a>` and
  `<img>`, and `dir="ltr"` on `<p>` and `<li>`. Preserving an attribute is not
  the same as offering a way to edit it: the toolbar never sets `style` or
  `dir`, it just keeps them.
- **What the HTML loses even on a clean round-trip.** These are the
  normalisations `normaliseHtml()` treats as equal (E4). They are chosen
  because each renders the same, or close enough:
  - an attribute-less `<span>` is dropped and its text kept (Google Docs paste
    leaves these);
  - empty inline formatting such as `<strong></strong>` is dropped;
  - `&nbsp;` and a literal U+00A0 are the same;
  - a list item's text is always wrapped in a paragraph (`listItem` content
    is `paragraph block*`), so `<li>text</li>` comes back as
    `<li><p>text</p></li>`. **This one does not render the same**: the
    paragraph brings its own margin, so the list spaces out a little. Two of
    the three real intros already use `<li><p>`, so we accept it rather than
    fighting the schema, and the docs (step 9) say so.

  The guarantee is "no content lost", not "byte-for-byte the same". Once an
  author edits in Visual mode, the saved HTML is in the editor's own
  consistent form.
- **A small `Div` node** (`content: "block+"`, attributes `class` and
  `style`) so the GOV.UK grid wrapper survives. The toolbar cannot create
  divs; the node exists only so existing ones are preserved.
- `{{ vars }}` are supported only in text (options decision D3). A variable
  in an attribute (e.g. `href="{{ … }}"`) may be dropped by Link's URL check;
  the round-trip check catches that and keeps the author in HTML mode.
- **The limitation is documented where authors will see it**, not only here:
  - help text under the Visual/HTML switch: "The visual editor supports
    variables like {{ assembly_title }} in text. To use a variable anywhere
    else, such as in a link address, edit the HTML.";
  - the "opens as HTML" / refused-switch message names this as one of the
    common causes;
  - a new `docs/registration-intro-editor.md` (for developers and support)
    that lists what the visual editor keeps, what forces HTML mode and why,
    linked from the registration section of `CLAUDE.md`'s further
    documentation list.

### E6 — Toolbar markup comes from the server; JS only wires it up

A new macro `rich_editor_toolbar(id)` renders the toolbar in Jinja, so every
label and tooltip is a normal `_()` string in our catalogues. JS finds it by
`aria-controls` / `data-rich-editor-toolbar` and wires each
`button[data-command]`. It follows `docs/agent/component_accessibility.md`
(load the `ui-components` skill first): `role="toolbar"` with an accessible
name, roving tabindex with arrow keys, `aria-pressed` on mark and heading
toggles, kept in sync on every selection change. The commands are paragraph,
H1, H2, H3, bold, italic, bullet list, numbered list, link, image and
undo/redo. The toolbar is hidden outside edit mode.

The editable area gets `role="textbox"`, `aria-multiline="true"`, and
`aria-labelledby` pointing at the step heading, because the textarea's
`label=""` gives it no name.

### E7 — Link dialog

"Link" opens a modal with a URL field (and the selected text shown), built
with the existing modal pattern from `_modals.html`. It can apply, update or
remove a link. Cmd/Ctrl-K opens it too.

### E8 — Images reuse the existing upload modal, through DOM events

The editor and the images Alpine slice don't import each other. They talk
through `CustomEvent`s on `document`:

1. **Drop or paste** (FileHandler `onDrop`/`onPaste`, png/jpeg/gif/webp
   only) → the editor dispatches `rich-editor:image-file` with
   `{editorId, file, pos}`.
2. **`registration-images.js`** listens and opens the existing upload modal
   with that file already chosen, so the author still writes alt text the
   same way as now. On successful upload it dispatches
   `rich-editor:insert-image` with `{editorId, src: public_url, alt, pos}`.
   It also adds the image to the Assets list as usual.
3. The **Assets list** gains an "Insert" button next to "Copy snippet". It is
   shown while the intro is in Visual mode and dispatches the same
   `insert-image` event at the cursor.
4. The **toolbar "Image" button** opens the upload modal with no file.

The URL inserted is `public_url`, which E13 (below) changes to a stable,
slug-free URL. That fixes two problems with today's URL: it breaks when the
registration URL changes, and it is empty until the page has a slug.

### E9 — Variable highlighting is a view-only decoration

A ProseMirror plugin finds `/\{\{\s*[A-Za-z_][\w.]*\s*\}\}/g` in text nodes
and adds `Decoration.inline` with class `rich-editor__variable`. The stored
HTML never changes. The pure helper `findVariableRanges(doc)` is unit
tested. Inserting variables from a menu is out of scope.

### E10 — CSS and CSP

Set `injectCSS: false` and ship our own styles: the editor surface and
toolbar in the backoffice Tailwind source, using the design tokens the
CodeMirror theme already uses. Variable highlight colours must meet 4.5:1
contrast in both themes. No `eval` is involved.

### E11 — Read-only view shows Visual mode

Outside edit mode the textarea is `readonly`. The rich editor mounts with
`editable: false` and no toolbar, so the step shows the intro as it will
look. If the content doesn't round-trip, the read-only view shows
read-only CodeMirror, as now.

### E12 — Render-time GOV.UK classes (step 8)

- **Enum `ContentStyle`** (`PLAIN = "plain"`, `GOVUK = "govuk"`) in
  `domain/value_objects.py`, with a `content_style_labels` dict (one `_l()`
  per member) exposed to Jinja. We never render `.value`.
- **Column `content_style`** on `registration_page_html_sources` (it describes
  the HTML, next to `intro_html`), `server_default "plain"`. Every existing
  page therefore renders byte-for-byte as now. Pages created after the
  migration default to `GOVUK` in the domain constructor (Q2, agreed).
- **Pure function `apply_default_govuk_classes(html) → str`** in a new
  `domain/html_default_classes.py`, using stdlib `HTMLParser` with
  `convert_charrefs=False`. It writes every token back out verbatim
  (`get_starttag_text()`, data, comments, entities, declarations) and changes
  only start tags of mapped elements that have **no** `class` attribute,
  inserting one. So it is idempotent and leaves author-chosen classes alone.
  The mapping is one constant, matching the classes the GOV.UK skeleton
  already uses (h1 is `xl`, stepping down from there — Q3):

  | Element | Class                           |
  | ------- | ------------------------------- |
  | `h1`    | `govuk-heading-xl`              |
  | `h2`    | `govuk-heading-l`               |
  | `h3`    | `govuk-heading-m`               |
  | `p`     | `govuk-body`                    |
  | `ul`    | `govuk-list govuk-list--bullet` |
  | `ol`    | `govuk-list govuk-list--number` |
  | `a`     | `govuk-link`                    |

- **What counts as opting out.** Only a non-empty `class` attribute.
  - `class=""` gets the default (Q5). The documented way to opt a single
    element out is to give it any class of your own; the docs suggest
    `class="plain"`.
  - **An inline `style` does not opt out.** Chewie asked whether it should.
    I think not. An inline style is most often a tweak (`text-align: center`,
    a margin) on top of the look the author otherwise wants, and GOV.UK
    classes and inline styles combine — the inline declarations win where
    they conflict and everything else still comes from the class. Skipping
    styled elements would make a centred paragraph suddenly lose the GOV.UK
    font and spacing, which is the more surprising result. If an author
    really does want no GOV.UK styling on that element, `class="plain"` says
    so explicitly. This rule is easy to change later because it lives in one
    predicate (`_wants_default_class(attrs)`) with its own tests.
  This is recorded as decision E14 and documented for authors (step 9).

- **`render()`** applies the function to the **rendered intro only**, after
  Jinja substitution, when `content_style == GOVUK`. Variables are
  autoescaped, so they can't inject tags the function then styles. The form
  HTML is untouched.
- **Backoffice:** a radios control on the intro step ("Style: GOV.UK
  (recommended, accessible) / Plain — bring your own styles"), posted with the
  intro form and saved by `update_registration_page_intro_html` (which gains
  `content_style`, and records it in the activity entry when it changes).
  `duplicate_registration_page` copies it, and `dev.py` exposes it.
- **Editor preview:** a new `src/scss/rich-editor.scss` uses govuk-frontend's
  typography mixins scoped under `.rich-editor--govuk .ProseMirror`. The
  editor toggles that class to match the radios, so Visual mode looks like
  the public page.
- Changing the GOV.UK intro skeleton to plain semantic HTML is a follow-up,
  not part of this work.

### E13 — Image URLs that survive a change of registration URL

Today images are served at `/register/<url_slug>/assets/<sha>.png`, and only
while the page is publicly loadable (`get_registration_image_for_serving`
checks `page.is_publicly_loadable()`: slug set, status TEST or PUBLISHED).
Three consequences:

- changing the registration URL breaks every image link already in the HTML;
- `public_url` is `""` until the page has a slug;
- **on a draft page the images don't load at all** — so in the visual editor
  they would show as broken until the page is published.

We key the URL on the **image's own UUID**:
`/register-assets/images/<image_id>.png`. This is one step further than
Chewie's suggestion of the assembly UUID, and Chewie agreed. The prefix is
`/register-assets/` rather than `/register/images/` so it can never collide
with a page whose slug is `images`. That keeps us out of the business of
keeping a block list of reserved slugs. Short URLs live under `/r/`, so
nothing at the root competes with `/register-assets/` either.

- It never changes, whatever happens to the slug, and needs no slug, so it is
  never empty.
- It's one indexed lookup, with no `(assembly, sha)` pair to resolve.
- It doesn't put the assembly UUID in public HTML. That ID is in every
  backoffice URL, so it's better not to hand it out, even though the
  backoffice is behind login.
- Caching is unchanged: the ETag stays the image's sha256, and image rows
  are immutable.

Who may fetch it:

- **Anyone**, if the image's assembly has at least one publicly loadable
  registration page. That matches today's rule, which is per page in name but
  per assembly in effect, since images belong to the assembly.
- **Otherwise**, only a logged-in user who `can_view_assembly`. This is what
  makes images show in the editor and on the preview step while the page is
  a draft.
- Anyone else gets a 404, as now.

Documents (`/register/<slug>/documents/<name>`) have the same
slug-dependence. They would naturally become
`/register-assets/documents/<document_id>.<ext>` under the same rule. That is
out of scope here because the editor doesn't insert documents, but the prefix
leaves room for it.

The old `/register/<slug>/assets/<sha>.png` route stays, unchanged, so
snippets already pasted into live pages keep working. `img_snippet` and
`public_url` switch to the new URL, so newly copied snippets use it too.
`_image_to_dict`'s fixture in `tests/fixtures/json_api/` is re-recorded, and
the JSON Schema is unchanged apart from `public_url` no longer being empty.

This is step 5, before the editor's image work, because the editor depends
on images loading in draft.

This is what "configurable upload behaviour per editor" means in this round:
the textarea's `data-rich-editor-images="true"` turns images on (the intro).
The email editor will leave it off (options decision D6).

### E14 — An inline `style` does not opt an element out of GOV.UK classes

Decided in review: under the GOV.UK content style, an element without a
`class` gets its default GOV.UK class **even if it has an inline `style`**.
The inline style is applied on top, and wins wherever the two set the same
property.

Why: an inline style is usually a tweak, such as centring or a margin, made
to an element whose overall look the author still wants. Skipping styled
elements would make a centred paragraph lose the GOV.UK font and spacing,
which is the more surprising result. The explicit way to opt out is a class
of your own (`class="plain"`); `class=""` does not count (Q5).

Where it lives: in one predicate, `_wants_default_class(attrs)`, with tests
that name this decision, so a later change is a one-line edit plus its
tests. Where it's documented for authors: `docs/registration-intro-editor.md`
(step 9), and the hint text under the content-style radios ("Elements you
give a class of your own keep only your class.").

## Implementation steps

Ordered so each step leaves `just check` and `just test-nobdd` green.
Commit this plan separately from the code.

### ✅ 1. Split `html-editor.js` (no behaviour change)

Move the CodeMirror code into `code-editor.js` with the `mountCodeEditor` API
(E2), and keep the entry's auto-mounting. Add `code-editor.test.js` (mount
syncs to the textarea, readonly is respected, double mount is a no-op,
`setValue` updates the textarea). The existing BDD intro scenarios must still
pass unchanged; that is the check for this step.

### ✅ 2. Dependencies and the schema

Done. As built:

- The helpers live in two modules rather than in `rich-editor.js`:
  `rich-editor-schema.js` (`createSchemaExtensions`, `findVariableRanges`,
  the `VariableHighlight` extension) and `rich-editor-html.js`
  (`normaliseHtml`, `roundTrip`, `roundTripsCleanly`).
- StarterKit's `trailingNode` is off too. Otherwise the live editor appends an
  empty `<p></p>` whenever the intro ends with something other than a
  paragraph, such as the GOV.UK skeleton's `<div>`.
- `normaliseHtml` needed two rules beyond E5's list, both found by the real
  intros:
  - **Styles are compared in parsed form.** The round trip rewrites
    `color: #0c7e8f` as `rgb(12, 126, 143)` and `margin: 0 auto` as
    `margin: 0px auto`.
  - **Inline content is compared as runs of text, each with a set of
    formatting.** So `<strong><a>…</a></strong>` and `<a><strong>…</strong></a>`
    are equal, since ProseMirror orders marks its own way. An empty `<a>` (an
    anchor) still counts as content.
- **A `{{ variable }}` in an attribute survives** (`href="{{ url }}"`,
  `src="{{ logo }}"`), contrary to E5's expectation. The limitation that
  remains is that the visual editor has no way to *edit* such a variable, and
  doesn't highlight it. The help text and docs say that instead.
- Outcomes on the real intros are as planned. Text, link addresses and image
  sources survive the round trip for all three, including the table one,
  which is still refused because its `<table>` is lost.


`npm install` the E1 packages (approved). In `rich-editor.js`, build
the extension list (E5) and the pure helpers `createSchemaExtensions()`,
`roundTripsCleanly()`, `normaliseHtml()` and `findVariableRanges()`. Write
the vitest tests first:

- Both starter intros (plain and GOV.UK) and an empty string round-trip
  cleanly.
- Unknown elements (`<table>`, `<span style="…">` — a span *with*
  attributes), `data:` images and an attribute variable do not.
- `findVariableRanges()` finds `{{ x }}` and `{{ assembly.title }}` and
  ignores `{ x }` and `{{ }}`.
- The **real intros** in `tests/fixtures/registration_intros/` (Q4; see its
  README). Expected results with the slice's schema:
  - `inline_styles_intro.html` and `centred_image_intro.html` round-trip
    cleanly, given the E5 attribute preservation and normalisations;
  - `layout_table_intro.html` falls back to HTML because of its `<table>`,
    until step 10, where it moves to the clean list.

  The tests assert those outcomes and, for the fallback, the reason. A test
  per fixture also checks that text, link `href`s and image `src`s all
  survive the Visual round-trip, so the "no content lost" guarantee is
  tested directly and not only through the normaliser.

Measure the bundle size before and after, and record it in the PR.

### ✅ 3. Mount the editor and the mode switch

Done. As built:

- The controls (switch, hint, notice, editing area) are a macro,
  `rich_editor_controls` in `templates/backoffice/components/rich_editor.html`.
  The `textarea` macro renders it when `rich_editor=true`, with
  `rich_editor_label`, `rich_editor_images` and `rich_editor_editable`. The
  controls are `hidden` until the JS mounts them, so with JS off the page
  shows the plain textarea, as before.
- The "opens as HTML" and refused-switch messages appear in an inset notice
  with `role="status"` inside the editor, not the page toast. That keeps the
  explanation next to the editor it's about, and is still announced.
- Tailwind only scans `templates/backoffice/`, so it purged the rules for the
  classes Tiptap sets from JS (`rich-editor__content`,
  `rich-editor__variable`). `tailwind.config.js` now also scans
  `src/js/backoffice/rich-editor*.js` and safelists
  `ProseMirror-selectednode`.
- The existing intro BDD steps were updated here, not in step 7, to keep
  them green. "Type into the intro code editor" switches to the HTML view
  first.
- Bundle size (`html-editor.js`, minified): 566,626 → 965,043 bytes;
  gzipped 192,906 → 318,609 (about +125 KB). It's loaded only on the
  registration editor page.


`mountRichEditor()`: Tiptap editor, textarea sync and `input` dispatch (E3),
the switch with the guard (E4), read-only mount (E11), variable decorations
(E9). The macro gains `rich_editor=false`, which adds `data-rich-editor` and
renders the switch and the toolbar slot. Turn it on for `intro_content` only.
Write the vitest tests first for: the sync, `input` event dispatch, the
initial mode choice, the refused switch, and Visual → HTML → Visual
preserving content.

### ✅ 4. Toolbar and link dialog

Done. As built:

- The toolbar macro is `rich_editor_toolbar` in the same component file, and
  its wiring is `src/js/backoffice/rich-editor-toolbar.js`. Buttons have
  visible text labels ("Bold", "Heading 2", …), so no `aria-label` is
  needed and browser translation tools can see them. Undo and redo use
  `aria-disabled` without `disabled`, following the WAI-ARIA toolbar pattern:
  a `disabled` button drops out of the arrow-key order. This departs from
  the component checklist's "both attributes" rule, and the macro's comment
  explains why.
- The link dialog is a `controlled_modal` in `registration/_modals.html`,
  driven by a new controller slice, `richEditorLinkDialog`
  (`src/js/components/rich-editor-link-dialog.js`).
  - The page root listens with
    `@rich-editor-link-request.document="openLinkDialog($event)"`.
  - The event names live in `src/js/lib/rich-editor-events.js`, so the editor
    and the slice share them without importing each other. They use hyphens
    rather than colons.
  - Focus moves to the address field with `$nextTick`, after the dialog
    renders. Focus goes back to the editor on Apply, Remove or Cancel.
  - Applying with nothing selected inserts the address as linked text.
    Tiptap's own check rejects `javascript:` addresses.
- Checked on the dev server: the toolbar wraps to two rows at the editor's
  width in the takeover dialog, which is fine. Focus behaves as described,
  and there were no console errors.


The `rich_editor_toolbar` macro and the JS wiring (E6), the link modal (E7)
and Tailwind styles (E10). Vitest tests for each command toggling the right
node or mark, `aria-pressed` tracking the selection, and roving tabindex.
Load the `translate-catalogues` skill after adding the strings.

### ✅ 5. Stable image URLs (E13)

Done. As built:

- `get_registration_image_for_serving_by_id(uow, image_id, user_id)` returns a
  `ServedRegistrationImage(image, public)`, or None for a 404. There is no
  "draft" status: pages are TEST, PUBLISHED or CLOSED, and a TEST page with a
  URL already serves publicly. So the signed-in-only path covers images whose
  assembly has no page with a URL yet, or only closed pages.
- Route `GET /register-assets/images/<uuid:image_id>.png`
  (`registration.serve_registration_image_by_id`).
- **Caching:** the global after-request hooks force `no-store` on everything
  except `PUBLIC_IMMUTABLE_ASSET_ENDPOINTS`, and this one endpoint can serve
  either way. So the view sets `g.public_immutable_asset` when it serves
  publicly, and `flask_app._is_public_immutable_asset()` checks both. A
  signed-in-only response keeps `no-store`, which is stricter than the
  `private` the plan suggested.
- `_image_to_dict` lost its `url_slug` parameter. `public_url` and
  `img_snippet` are never empty now. `dev.py`'s snippet handler uses the same
  URL. The schema descriptions were updated and the two fixtures re-recorded;
  the only diff is the URL.
- The image details dialog's "No preview" fallback, for a blank
  `public_url`, can no longer show. It's left in place because it's harmless.
- Full non-BDD suite: 6,497 passed. Its 4 warnings come from unrelated tests
  (ORM identity, a Celery task, sortition status, registration page delete).


- Service: `get_registration_image_for_serving_by_id(uow, image_id, user)`
  with the public-or-can-view rule. Service tests with the fake UoW cover:
  published, test, draft-anonymous (404), draft-with-viewer (served),
  draft-with-user-who-has-no-role (404), unknown id (404).
- Route `GET /register-assets/images/<uuid:image_id>.png`. It sends the same headers
  as the existing route (`nosniff`, ETag) and adds `Cache-Control: private`
  when served only because of login, so a shared cache never stores a draft
  image.
- `_image_to_dict` and `generate_image_html` callers use the new URL. Re-record
  the API fixture with `UPDATE_API_FIXTURES=1` and read the diff.
- e2e: both routes serve; the old route's behaviour is unchanged; changing a
  page's slug leaves the new URL working.

### ✅ 6. Images

Done. As built:

- The events are `rich-editor-image-request` (`{editorId, file, pos}`) and
  `rich-editor-insert-image` (`{editorId, src, alt, pos}`), defined in
  `src/js/lib/rich-editor-events.js`. The page root listens with
  `@rich-editor-image-request.document="requestImageForEditor($event)"`.
- FileHandler accepts only PNG, JPEG and WebP, the formats the upload route
  takes. It uses `consumePasteEvent: true`, because an image copied from a
  web page also carries an `<img>` pointing at that site, and only the
  uploaded copy should land in the intro.
- The toolbar gains an **Image** button, rendered only when the textarea
  allows images. It opens the upload modal with no file.
- **The Assets panel's Insert button is always shown on the intro step,**
  not only in Visual mode. In HTML mode it inserts an `<img>` snippet at
  the CodeMirror cursor (`insertAtCursor` on the code editor handle). That
  beats a button that comes and goes. An insert without an `editorId` goes
  to the page's one visual editor. Its per-image accessible name is a new
  `aria_label_insert` key, server-built like its neighbours. The JSON
  Schema and both fixtures were updated, and the fixture diff is that key.
- Drop is tested in BDD (step 7) and by hand on the dev server, because
  FileHandler's drop handler needs `posAtCoords`, which jsdom lacks. Paste
  is tested in vitest.


FileHandler and the event bridge (E8), and the "Insert" button in the Assets
list. Vitest tests: the editor dispatches `image-file` on drop/paste and
ignores other file types; the images slice opens the modal with the file and
dispatches `insert-image` after upload. Use `loadApiFixture` for the upload
response — never hand-typed JSON.

### 7. BDD and e2e for the editor

- Update `tests/bdd/test_backoffice.py:506-531`. Its steps type into the
  intro's `.cm-editor`, and the intro now opens in Visual mode. Typing via
  HTML mode keeps those scenarios' meaning.
- New scenarios in `backoffice-registration-editor.feature`:
  - type in Visual mode, apply bold and a heading from the toolbar, save,
    and see the HTML in HTML mode and on the preview step;
  - switch to HTML, add a `<table>`, and see the switch back refused with
    the message;
  - keyboard-only: Tab into the toolbar, arrow keys to Bold, Enter;
  - a `{{ assembly_title }}` variable shows the highlight class;
  - an image inserted on a **draft** page displays (not broken) in the
    editor and on the preview step;
  - dropping an image file opens the upload modal; after upload the image
    appears in the editor and in Assets;
  - the read-only view (not editing) shows Visual mode with no toolbar.
- e2e: posting `intro_content` with toolbar-style HTML saves verbatim (the
  server is unchanged, but this pins it).

### 8. Render-time GOV.UK classes (E12)

1. **Domain:** `ContentStyle` and its labels; `apply_default_govuk_classes`
   with unit tests (every mapped element; existing class untouched, including
   `class=""` **(Q5)**; idempotent; comments, entities, `<br/>`, attribute
   quoting and `{{ }}` text preserved byte-for-byte; unmapped elements
   untouched); `RegistrationPageHtml.content_style` and the change to
   `render()`, with tests for GOVUK vs PLAIN and the form left untouched.
2. **Persistence:** ORM column, then
   `uv run alembic revision --autogenerate -m "add content_style to registration_page_html_sources"`,
   and read the generated file. No new table, so the test-data delete
   functions don't change.
3. **Service:** `update_registration_page_intro_html` and duplication. Tests
   in the service suite with the fake UoW.
4. **Route and template:** the radios, the save handling, `dev.py`. e2e:
   saving the style; the public page HTML has the classes for GOVUK and not
   for PLAIN; an existing (plain-default) page is unchanged.
5. **Editor:** `rich-editor.scss` and the class toggle following the radios.
   BDD: changing the radio changes how Visual mode looks (check a computed
   style on a paragraph), and the preview step shows GOV.UK classes.
6. **Translations and docs:** run `translate-catalogues`; add "content
   style" to `docs/language.md` if it needs a glossary term.

### 9. Documentation

- `docs/registration-intro-editor.md` (E5): what the visual editor keeps,
  what forces HTML mode and why (variables outside text, unsupported
  elements), what a Visual edit normalises (E5, including the `<li><p>`
  spacing), how the content style works, the `class="plain"` opt-out, and
  that an inline `style` does not opt out (E14).
  Link it from `CLAUDE.md`'s further documentation list.
- `docs/agent/component_accessibility.md`: add the rich editor toolbar as a
  worked example if the pattern is new to that doc.

### 10. After the slice is accepted: fuller toolbar and tables

Only once Chewie has tried the slice and decided to go forward. Its own PR.

- **Underline, strike, blockquote, horizontal rule:** stop disabling them in
  StarterKit, add toolbar buttons, add `class` to the global attributes for
  blockquote and hr. GOV.UK default classes (E12 mapping):
  `hr` → `govuk-section-break govuk-section-break--m govuk-section-break--visible`,
  `blockquote` → `govuk-inset-text`. One accessibility note for the
  user-facing docs: GOV.UK advises against underlining anything that isn't a
  link, because readers take it for one.
- **Tables**, with `@tiptap/extension-table` (approved, E1). The known use
  is laying out several images side by side, as in
  `layout_table_intro.html`.
  - **Its HTML output must be overridden.** By default Tiptap writes a
    `<colgroup>` and a `min-width` style into every table, so even a
    hand-written table would fail the round-trip check, and the stored HTML
    would fill with sizing noise. Extend `Table` with a `renderHTML` that
    writes a plain `<table>` (keeping `class`, `style`, `border` and `role`
    as global attributes), and leave column resizing off.
  - **Cells hold blocks** (`content: "block+"`), so `<td>text</td>` comes
    back as `<td><p>text</p></td>`. `normaliseHtml` treats a cell's single
    unclassed `<p>` as equal to bare text, the same as for list items (E5).
  - **Existing `<colgroup>`s.** The real layout table has one, with
    percentage widths on each `<col>`. Tiptap reads `<col>` widths into
    pixel `colwidth` cell attributes, so the percentages don't survive, and
    dropping the `<colgroup>` changes the column widths. So that fixture
    still **opens in HTML mode after step 10** — content is never lost — and
    tables the toolbar makes are plain. Supporting `<colgroup>` is a later
    decision if authors need visual editing of existing layout tables.
  - Toolbar: insert a table (rows × columns), add or delete a row or column,
    delete the table. These can be a small menu rather than six more
    buttons.
  - **Layout or data tables (Q6) is undecided, so we do the minimal thing
    that is easiest to change later: store nothing that commits to either
    answer.** A table inserted from the toolbar is a plain `<table>` with no
    `role`, no class and no header row. The GOV.UK mapping leaves `table`
    unmapped, and there's no header-row button.
    - If the team decides "layout": add `role="presentation"` in the insert
      command.
    - If "data": add a header-row toggle and map `table` → `govuk-table` (and
      `th`/`td` → their classes) in the E12 constant.
    - Either way it's a small change in one place, and no stored HTML needs
      migrating. A role or class baked in now would be stored in every table
      made before the decision.
    - Cost of waiting: browsers already guess that a borderless table with
      no `<th>` and no `<caption>` is for layout, and most screen readers
      follow that guess. So a plain table of images is a reasonable stopgap,
      though not as certain as an explicit role.
- Vitest round-trip fixtures for each new element, and BDD for building a
  2×1 table of images with the keyboard.

## Tests summary

| Tier               | What                                                                                                                                                |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit (Python)      | `apply_default_govuk_classes`, `ContentStyle` labels, `render()` with each style.                                                                   |
| Service            | Saving, recording activity for and duplicating `content_style`; the image-serving rule (public or can-view).                                        |
| Integration        | ORM round-trip of `content_style`; migration upgrade/downgrade.                                                                                     |
| e2e (Flask client) | Saving the intro and style; public page output for each style; existing pages unchanged; old and new image routes; slug change keeps images.        |
| JS unit (vitest)   | `code-editor`, round-trip check (incl. real intros), variable ranges, mode switch, sync/dirty, toolbar commands and a11y state, image event bridge. |
| BDD (Playwright)   | Visual editing, refused switch, keyboard toolbar, highlight, image drop, read-only view, style radio.                                               |

Run `just build-all` before BDD (a stale bundle looks like a regression), and
run `just test-nobdd` and `just test-bdd-headless` one after the other, never
at the same time.

## Risks and things to watch

- **Tiptap under jsdom.** ProseMirror mostly works in jsdom, but selection
  and `contenteditable` behaviour don't. Keep vitest to schema, helpers and
  commands run through `editor.commands`; anything about real
  focus/selection/drag goes to BDD.
- **False "not lossless" results.** If normalisation is too strict, real
  intros will open in HTML mode for cosmetic reasons (whitespace, `&nbsp;`,
  `<br>` vs `<br/>`). The real-intro fixtures in step 2 are the guard. Loosen
  `normaliseHtml`, not the check.
- **Dirty tracking:** confirm `markEditDirty()` is idempotent, because E3
  fires an `input` per change.
- **Bundle size:** the page grows by ProseMirror plus extensions. It is only
  loaded on the registration editor page.
- **Image visibility widens slightly.** With E13 a logged-in user with a
  role on the assembly can fetch its images while the page is a draft. Today
  nobody can. That's intended, and limited to people who can already see the
  assembly. Images aren't personal data, so the erasure rules aren't
  affected.
- **Old image URLs live on.** Intros pasted before E13 still use the slug
  URL, which still breaks on a slug change. We could rewrite them in a data
  migration, but rewriting live public HTML is the fragile kind of migration
  767 already rejected (its D3), so the plan doesn't.
- **Pasted rich text** (Word, web pages) is cut down to the schema. That's
  the point, but authors may be surprised to lose colours and fonts.

## Out of scope

- The auto-reply email editor (follows once this works; no images, D6).
- Email styling (D5).
- An "insert variable" menu; warnings about unknown variables.
- Changing the GOV.UK intro skeleton to rely on render-time classes.
- The thank-you HTML, though `apply_default_govuk_classes` is written so it
  can be reused there.

## Questions for Chewie

Answered in review:

- **Q1** — Remember the Visual/HTML choice per author? **No — worked out on
  each load.**
- **Q2** — New pages default to GOV.UK style, existing pages to plain?
  **Agreed.**
- **Q3** — Heading sizes? **`xl` for h1 and step down from there** (h2 `l`,
  h3 `m`).
- **Q4** — Real live intros for the round-trip fixtures? **Done**: three, in
  `tests/fixtures/registration_intros/`, with organisations and URLs
  anonymised. They changed the plan: E5 now preserves `style`, `dir`,
  `target` and `rel`, makes images inline, and stops Link adding its default
  `target` and `rel`. Without those changes all three would have opened in
  HTML mode.
- **Q5** — Should `class=""` count as "author chose no class" and be left
  alone? **No — it gets the default.** Opting out is done by giving the
  element a class of your own; the docs suggest `class="plain"`.
- **Q7** — `@tiptap/extension-table`? **Approved.**
- Does an inline `style` opt out of GOV.UK classes? **No** — decision E14.
- Image URL keyed on the image UUID? **Yes**, under `/register-assets/` so
  it can't collide with a slug (E13).

Still open:

- **Q6** — Tables: layout only, or data tables too? Needs a conversation
  with the team. Until then step 10 stores plain tables that commit to
  neither, so either answer is a small change later (see step 10).
