# 1229 — Edit the thank-you page

Status: draft plan, third round — all questions resolved, ready for a final
read before implementing.

## Implementation phases

- [x] P1. Domain: starter, flag, variables, validation, rendering, readiness
- [x] P2. ORM column, migration, test cleanup
- [x] P3. Service layer: seeding, duplicate, save with flag, fill, render with fallback
- [x] P4. Public route and the standard page's restart link
- [ ] P5. Backoffice step: template, stepper, saving
- [x] P6. JS round-trip test against a fixture of the starter
- [ ] P7. E2E journey and BDD scenario
- [ ] P8. Docs and translation catalogues

## Goal

Give authors a way to set what a respondent sees after sending the form.
`RegistrationPage.thank_you_html` already exists, is seeded, copied and served;
it has no editor. Add a sixth step, **Thank-you page**, to the registration
editor, between **Form** and **Auto-reply email**. On it the author chooses
between the standard, translated thank-you page and their own HTML, edited in
the visual editor the intro step uses.

## What exists today

- **Domain** — `RegistrationPage.thank_you_html` (`domain/registration_page.py:201`),
  `update_thank_you_html()` (bumps `updated_at`), and `DEFAULT_THANK_YOU_HTML`
  (`registration_page.py:33`): a GOV.UK confirmation panel inside the same
  grid wrapper the starter intro uses. English only.
- **Service** — `update_thank_you_html()` (`registration_page_service.py:640`)
  checks permission, enforces `REGISTRATION_THANK_YOU_HTML_MAX_BYTES` (50 KB
  default), records an `EDIT` activity, and is a no-op when nothing changed.
  Both create paths seed `DEFAULT_THANK_YOU_HTML`; `duplicate_registration_page`
  copies the source's.
- **Public route** — `registration.thank_you` (`registration.py:422`) renders
  `thank_you_html` verbatim (`render_thank_you_html`) into
  `register/thank_you.html`. If it is blank it falls back to
  `register/thank_you_default.html`, which is translated *and* adds a
  "start a new registration" link back to the referrer. Its language is the
  visitor's (`get_locale`: `?lang=`, then the browser), not the page's
  `language` field — the same as every other public page.
- **Backoffice view** — `view_registration_page` already passes
  `thank_you_html` to the template; nothing uses it.
- **Editor steps** — `_SECTIONS = ("page", "intro", "form", "email", "preview")`
  in `backoffice_registration.py:417`. Each step is a
  `templates/backoffice/registration/_step_<key>.html` included from
  `assembly_registration.html`, which also builds the stepper list. Name/URLs,
  intro and form all post to the one `save_assembly_registration` route, which
  works out what to save from which fields are present
  (`_apply_posted_html`); the email step has its own route.
- **Intro rendering** — `RegistrationPageHtml.render` runs the intro through
  `_SANDBOX_ENV` (sandboxed, autoescaping, `StrictUndefined`), then
  `apply_default_govuk_classes` under the GOV.UK content style. A syntax error
  is caught at publish by `_intro_problems`; an unknown variable is not caught
  until the page is shown.

### The current default opens as HTML

