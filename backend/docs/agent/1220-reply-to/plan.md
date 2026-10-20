# 1220 — Reply-to address for the registration auto-reply

Status: **all decisions made, ready to implement**. Questions are marked **Q1…Qn**.
Each answered one keeps its options for the record, with the decision marked ✅.

## 1. Goal

Let an assembly manager set the Reply-To address (and display name) of the auto-reply
email sent after someone registers. Set it in the auto-reply email step of the
registration editor, next to the subject and body, and store it per registration
page. The From address stays as configured (`SMTP_FROM_EMAIL` / `SMTP_FROM_NAME`).
We can't change it per assembly, because SPF/DKIM/DMARC and the relay's
`ALLOWED_SENDER_DOMAINS` tie it to our sending domain.

Out of scope: a default reply-to for each assembly (with a UI to set it), mass email,
and changing the From address or its display name.

## 2. Checking the brief against the code

| Your assumption | What the code says |
|---|---|
| "we already have reply-to in `adapters/email.py`" | ✅ Yes. `EmailAdapter.send_email(..., reply_to: str \| tuple[str, str] \| None)` (`adapters/email.py:32`). SMTP sets the `Reply-To` header (`:210`) and the console adapter logs it (`:119`). Both shapes are tested in `tests/unit/test_email_adapters.py`. **No adapter change needed.** |
| "save it in the database, on `EmailTemplate` or `RegistrationPage`" | ⚠️ **There is already a reply-to in the database, on `Assembly`.** It has `reply_to_name` and `reply_to_email` (`domain/assembly.py:57-72`, `adapters/orm.py:300-301`), plus `Assembly.set_reply_to()` with email validation. They came in with 609 (`docs/agent/history/609-templated-emails/plan.md` Q7/Q10). **But nothing in the app ever sets them**: `set_reply_to` is only called from tests, and no form, service or CLI touches the fields. So in practice every auto-reply goes out today with no Reply-To, unless someone has set the columns by hand in SQL. |
| "use it when we send the email in `email_send_service.py`" | ✅ The plumbing exists. `_reply_to(assembly)` (`email_send_service.py:36`) builds the value and both send paths use it: `_build_and_send` (the real auto-reply) and `prepare_test_auto_reply` (the "Send test email" button). **We change where the value comes from.** We don't need to plumb it through. |
| "configure it in the auto-reply step, where subject and body are" | ✅ `templates/backoffice/registration/_step_email.html`. Save goes through `_handle_email_action_save` → `update_email_template(subject=, body_html=)` (`backoffice_registration.py:719`). |
| "for now per registration page" | ✅ An `EmailTemplate` is assembly-scoped in the schema but **in practice 1:1 with a page**. "Set up auto-reply email" always creates a new template and assigns it to one page (`_create_and_assign_default_template`). Copying a page deep-copies its template (`_copy_auto_reply_template`, `registration_page_service.py:393`) so the two "never share mutable content". So "per template" and "per page" mean the same thing today. |

So the "later round" (a default reply-to for each assembly) is half-built already. The
fields, the validation and the send-path fallback exist. Only the UI is missing.

## 3. Where to store it — `EmailTemplate` vs `RegistrationPage` (Q1)

✅ **Decision: Option A, on `EmailTemplate`.**

**Option A — on `EmailTemplate`** (`reply_to_name`, `reply_to_email` columns on `email_templates`)

- \+ It's saved by the same form, the same POST and the same service call
  (`update_email_template`) as subject and body. One aggregate is updated in one
  place. This is the smallest change.
- \+ Page copy already deep-copies the template, so we add two lines there and copying
  keeps working.
- \+ Future templated emails (mass email, confirmation-call follow-ups) are
  `EmailTemplate`s with no registration page. A reply-to on the template carries over
  to them. A reply-to on the page wouldn't.
- \+ `RespondentEmailSendRecord` already links to the template, so "what reply-to did
  this send use" can be read from the record (see Q6).
- − A template mixes content (subject, body) with sending settings (reply-to). If
  templates are later shared between several pages or emails, the reply-to goes
  wherever the template goes. That's what you'd want for a shared template anyway.

**Option B — on `RegistrationPage`** (not chosen)

- \+ Literally "per page". The page is the sending context.
- − The email-step save then has to update two aggregates (page and template) in one
  UoW, or make two calls. That means more service code and more ways for half a save
  to fail.
- − Mass emails in future have no page, so they'd need a different store, which
  means a second reply-to concept.
