# 1287 — Fixes on the sign-up page

Status: implemented. Three fixes to the public sign-up page
(`templates/public/register.html`), what each one rests on, and why the fourth,
the link colour, is not made here. Then the password rules tick as the password
is typed (5).

Design reference: the OpenDLP - UI Figma file, sign-up frame node `5570-7007`
and sign-in frame node `5570-6325`.

## The story

1. Remove the note about the invite code; make it the invite code field's
   helper text, with a link to contact support: "If you don't have one, please
   contact OpenDLP support", the link a mailto to the support address.
2. Google and Microsoft logos without a border.
3. Simpler password requirements, as the Figma has them: "Your password must:"
   and four ticked lines, "10–256 characters", "Include at least one letter",
   "Not be a commonly used password", "Not be too similar to your personal
   information".
4. Link text blue, not red.

## 1. Invite code helper text

- **The support address** is configured once: the `SUPPORT_EMAIL` environment
  variable, read into `config.SUPPORT_EMAIL` (default
  `opendlp-support@sortitionfoundation.org`) and given to every template as
  `support_email_address` by `entrypoints/context_processors.py`. The emails
  and the home page's Contact us use the same value.
- **Invite code required** (no open signup): the grey panel above the form is
  gone. The field has helper text under the input, after any error message:
  "If you don't have one, please contact OpenDLP support.", where "OpenDLP
  support" is the mailto link, styled like the page's other links in running
  text. The `<p>` has `id="invite_code-help"` and the input names it in
  `aria-describedby`.
- The field's old hint, "Enter your invite code to register", said no more than
  the label, so it went with the form field's `description` that held it.
- **Open signup**: unchanged. The field shows only when a code is in play, with
  its "Optional — if you were given an invite code, enter it here." hint, and
  without the support link, since nobody needs a code there.
- The link is a few words inside a translated sentence, so the msgid carries
  `%(link_start)s…%(link_end)s` markers rather than the anchor: a translation
  can inflect the words it wraps (Hungarian puts a case ending on them), and the
  href and styling stay out of the catalogue.

## 2. Logo border

- **Cause**: a button draws its leading icon in `.btn-icon`, and
  `.btn-icon svg { stroke: currentColor; fill: none; }` in
  `static/backoffice/src/main.css` strokes that svg for the Lucide icons. The
  brand marks' paths inherited the stroke: in the browser every path had a
  computed stroke of `rgb(47, 52, 66)`, which outlined each shape, and the
  Google mark's last path, its unfilled 48×48 frame, drew a box round the G.
- **Fix**: both marks set `stroke: none` on their svg
  (`templates/components/brand_marks.html`); an inline style outranks the rule.
  After the fix every path's computed stroke is `none`.
- The marks are shared, so the fix reaches every button that draws them: the
  sign-up page's method chooser and its Google and Microsoft submit buttons, the
  sign-in page's SSO buttons, and the profile page's Link Google account and
  Link Microsoft account buttons.
- Not changed: the marks render at the icon slot's 16px; the Figma draws them
  at 20px.

## 3. Password requirements

`service_layer.security.password_requirements()` returns the four lines; the
page puts them under "Your password must:", each with an icon (`aria-hidden`)
that shows whether the password typed so far meets it (see 5), in a `<ul>`
whose container (`id="password-requirements"`) describes the password input.
The lines are translatable; the long help texts the page showed before were
English in every language.

Each line against the validators in `get_password_validators()`:

