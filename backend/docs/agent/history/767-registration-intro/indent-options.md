# Indent and outdent buttons for the visual editor

**Status: decided - option A (lists only), implemented.** Chewie asked for
buttons that increase and decrease the indent of the text. Before building
them there was a question for the team: what should indent *act on*? This
note covers what I found, the options, and their pros and cons. The team
chose option A. Tab inside a list in a table cell moves to the next cell
rather than nesting the item; the Indent button nests it, and a vitest pins
that down.

Related: [tiptap-intro-editor-plan.md](tiptap-intro-editor-plan.md) (E5
schema, E12 GOV.UK classes, E14 inline styles, step 10 toolbar) and
[auto-reply-plan.md](auto-reply-plan.md). The auto-reply email uses the same
toolbar, so whatever we choose shows up there too.

## What I found

- **The Figma icons are list icons.** The OpenDLP "Icons" sheet (node
  1809:25) has `list-indent-increase` (5032:10623) and
  `list-indent-decrease` (5032:10625). It has no plain `indent` / `outdent`
  or `indent-increase` / `indent-decrease` glyphs. So the icons we have
  suggest nesting lists. Using them for paragraphs would still work, but a
  bulleted icon on a paragraph button is a small mismatch.
- **List nesting already works from the keyboard.** StarterKit's `ListItem`
  binds Tab to `sinkListItem` and Shift+Tab to `liftListItem`. They write
  plain nested `<ul>`/`<ol>`, which the schema, `normaliseHtml`,
  `formatHtml` and the GOV.UK class mapping already handle. A list item
  lifted out of a top-level list becomes an ordinary paragraph. What's
  missing is a visible button: nothing on screen tells an author that Tab
  nests, and a pointer-only user can't nest at all.
- **HTML has no element for "indented paragraph".** Indenting a `<p>` or
  heading means one of:
  - an inline `margin-left` (or `padding-left`) style. This is what
    CKEditor's and TinyMCE's indent plugins do by default; or
  - a class such as `indent-1`. CKEditor can do this instead.
- **We keep `style` but never edit it.** `style` is a preserved attribute
  (E5): the editor holds whatever string the HTML had and writes it back.
  Nothing in the toolbar sets it. An indent that edits `margin-left` would
  be the first thing to change part of that string, so it has to merge with
  whatever else is there (`text-align`, colours pasted from Google Docs) and
  leave the rest exactly as it was.
- **A class would switch off the GOV.UK defaults.** Under E12/E14 any
  element with a class of its own gets no default GOV.UK class. So
  `<p class="indent-1">` would lose `govuk-body` and its font and spacing.
  We'd need a carve-out in `_wants_default_class`, and the CSS for the class
  would have to reach the public page and email clients. Email clients
  mostly ignore stylesheets, so a class wouldn't indent anything in the
  auto-reply.
- **GOV.UK has no indent style.** Its pattern for text set apart from the
  rest is inset text (`govuk-inset-text`), which the Quote button already
  produces. Indented body paragraphs also cause trouble for screen
  magnifier users, and on phones every step of indent takes width from a
  narrow column.
- **The public page CSP allows inline styles** (`style_src` includes
  `'unsafe-inline'` in `flask_app.py`), and the real intros already use
  `style`, so an inline `margin-left` would render. Email clients honour
  inline `margin-left` too.

## Options

### A. Lists only (my recommendation)

Indent and Outdent buttons run `sinkListItem` / `liftListItem` on the list
item at the cursor. Outside a list, or where the command can't run (such as
the first item, which has nothing to nest under), they're `aria-disabled`,
like the table menu items, with `enabled: (editor) =>
editor.can().sinkListItem("listItem")`.

Pros:

- No schema change, and no new attributes. The HTML is semantic nested
  lists that screen readers announce as levels.
- Every existing intro still round-trips exactly as it does now.
- It's what the Figma icons show.
- It makes the existing Tab / Shift+Tab behaviour visible and usable with a
  pointer.
