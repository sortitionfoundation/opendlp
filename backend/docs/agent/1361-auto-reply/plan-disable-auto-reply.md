# 1361 — Let a registration page turn its auto-reply off

Status: **in progress**, on `1361-disable-auto-reply` (branched
from `1361-auto-reply-fixes`). Questions are marked **Q1…Q5**; all are
answered. Each keeps its options for the record, with the decision marked ✅.

## 1. Goal

An assembly manager can switch a registration page's auto-reply email off, and
back on, from the auto-reply step of the registration editor. When it is off,
nobody who registers through that page gets the email. The template is kept, so
turning it back on sends the same email as before.

Out of scope: more than one template per page, scheduling the auto-reply, and
an assembly-wide default (on or off) for new pages.

## 2. How it works today

| What | Where |
|---|---|
| The checkbox is `checked=true, disabled=true`, a fixed "always on" indicator. | `templates/backoffice/registration/_step_email.html`, card header |
| Why: `bf742eaa` removed the old toggle. That toggle worked by unassigning the template (`auto_reply_email_template_id = NULL`) and sent the association back and forth in a hidden form field. The commit said a real enable/disable should be a proper service-layer feature if anyone ever needs one. | `git show bf742eaa` |
| A page sends an auto-reply exactly when `page.auto_reply_email_template_id` is set. | `send_registration_auto_reply`, `service_layer/email_send_service.py:277` |
| New pages get the default template assigned when they are created. Saving the step re-assigns a template to old pages that lost theirs under the old toggle. | `_create_and_assign_default_template`, `backoffice_registration.py:727` |
| Readiness problems (no email field: ERROR; optional email, no reply-to, `[placeholders]`, missing first date: WARNING) show above the step. | `auto_reply_readiness_problems`, `service_layer/email_template_service.py:129` |
| Copying a page deep-copies its template. | `_copy_auto_reply_template`, `registration_page_service.py:394` |
| The blueprint docstring and the template comment both say there is deliberately no enable/disable. | `save_assembly_registration_email`, `_step_email.html` |
| A component test pins the checkbox as checked, disabled and read-only. | `test_checkbox_renders_checked_and_disabled_with_no_toggle_form`, `tests/component/test_backoffice_registration_email.py:267` |

We must **not** bring back "unassigned template means off". It mixes up "no
template" with "turned off", the self-heal on save would quietly switch the
auto-reply back on, and deleting a template would also look like turning it off.

## 3. Where the flag lives (Q1)

✅ **Decision: Option A, on `RegistrationPage`.**

**Option A: `RegistrationPage.auto_reply_enabled`**

- \+ Whether a page sends an email is about the page. The template is the
  content.
- \+ The send path already loads the page first. One check, before the template
  is loaded.
- \+ Copying a page copies its fields, so the copy keeps the setting for free.
- \+ Stays correct if a page can one day choose between templates.
- − Saving the step then touches two aggregates (page and template). Both happen
  in the one `with uow:` the route already opens, so it is still one commit.

**Option B: `EmailTemplate.enabled`**

- \+ Saved by the same `update_email_template` call as subject and reply-to.
- − Templates belong to the assembly, and "enabled" means nothing for any other
  use of a template (later: confirmation and reminder emails).
- − A page with no template would need its own rule.

## 4. Schema and migration

Add `auto_reply_enabled BOOLEAN NOT NULL DEFAULT true` to `registration_pages`,
with `server_default=text("true")` on the ORM column, as `thank_you_use_default`
does (`adapters/orm.py`, migration `a78dcf4c5649`).

- **Safe with zero downtime.** A new NOT NULL column with a server default, and
  no constraint. The previous release ignores the column, and every existing row
  becomes `true`, which is what every page does today. No data migration, and no
  `update-with-downtime` needed.
- Create it with `uv run alembic revision --autogenerate -m "add auto_reply_enabled to registration_pages"`.
- No new table, so `_delete_all_test_data()` and the BDD clean-up need no change.

## 5. Domain

In `domain/registration_page.py`:

- Constructor argument `auto_reply_enabled: bool = True`, kept in
  `create_detached_copy`.