`DEFAULT_THANK_YOU_HTML` fails the visual editor's `roundTripsCleanly`: the panel
body is `<div class="govuk-panel__body">text</div>`, and the editor wraps text
directly inside a div in a `<p>`. Using `<p class="govuk-panel__body">` instead
round-trips cleanly (checked with the editor's schema). Check it renders
the same in the panel (a `<p>` may bring a margin the div didn't).

## Decisions

**D1. Name and key.** Label `_("Thank-you page")`, section key `thank-you`
(matching the public URL `/register/<slug>/thank-you`).

**D2. Standard or own, as a flag.** A new boolean on `RegistrationPage`,
`thank_you_use_default`. When it is true the public route shows the
standard translated page (`thank_you_default.html`) and ignores
`thank_you_html`. When it is false it shows the author's HTML. Turning the flag
on does **not** clear the saved HTML, so an author can switch to the standard
page, try it in a few languages, and switch back to what they wrote.

- New pages: `thank_you_use_default=True`, `thank_you_html=""`.
- Duplicated pages copy both fields.
- Own HTML that is blank still falls back to the standard page — a safety net,
  so the public never sees an empty page.
- The flag change records an `EDIT` activity ("Switched to the standard
  thank-you page" / "Switched to its own thank-you page").

**D3. Starter content, not a default.** "Default" now means the standard,
translated page, so `DEFAULT_THANK_YOU_HTML` is renamed
`STARTER_THANK_YOU_HTML`. It is no longer seeded; the step's
**Fill with starter content** button (D6) puts it in the editor, in English, to
be edited. It uses the `<p>` panel body so it opens in Visual, and gains the
restart link (D8). The link stays: invitations usually go to households, and
more than one person in a household registering is fine.

```html
<div class="govuk-grid-row">
<div class="govuk-grid-column-two-thirds" style="float: none; margin: 0 auto;">
<div class="govuk-panel govuk-panel--confirmation">
<h1 class="govuk-panel__title">Thank you for registering</h1>
<p class="govuk-panel__body">Your registration has been received</p>
</div>
<p class="govuk-body">We'll be in touch.</p>
<p class="govuk-body"><a class="govuk-link" href="{{ restart_url }}">Start a new registration</a></p>
</div>
</div>
```

**D4. Existing pages (migration).** Every page so far holds the old
`DEFAULT_THANK_YOU_HTML` byte for byte, since nobody could edit it. One Alembic
migration:

- adds `thank_you_use_default BOOLEAN NOT NULL`, server default `true`;
- sets it `false` on any row whose `thank_you_html` is neither blank nor the
  old default exactly (expected: none, but someone may have set it in SQL);
- blanks `thank_you_html` where it equals the old default, which the migration
  spells out in full as migrations should, so that switching to own HTML later
  starts from an empty editor and the starter button, not from HTML that opens
  in the HTML view.

Downgrade puts the old default back into rows with the flag on and blank HTML,
then drops the column. What the public sees on those pages barely changes: the
same English words, now translated, plus the restart link.

**D5. Content style follows the intro.** With own HTML, the thank-you is shown
with `apply_default_govuk_classes` when the page's intro style is GOV.UK, and
the editor previews in that style. One style per page, no second radio.

**D6. The step.** New `templates/backoffice/registration/_step_thank_you.html`,
modelled on `_step_intro.html`: Edit/Cancel/Save header, Assets panel in edit
mode (image URLs are slug-free, so they work on the thank-you page), sticky
wizard footer.

- Hint under the heading: `_("Choose what respondents see after they send the form.")`.
- A radio group, `thank_you_use_default`: **Standard thank-you page** — hint
  `_("A short thank-you, in the language the respondent is viewing the page in.")`
  — and **Your own thank-you page**. Read-only outside edit mode, like the
  intro style radios.
- The editor (`thank_you_html`, `code_editor`, `rich_editor`, images and
  tables on, `rich_editor_style` from the intro style,
  `rich_editor_variable_example="{{ assembly_title }}"`) shows only while
  **Your own** is chosen — Alpine `x-show` off the radio, CSP-safe, so switching
  back and forth before saving keeps what is in the editor. Without JavaScript
  both show.
- **Fill with starter content** button, offered only while the saved
  `thank_you_html` is blank — the same rule as the form step's fill buttons
  (`_step_form.html:76`): outside edit mode, not on a CLOSED page, under the
  radios so it shows whichever option is chosen. It posts `fill_thank_you=1`;
  a new service function `fill_empty_thank_you_html` writes
  `STARTER_THANK_YOU_HTML` and turns the flag off, so the starter is what the
  public sees. Like `fill_empty_registration_form_html` it refuses
  (`ValueError`, "The thank-you page already has HTML, so it was left as it
  is") when HTML is already saved, since then the request is stale and a fill
  would lose someone's work. It lands back on the step, read-only, as the form
  fill does; the author clicks Edit to change the words. No confirmation
  dialog is needed, since there is nothing to lose.
- A **View the thank-you page** link, new tab, to `/register/<slug>/thank-you`.
  The route does not check status, so it works for TEST pages. Shows the saved
  state, not unsaved edits. To be refined after team feedback.

**D7. Language.** The starter is English; the author translates it, as they do
the intro. Seeding a translated starter is a possible follow-up.

**D8. Template variables.** Own thank-you HTML is rendered through
`_SANDBOX_ENV`, with these variables and nothing else:

| Variable | Value |
| --- | --- |
| `{{ assembly_title }}` | the assembly's title |
| `{{ assembly_question }}` | the assembly's question |
| `{{ restart_url }}` | the page's public form URL, `registration_url(page.url_slug)` |

Not the form helpers (`csrf_form_element`, `value()` …): there is no form here.
Not anything about the respondent: the thank-you page is a plain GET after a
redirect and does not know who just registered. Carrying that across would
mean putting personal data in the session — out of scope, and a GDPR
conversation of its own.

A broken thank-you is worse than a broken intro: it is shown *after* the
registration has been saved. So:

- **On save**, own HTML is parsed; a syntax error or a variable outside the
  table is refused with a `ValueError` naming it, and the author lands back in
  edit mode with the text intact. (The flash goes through `_()`; the message is
  curated, not `str(e)` of a Jinja error.)
- **At publish**, the same check joins `RegistrationPage.readiness_problems`,
  for HTML saved before this check existed or set by other means.
- **When shown**, a render failure is logged and the respondent gets the
  standard page — never a 500 after a successful registration.

The domain gets a `RegistrationPage.render_thank_you(...)` (or a small
`ThankYouContext` alongside `RenderContext`) so the sandbox stays in one module;
`render_thank_you_html` in the service layer loads the assembly and the HTML
source for the content style and calls it.

**D9. The standard page's restart link** uses `restart_url` too, not
`request.referrer`, so it always shows and points at the canonical form URL.
`thank_you_default.html` gets `restart_url` from the route; the `{% if referer %}`
goes. A query string on the referrer (such as `?source=poster`) is no longer
carried back; accepted in review. The link's text ("Please click here…")
stays as it is for now.

## Saving

- `_SECTIONS` becomes `("page", "intro", "form", "thank-you", "email", "preview")`,
  so `save_and_next` and Back/Next work by position. The form step's Next and
  the email step's Back change to point at the new step.
- `_apply_posted_html` gains a branch: when `thank_you_use_default` or
  `thank_you_html` is in the form, call a service function
  `update_thank_you(uow, user_id, page_id, *, use_default, thank_you_html)`
  (the existing `update_thank_you_html` grows the flag, or is wrapped by it).
  Validation (D8) runs only when own HTML is chosen: an author can switch to
  the standard page even with broken HTML saved.
- The docstrings that list the step order (`save_assembly_registration`,
  `_post_action_section`) get the new step; the "all five steps" comment in
  `assembly_registration.html` becomes six.

## Other edits

- `register/thank_you_default.html`: restart link from `restart_url` (D9).
- `docs/registration-intro-editor.md`: a "The thank-you page" section, as it has
  for the auto-reply — same editor, its variables, the standard/own switch,
  and what happens when the HTML breaks.
- Translatable strings → run the `translate-catalogues` skill.

## Tests

- **Unit, domain** — `render_thank_you` fills the three variables and escapes
  them; refuses an unknown variable and a syntax error; applies GOV.UK classes
  only under the GOV.UK style; readiness reports a broken own thank-you and
  ignores one when the flag is on. The starter contains the panel, a `<p>`
  body and `{{ restart_url }}`.
- **Unit, service** — `fill_empty_thank_you_html` fills a blank page and
  turns the flag off, and refuses one with HTML; the flag and HTML save together; switching to the
  standard page keeps the HTML; the activity text for each change; invalid HTML
  refused only when own HTML is chosen; create seeds flag on and blank HTML;
  duplicate copies both.
- **Migration** — old default → flag on, HTML blank; edited HTML → flag off,
  HTML kept; blank → flag on; downgrade restores the old default.
- **JS (vitest)** — the starter round-trips cleanly, `href="{{ restart_url }}"`
  included, read from a fixture that a Python test checks matches
  `STARTER_THANK_YOU_HTML`, so the two can't drift.
- **Component, view** — `?section=thank-you` renders `reg-steps-panel-thank-you`;
  read-only without `edit=1`; a CLOSED page stays read-only; the stepper lists
  six steps in order; the starter button shows only while the saved HTML is
  blank, outside edit mode, and not on a CLOSED page.
- **Component, save** — posting the flag and HTML from `step=thank-you` saves
  both and lands on `?section=thank-you`; `save_and_next` lands on `email`; the
  form step's `save_and_next` lands on `thank-you`; over-size and invalid HTML
  flash and land in edit mode; `fill_thank_you` fills the starter and turns the
  flag off; `fill_thank_you` over saved HTML is refused and leaves it alone; a
  lifecycle post leaves both alone.
- **Component, public route** — flag on → standard page, translated (`?lang=`),
  with the restart link to the form URL even with no referrer;
  own HTML → rendered with variables; own but blank → standard page; a render
  failure → standard page and a logged error.
- **E2E** — `test_registration_stepper_journey.py` gains the step between form
  and email, sets own HTML using `{{ assembly_title }}`, then fetches the public
  thank-you page and sees the title.
- **BDD** — fill with starter content, edit a sentence in the visual editor
  (which proves the starter opens in Visual), save, send the public form, see
  the edited thank-you and follow its restart link back to the form.

## Questions

All resolved. First round: Q1 → D1; Q2 and Q3 → D2–D4; Q4 → D5; Q5 → D7;
Q6 → D6 (link on the step); Q7 and Q8 → D8. Second round: Q9 → D9 (switch to
`restart_url`); Q10 → D6 (starter button only while blank, as on the form
step); Q11 → D3 (keep the restart link in the starter).

## Out of scope

- Respondent-specific variables on the thank-you page (D8).
- A translated starter (D7).
- The standard page's link text (D9).
- Any change to the email step.
