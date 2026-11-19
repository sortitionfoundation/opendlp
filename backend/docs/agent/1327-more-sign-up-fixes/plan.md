# 1327 — More fixes on the sign-up page

Status: implemented. Two additions to the public sign-up page
(`templates/public/register.html`): one more optional survey question, and a
beta disclaimer shown as text. The disclaimer is the one sc-1305 asked for, so
this covers that story as well.

## The story

1. Add the disclaimer text with a tickbox.
2. Add one more question with drop-down answers: where did you hear about us?
   Social media, an event, a forum, a newsletter, a friend, or other.

The disclaimer is information, not an agreement, so it has no tickbox and
nothing is stored: see [2. The beta disclaimer](#2-the-beta-disclaimer).

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

The text:

> Registration for OpenDLP is currently only open for beta testing. Please
> contact us if you intend to use it in actual democratic lottery processes
> and/or with actual personal datasets.

It tells people what OpenDLP is ready for and who to talk to; it asks nothing
of them. So there is nothing to tick, and nothing is stored.

### On the page

- Under the data agreement, above the Turnstile check and the submit buttons,
  so it is the last thing read before the account is created. It sits with the
  fields every sign-up method shares, so email, Google and Microsoft sign-ups
  all show it.
- A plain block, not a fieldset: a fieldset groups form controls, and there is
  none. Its title, "Beta disclaimer", is an `h2` under the page's `h1`, as the
  survey's "Tell us a little about yourself" is; the text is one paragraph in
  the secondary text style, as the data agreement's is.
- "contact us" links to the support address: `mailto:` and the context
  processor's `support_email_address`, escaped, coloured with `--color-links`,
  the way the invite code's helper text links "OpenDLP support". The two share
  one `support_link_start`, set at the top of the template, since the invite
  code's helper text shows only when an invite is required and the disclaimer
  always shows.
- The sentence is one msgid with the link's start and end as placeholders, so
  a translation can move or inflect the linked words.

### Nothing stored

With nothing accepted, the form, the services, the user record, the OAuth
session and the admin user view stay as they are: no form field, no column and
no migration. Main's migration head, `a62d0a510eee`, is still the head.

## Tests

- `tests/component/test_register_page.py`: the question's options and their
  order, and that it shows only with open sign-up; the disclaimer's text as
  written; its "contact us" link to the support address, with invites required
  and with open sign-up, where the invite code's helper text is hidden; its
  title as an `h2` in a heading outline that skips no level; its place under
  the data agreement and above the submit buttons; the data agreement's
  tickbox as the only one on the page; and an email sign-up with only the data
  agreement ticked.
- `tests/component/test_oauth_flow.py`: a Google or Microsoft sign-up hands off
  to the provider with only the data agreement ticked.
- `tests/e2e/test_auth_flow.py`, `tests/e2e/test_oauth_flow.py`: the new answer
  saved by email and Google sign-up; `tests/e2e/test_admin_user_management.py`:
  its label on the admin user view; `tests/unit/test_signup_survey_service.py`:
  the token in the export.
- BDD (`features/login.feature`): the sign-up page shows the disclaimer, with
  its heading, its text and the support link, and no tickbox but the data
  agreement's.

## Translations

The nine new strings, the question with its six answers, the disclaimer's
title and its text, have fuzzy Hungarian proposals in the sign-up page's
informal register, so they show in English until a reviewer accepts them. In
the disclaimer, "contact us" is "lépj kapcsolatba velünk", the catalogue's
usual words for contacting someone, with the link's markers around it.

## Seen, not changed

- With open sign-up on, "Sign in with Google" or "Sign in with Microsoft" on
  the sign-in page creates an Organiser account for an email OpenDLP does not
  know yet, without passing the sign-up page: the data agreement is neither
  ticked nor recorded, and the survey and the beta disclaimer are not seen.
  That is how main behaves. Sending such a sign-in to the sign-up page instead
  would be a change of its own.
