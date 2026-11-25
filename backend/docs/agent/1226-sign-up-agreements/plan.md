# 1226 — Agree to the terms and the data agreement at sign-up

Status: the agreed parts are implemented. The sign-up page asks for one
agreement to the Terms and Conditions and the data agreement together, the
user row records the time and the version of each, and a sentence says that
account holders are emailed about important changes. Three questions are still
open and are not built here: see [Open decisions](#open-decisions).

**Before this merges, the Terms and Conditions page has to exist** at
`HELP_SITE_TERMS` (by default
<https://docs.democraticlottery.org/data-and-legal/terms/>). Its text is
sc-1304's, being drafted. Until it is published, the sign-up page links to a
page that is not there, and asks people to agree to it.

## The story

At sign-up a user agrees to:

1. the Terms and Conditions, once there are some;
2. receiving emails about changes to the service;
3. Sortition Foundation contacting them about their usage, to learn about its
   users and their needs (also sc-1207).

## Decisions

- **One tickbox for both documents.** "I agree to the Terms and Conditions and
  the Data Agreement", required, replaces the "Accept Data Agreement" tickbox.
- **Emails about changes: a sentence, no tickbox.** They are service messages
  to account holders, so there is nothing to agree to and nothing to store.
- **Record the version of each document**, not only the time, so that once a
  document changes it is clear who agreed to which text.

## 1. What is recorded

- `users` gains three nullable columns beside `user_data_agreement_agreed_at`:
  `user_data_agreement_version`, `terms_agreed_at` and `terms_version`
  (migration `c654b45ee8dc`). They are added empty: an account made before this
  keeps its data agreement time, with no version, and has not agreed to the
  terms. The previous release never reads them, so the migration is backwards
  compatible; its downgrade drops them.
- `User.mark_data_agreement_agreed(version)` records the time and the version;
  `User.mark_terms_agreed(version)` is new and does the same for the terms.
- The versions in force come from the environment, `TERMS_VERSION` and
  `DATA_AGREEMENT_VERSION`, read by `config.get_terms_version()` and
  `config.get_data_agreement_version()`. Both default to `1`, the text in force
  when sign-up began recording versions; a blank value counts as unset. A
  version is a short label, at most 50 characters, raised when the published
  text changes. Raising one asks nobody to agree again.
- `create_user()` takes `accept_terms` beside `accept_data_agreement` and records
  each document with its version. `find_or_create_oauth_user()` passes both on
  to a new account only; signing in to an existing account records nothing.
- `HELP_SITE_TERMS` is configured beside `HELP_SITE_DATA_AGREEMENT`, and given to
  every template as `help_site_terms`.

## 2. The sign-up page

In `templates/public/register.html`, where the data agreement was:

- A fieldset, "Terms and data agreement": "Please read and accept our terms and
  our data agreement to proceed.", then a link to each document, "View terms and
  conditions" and "View data agreement". The links sit outside the label, so
  following one never ticks the box, and open in a new tab, so nothing typed is
  lost.
- The tickbox, `accept_terms_and_data_agreement` on `RegistrationForm`. Left
  unticked: "You must accept the terms and the data agreement to register".
- The sentence, "We'll email you about important changes to OpenDLP and to these
  documents.", is the tickbox's hint: it sits under the label and is read out
  with it (`aria-describedby`). It is a notice, so it asks nothing and nothing
  is stored for it.
- The beta disclaimer stays under the agreement, above the submit buttons.

## 3. Every sign-up method

- **Email:** `_register_with_email()` passes the tick to `create_user()` as both
  `accept_terms` and `accept_data_agreement`.
- **Google and Microsoft:** `_start_oauth_registration()` stores the tick in the
  session, and each callback passes it to `find_or_create_oauth_user()`, then
  clears it. The session key is now `oauth_accept_terms_and_data_agreement`
  (it was `oauth_accept_agreement`), so a hand-off begun on the old page, which
  showed only the data agreement, is not recorded as agreeing to the terms.

## 4. Site Admin

The user page (`templates/admin/user_view.html`) has two rows where it had one:
"Terms and conditions", then "Data agreement". Each reads "Agreed on <date>,
version <version>"; an account from before versions has its data agreement time
alone, and "Not agreed" for the terms.

## Open decisions

Not built here, each waiting for a decision:

1. **Contact about usage (sc-1207).** Either a notice at sign-up with an opt-out
   in My Account, which rests on legitimate interest, or an optional, unticked
   tickbox, stored with its time, which is consent.
2. **The sign-in page's Google and Microsoft buttons.** With open sign-up on, an
   email OpenDLP does not know yet becomes an account without the agreement, as
   on main. Either an accept page before the account is made, or sending the
   person to the sign-up page.
3. **Existing users when the terms launch, or change.** Either they accept at
   their next sign-in, which records it, or a banner tells them, which records
   nothing.

## Tests

- Unit: the domain records (`tests/unit/domain/test_users.py`); `create_user()`
  and `find_or_create_oauth_user()` recording each document with the configured
  version, a new OAuth account only (`tests/unit/test_user_service.py`); the two
  version settings (`tests/unit/test_config.py`); `help_site_terms`
  (`tests/unit/test_context_processors.py`).
- Integration: the columns round-trip (`tests/integration/test_orm.py`); the
  migration's upgrade and downgrade against PostgreSQL, in a transaction rolled
  back at the end, including an older user's row
  (`tests/integration/test_sign_up_agreements_migration.py`).
- Component: the fieldset, its one tickbox and label, the links and their
  setting, the hint as the tickbox's description, the refusal without the tick,
  and the record with each version by email (`test_register_page.py`); the
  Google and Microsoft buttons refused without the tick, and recording both
  documents on the new account, and the sign-in page's buttons recording none
  (`test_oauth_flow.py`); the Site Admin rows (`test_admin_user_management.py`).
- e2e: the record in PostgreSQL after an email, a Google and a Microsoft sign-up.
- BDD (`features/login.feature`): the page asks for the agreement, a sign-up
  without it is refused, and a sign-up records it.

## Translations

Eight new strings have Hungarian proposals marked fuzzy, in the sign-up page's
informal register. "Terms and Conditions" is proposed as "felhasználási
feltételek"; a reviewer may prefer "Általános Szerződési Feltételek".

## Seen, not changed

- An existing account found by email in an OAuth callback is signed in, and the
  tick is not recorded on it, even when it came from the sign-up page.
- The OAuth session values of an abandoned sign-up stay in the session, so a
  later sign-in with Google or Microsoft from the sign-in page can still pick
  them up, as on main.
- The Site Admin users export has no agreement columns, as on main.
