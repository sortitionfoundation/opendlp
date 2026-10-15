# Registration intro fixtures

Real registration page intros, for testing that the visual intro editor
round-trips HTML authors actually write (see
`docs/agent/767-registration-intro/tiptap-intro-editor-plan.md`, step 2).

Each file is the inner HTML of `<div class="intro">` from a live registration
page on the team's current (pre-OpenDLP) platform. The markup is kept exactly
as it was, because the oddities are the point: `&nbsp;` padding paragraphs,
`dir="ltr"` and stray `<span>`s from pasting out of Google Docs, empty
`<strong></strong>`, inline styles, and a borderless table with a
`<colgroup>` used to lay out logos side by side.

Only the content was changed. Organisation names, programme names, assembly
questions, URLs, image and document paths, email addresses and the phone
number are made up. The phone number is from Ofcom's range reserved for drama.
The live pages' email links were Cloudflare's obfuscation markup, which is
added when the page is served and isn't part of the stored HTML. They are now
plain `mailto:` links.

| File | What it exercises |
|---|---|
| `layout_table_intro.html` | Layout table with `<colgroup>`, `style` and `border` attributes; images in cells; `dir` attributes; `<p>` inside `<li>` |
| `inline_styles_intro.html` | Two images in one paragraph, inline `style` on `<img>`, `<a>` and `<p>`; `target`/`rel` on links; a "list" made of `●` and `<br>` |
| `centred_image_intro.html` | Image centred with inline style; `<br>` and empty `<strong>` inside `<li>`; bare-text `<li>`s |
