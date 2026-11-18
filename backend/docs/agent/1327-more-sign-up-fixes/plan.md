# 1327 — More fixes on the sign-up page

Status: implemented. Two additions to the public sign-up page
(`templates/public/register.html`): one more optional survey question, and the
beta disclaimer with a required tickbox. The disclaimer's text is the one
written for sc-1305, so this covers that story as well.

## The story

1. Add the disclaimer text with a tickbox.
2. Add one more question with drop-down answers: where did you hear about us?
   Social media, an event, a forum, a newsletter, a friend, or other.

## 1. Where did you hear about us?

- One more entry in `SIGNUP_SURVEY_QUESTIONS`
  (`domain/user_signup_surveys.py`): key `heard_about_us`, a SELECT question,
  "Where did you hear about us?", with the answers `social_media` "Social
  media", `event` "An event", `forum` "Forum", `newsletter` "Newsletter",
  `friend` "From a friend" and `other` "Other", in that order.
- The form, the admin user view and the users export are all generated from
  that list, so nothing else changes. The page shows an optional drop-down; the
  admin user view shows the answer's label; the export has a `heard_about_us`
  column holding the stored token, so the column reads the same in every
  interface language.
- It is the last question. The questions already there, and their export
  columns, keep their places.
- Answers live in the survey's JSON dict, so there is no migration.
- The story words it "Where did you hear from us?". The page asks "Where did
  you hear about us?": hearing *from* us would mean getting messages from
  Sortition Foundation.

## 2. The beta disclaimer

The text, as Sortition Foundation wrote it:

> By registering an account I understand that currently OpenDLP is only open
> for beta testing, therefore using it in actual democratic lottery processes
> and/or with actual personal datasets is forbidden. I agree to contact
> Sortition Foundation directly before using OpenDLP for actual projects
> described earlier. I also consent to Sortition Foundation contacting me to
> learn more about my usage patterns and user needs.

### On the page

- A fieldset of its own under the data agreement, with the legend "Beta
  disclaimer", the text as a paragraph, and under it a required tickbox
  labelled "Accept beta disclaimer" — the shape of the data agreement block
  above it, whose tickbox is "Accept Data Agreement".
- The text is not the tickbox's label because it is 63 words. The checkbox
  component sets its label in the semibold label style and centres the box on
  it, which suits one line; three sentences there would be a heavy block with
  the box floating beside its middle.
- The paragraph is the tickbox's description. The checkbox macro
  (`backoffice/components/input.html`) gained `described_by_id`, as `input`
  already had, so the tickbox's `aria-describedby` names the paragraph and a
  screen reader reads it out with the short label. After a refused submit the
  error and the paragraph share the one attribute, error first.

### Required

- `RegistrationForm.accept_beta_disclaimer` (`entrypoints/forms.py`) is a
  `BooleanField` with `DataRequired`, as `accept_data_agreement` is. Unticked,
  the page comes back with "You must accept the beta disclaimer to register"
  under the tickbox and keeps everything else that was entered.
- `relax_for_oauth()` leaves it required, so the Google and Microsoft buttons
  refuse to hand over to the provider until it is ticked, as with the data
  agreement.

### Stored and shown

- `User.beta_disclaimer_agreed_at`, nullable, set to the current time by
  `User.mark_beta_disclaimer_agreed()` — the same as
  `user_data_agreement_agreed_at` and `mark_data_agreement_agreed()`.
- `create_user()` and `find_or_create_oauth_user()` take
  `accept_beta_disclaimer`, as they take `accept_data_agreement`. The email
  path passes the form's value. The Google and Microsoft paths carry it across
  the provider redirect in the session as `oauth_accept_beta_disclaimer`, next
  to `oauth_accept_agreement`; the callbacks hand it to
  `find_or_create_oauth_user()` and pop it with the other OAuth keys.
- The admin user view (`templates/admin/user_view.html`) has a "Beta
  disclaimer" row under "Data Agreement": "Agreed on <time>", or "Not agreed".
- The users export carries neither agreement time, and is unchanged.

### Migration

`50903a521008` adds the nullable `users.beta_disclaimer_agreed_at` column, with
no backfill; the downgrade drops it. It is safe for a zero-downtime deploy: the
previous release's mapper never selects or inserts the new column. Accounts
made before the disclaimer, and accounts made by the CLI or the seed command,
stay null and show "Not agreed".

## Tests

- `tests/component/test_register_page.py`: the question's options and their
  order, and that it shows only with open sign-up; the disclaimer's text as
  written, its place under the data agreement, the tickbox's short required
  label, its description, and the refusal with the error under the tickbox.
- `tests/component/test_auth_flow.py`: no account without the disclaimer, and
  both errors when neither box is ticked.
- `tests/component/test_oauth_flow.py`: Google and Microsoft refuse to hand
  off without the disclaimer, and carry it through the callback to the new
  account, then drop it from the session.
- `tests/component/test_admin_user_management.py`: the admin view's "Agreed
  on" and "Not agreed".
- `tests/e2e/test_auth_flow.py`, `tests/e2e/test_oauth_flow.py`: both
  agreement times stored on PostgreSQL by the email, Google and Microsoft
  paths; the new answer saved by email and Google sign-up.
- `tests/unit/test_signup_survey_service.py`: the token in the export;
  `tests/unit/test_user_service.py`, `tests/unit/domain/test_users.py`,
  `tests/integration/test_orm.py`: the domain method, the services and the
  column round trip; `tests/unit/test_input_macros.py`: the macro's
  `described_by_id`.
- BDD (`features/login.feature`): the disclaimer is read out with its tickbox,
  and sign-up without it is refused. The steps that register now tick both
  boxes.

Every test that posts the sign-up form now ticks the disclaimer as well as the
data agreement.

## Translations

The eleven new strings have fuzzy Hungarian proposals in the sign-up page's
informal register, so they show in English until a reviewer accepts them. The
disclaimer is what users agree to, so its Hungarian deserves a careful read.

## Seen, not changed

- With open sign-up on, "Sign in with Google" or "Sign in with Microsoft" on
  the sign-in page creates an Organiser account for an email OpenDLP does not
  know yet, without passing the sign-up page, so neither the data agreement
  nor the beta disclaimer is ticked or recorded: both stay null. That was
  already so for the data agreement. Sending such a sign-in to the sign-up
  page instead would be a change of its own.