- − The page domain object is already busy (slugs, status, activity, language).

## 4. Resolving the reply-to at send time (Q2)

✅ **Decision: Q2a, keep the assembly fallback.** At send time the reply-to is:

1. the template's reply-to, if its `reply_to_email` is set
2. else the assembly's reply-to, if set (today this is always empty, since there's no UI)
3. else no Reply-To header

Name and email resolve **together**. We never take the name from the template and the
email from the assembly.

Doing this costs one `if`. It keeps the existing `Assembly` fields meaningful. When
the assembly-default round happens it's only UI work. It also covers any assemblies
where someone has set the columns by hand. (*Chewie: optionally run
`SELECT count(*) FROM assemblies WHERE reply_to_email <> ''` on prod to see whether
any exist. It doesn't change the plan.*)

Options not chosen: Q2b (template only, drop the assembly fields), Q2c (template only,
leave the assembly fields unused).

## 5. Field details

### Q3 — store a display name as well as the address?

✅ **Decision: yes.** Store `reply_to_name` as well as `reply_to_email`. This matches
`Assembly`, and the adapter already accepts `(name, email)`. The name is optional, and
we use it only when there's an email.

### Validation

- `reply_to_email`: may be empty. If set, it must pass `validate_email()`
  (`domain/validators.py:148`), the same check `Assembly` uses.
- `reply_to_name`: may be empty. ✅ **Reject control characters**, as defined in the
  sub-bullet below. We need this because a newline in the name makes the stdlib raise
  `HeaderParseError("header value appears to contain an embedded header")` when the
  message is serialised. The SMTP adapter catches that and returns `False`, so every
  auto-reply for the page would fail silently, with only a `FAILED` send record and a
  log line. It's not an injection hole, but it's a nasty way to fail, and catching it
  at save time is cheap.
  - ✅ Decided: reject only `Cc` (C0/C1 controls, including CR/LF/tab) plus the line
    and paragraph separators (`U+2028`, `U+2029`). We don't reject all of `C*`,
    because `Cf` includes zero-width joiners, which some scripts and emoji use.
- Cap both fields at 255 characters (the column width).
- `EmailTemplate` reports problems as a list (`validation_problems()` →
  `EmailTemplateInvalid`, flashed one by one). It doesn't raise from the constructor
  the way `Assembly` does. The new checks go into `validation_problems()` so they
  follow the template's own pattern.
- Strip surrounding whitespace from both fields on save, the same as the subject.

### Q4 — what should a fresh template's reply-to be?

✅ **Decision: (a) blank.** When "Set up auto-reply email" creates the template, both
fields are `""`. This is predictable, adds no personal data unless someone types it,
and Q5's warning nudges them to fill it in.

Options not chosen: (b) the signed-in manager's own email, (c) the assembly's
reply-to.

### Q5 — warn when no reply-to is set?

✅ **Decision: (a), a WARNING in `auto_reply_readiness_problems`.** It appears in the
existing banner on the email step. It's a warning, not an error, and it never blocks
publishing.

- The warning fires when the reply-to that would be used at send time is empty, which
  means after the assembly fallback. So it uses the same resolution as §4. If an
  assembly has a hand-set reply-to, there's no warning.
- Wording: the default From is a no-reply address in most deployments, but that's a
  deployment fact, not a code fact. So the message hedges:
  *"Replies to the auto-reply will go to the address it is sent from, which may not
  be monitored. Set where replies go so registrants can reach you."*
- Signature change: `auto_reply_readiness_problems` currently takes only
  `assembly_id` and looks at the email field definition. The new check needs the
  page's template, so it gains a `page_id` (or the template). Update both callers:
  the email-step view (`backoffice_registration.py`, which already knows the page)
  and the logging loop in `assign_auto_reply_template`. Both problems can show at
  once (for example, optional email *and* no reply-to), so the function returns them
  all, not just the first one.

### Q6 — the send record's `from_email` column is misnamed

✅ **Decision: (a), rename the column to `reply_to_email`**, and store the email part of
the reply-to that was actually used (`""` when there was none).

`_build_and_send` currently writes `from_email=assembly.reply_to_email` into
`RespondentEmailSendRecord` (`email_send_service.py:69`). That's the reply-to, not the
From. Nothing reads the column yet (no template, route or service), so renaming it now
is cheap. The rename covers the ORM column, the domain attribute and its constructor
argument, `create_detached_copy`, and every test that builds a record.

### Q7 — show the From address on the email step?

✅ **Decision: (a), show it read-only.** The card shows a line like *"Sent from:
OpenDLP &lt;noreply@example.org&gt;. This can't be changed."* above the "Replies go to"
fields.

- The blueprint reads `SMTPEmailCfg.from_env()` (`config.py:181`), or the equivalent
  already loaded at bootstrap, and passes `from_name` / `from_email` into the template
  context. The adapter doesn't change.
- If `from_email` is empty (for example the console adapter in dev), leave the line
  out rather than showing an empty address.
- The rendered `name <email>` is display text. Format it in the template, escaped as
  usual, not with `formataddr`, so a name with a comma isn't shown wrapped in quotes.

## 6. Change list

**Domain** — `domain/email_template.py`

- Add `reply_to_name: str = ""` and `reply_to_email: str = ""` to `__init__`,
  `update()` (keeping the existing `None`-means-unchanged pattern) and
  `create_detached_copy()`.
- Add a `reply_to()` method returning `(name, email)` / `email` / `None`, the same shape
  as today's `_reply_to(assembly)`. Give `Assembly` the same method, so
  `email_send_service._reply_to` becomes "template's, else assembly's", and both halves
  can be unit-tested on their own.
- Add the new checks to `validation_problems()` (§5 Validation).
- ✅ **Wrap all of `validation_problems()`'s messages for translation**, the existing
  three ("needs a name", "needs a subject", "body is empty") as well as the new ones.
  They're flashed straight to the user. Use `gettext as _` from
  `opendlp.translations`, as `domain/registration_page.py` already does. It works
  with or without a request context. Check whether `template_syntax_problems` (in
  `domain/email_template_render.py`) returns English text that ends up in the same
  list. If so, wrap its fixed wording too, but leave Jinja's own error text in it
  untranslated.
- `email_template_service._validate` adds its own English problem ("The email body
  must be at most %(max)s bytes"). Wrap that too, since it lands in the same flash
  list.
- `RespondentEmailSendRecord`: rename `from_email` → `reply_to_email` (Q6).

**ORM / migration**

- `adapters/orm.py`: two `String(255), nullable=False, server_default=""` columns on
  `email_templates`, the same as `assemblies`. Rename
  `respondent_email_send_records.from_email` → `reply_to_email`.
- `uv run alembic revision --autogenerate -m "add reply-to to email templates"`.
  Autogenerate will see the rename as a drop and an add, so hand-edit it into
  `op.alter_column(..., new_column_name=...)` in both directions, and check the
  downgrade.
- No data migration. Existing templates get `""`, which falls back to the assembly
  (Q2a). That's what happens today.
- No change to `_delete_all_test_data()`, because there's no new table.

**Service layer**

- `email_template_service.update_email_template` / `create_email_template`: accept
  `reply_to_name` and `reply_to_email`.
- `email_send_service._reply_to(template, assembly)`: resolve template → assembly
  (§4). Use it in both `_build_and_send` and `prepare_test_auto_reply`, so the test
  send carries the real header.
- `_build_and_send`: record the reply-to email that was used (Q6).
- `registration_page_service._copy_auto_reply_template`: copy both fields.
- `email_template_service.auto_reply_readiness_problems`: the new warning and the
  `page_id` parameter (Q5).

**Entrypoints**

- `backoffice_registration._handle_email_action_save`: read `template_reply_to_name`
  and `template_reply_to_email` from the form, strip them, and pass them through.
  `EmailTemplateInvalid` is already caught and flashed.
- The email-step view: pass the page to `auto_reply_readiness_problems` (Q5), and the
  From name and address to the template (Q7).
- ✅ **Q8: validation errors lose unsaved edits. Accepted for this round.** This
  already happens today: on a validation failure we redirect to edit mode, and the
  typed values are lost, including the subject and body. A typo in the reply-to
  address will now also throw away an unsaved body edit. We accept that for now. It's
  written up in
  [`future_work/registration_editor_loses_edits_on_error.md`](../future_work/registration_editor_loses_edits_on_error.md). The input's `type="email"` lets the browser catch the
  common typo before submit, and the server check stays as the backstop. Not chosen:
  fixing it this round by re-rendering instead of redirecting.
- `dev.py` service-docs handlers (`_serialise_email_template`, create and update):
  add the fields so the service docs page stays truthful. `templates/backoffice/
  service_docs/_emails.html` gets inputs for them.

**Template** — `_step_email.html`

- Load the `ui-components` skill before touching it.
- In the card, above the subject:
  - The read-only "Sent from" line (Q7).
  - ✅ A group headed **"Replies go to"** (Q9). Use a `<fieldset>` with that legend, so
    a screen reader announces the context for both inputs. It holds two inputs:
    **"Name"** (optional) and **"Email address"** (`type="email"`, optional). A hint
    on the fieldset says something like *"When registrants reply to the auto-reply,
    their email goes here."* The inputs use the same readonly/edit treatment as the
    subject (`common_input_attrs`).
- Check `docs/language.md` and add the term if it fits the glossary. Then run the
  `translate-catalogues` skill.

**Docs**

- A short paragraph wherever the auto-reply step is documented (probably
  `docs/registration-intro-editor.md`, which already covers the auto-reply editor). It
  says what "Replies go to" does, that the assembly's reply-to is the fallback, and
  why the From address is fixed.
- ✅ `docs/personal-data.md`: one line. The reply-to name and address are free text
  typed by staff and may be a staff member's personal address. They aren't tied to a
  `User` row, so deleting a user won't blank them. They're the same class of data as
  names typed into an email body.

## 7. Tests

- **Unit**
  - `EmailTemplate`: defaults to empty; `update` sets and keeps values; validation
    rejects a bad email, a name with CR/LF, a name with another control character,
    and over-length values, and accepts an empty pair; `create_detached_copy` keeps
    the fields; `reply_to()` shape (tuple, bare email, `None`, and a name with no
    email gives `None`).
  - `Assembly.reply_to()`: the same shape tests.
  - Validation messages are translated (patch or run with a non-English locale, the
    same way the existing translation tests do, if there are any for domain
    messages).
  - `email_send_service`: template reply-to wins over the assembly's; falls back to
    the assembly when the template is blank; `None` when both are blank; the send
    record stores the used reply-to email; the test send uses the template's
    reply-to. Extend `tests/unit/test_email_send_service.py` and
    `test_registration_auto_reply_service.py`.
  - Readiness: the warning appears when nothing resolves; it doesn't appear when the
    template or assembly has one; it appears together with the email-field warning.
  - Page copy copies the reply-to.
- **Integration**: the ORM round trip for the new template columns and the renamed
  send-record column, next to
  `tests/integration/test_email_send_service_transactions.py`. The migration runs up
  and down cleanly.
- **Component**: `tests/component/test_backoffice_registration_email.py`. Saving the
  form persists both fields; an invalid address flashes the problem and saves
  nothing; view mode shows the values read-only; the "Sent from" line renders when
  configured and is absent when it isn't; the readiness warning shows when blank.
  Add the dev handlers to `test_dev_email_handlers.py`.
- **E2E**: `tests/e2e/test_registration_auto_reply.py`. Register through a page
  whose template has a reply-to and assert the adapter received it.
- ✅ **BDD, happy path only.** `features/backoffice-registration-email-editor.feature`
  already has *"Formatting the auto-reply email from the toolbar and saving it"*. It
  opens the editor, edits, saves, and checks the result (steps in
  `tests/bdd/test_backoffice.py:2448+`). Extend that scenario: before saving, fill in
  the "Replies go to" name and email address; after saving, check that the read-only
  view shows them. If adding these steps muddies the scenario's purpose (it's about
  toolbar formatting), add a sibling scenario in the same feature that reuses its
  Given/When steps instead. I'll decide when I'm in the code.

## 8. Questions, collected

- **Q1** ✅ Store on `EmailTemplate`.
- **Q2** ✅ Template, else assembly, else none (Q2a).
- **Q3** ✅ Store a display name too.
- **Q4** ✅ A new template starts blank.
- **Q5** ✅ Readiness warning when nothing resolves, worded "may not be monitored".
- **Q6** ✅ Rename `respondent_email_send_records.from_email` → `reply_to_email`.
- **Q7** ✅ Show the fixed From address read-only.
- **Q8** ✅ Accept for now that a validation error loses unsaved edits (existing
  behaviour), and log an issue.
- **Q9** ✅ "Replies go to", as a fieldset with Name and Email address inputs.
- **Q10** ✅ One line in `docs/personal-data.md`.
- **Q11** ✅ BDD happy path, extending the existing save scenario.
- ✅ Control-character rule (§5): `Cc` plus U+2028/U+2029.

## 9. Unrelated things I noticed

- ✅ *Now in scope:* the validation messages flashed by `EmailTemplate` were never
  translatable. They're in the §6 domain changes.
- The `Assembly.reply_to_*` fields have no UI at all. That's left for the
  assembly-default round.
