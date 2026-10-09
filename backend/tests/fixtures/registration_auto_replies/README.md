# Registration auto-reply fixtures

Real registration auto-reply email bodies, for testing that the visual email
editor round-trips HTML authors actually write (see
`docs/agent/767-registration-intro/auto-reply-plan.md`, step 1).

Each file is the HTML body of an auto-reply from the team's current
(pre-OpenDLP) platform. The markup is kept exactly as it was, because the
oddities are the point: `<span style="font-weight: 400;">` wrapped round most
of the text by pasting from Google Docs, `dir="ltr"`, empty `<strong></strong>`
(one with a Google Docs `id`), `<br>` inside `<strong>`, and `&nbsp;` padding.

Only the content was changed. Organisation names, programme names, assembly
questions, places, staff names, URLs and phone numbers are made up. The phone
numbers are from Ofcom's range reserved for drama. Two of the seven emails we
were given were exact copies of others, and were dropped.

The variables are the old platform's: `{{ recipient.first_name_or_friend }}`
and `{{ site.full_url }}`. OpenDLP's auto-reply has `{{ respondent.… }}` and no
`site`, so these bodies would need their variables renamed to be sent from
OpenDLP. That doesn't matter for the round trip, which only needs a variable
to survive as text.

None has a table or an image.

| File                                   | What it exercises                                                                                                                                                 |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `google_docs_list_auto_reply.html`     | `dir` on `<p>` and `<li>`; `<p>` inside `<li>`; empty `<strong>` with an `id`; `<br>` inside `<strong>`; styled spans                                              |
| `unbolded_span_auto_reply.html`        | `<span style="font-weight: 400;">` **inside** `<strong>`, which un-bolds that text - dropping the span would change how it looks                                    |
| `plain_list_auto_reply.html`           | A list of bare-text `<li>`s next to one whose items are wrapped in styled spans                                                                                    |
| `coloured_text_auto_reply.html`        | `<span style="color: rgb(0, 0, 0);">` round `<strong>`; `style` with a colour on an `<li>`; text run on with `<br><br>` instead of paragraphs                        |
| `placeholder_template_auto_reply.html` | The team's starting template: escaped `&lt;placeholders&gt;`, empty `<strong>` at the end of a paragraph, unstyled `<li>`s                                           |