- `set_auto_reply_enabled(enabled: bool) -> None` bumps `updated_at`, as
  `set_auto_reply_template` does.
- `sends_auto_reply() -> bool`: `self.auto_reply_enabled and
  self.auto_reply_email_template_id is not None`. This is the single answer to
  "will a registrant get an email", for the send path and the readiness check.

## 6. Service layer

- **New** `set_auto_reply_enabled(uow, user_id, page_id, enabled)` in
  `registration_page_service.py`:
  - checks permission with `_load_manageable_page`, like `set_auto_reply_template`;
  - does nothing if the value is unchanged;
  - otherwise sets it and records it with `page.record_edit` (**Q4**);
  - returns a detached copy.
- `send_registration_auto_reply`: check `page.sends_auto_reply()` instead of
  only the template id. When it is off, return `None` and log at info level with
  the page id only (no PII), so a support question ("why did nobody get an
  email?") can be answered from the logs.
- `auto_reply_readiness_problems(..., page_id=...)`: when that page's auto-reply
  is off, return `[]` straight away, before any check runs. That covers every
  problem, the page-level ERROR ("no email field") included, not just the
  template ones: none of them matter for an email we are choosing not to send.
  The assembly-level call without a `page_id` is unchanged. See §7, "When it is
  off".
- `duplicate_registration_page` passes `auto_reply_enabled=source.auto_reply_enabled`.
- `prepare_test_auto_reply` is unchanged. Sending a test while the auto-reply is
  off still works (**Q3**).

## 7. The auto-reply step

### How the checkbox saves (Q2)

✅ **Decision: Option A, part of edit mode.**

**Option A: part of edit mode**. Outside edit mode the checkbox is
a read-only indicator showing the stored value (as now, but no longer always
ticked). In edit mode it is a normal checkbox, saved by the card's Save button
with everything else.

- \+ Works like every other control on the step and on the other steps
  (`thank_you_use_default` and the intro style are both edit-mode controls).
- \+ No new endpoint and no Alpine state. The unsaved-changes guard
  (`markEditDirty`) covers it already.
- − Turning it off takes three clicks (Edit, untick, Save).

**Option B: an immediate toggle outside edit mode**, as its own small form
posting `action=enable` / `action=disable`.

- \+ One click.
- − A second way of saving on a step that otherwise has one. It also has to
  behave sensibly while you are in edit mode with unsaved changes.

### Detail for Option A

- An unticked checkbox is not submitted, so "field missing" has to mean "off".
  That would turn off any page whose save POST lacks the field: a tab opened
  before the deploy, or a test posting only subject and body. Add a hidden
  `auto_reply_enabled_shown=1` field. Only change the flag when that field is
  present; otherwise leave it as it is.
- `_handle_email_action_save` calls `set_auto_reply_enabled` inside the `with
  uow:` it already opens for `update_email_template`. One unit of work, one
  commit.
- Subject and body stay required when the auto-reply is off, so turning it back
  on never finds an invalid template.
- Remove the "deliberately no enable/disable" text from the blueprint docstring
  and the template comment, as it will no longer be true.

### When it is off

✅ **Decision: when the auto-reply is off, the step shows no other messages.**
Only one notice appears, where the readiness banner would be:
"The auto-reply is off. People who register through this page will not get an
email."

What that suppresses, and how:

| Message | Today | When off |
|---|---|---|
| ⛔ "Auto-reply cannot be sent": the page collects no email | readiness ERROR | gone: readiness returns `[]` (§6) |
| ⚠️ Email is optional, so some registrants get nothing | readiness WARNING | gone, same way |
| ⚠️ Replies go to the sending address; `[placeholders]` left; first event date missing | readiness warnings | gone, same way |
| The test-send box's "Registrants still won't receive the auto-reply until the problem above is fixed" | shown when there is a readiness ERROR | gone: it keys off the same list |

Suppressing in the service rather than the template means nothing else that
asks "is this page's auto-reply ready?" sees stale problems, and there is one
place to test it. The template fields stay visible (view mode is already
read-only), so you can see what will go out when it is turned on again.

### Q3: test send while off

✅ **Decision: keep it.** It is harmless, and it is how you would check the
email before turning it back on. The alternative is to hide the section while
the auto-reply is off.

### Q4: activity log

Review note: we don't have the activity log yet, so leave a TODO comment, or
start `docs/agent/future_work/activity_log_notes.md` for when we do.

What the code has: there is no activity log anyone can **see**. But the page
already **records** one. `RegistrationPage.activity` is a JSON column, and
`record_edit` is already called when the intro, form, thank-you page and intro
style change (`registration_page_service.py:597-755`). Nothing displays it.
Only `has_ever_been_published()` and `last_published_at()` read it.

✅ **Decision: record it; don't show it yet.** Follow-up review note: "if
there is a log we could add to it. But don't worry about showing it as yet."

- `set_auto_reply_enabled` calls `page.record_edit(user.id, "Turned the
  auto-reply off")` (or `"… on"`), as the steps beside it do. The entries are
  there for when a log UI arrives.
- No UI for the log is part of this work.

The activity texts are stored, not shown, so they are not translated: the
existing `record_edit` texts are plain English for the same reason.

### Q5: the empty state

When a page has no template, the step shows "Set up auto-reply email". Since
`bf742eaa` that only happens to old pages.

✅ **Decision: leave it as it is.** A page with no template already sends
nothing, and `sends_auto_reply()` covers it.

## 8. Text and translations

New strings: the notice in §7, and possibly a reworded checkbox label. The
activity texts are not translated (Q4). Check `docs/language.md`, then load
`translate-catalogues` and fill in the Hungarian.

## 9. Documentation

- `docs/registration-intro-editor.md`, "The auto-reply email": say it can be
  turned off, what that does to sends and to the warnings, and that the template
  is kept.
- The service docs page (`templates/backoffice/service_docs/_emails.html`):
  correct the `send_registration_auto_reply` description ("skips when no
  auto-reply is configured" becomes "... or it is turned off"). Adding an
  interactive card for the new service is **out of scope** unless you want it.

## 10. Tests

| Kind | What |
|---|---|
| Unit (domain) | Default is on; `set_auto_reply_enabled`; `sends_auto_reply()` for all four combinations of flag and template; the detached copy keeps the flag. |
| Unit / service (fake UoW) | `set_auto_reply_enabled`: permission refused for a non-manager, no-op when unchanged, records activity when changed. `send_registration_auto_reply` returns `None` and writes no record when off. Readiness returns `[]` for an off page, **including a page with no email field** (the ERROR case) and one with every WARNING; unchanged for an on page. A copied page keeps the flag. |
| Integration (real DB) | The column round-trips through the ORM. An existing row without the value reads as `true` (server default). |
| Component (blueprint) | View mode: read-only checkbox matching the stored value. Edit mode: an enabled checkbox. Save with it unticked turns it off; ticked turns it on. A save without `auto_reply_enabled_shown` leaves it alone. When off: the notice shows, and neither the readiness banner nor the test-send box's "Registrants still won't receive…" line appears, even on a page with no email field. Replaces `test_checkbox_renders_checked_and_disabled_with_no_toggle_form`. |
| E2E | In `tests/e2e/test_registration_auto_reply.py`: a published page with the auto-reply off takes a registration and sends no email and writes no send record. |
| BDD | One scenario: Edit, untick "Send auto-reply email", Save, then see it unticked and the notice (the `I uncheck the "…" checkbox` step already exists in `tests/bdd/test_backoffice.py:1550`). |

## 11. Order of work

1. ✅ Domain flag and `sends_auto_reply()`, with unit tests.
2. ✅ ORM column and migration (`bb3237d4dfc8`), with the integration tests.
   Committed with step 1: a page loaded from the database is built without
   `__init__`, so the domain attribute cannot ship without its column.
3. ✅ Service: `set_auto_reply_enabled`, the send path, readiness, copy, with tests.
4. Blueprint and template, with component tests.
5. Text, catalogues, docs.
6. E2E and BDD.

Each step is its own commit.