- It works in the email as well, since nested lists render everywhere.
- Small: two `COMMANDS` entries, two icons, two labels, tests.

Cons:

- It doesn't indent a paragraph, which may be what authors expect if they
  come from Word or Google Docs. A disabled button with the cursor in a
  paragraph may puzzle them; the tooltip could say "Indent list item" to
  make the scope clear.

### B. Lists, plus paragraphs and headings with an inline margin

In a list: as option A. Anywhere else: each press adds one step of
`margin-left` (say `2em`, up to about 5 steps) to the `p` or `h1`–`h3`, and
Outdent takes one away.

Pros:

- It matches what authors know from word processors.
- Inline styles render on the public page and in email clients.
- Inline styles don't opt out of GOV.UK classes (E14), so the paragraph
  keeps `govuk-body`.

Cons:

- The biggest change. It needs an `indent` attribute that is read out of,
  and written back into, the preserved `style` string without disturbing
  the rest of it. That means new parsing code, round-trip fixtures for
  merged styles, and `normaliseHtml` rules for margin spellings (`2em`,
  `32px`, `margin` shorthand). A hand-written `margin-left` in another unit
  would either be read as a level or have to send the intro to HTML mode.
- It's the first time the toolbar writes presentation into the HTML. Up to
  now everything it makes is semantic.
- Indent on a paragraph is a visual-only signal. A screen reader user hears
  nothing, so meaning carried by the indent is lost (WCAG 1.3.1).
- Indented text is worse on phones, and GOV.UK steers away from it.
- The same button does two different things depending on where the cursor
  is, which is harder to document and to explain in the tooltip.

### C. Lists, plus paragraphs with an indent class

As option B, but with `class="indent-1"` … `indent-n`, with the CSS in
`application.css`.

Pros:

- No parsing of the `style` string, and the HTML stays tidy.

Cons:

- It breaks the GOV.UK default-class rule (E12/E14) unless we add a
  carve-out for our own classes.
- It does nothing in the auto-reply email, since email clients mostly ignore
  stylesheets, so the email editor would need the paragraph half turned off.
- A pasted or hand-written intro with a `margin-left` wouldn't map onto the
  levels, so there'd still be two ways of indenting.
- It has option B's accessibility and phone costs.

### D. No buttons

Keep Tab / Shift+Tab for lists and mention them in the hint above the
toolbar, next to the Alt+F10 hint.

Pros:

- Nothing to build.

Cons:

- There's still no way to nest a list without a keyboard. The component
  rules expect pointer and keyboard to be equivalent, so a button is the
  better fix.

## Things to check whichever option we pick

- **Tab inside a table cell that holds a list.** The table's Tab binding
  (`PlainTable` in `rich-editor-schema.js`) and `ListItem`'s Tab both claim
  the key, so which one wins depends on extension order. The buttons would
  sidestep this, but the keyboard behaviour should be checked and, if
  needed, pinned down with a test.
- **Icons:** `list-indent-increase` and `list-indent-decrease` from the
  Figma sheet, added to `icons.html` as `icon_list_indent_increase` /
  `icon_list_indent_decrease` and to the icon showcase
  (`templates/backoffice/showcase/icons.html`).
- **Toolbar position:** straight after Numbered list, so the list controls
  sit together.
- **Labels:** "Indent" / "Outdent", or "Indent list item" / "Outdent list
  item" for option A. These are new strings, so the `translate-catalogues`
  skill applies.
- **Tests:** vitest for the commands and their `aria-disabled` state, and
  BDD for nesting a list item with the button and the keyboard.

## Question for the team

Should indent act on **lists only** (A), or also on **paragraphs and
headings** (B or C)? If paragraphs, should the indent be an **inline
margin** (B: works in email, but it's the first time the toolbar writes
style) or a **class** (C: tidier HTML, but no effect in email and it clashes
with the GOV.UK defaults)?
