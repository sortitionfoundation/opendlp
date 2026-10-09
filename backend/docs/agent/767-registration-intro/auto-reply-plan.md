# Visual editor for the auto-reply email

Branch: `767-rich-text-autoreply`, off `767-rich-text-editor`. Follows
decision D1 in [wysiwyg-editor-options.md](wysiwyg-editor-options.md): once
the intro editor worked, the auto-reply email gets the same editor. Built on
everything in [tiptap-intro-editor-plan.md](tiptap-intro-editor-plan.md); this
plan only covers what is different for the email.

**Status: in progress.** Steps 1, 1b and 2 are done (marked ✅).

## Goal

When editing the auto-reply email body, the author sees the same visual
editor as the intro: a toolbar, `{{ vars }}` highlighted, and a switch to the
existing CodeMirror HTML view and back. The editor offers what makes sense in
an email and nothing else: no images, no tables, and only links that work
from an inbox. The subject stays a plain text input. With JavaScript off, the
step works as it does today.

## How it works today (what this touches)

| Layer    | Where                                                       | Today                                                                                                                                                                                                                                                 |
| -------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Template | `templates/backoffice/registration/_step_email.html`        | `textarea(name="template_body_html", label=_("HTML body"), code_editor=true, …)`, hint "Jinja + HTML…". `readonly` + `aria-readonly` outside edit mode. Variables aside in edit mode, with copy buttons for `{{ assembly.title }}` and the others. |
| Macros   | `components/input.html`, `components/rich_editor.html`      | `textarea(rich_editor=true, rich_editor_images=…)` renders the controls and `data-rich-editor` / `data-rich-editor-images`. The toolbar gates only Image and Image size on `images`; Table and its menu are always there.                         |
| JS       | `rich-editor.js`, `rich-editor-schema.js`, `-toolbar.js`    | `createSchemaExtensions({images, resizable})` always includes the table extensions. `mountRichEditor` reads `data-rich-editor-images`. The link request carries `{editorId, href, text}`.                                                            |
| JS       | `src/js/components/rich-editor-link-dialog.js`              | `applyLink()` only checks the URL isn't empty. A relative URL such as `/register/foo` is accepted.                                                                                                                                                  |
| Domain   | `domain/email_template_render.py`, `domain/html_to_text.py` | Renders `body_html` in a sandboxed Jinja env; the plain-text part comes from `html_to_text`, which now handles the editor's HTML (`<li><p>`, layout whitespace, quotes, rules - commit `d4bea35e`).                                                 |
| Routes   | `backoffice_registration.py` `_handle_email_action_save`    | Saves `template_subject` and `template_body_html` from the posted form. Nothing to change.                                                                                                                                                            |

The default body (`_default_email_template_content`) uses only `<p>`,
`<strong>` and `<br>`, so a new template opens in Visual mode.

## Decisions

### A1 — No tables in the email (Chewie)

Unstyled tables look poor in most email clients, and the tables question (Q6
in the intro plan, layout or data) is still open. The email editor leaves the
table extensions out of its schema and renders no Table button or menu.

Consequence: a body that contains a `<table>` fails the round-trip check, so
it **opens in HTML mode** and stays editable there, exactly as an intro with
a `<h4>` does. Nothing is lost. If the real emails (step 1) show that most
live auto-replies are layout tables, that is the moment to revisit this, not
before.

### A2 — No images in the email (options decision D6)

Already decided: `rich_editor_images` stays off, so no Image or Image size
button, no FileHandler, and the image node is not in the schema. An `<img>`
in an existing body therefore opens it in HTML mode, as for tables.

### A3 — Each feature is its own switch on the textarea

Tables join images as an explicit switch: `rich_editor_tables` on the
`textarea` macro, `data-rich-editor-tables="true"` on the textarea,
`tables=` on `rich_editor_controls` / `rich_editor_toolbar`, and a `tables`
option on `createSchemaExtensions`. Likewise `rich_editor_absolute_links`
(A4).

Rejected: one `rich_editor_profile="email"` setting that implies the rest.
It reads well at the call site but hides what each editor allows, and the
next box (the thank-you HTML) would need yet another profile. Flags are what
`images` already does, and each one is tested on its own.

The intro passes `rich_editor_tables=true`; the default is `false`, matching
`images`, so a new editor gets the least and opts in.

### A4 — Links in the email must be absolute

