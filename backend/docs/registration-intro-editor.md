# The registration intro editor

The intro is the HTML shown above a registration page's form. Authors edit it
in a **visual editor**, with a switch to the **HTML** view. This page says what
the visual editor keeps, what makes it fall back to HTML, what an edit in it
changes, and how the **intro style** works. It is for developers, and for
anyone supporting an author who asks why their intro "opens as HTML".

The design and its decisions are in
[docs/agent/767-registration-intro/tiptap-intro-editor-plan.md](agent/767-registration-intro/tiptap-intro-editor-plan.md).

## The two views

- **Visual** is a [Tiptap](https://tiptap.dev/) editor
  (`src/js/backoffice/rich-editor.js`). Its toolbar offers text, headings 1–3,
  bold, italic, bulleted and numbered lists, links, images, undo and redo.
- **HTML** is the CodeMirror editor that every other HTML box uses
  (`src/js/backoffice/code-editor.js`).

The intro's `<textarea>` stays the source of truth: both views write to it,
and it is what the form submits. Without JavaScript the page shows the plain
textarea, as before the editor existed.

The editor opens in Visual mode only if the intro survives a trip through it
unchanged; otherwise it opens in HTML mode and says why. Switching from HTML
to Visual runs the same check, and the switch is refused when it fails. Visual
to HTML can always happen.

## What the visual editor keeps

- **Elements:** paragraphs, `h1`–`h3`, `strong`/`b`, `em`/`i`, `ul`/`ol`/`li`,
  `a`, `img`, `br`, and `div` (so wrappers such as the GOV.UK grid row
  survive, although the toolbar cannot make one).
- **Attributes:** `class`, `style` and `dir` on all of those; `href`, `target`
  and `rel` on links; `src`, `alt`, `title`, `width` and `height` on images.
- **Template variables** like `{{ assembly_title }}`, which are highlighted in
  text. A variable in an attribute, such as `href="{{ url }}"`, survives too,
  but the visual editor cannot show it or offer a way to change it: edit it in
  the HTML view.

## What makes it fall back to HTML

Anything else, because the visual editor would silently drop it. The common
causes:

- **tables** (they are on the list to support; see step 10 of the plan);
- **HTML comments**;
- **headings below level 3** (`h4`–`h6`), blockquotes, horizontal rules,
  underline and strikethrough;
- **text outside any paragraph**, including a bare Jinja tag such as
  `{% if … %}` between elements. Only `{{ variables }}` are supported in the
  intro;
- a `<span>` that carries attributes, such as `style`;
- an image embedded as a `data:` URL.

## What an edit in Visual mode changes

The check guarantees **no content is lost**; it does not promise the HTML comes
back byte-for-byte. The first time an author changes something in Visual mode,
the saved HTML is rewritten in the editor's own consistent form:

- whitespace between elements goes, and `&nbsp;` may become a literal no-break
  space (they render the same);
- attribute order changes, and `style` values are re-spelt
  (`color: #0c7e8f` → `color: rgb(12, 126, 143)`);
- `<b>` becomes `<strong>` and `<i>` becomes `<em>`;
- attribute-less `<span>`s (common in text pasted from Google Docs) and empty
  `<strong></strong>` disappear;
- formatting may nest differently: `<strong><a>…</a></strong>` can come back as
  `<a><strong>…</strong></a>`;
- **a list item's text is wrapped in a paragraph**: `<li>text</li>` becomes
  `<li><p>text</p></li>`. This is the one change that can be seen: the
  paragraph brings its own margin, so the list spaces out a little.

Opening an intro in Visual mode and saving without changing anything leaves
the HTML exactly as it was.

## Images

The Image button, dropping a file into the editing area, and pasting one all
open the usual upload dialog, so the author writes alt text as for any other
upload. The uploaded image is then inserted where it was dropped or pasted.
The Assets panel's **Insert** button puts an existing image at the cursor, in
either view.

Images are inserted with the slug-free URL `/register-assets/images/<id>.png`,
which keeps working when the page's URL changes. It is served to anyone once
the assembly has a page in test or published status, and before then only to
signed-in users who can view the assembly, so images show in the editor and
preview straight away.

## The intro style

The intro step has an **Intro style** choice:

- **GOV.UK** (the default for new pages) gives the intro the accessible GOV.UK
  look when the page is shown. At render time, each element without a class
  of its own gets one:

  | Element | Class                           |
  | ------- | ------------------------------- |
  | `h1`    | `govuk-heading-xl`              |
  | `h2`    | `govuk-heading-l`               |
  | `h3`    | `govuk-heading-m`               |
  | `p`     | `govuk-body`                    |
  | `ul`    | `govuk-list govuk-list--bullet` |
  | `ol`    | `govuk-list govuk-list--number` |
  | `a`     | `govuk-link`                    |

- **Plain** renders the intro exactly as written, for authors bringing their
  own styles. Every page that existed before the intro style was introduced is
  plain, so none of them changed.

The classes are added to the rendered page, never stored in the intro's HTML,
so switching style changes the whole intro at once.

**To keep one element out of the GOV.UK look, give it a class of your own**,
for example `class="plain"`: an element with any non-empty class is left alone.
An empty `class=""` does not count. **An inline `style` does not opt an
element out**: the element still gets its GOV.UK class, and the inline style
adjusts it, winning wherever the two set the same property. So
`<p style="text-align: center;">` is a centred GOV.UK paragraph.

The visual editor previews the chosen style as you switch between the options.

The form below the intro is never given default classes; it carries its own.
The code is `src/opendlp/domain/html_default_classes.py`.
