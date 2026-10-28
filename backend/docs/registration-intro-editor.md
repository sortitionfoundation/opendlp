# The registration intro editor

The intro is the HTML shown above a registration page's form. Authors edit it
in a **visual editor**, with a switch to the **HTML** view. This page says what
the visual editor keeps, what makes it fall back to HTML, what an edit in it
changes, and how the **intro style** works. The thank-you page uses the same
editor; see [The thank-you page](#the-thank-you-page). The auto-reply email's
body uses it too, with less in it; see [The auto-reply email](#the-auto-reply-email).
It is for developers, and for anyone supporting an author who asks why their
intro "opens as HTML".

The design and its decisions are in
[docs/agent/767-registration-intro/tiptap-intro-editor-plan.md](agent/767-registration-intro/tiptap-intro-editor-plan.md).

## A new page's intro

A new page's intro starts with the assembly's title as a heading and its
question as a paragraph, written in as literal text inside the GOV.UK grid
wrapper that lines the intro up with a GOV.UK styled form
(`generate_initial_intro_html` in `src/opendlp/domain/registration_page.py`).
The author edits the words directly. The editor shows whatever was saved
after that, and an empty intro is allowed: it adds nothing to the page.

The intro also understands `{{ project_title }}` and `{{ project_question }}`,
which fill in the project's current title and framing question when the page
is shown. The editor doesn't mention them; they are for authors who want the
intro to follow a later change to the project. `{{ assembly_title }}` and
`{{ assembly_question }}` mean the same, and keep intros written before the
interface said project working.

## The two views

- **Visual** is a [Tiptap](https://tiptap.dev/) editor
  (`src/js/backoffice/rich-editor.js`). Its toolbar offers text, headings 1–3,
  bold, italic, underline, strikethrough, left, centre and right alignment,
  bulleted and numbered lists, quotes, links, images, horizontal lines,
  tables, undo and redo.
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

- **Elements:** paragraphs, `h1`–`h3`, `strong`/`b`, `em`/`i`, `u`,
  `s`/`del`/`strike`, `ul`/`ol`/`li`, `blockquote`, `hr`, `a`, `img`, `br`,
  `table` with `tr`, `td` and `th`, and `div` (so wrappers such as the GOV.UK
  grid row survive, although the toolbar cannot make one).
- **Styled spans:** a `<span>` with a `style`, such as the
  `<span style="font-weight: 400;">` that pasting from Google Docs wraps round
  most of the text. The toolbar cannot make one, and cannot show or remove
  one either: do that in the HTML view.
- **Attributes:** `class`, `style` and `dir` on all of those; `href`, `target`
  and `rel` on links; `src`, `alt`, `title`, `width` and `height` on images;
  `border` and `role` on tables; `colspan` and `rowspan` on cells.
- **Alignment:** the toolbar centres or right-aligns a paragraph or heading
  with `style="text-align: …"`, from `@tiptap/extension-text-align`. Left is
  the default, so aligning left removes the style rather than writing
  `text-align: left`. Any other alignment, such as `justify`, is kept as part
  of the style but the toolbar does not show it.
- **Template variables** like `{{ project_title }}`, which are highlighted in
  text. A variable in an attribute, such as `href="{{ url }}"`, survives too,
  but the visual editor cannot show it or offer a way to change it: edit it in
  the HTML view.

## What makes it fall back to HTML

Anything else, because the visual editor would silently drop it. The common
causes:

- **table column widths**: a `<colgroup>`, or a `width` attribute on a cell
  (a `style` width is kept). A `<thead>`, `<tfoot>` or `<caption>` also
  forces HTML mode;
- **HTML comments**;
- **headings below level 3** (`h4`–`h6`);
- **text outside any paragraph**, including a bare Jinja tag such as
  `{% if … %}` between elements. Only `{{ variables }}` are supported in the
  intro;
- a `<span>` with a `class` or `dir` but no `style`, or a styled span
  inside another styled span (the editor would merge them into one);
- a styled span whose place the editor would change in a way that shows,
  such as `<span style="color: red;"><a>…</a></span>`: the editor puts
  the span inside the link, which turns the link red;
- an image embedded as a `data:` URL.

## What an edit in Visual mode changes

The check guarantees **no content is lost**; it does not promise the HTML comes
back byte-for-byte. The first time an author changes something in Visual mode,
the saved HTML is rewritten in the editor's own consistent form:

- the HTML is laid out one block per line, indented by nesting; text inside a
  paragraph is never rewrapped;
- `&nbsp;` may become a literal no-break space (they render the same);
- attribute order changes, and `style` values are re-spelt
  (`color: #0c7e8f` → `color: rgb(12, 126, 143)`);
- `<b>` becomes `<strong>` and `<i>` becomes `<em>`;
- attribute-less `<span>`s (common in text pasted from Google Docs) and empty
  `<strong></strong>` disappear;
- formatting may nest differently: `<strong><a>…</a></strong>` can come back as
  `<a><strong>…</strong></a>`. A styled span always goes inside a link and
  outside bold, italic, underline and strikethrough. The check only accepts
  that where it looks the same: where the span and the tag round or in it
  set the same thing (a weight, `font-style`, or a link's colour), whichever
  is inner wins;
- `<strong><span style="font-weight: 400;">…</span></strong>` loses its
  `<strong>`, which the span had already cancelled;
- **a list item's, table cell's or quote's text is wrapped in a paragraph**:
  `<li>text</li>` becomes `<li><p>text</p></li>`, and the same for `<td>`,
  `<th>` and `<blockquote>`. This is the one change that can be seen: the
  paragraph brings its own margin, so the list or table spaces out a
  little;
- a table gains a `<tbody>`, and `<del>` and `<strike>` become `<s>`.

Opening an intro in Visual mode and saving without changing anything leaves
the HTML exactly as it was.

## Tables

The Table button opens a menu: Insert table (2 × 2), Add row below, Add
column to the right, Delete row, Delete column and Delete table. The table
written to the HTML is plain — no `<colgroup>`, no sizes, no header row and
no `role` — because whether intro tables are for layout (such as logos side
by side) or for data is not yet decided, and a role or class added now would
be stored in every table made before the decision. See Q6 in the plan.

In the editor, dashed lines show where the cells are. Tab and Shift+Tab move
between cells, and leave the table from its last or first cell, so focus is
never trapped. **Alt+F10** moves from the text to the toolbar without moving
the cursor; inside a table it is the only way to reach the toolbar with the
keyboard while keeping your place.

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

### Resizing images

In Visual mode an image can be resized two ways:

- **Drag a corner.** Hovering over or selecting an image shows a handle at
  each corner. Dragging one keeps the image's shape.
- **The Image size dialog.** Select the image (click it, or move onto it
  with the arrow keys) and press the **Image size** toolbar button, or
  double-click the image. Enter a width in pixels, from 20 to 2000. The
  height follows the image's shape. **Original size** takes the size away.

Both write ordinary `width` and `height` attributes, such as
`<img src="..." alt="..." width="120" height="90">`, so the size can also be
set or removed in the HTML view.

An image is never shown wider than the page. The public page caps images at
the width of the main column and lets the height follow
(`.govuk-main-wrapper img` in `src/scss/application.scss`), so a large image
shrinks to fit a phone screen and keeps its shape. The `width` and `height`
attributes still tell the browser the image's shape before it loads, so the
page doesn't jump about while it does.

## The intro style

The intro step has an **Intro style** choice:

- **Accessible** (the default for new pages, stored as `govuk`) gives the intro
  the accessible GOV.UK look when the page is shown. At render time, each element without a class
  of its own gets one:

  | Element      | Class                                                                     |
  | ------------ | ------------------------------------------------------------------------- |
  | `h1`         | `govuk-heading-xl`                                                        |
  | `h2`         | `govuk-heading-l`                                                         |
  | `h3`         | `govuk-heading-m`                                                         |
  | `p`          | `govuk-body`                                                              |
  | `ul`         | `govuk-list govuk-list--bullet`                                           |
  | `ol`         | `govuk-list govuk-list--number`                                           |
  | `a`          | `govuk-link`                                                              |
  | `blockquote` | `govuk-inset-text`                                                        |
  | `hr`         | `govuk-section-break govuk-section-break--m govuk-section-break--visible` |

  Tables get no class (see Tables above).

  GOV.UK advises against underlining anything that isn't a link, because
  readers take it for one. The Underline button is there for intros that
  already use it.

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

## The thank-you page

The **Thank-you page** step chooses what a respondent sees after sending the
form:

- **Standard thank-you page** (`thank_you_use_default`, on for a new page):
  `templates/register/thank_you_default.html`, a short confirmation in the
  language the respondent is viewing the page in, with a link back to the
  form.
- **Your own thank-you page**: the page's `thank_you_html`, in the same
  visual editor as the intro, images and tables included. It is shown in the
  intro's style, so under the GOV.UK style a plain paragraph gets
  `govuk-body` as it would in the intro. A page has one style, so the step
  names it and links to the intro step to change it, rather than offering
  radios of its own.

Switching to the standard page keeps the page's own HTML, so an author can
try the standard page and switch back. Own HTML that is blank shows the
standard page too.

The step links to both pages, whichever is chosen: the public thank-you URL
takes `?show=own` or `?show=standard` to show that page instead of the chosen
one. The links show what is saved, not edits still in the editor. `?show=` is
honoured only for a signed-in user who can view the assembly, because own HTML
kept behind the standard page may be an unfinished draft, and is not checked
when it is saved. Anyone else gets the chosen page.

While the saved HTML is blank, the read-only step offers **Fill with starter
content**, as the form step offers its fills. It writes
`STARTER_THANK_YOU_HTML` (`src/opendlp/domain/registration_page.py`) and
switches to it. The starter is in English, whatever the page's language.

Own HTML can use three variables, and no others:

- `{{ project_title }}` and `{{ project_question }}`, as in the intro (or
  their older spellings `{{ assembly_title }}` and `{{ assembly_question }}`);
- `{{ restart_url }}`, the page's registration form, for a link to register
  someone else.

Nothing about the respondent is on offer: the thank-you page is a plain GET
after a redirect, and does not know who registered.

A broken thank-you page would show *after* the registration has been saved,
so its HTML is checked harder than the intro's. Saving own HTML with a
template syntax error or an unknown variable is refused, and so is
publishing a page that holds one. If it still fails when shown, the error is
logged and the respondent gets the standard page.

## The auto-reply email

The auto-reply email's body uses the same visual editor, offering only what
works in an email. Everything above applies, except:

- **No images.** An email that shows an image needs an absolute URL that
  stays served for as long as the email might be opened, and many clients
  block remote images anyway. Not supported yet.
- **No tables.** Unstyled tables look poor in most email clients.
- **Links must be full addresses.** A link like `/register/…` works on the
  registration page but not from an inbox, so the link dialog only accepts
  an address starting with `https://`, `http://`, `mailto:` or `tel:`, or
  one starting with a `{{ variable }}` that fills in such an address. Links
  already in the HTML are left alone, and the HTML view can still write
  anything. The page editors turn a pasted link or image on this site into a
  path, so it isn't tied to the host it was edited on; the email's editor
  doesn't, so a pasted link keeps its full address.
- **No content style.** The email is plain HTML, and no GOV.UK classes are
  added when it is sent; email clients don't have the GOV.UK stylesheet.

A body containing a table or an image opens in HTML mode, with the usual
notice, and loses nothing.

The editor lists the email's variables in a **Dynamic fields** panel beside
the body. They are spelt with dots, like `{{ project.title }}` and
`{{ respondent.first_name_or_friend }}`, and are highlighted the same way.
Emails written when the interface still said assembly use `{{ assembly.title }}`,
`{{ assembly.question }}`, `{{ assembly.first_assembly_date }}` and
`{{ assembly.first_assembly_date_text }}`; those keep working, and mean the
same as the `project` spellings below.
An email copied from the team's previous platform uses that platform's
names, such as `{{ recipient.first_name_or_friend }}` and
`{{ site.full_url }}`. Rename them: a variable OpenDLP doesn't know renders
as an empty string, and nothing warns while editing.

`project.first_event_date` is the date as `2026-11-14`.
`project.first_event_date_text` is the same date written out in the
language the respondent registered in, such as "14 November 2026" or
"2026. november 14.". The auto-reply is sent while their request is still
open, so that request's language is the one used; a test send uses the
organiser's.

`respondent.first_name` comes from a question keyed like "first name". When
there is none, it is the whole answer to a question keyed "name" or "full
name", not split into parts: splitting would guess wrong for names written
family name first, as in Hungarian. `respondent.first_name_or_friend` falls
back to the word "Friend" when there is no first name, translated into the
language the email is read in.

The auto-reply goes to the address given in the fixed email field. When that
field is not on the page, a question of type Email stands in for it, but only
if it is the page's only one: with two, there is no telling which address to
use. The answer is copied to the respondent's email address and also kept
under its own question. Respondents imported from a file are not affected.

Every email is sent with a plain-text version made from the HTML
(`src/opendlp/domain/html_to_text.py`), which reads lists, quotes and
horizontal lines as plain text would.

### Where replies go

The email is sent from the deployment's mail settings (`SMTP_FROM_EMAIL`,
`SMTP_FROM_NAME`), the same for every assembly. The step doesn't show that
address and it can't be changed per page, because the mail relay and the
sending domain's SPF, DKIM and DMARC records only vouch for that one address.
It is often a no-reply address that nobody reads.

**Reply-to** sets the email's Reply-To: a name and an email address,
both optional, stored on the page's auto-reply template. When someone replies,
their mail client uses this address instead of the sending one. A copied
page keeps it.

If the template has no reply-to address, the assembly's reply-to is used.
Nothing in the interface sets that yet; it is there for a future default for
each assembly. If neither is set, the email has no Reply-To, and the step
shows a warning. Every send records the reply-to address it used.

The reply-to's name is also put in the From name, as "The Team via OpenDLP"
(the second part is `SMTP_FROM_NAME`), so the inbox shows who the email is
from. The From address doesn't change. "via" is the convention mailing lists
such as Google Groups use for mail sent on someone's behalf, and it stops a
name that looks like an email address from passing as the real sender. It is
not translated: the email adapter that builds it doesn't know the reader's
language. With no reply-to name, the From name is `SMTP_FROM_NAME` alone.

The step warns about two more things in the email itself. Text in square
brackets with a letter in it, such as `[Your name]`, is a placeholder the
default auto-reply leaves for the organiser to replace; the warning lists the
ones still there. And an email that shows the first assembly date, in either
form, warns while the assembly has no date, as it would send a blank. Like
the reply-to warning, neither stops the page being published.

The name may not contain line breaks or other control characters: a line
break in an email header makes the send fail.

The design and its decisions are in
[docs/agent/767-registration-intro/auto-reply-plan.md](agent/767-registration-intro/auto-reply-plan.md)
and, for the reply-to,
[docs/agent/1220-reply-to/plan.md](agent/1220-reply-to/plan.md).