| Line | Enforced by |
| --- | --- |
| 10–256 characters | `MinimumLengthValidator(10)`, `MaximumLengthValidator(256)`; both numbers are read from the validators |
| Not be numbers only | `NumericPasswordValidator`, which refuses a password made of digits alone |
| Not be a commonly used password | `SafeCommonPasswordValidator` (Django's list) |
| Not be too similar to your personal information | `UserAttributeSimilarityValidator` over email, first and last name |

- The design's second line, "Include at least one letter", asked for more than
  `NumericPasswordValidator` enforces: "1234567890!" and "!@#$%^&*()_+" are
  accepted. The page says "Not be numbers only", which is the rule; validation
  is unchanged.
- The form's own `Length(min=8)` on the password field is looser than the 10
  the service enforces (`create_user` calls `validate_password_strength`); the
  page shows 10, which is the limit that applies. Unchanged.
- Tests in `tests/unit/test_security.py` hold the list to the validators: the
  length line follows the validators' numbers, a validator added or removed
  fails `test_every_validator_has_a_line`, and each line is checked against
  `validate_password_strength`, including digits with a symbol and no letter.
- The reset password page and the profile's change and set password pages
  still show the long help texts (`password_validators_help_text_html()`).

## 4. Link colour

Unchanged here: the sign-up page's links keep `--color-links`, the brand
crimson, like every other link. Every link turns blue in a follow-up change that
repoints `--color-links` itself, so this page gets no token or colour of its
own. For that change: the Figma sign-up frame binds "View data agreement" to
`info-600` (#2B5FA6), which the code already has as `--color-info-600`, and its
contrast on the page background (#F7F7F8) is about 6:1.

## 5. Live password rules

The rules tick as the password is typed. Every line starts with a hollow
circle, `icon_circle_small` (Lucide's circle-small, from the Figma Icons sheet),
in the secondary text colour, and turns into the Lucide check in
`--color-success-text` while the password meets its rule. Nothing turns red: a
rule not met yet keeps its circle. Without JavaScript the page shows the
circles and nothing more.

`password_requirements()` returns each line with a key and where it is checked
while the password is typed (`PasswordRequirement.live_check`); the template
puts both on the `<li>` (`data-password-rule`, `data-live-check`). The
`passwordRules` Alpine component (`src/js/components/password-rules.js`) does
the ticking:

| Line | Checked | How |
| --- | --- | --- |
| 10–256 characters | in the browser, on every keystroke | counts code points, as Python's `len()` does, against `data-min-length` and `data-max-length`, which the template takes from the validators |
| Not be numbers only | in the browser, on every keystroke | unticked while every character is a number (`\p{N}`) |
| Not be a commonly used password | by the server | `SafeCommonPasswordValidator` |
| Not be too similar to your personal information | by the server | `UserAttributeSimilarityValidator`, against the email and names typed so far |

- **The browser's two** are decided as the validators decide them.
  `NumericPasswordValidator` uses Python's `str.isdigit()`, which is true for
  the digits of any script and for superscripts; all of those are in `\p{N}`,
  which also holds a few numbers that are not digits (½, Ⅻ). For those the
  rule stays unticked though the server would accept the password, which is
  the safe way to be wrong. `tests/fixtures/password_browser_checks.json`
  holds the cases that are easy to get wrong - other scripts' digits,
  superscripts, emoji that are two UTF-16 units but one character to Python -
  and `test_security.py` runs them through the validators,
  `password-rules.test.js` through the component.
- **The server's two** are asked about once typing pauses for 400 ms, and
  again when the email or a name changes. The page posts the password with the
  email, first and last name to `POST /auth/password-check`, which runs each
  rule's own validators from `get_password_validators()` on a `TempUser` built
  from those fields (`password_rule_results()`; `PASSWORD_RULE_VALIDATORS`
  maps each key to its validators), and answers a boolean per rule,
  `{"rules": {"length": true, "not-numbers-only": true, "not-common": true,
  "not-similar": false}}`, never a validator's message. The page takes the two
  server lines from it. After a change, while the answer is awaited, and when
  none comes (a network error, the rate limit), those two lines keep their
  circle. An answer about values that have changed since it was asked is
  dropped.
- **The endpoint** is unauthenticated, as the sign-up page is, and POST only.
  The app's CSRF protection applies; the page sends the token in
  `X-CSRFToken`. Checks are limited per IP (`password_check_rate_limit_service.py`,
  a Redis counter like the signup limit's; `PASSWORD_CHECK_RATE_LIMIT_PER_IP`,
  default 120 per `PASSWORD_CHECK_RATE_LIMIT_WINDOW_MINUTES`, default 10). Over
  the limit the answer is a 429 with `Retry-After`, and a refused check is not
  counted, so a page that keeps asking does not keep itself over it. The
  password is read from the JSON body only and never logged; the request log
  has the path and the status. Every answer carries `Cache-Control: no-store`.
  The shape is pinned by `schemas/json_api/password-check.schema.json` and the
  recorded `tests/fixtures/json_api/password-check.json`.
- **Sending the form is unchanged.** The server validates the password in full
  when the form arrives, as before; the ticks are guidance.
- **Screen readers**: each line ends in its state, visually hidden and
  translated, " (met)" or " (not met yet)", which shows only once the script
  runs. The list describes the password field, so the states are read with the
  field's description. They are not announced as they change, so typing is not
  interrupted. The icons are `aria-hidden`, and nothing is animated.
- The confirm password field has no live check.
- Tests: `tests/unit/test_security.py` (keys, where each line is checked, the
  verdicts per rule, the shared browser cases),
  `tests/component/test_password_check.py` (the verdicts, CSRF, the rate limit,
  no-store, no password in the log), `tests/unit/test_password_check_rate_limit_service.py`,
  `tests/component/test_register_page.py`
  (circles, cloaked ticks and states, the data attributes),
  `src/js/components/password-rules.test.js` (the pause, the pending and failed
  states, dropped answers), and the `login.feature` scenario "The password
  rules tick while the password is typed".

## Open question

- Whether the reset password and profile password pages should get the short
  list, and its live ticks, too.

## Seen, not changed

- At 390px wide the footer's link row is wider than the screen on the public
  pages (406px on the sign-up page, more with a long version string), so the
  page scrolls sideways. Same on main.