A relative link works on the registration page and is broken in an inbox.
With `data-rich-editor-absolute-links="true"`, the editor adds
`absoluteOnly: true` to the link request, and the dialog refuses a URL that
doesn't start with `https://`, `http://`, `mailto:` or `tel:`, showing a new
message (`linkUrlNotAbsolute`, "Email links must be full addresses, starting
with https://"). The check is in the dialog slice, where the empty-URL check
already is.

A URL starting with `{{` is allowed: a variable in a link address survives
the editor (see `docs/registration-intro-editor.md`), and it could render to
an absolute URL. This is the only check on links - links already in the HTML
are left alone, and HTML mode can still write anything.

Not done: rewriting `/path` into `https://our-host/path` for the author. The
host the author means is a guess (production or a test server), so a clear
refusal is better than a silent rewrite.

### A5 — The hint names the email's variables

The editor's hint says "variables like `{{ assembly_title }}`", which is the
intro's spelling; the email's are dotted (`{{ assembly.title }}`).
`rich_editor_controls` takes a `variable_example` argument used in the hint,
and the intro passes `{{ assembly_title }}`. `VARIABLE_PATTERN` already
matches dotted names, so highlighting needs no change.

The step's own hint ("Jinja + HTML. A plain-text version is generated
automatically…") becomes "A plain-text version is generated automatically
for email clients that need it.", and the label "HTML body" becomes "Email
body", since the author no longer sees HTML by default.

### A6 — No content style, no email styling

Options decision D5 stands: the email editor produces plain semantic HTML,
with no GOV.UK classes and no inline styles. `rich_editor_style` is left
empty, so the editing area shows the plain look, and no style radios are
rendered.

### A7 — Visual mode saves formatted HTML, as for the intro

E15 applies unchanged: an edit in Visual mode saves the body one block per
line. Email clients ignore that whitespace, and `html_to_text` was fixed to
ignore it too (with tests), so the plain-text part is unaffected.

### A8 — Keep styled spans (Chewie)

The five real auto-replies (step 1) **all open in HTML mode** today, and for
one reason only: `<span style="…">`, which pasting from Google Docs wraps
round most of the text. With the spans removed, all five round-trip cleanly.
They have no tables and no images, so A1 and A2 cost nothing on real emails.
A styled span was a documented reason to open as HTML, so this isn't a bug,
but it would make the email editor HTML-only for every email the team sends.

Decided: **keep styled spans.** `@tiptap/extension-text-style` (already
installed, as FileHandler's peer, so not a new dependency) turns
`<span style="…">` into a `textStyle` mark, and `PreservedAttributes` gains
`textStyle` so its `style`, `class` and `dir` survive. The toolbar gains no
button: spans are kept, never made. It's a schema change, so the intro gets
it too, which has the same Google Docs spans.

Rejected:

- **Treat `font-weight: 400` spans as no-ops.** `unbolded_span_auto_reply.html`
  has one inside `<strong>`, where it un-bolds the text; dropping it would
  make that text bold.
- **A "Remove pasted formatting" action.** It changes how the email looks, so
  it could only ever be offered, never automatic. It could follow later; not
  in this plan.

**What the spike found** (throwaway test, against both fixture sets):

- With the mark, 4 of the 5 emails round-trip cleanly. The intro fixtures are
  unchanged: two clean, and the layout table still refused for its
  `<colgroup>`, as before.
- Adjacent spans with the same style are merged by Tiptap; `normaliseHtml`
  already treats that as equal.
- **A span outside a `<strong>`** comes back as it went in.
- **A `font-weight: 400` span inside a `<strong>`** (the fifth email): Tiptap's
  Bold extension has a parse rule that clears bold for `font-weight: 400`, so
  `<strong><span style="font-weight: 400;">x</span></strong>` comes back as
  `<span style="font-weight: 400;">x</span>`. That **renders the same** - the
  inner span already overrode the bold - so Tiptap is right and our check is
  too strict. Keeping both marks would be wrong: Tiptap always puts the span
  outside the `<strong>`, which would make the text bold. So `normaliseHtml`
  learns the rendering rule: a `<strong>`/`<b>` whose text is all inside a
  `font-weight: 400` or `normal` span is dropped. Only that direction, and
  only those two values.
- **A span nested in a span** comes back as one span with both styles merged,
  which also renders the same. None of the real emails or intros has one, so
  this plan doesn't teach the check about it: such HTML keeps opening as
  HTML, which loses nothing. A one-line change later if it turns up.

## Implementation steps

Ordered so each step leaves `just check` and `just test-nobdd` green.
Commit this plan separately from the code.

### ✅ 1. Round-trip fixtures from real auto-reply emails

Done: five real, anonymised auto-reply bodies are in
`tests/fixtures/registration_auto_replies/`, with a `README.md` saying what
each one exercises. (Seven were supplied; two were exact copies.) What they
showed is A8.

Tests land with step 1b, because until then every fixture is refused.

### ✅ 1b. Keep styled spans (A8)

- `rich-editor-schema.js`: add `TextStyle` to `createSchemaExtensions`, and
  `"textStyle"` to `PRESERVED_ATTRIBUTE_TYPES`. Pin
  `@tiptap/extension-text-style` exactly in `package.json`, as the other
  Tiptap packages are (it is `^3.31.4` today).
- `rich-editor-html.js`: in `normaliseHtml`, drop a bold mark from a run
  that sits inside a span whose style sets `font-weight` to `400` or
  `normal` (A8). Update the function's doc comment, which lists what it
  erases.
- Tests in `rich-editor-schema.test.js` / `rich-editor-html.test.js`:
  - a styled span round-trips, with `style`, `class` and `dir`;
  - a span round a `<strong>` keeps its order;
  - the un-bolding span inside `<strong>` round-trips, and a
    `font-weight: 700` span inside `<strong>` does **not** have its bold
    dropped by the normaliser;
  - a span nested in a span is still refused (A8 leaves it);
  - a bare `<span>` is still dropped, as now;
  - every file in `tests/fixtures/registration_auto_replies/` round-trips
    cleanly against the **email** schema
    (`createSchemaExtensions({images: false, tables: false})`, once step 2
    adds `tables`);
  - the intro fixtures' expectations are unchanged;
  - the default body (`_default_email_template_content`) round-trips.
- `docs/registration-intro-editor.md`: a styled `<span>` stops being a reason
  to open as HTML; add spans to "What the visual editor keeps", and the
  un-bolding rule to what the check treats as equal.
- BDD: a scenario in the intro editor feature that opens an intro with a
  styled span in Visual mode, edits another paragraph, saves, and still
  finds the span.

As built:

- **Nesting order now matters for styled spans.** A second spike showed
  Tiptap always nests a span inside a link and outside bold, italic,
  underline and strikethrough. `normaliseHtml` ignored nesting order, so
  `<span style="color: red;"><a>` → `<a><span style="color: red;">` (a blue
  link turning red) would have passed as clean. So the rule is wider than
  planned: `settleSpanStyle` settles a run's single styled span against the
  `<strong>`, `<em>` and `<a>` round and in it the way a browser does - the
  inner one sets `font-weight`, `font-style` or `color`. That covers the
  un-bolding case and refuses the link case. Tiptap only un-bolds for exactly
  `font-weight: 400`; `normal` keeps the bold and moves it inside, which the
  check now refuses. Text in more than one span is left alone, so nested
  spans stay refused.
- The `font-weight: 700` test became "keeps the weight of a bold span inside
  `<strong>`": the span is inner, so its weight is what shows.
- No `package.json` change: none of the Tiptap packages is pinned exactly;
  all are `^3.31.4` with the lockfile, and text-style already matched.
- The default body is a fixture, `default_auto_reply.html`.
  `tests/unit/test_default_auto_reply_body.py` checks it is the real default,
  and that every catalogue's translation of it uses the same tags (the
  Hungarian risk below).
- Confirmed in a vitest: text typed at the end of a styled span takes its
  style.

### ✅ 2. Tables become a switch (A1, A3)

- `rich-editor-schema.js`: `createSchemaExtensions({images = true,
  resizable = true, tables = true})` adds the four table extensions only when
  `tables` is on. (Default `true` here keeps every current caller and test
  as they are; the template default is what new editors see.)
- `rich-editor.js`: read `data-rich-editor-tables`; pass it to the schema.
  Check that nothing else assumes the table extension is loaded - the
  Shift+Tab handling in `rich-editor-toolbar.js` (line ~266) and the table
  commands' `enabled` checks call `editor.can().deleteTable()` and
  `isActive("table")`, which must not throw without the extension.
- `rich_editor.html`: `tables` argument on both macros; the Table button and
  its menu render only when it is on.
- `input.html`: `rich_editor_tables=false` argument, documented in the
  docstring; renders `data-rich-editor-tables="true"`.
- `_step_intro.html`: pass `rich_editor_tables=true`.

As built: the toolbar needed no change. It only wires the buttons it finds,
so with no Table button it never calls a table command; a vitest drives a
toolbar and editor with no tables to show it. The e2e test for the intro
step now also asserts the Table button and menu.

### 3. Absolute links (A4)

- `input.html`: `rich_editor_absolute_links=false` →
  `data-rich-editor-absolute-links="true"`.
- `rich-editor.js`: add `absoluteOnly` to the `LINK_REQUEST_EVENT` detail.
- `rich-editor-link-dialog.js`: store `linkAbsoluteOnly`; in `applyLink()`,
  after the empty check, refuse a non-absolute URL with
  `messages.linkUrlNotAbsolute`. Keep the pattern in one exported constant so
  the test and the code share it.
- `_page_data.html`: the new message.

### 4. Hint wording (A5)

- `rich_editor.html`: `variable_example` argument in the hint;
  `input.html` passes `rich_editor_variable_example` through.
- `_step_intro.html`: `{{ assembly_title }}`.

### 5. Turn it on in the email step

- `_step_email.html`: `rich_editor=true`, `rich_editor_label=_("Email
  body")`, `rich_editor_editable=edit_mode`,
  `rich_editor_absolute_links=true`,
  `rich_editor_variable_example="{{ assembly.title }}"`, images and tables
  left off. Change the label and hint (A5). Drop `code_editor=true` (the
  rich editor brings its own HTML view) and the monospace `body_attrs` style,
  which only applied to the raw textarea, keeping `readonly` /
  `aria-readonly`.
- Confirm the edit guard (`markEditDirty()` / `allowLeave()`) still fires:
  the editor writes to the textarea and dispatches `input`, as on the intro.
- Load the `ui-components` skill before touching the templates.

### 6. Translations and docs

- New and changed strings → the `translate-catalogues` skill. Changing the
  label and hint discards their Hungarian translations; that's accepted,
  because the old wording is now wrong.
- `docs/registration-intro-editor.md`: a short "The auto-reply email"
  section - what its editor leaves out and why (A1, A2, A4), and that a body
  with a table or image opens as HTML. Or rename the page to
  "rich text editor" if the section grows past a screen; decide when writing
  it.
- `CLAUDE.md`'s doc list entry, if the page is renamed.
- Mark this plan's steps ✅ with any as-built notes.

## Tests

| Tier             | What                                                                                                                                                                                                                                                                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit (Python)    | Already done: `html_to_text` on the editor's lists, quotes, rules and layout whitespace.                                                                                                                                                                                                                                                       |
| Component        | `test_backoffice_registration_email.py`: edit mode renders `data-rich-editor` on the body without images, tables or `data-code-editor`, with absolute links on, and the controls with no Table button; view mode renders the controls with no toolbar. The intro step still renders the Table button. A test send of a body with a `<ul><li><p>` list sends a plain-text part with `- ` bullets. |
| e2e              | `test_registration_stepper_journey.py` still walks through the email step; saving the email posts `template_body_html` as before.                                                                                                                                                                                                            |
| JS unit (vitest) | Schema without tables refuses a table and still accepts everything else; the email fixtures (step 1); `mountRichEditor` reads the tables and absolute-links flags; the link request carries `absoluteOnly`; the link dialog accepts `https:`, `http:`, `mailto:`, `tel:` and `{{`, refuses `/path`, `www.example.com` and `example.com`, and accepts anything when the flag is off; the toolbar works with no Table button. |
| BDD (Playwright) | New `features/backoffice-registration-email-editor.feature`: format the email in the visual editor and save, then see the HTML; the toolbar has no Image or Table button; a body with a table opens in HTML mode with the notice; a relative link is refused with the message and an absolute one is set; the read-only view shows Visual mode with no toolbar. |

Run `just build-all` before BDD, and run `just test-nobdd` and
`just test-bdd-headless` one after the other, never at the same time.

## Risks and things to watch

- **Live emails that open as HTML.** Step 1 found that every real
  auto-reply did, because of styled spans. A8 fixes that; the fixture tests
  are the guard.
- **Spans make editing slightly odd.** Text typed at the end of a styled
  span takes its style (confirmed by a test in step 1b), as it would in
  Google Docs. That's what the author
  will expect from a paste, but the toolbar can't show or remove it; HTML
  mode can. The "Remove pasted formatting" idea in A8 is the answer if
  authors ask.
- **Old variable names.** The real emails use the old platform's
  `{{ recipient.… }}` and `{{ site.full_url }}`. Pasted into OpenDLP they
  would render as empty strings, and nothing warns while editing: missing
  variables are only logged and stored on the send record when an email is
  sent. Not the editor's problem, but the team will
  hit it when they move their emails across; worth a line in the user docs.
- **A Hungarian default body.** `_default_email_template_content` is
  translated. A translator could add markup the editor lacks; the round-trip
  check would send it to HTML mode, which is safe but wrong for a new
  template. Done in step 1b: a test checks every translation uses the
  English markup.
- **Link check is client-side only.** HTML mode, and anyone posting the form
  directly, can still save a relative link. That's fine: A4 is help for the
  author, not a security rule. A server-side readiness warning for relative
  links in the email could follow if it turns out to matter.
- **Bundle and CSS** are already loaded on every section of the registration
  editor page, so the email step needs no new assets.

## Out of scope

- Images in the email (D6) and email styling (D5).
- Tables in the email (A1). The real emails have none.
- The subject line, which stays a plain input.
- An "insert variable" menu; the variables aside's copy buttons stay.
- Ordered lists in the plain-text part still show `- `, not numbers.
