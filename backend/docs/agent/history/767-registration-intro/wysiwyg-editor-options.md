# WYSIWYG editor for the registration intro and auto-reply email — options

Status: **decided — spike Tiptap on the intro box.** See
[Decisions](#decisions) at the end. Researched October 2026; versions and
licences below were checked against npm on 2026-10-08.

## What we want

Two HTML boxes get a rich text editor: the registration page **intro**
(`RegistrationPageHtml.intro_html`) and the **auto-reply email**
(`EmailTemplate.body_html`). The form HTML does not — it is heading towards
being generated from the questions.

Must have: toolbar with headings, bold/italic, bulleted and numbered lists,
links.

Nice to have:

1. Images shown in the editing area.
2. Drag-and-drop / paste of an image triggers an upload, configurable per
   editor (the intro and the email may want different behaviour).
3. Template variables (`{{ assembly_title }}` …) highlighted.
4. "Default accessible style" automatically applies `govuk-body`,
   `govuk-heading-l` etc.
5. Editing the underlying HTML directly.

## Constraints from our codebase that shape the choice

These matter more than any feature table, so they come first.

- **Licence.** OpenDLP is Apache-2.0. We bundle the editor with esbuild and
  serve it, which is distribution. TinyMCE (≥7) and CKEditor 5 are free only
  under **GPL-2.0-or-later**; GPLv2 is incompatible with Apache-2.0, GPLv3 is
  compatible one way (the combined work would have to be GPLv3). Either way,
  depending on one would push the licence of what we ship. It could be
  acceptable, but we're going with an MIT editor for now, so it doesn't need
  settling yet (decision D2). It is flagged on each GPL option below.
- **CSP.** `script-src` is nonce + `'strict-dynamic'` with no `unsafe-eval`;
  `style-src` allows `'unsafe-inline'`; `img-src` is `'self' data:`. So an
  editor that injects inline styles is fine; one that uses `eval`/`new
Function` is not. Scripts it loads dynamically are trusted under
  `strict-dynamic`.
- **Build.** Everything is an npm package bundled by `esbuild.config.mjs`, or a
  vendored file. No CDN. We already ship CodeMirror 6 this way
  (`src/js/backoffice/html-editor.js`, progressive enhancement of any
  `textarea[data-code-editor]`). A rich editor should follow the same pattern:
  enhance a textarea, sync back on submit, so the page still works with JS
  off.
- **The HTML is a Jinja template, not just HTML.** It is rendered through a
  sandboxed Jinja environment. `{{ var }}` in text survives any editor. But
  `{% if %}…{% endif %}` wrapped round elements, or `{{ }}` inside attributes
  (`href="{{ … }}"`), will be mangled or dropped by any editor that parses HTML
  into its own document model. See "Round-tripping" below — it applies to
  every option. We only tell authors to use `{{ vars }}`, `{% %}` blocks are
  not used in practice and not encouraged, so the visual editor supports
  `{{ vars }}` in text and nothing more (decision D3).
- **Image upload already exists.** `POST
/assembly/<id>/registration/images` stores the image and returns a
  `public_url` (`/register/<slug>/assets/<sha>.png`), and `PATCH` sets alt
  text. Feature 2 is mostly front-end wiring to this.
- **Accessibility.** The toolbar must meet our component accessibility rules
  (`docs/agent/component_accessibility.md`): toolbar role, roving focus,
  `aria-pressed` on toggles, labelled buttons.

## Things that are true whichever editor we pick

### Round-tripping HTML is the real risk

"Edit the HTML directly" (feature 5) plus a WYSIWYG view means the HTML goes
HTML → editor model → HTML every time the author switches view. Schema-based
editors (ProseMirror/Tiptap, Lexical, Quill, CKEditor 5) **silently drop
anything not in their schema** — unknown tags, unknown attributes, classes,
Jinja blocks between elements. DOM-based editors (Squire, Jodit, TinyMCE)
are more tolerant, but still normalise.

Whichever we pick, I'd recommend:

- Keep the existing CodeMirror editor as the "HTML" view, rather than relying
  on the editor's own source mode. One code editor in the app, and it already
  works.
- When switching HTML → visual, parse, re-serialise, and compare (normalised)
  with the input. If they differ, **don't switch**: tell the author this HTML
  uses things the visual editor can't show, and keep them in HTML mode for
  that box. Silent loss of markup on a live public page is the failure to
  avoid.

Since we only support `{{ vars }}` in text, the check is about ordinary HTML
the schema doesn't know (unusual tags, `style`, `id`, custom attributes)
rather than Jinja. It still matters: an author may have hand-written HTML in
the intro before the visual editor existed.

### "Default accessible style" is applied at render time (decision D4)

Rather than baking `class="govuk-body"` into the stored HTML, we store plain
semantic HTML and add the GOV.UK classes when rendering the public page if the
page's style setting is "accessible default". Pros: switching style later just
works, the editor needn't know about GOV.UK, and pasted content is styled
consistently. Cons: one more transform in the render path (a small,
well-tested function on the domain object, run on the _output_ of the Jinja
render). The editor can still _show_ GOV.UK styling by loading the GOV.UK CSS
inside the editing area.

Two things the code today implies for this:

- **There is no stored style setting yet.** "Plain" vs "GOV.UK" is only a
  choice of starter skeleton (`generate_starter_intro_html` vs
  `generate_starter_intro_html_govuk`); nothing on `RegistrationPage` records
  it. Render-time styling needs a new column (e.g. `content_style`, plain /
  govuk) and a control for it in the editor.
- **Existing intros already have classes baked in** from the GOV.UK skeleton,
  and authors may have added their own. So the transform only _fills in_ a
  default class on elements that have **no** class attribute, and never
  touches one that has. That makes it idempotent and leaves every existing
  page rendering exactly as it does now.

**How hard is it to change our minds after doing the intro only?** Cheap in
the direction we're starting from, which is the reason to start there:

- **Render-time → baked in** is easy. The same "fill in missing classes"
  function moves from render to save (or into the editor's serialiser), and a
  one-off data migration can run it over stored intros. Because it only adds
  classes where none exist, running it twice is harmless.
- **Baked in → render-time** would be the hard direction: we'd have to tell
  author-chosen classes from editor-added ones in stored HTML. Starting with
  render-time avoids ever needing that.
- **Extending to other boxes** (e.g. the thank-you HTML) is just calling the
  same function on their render path. The form HTML stays as it is — it's
  generated with its own classes.

**The email is out of scope for this.** Email clients don't have the GOV.UK
stylesheet and most strip `<style>` blocks, so email styling needs inline
`style=""` attributes or a CSS-inlining step when sending. Decision deferred
(D5); the visual editor for the email produces plain semantic HTML until then.

### Images in email are a different beast

**Not for now (decision D6):** the auto-reply editor has no image support. If
authors ask for it, it's a future round of work, and these notes are what that
round needs to handle:

- Relative URLs don't work in email: the upload handler for the email editor
  must insert an **absolute** URL (`url_for(..., _external=True)`).
- `data:` URIs are blocked by Gmail and others, so pasted images must always be
  uploaded, never inlined.
- Many clients block remote images by default, so alt text matters even more.
  The editor should ask for alt text on upload (our image `PATCH` route
  already supports it).
- The image must stay served for as long as anyone might open the email — fine
  today since images aren't personal data and aren't swept.

So "configurable upload behaviour" (feature 2) is really: per-editor config of
_upload URL_ and _absolute vs relative URL_, plus "images allowed at all".
Every option below can do that, because in each one we write the upload
callback ourselves. For now the only setting that varies is "images allowed":
on for the intro, off for the email.

## Option 1 — Tiptap 3 (on ProseMirror), headless, with our own toolbar _(my recommendation)_

[Tiptap](https://tiptap.dev/) is a framework-agnostic wrapper around
[ProseMirror](https://prosemirror.net/). It ships no UI: we build the toolbar.
Core, StarterKit and the extensions we need are **MIT** (`@tiptap/core`
3.31.4). The FileHandler extension, which used to be a paid "Pro" extension,
is now published as MIT (`@tiptap/extension-file-handler` 3.31.4). The paid
parts (collaboration cloud, AI, comments) are things we don't want.

How each feature lands:

| Feature                              | How                                                                                                                                                                         |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Headings, bold, italic, lists, links | StarterKit + Link.                                                                                                                                                          |
| Images in editor                     | `@tiptap/extension-image`.                                                                                                                                                  |
| Drag/paste upload, per-editor config | FileHandler `onDrop`/`onPaste` → our callback POSTs to the images route, inserts `public_url`. Upload URL / absolute-URL flag come from `data-` attributes on the textarea. |
| Highlight `{{ vars }}`               | A small ProseMirror plugin adding `Decoration.inline` over a regex match. Decorations are view-only, so the stored HTML is untouched. ~30 lines.                            |
| GOV.UK classes                       | Either render-time (above), or `addGlobalAttributes` so a `class` attribute survives the round-trip, with a default per node type when "accessible style" is on.            |
| Edit HTML                            | Toggle to our existing CodeMirror editor (`editor.getHTML()` / `setContent()`), with the round-trip check above.                                                            |

Pros:

- Permissive licence, actively maintained (released last week), large user
  base; ProseMirror underneath is the most battle-tested editing engine of the
  lot (NYT, Atlassian, GitLab).
- Headless means the toolbar is ours: GOV.UK buttons, our accessibility
  patterns, our translations via `_()` — nothing to restyle or fight.
- Plain npm + esbuild, no `eval`; fits the CodeMirror pattern exactly.
- Template-variable highlighting is cleanly possible _without_ polluting the
  HTML — the weakest point of most other options.
- Strict schema makes the output predictable and clean, which is good for the
  public page and for email.

Cons:

- We build and maintain the toolbar (buttons, link dialog, alt-text prompt,
  active-state tracking). Perhaps a few days' work plus tests, and we own its
  accessibility.
- Strict schema means it drops what it doesn't know; we need the round-trip
  check and probably a few `addGlobalAttributes` lines to keep `class`, `id`,
  `lang`.
- Tiptap the company sells a hosted product, so docs sometimes steer toward
  paid features; we'd need to pin and occasionally check that what we use
  stays MIT.
- Bundle size moderate (ProseMirror + extensions; roughly 100–200 KB minified,
  to be measured), loaded only on the registration editor page.

## Option 2 — Jodit 4, batteries included, MIT

[Jodit](https://xdsoft.net/jodit/) is a full WYSIWYG editor with toolbar,
dialogs, image handling, file browser and source mode, written in TypeScript
with no dependencies. **MIT** (`jodit` 4.17.2, released yesterday). There is a
paid PRO plugin pack we wouldn't need.

| Feature                   | How                                                                                                                                         |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Toolbar basics            | Built in; configurable button list.                                                                                                         |
| Images, drag/paste upload | Built in `uploader` config (URL, request builder, response parser) — point it at our images route. Per-instance config is natural.          |
| Highlight `{{ vars }}`    | No built-in way. Would mean wrapping matches in `<span>` in the editing DOM and stripping them on save — doable but fiddly and error-prone. |
| GOV.UK classes            | Render-time (above), or post-process on save.                                                                                               |
| Edit HTML                 | Built in source mode (plain textarea or ACE), or use our CodeMirror.                                                                        |

Pros:

- Everything on the nice-to-have list except variable highlighting is in the
  box; quickest route to a working editor.
- Permissive licence, actively released.
- DOM-based, so it is more tolerant of arbitrary HTML than a schema editor.

Cons:

- **Accessibility unknown.** I found no accessibility statement or WCAG
  claims for Jodit. We'd have to audit its toolbar and dialogs ourselves and
  may not be able to fix what we find without forking.
- Its own look and feel; restyling a full editor UI to sit inside our design
  system is usually more work than expected.
- Its UI strings use its own i18n system, not our gettext catalogues.
- ~400 KB minified; and largely one maintainer (xdsoft), so bus factor is a
  concern.
- Need to verify no `eval`/`new Function` under our CSP (spike item).
- Variable highlighting is awkward (see table).

## Option 3 — TinyMCE 8, the mature incumbent _(GPL — licence decision needed)_

[TinyMCE](https://www.tiny.cloud/) is the long-standing standard. Self-hosting
the open-source build needs `license_key: 'gpl'`; it is **GPL-2.0-or-later**
(`tinymce` 8.9.3). A commercial self-hosted licence starts at several hundred
dollars a year.

| Feature                   | How                                                                                                                                   |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Toolbar basics            | Built in.                                                                                                                             |
| Images, drag/paste upload | `images_upload_handler` callback — we write it, per instance.                                                                         |
| Highlight `{{ vars }}`    | Free `noneditable` plugin with `noneditable_regexp` makes `{{ … }}` atomic and styleable. (The nicer "merge tags" plugin is premium.) |
| GOV.UK classes            | `formats` / `style_formats` config can apply classes to headings and paragraphs; or render-time.                                      |
| Edit HTML                 | Free `code` plugin, or our CodeMirror.                                                                                                |

Pros:

- Most mature option here; vendor claims WCAG 2.1 AA conformance and has
  documented keyboard and screen-reader support.
- Documented CSP support, no `eval`.
- Variable highlighting is a config line.
- Very tolerant HTML handling with explicit `valid_elements` control.

Cons:

- **GPL.** See the constraint above — needs a deliberate decision, possibly
  legal advice, or a paid licence.
- Heavy, and loads skins/plugins from a base path at runtime, so we vendor a
  directory rather than bundling one file.
- Its own UI and i18n, as with Jodit (though its a11y is better documented).
- Free tier is steadily shrinking as features move to premium.

CKEditor 5 is similar in shape (mature, strong accessibility, GPL-2+, now
needs `licenseKey: 'GPL'`) but is schema-based like Tiptap, so it has the
round-trip losses _and_ the licence question. I'd only consider it if we went
the GPL route and preferred it to TinyMCE.

## Option 4 — Squire, minimal DOM editor from Fastmail, with our own toolbar

[Squire](https://github.com/fastmail/Squire) is the editor inside Fastmail's
composer (also used by Proton, Tutanota, Zoho Mail). **MIT** (`squire-rte`
2.4.9), ~16 KB gzipped, no dependencies, no UI. It works on the real DOM and
is designed to preserve arbitrary HTML — because it has to handle quoted
third-party email.

Pros:

- Email-native: built for exactly the auto-reply use case.
- Best HTML preservation of the permissive options; least round-trip risk.
- Tiny, no `eval`, toolbar is ours (same accessibility/i18n benefits as
  Tiptap).

Cons:

- Lower level than Tiptap: we write more ourselves (image insertion, upload
  wiring, link dialog, heading commands are thinner).
- No decoration layer, so variable highlighting has the same span-wrapping
  awkwardness as Jodit.
- Smaller community and fewer examples than Tiptap or TinyMCE.
- Tolerance cuts both ways: pasted Word/web content brings junk HTML with it,
  which we'd need to clean.

## Considered and set aside

- **Quill 2** (BSD-3) — converts to its Delta format and back, so arbitrary
  HTML and classes don't survive; last release January 2025.
- **Lexical** (MIT, Meta) — usable without React but the ecosystem and docs
  are React-first, and still pre-1.0 (0.52).
- **Trix** (MIT, Basecamp) — deliberately minimal; one heading level, no
  control over classes.
- **Summernote** — needs jQuery and Bootstrap.
- **Froala** — commercial only.
- **Roll our own (canvas or `contenteditable`).** Canvas means reimplementing
  text layout, selection, IME input, spellcheck and the whole accessibility
  tree — what Google Docs did with a large team, and a non-starter for screen
  readers. Raw `contenteditable` is the notorious "every browser behaves
  differently" problem that all of the above exist to solve; Squire is
  essentially the smallest sensible version of it.

## Summary

|                               | Tiptap 3                   | Jodit 4     | TinyMCE 8              | Squire            |
| ----------------------------- | -------------------------- | ----------- | ---------------------- | ----------------- |
| Licence                       | MIT                        | MIT         | **GPL-2+** / paid      | MIT               |
| UI                            | ours                       | built in    | built in               | ours              |
| Accessibility                 | ours to get right          | **unknown** | strong (vendor claim)  | ours to get right |
| Variable highlighting         | clean (decorations)        | awkward     | config (`noneditable`) | awkward           |
| Drag/paste upload             | FileHandler + our callback | built in    | our callback           | ours              |
| HTML preservation             | strict schema (lossy)      | tolerant    | tolerant               | most tolerant     |
| Fits our i18n / design system | yes                        | no          | no                     | yes               |
| Effort to integrate           | medium                     | low         | low–medium             | medium–high       |

My recommendation is **Tiptap**: permissive licence, the strongest engine,
the only option with clean variable highlighting, and a toolbar we control
fits GOV.UK styling, our gettext catalogues and our accessibility rules. The
price is building the toolbar, which I think is worth paying because we'd
otherwise be restyling and auditing someone else's. **Squire** is the
fallback if the round-trip losses turn out to bite on real pages.

## Decisions

- **D1 — Spike Tiptap on the intro box first.** Toolbar, variable
  highlighting, image upload via the existing images route, and the HTML ↔
  visual round-trip check, tried against the starter skeletons and a couple of
  real live intros before we commit to it. The auto-reply email follows once
  the intro works.
- **D2 — Tiptap, not a GPL editor, for now.** A GPL dependency could be
  acceptable, so TinyMCE/CKEditor are not ruled out for good, but Tiptap's MIT
  licence means we don't have to settle that question to proceed.
- **D3 — Only `{{ vars }}` in text are supported.** `{% %}` blocks aren't
  used and aren't encouraged; we only tell authors to use `{{ vars }}`. The
  visual editor promises nothing more, which makes round-tripping much
  simpler.
- **D4 — GOV.UK classes are applied at render time**, by a function that
  fills in a default class only where an element has none. This needs a new
  stored style setting on the registration page. Switching to baked-in classes
  later is cheap; see the render-time section above.
- **D5 — Email styling is deferred.** No inline styles or CSS inlining in this
  round; the email editor produces plain semantic HTML.
- **D6 — No images in the auto-reply email for now.** If authors ask for it,
  it's a future round of work; the notes under "Images in email" are its
  starting point.

## Sources

- [Strapi: best WYSIWYG editors](https://strapi.io/blog/best-wysiwyg-editors)
- [Tiptap FileHandler extension](https://tiptap.dev/docs/editor/api/extensions/file-handler)
- [Tiptap 3.0 launch](https://www.ycombinator.com/launches/NR5-tiptap-3-0-beta-the-next-gen-open-source-editor)
- [TinyMCE licence key docs](https://www.tiny.cloud/docs/tinymce/latest/license-key/)
- [CKEditor 5 licence key and activation](https://ckeditor.com/docs/ckeditor5/latest/support/licensing/license-key-and-activation.html)
- [Jodit](https://xdsoft.net/jodit/)
- [Squire 2.0 announcement](https://www.fastmail.com/blog/squire-2-0-fastmail/) and [repo](https://github.com/fastmail/Squire)
- [Lexical quick start](https://lexical.dev/docs/getting-started/quick-start)
- [Editor comparison, starterdocs](https://starterdocs.js.org/docs/comparisons/editors)
- npm registry metadata for each package (versions and licences), checked 2026-10-08
