# Cookie consent — research

**Issue:** #656
**Status:** Research complete, all decisions made (see [§9](#9-decisions)). Ready for
implementation; legal sign-off required before the branch merges.
**Date:** 2026-07-10

---

## TL;DR

**We almost certainly do not need a cookie consent banner today.** Every cookie OpenDLP
currently sets falls within a statutory exception to the consent requirement, in both the UK
and the EU.

What we _do_ need is a **cookies page** and a link to it from the footer. The page will be
published on the docs site (`docs.sortitionlab.org`) alongside the User Data Agreement, and
linked via a configurable URL (§9 D8) — so it is mostly a content task. The one piece of real
engineering is that `base_public.html`, the template behind the public registration form, has
**no footer at all** and needs one (§8.3).

Two findings worth flagging up front:

1. **The bot protection does not use cookies at all.** The assumption in the issue is wrong
   (details in [§2.3](#23-correction-bot-protection-uses-no-cookies)). It is honeypot form
   fields, a signed timestamp embedded in the HTML, and Redis counters keyed on IP address.
   Nothing is stored on the user's device.
2. **The front page sets no cookie for an anonymous visitor** — verified empirically, not just
   by reading the code. But `/?lang=es` _does_ set one, which is the only cookie in the whole
   app that needs anything beyond a plain factual disclosure.

Recommended option: **Option A — cookies page, no banner** (see [§6](#6-options)).

**Agreed.** Option A is the chosen approach, and if analytics is ever added it will be
cookieless and self-hosted (§7 Path 1). Both decisions are recorded in [§9](#9-decisions).
The one outstanding gate is legal sign-off before merge.

---

## 1. Method

- Read `docs/agent/614-bot-protection/{plan,research}.md` and the shipped implementation.
- Full static audit of `config.py`, `extensions.py`, `flask_app.py`, all blueprints, all
  templates, and all of `static/` for `document.cookie` / `localStorage` / `sessionStorage`.
- **Empirical verification** with the Flask test client, observing real `Set-Cookie` headers.
- Primary legal sources: ICO's guidance on storage and access technologies (the version
  reflecting the Data (Use and Access) Act 2025, in force 5 February 2026), PECR reg. 6, and
  Article 29 Working Party Opinion 04/2012 for the EU position.
- Secondary: GOV.UK Design System, law-firm analyses of the DUAA changes.

---

## 2. What cookies do we actually set?

### 2.1 The complete list

There are exactly **two** cookies. Both are first-party, both are `HttpOnly`.

| Cookie           | Set by        | When                                                                      | Lifetime                                               | Prod attributes                                            |
| ---------------- | ------------- | ------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------- |
| `session`        | Flask-Session | On CSRF token generation, `flash()`, `?lang=` selection, 2FA, OAuth start | 7 days (`PERMANENT_SESSION_LIFETIME`, `config.py:400`) | `Secure`, `SameSite=Lax`, `HttpOnly` (`config.py:561-562`) |
| `remember_token` | Flask-Login   | Only when the user ticks "remember me" at login                           | 7 days (`config.py:566`)                               | `Secure`, `SameSite=Lax`, `HttpOnly` (`config.py:564-565`) |

Notes:

- `SESSION_TYPE = "redis"` (`config.py:509`) means the session _payload_ lives in Redis, but a
  browser-side cookie carrying the session id is still set. Server-side sessions do not avoid
  the cookie.
- **There is no separate CSRF cookie.** Flask-WTF stores the CSRF secret inside the Flask
  session (`WTF_CSRF_COOKIE` / double-submit mode is not configured). So CSRF protection is a
  _reason the `session` cookie gets set_, not a cookie of its own.
- **There is no language cookie.** The chosen language is stored under the `"language"` key
  _inside_ the session (`extensions.py:132`).
- No `localStorage`, no `sessionStorage`, no `document.cookie` anywhere in `static/`. (One
  stale comment in `templates/backoffice/patterns/_pagination.html:131` claims scroll position
  is "saved to sessionStorage" — it isn't; scroll state is passed as a URL query param via
  `scroll_utils.py`. Worth fixing the comment separately; it is not a cookie issue.)
- No analytics, no Sentry, no Tag Manager, no advertising. Confirmed by grep.

### 2.2 Which pages set a cookie? (empirically verified)

Run against the real app with the Flask test client:

```
/                    -> 200  Set-Cookie: (none)
/?lang=es            -> 200  Set-Cookie: session=…; Expires=…; HttpOnly; Path=/
/auth/login          -> 200  Set-Cookie: session=…; Expires=…; HttpOnly; Path=/
```

So, against the three use cases in the issue:

| Use case                                       | Cookie set?                                                 | Why                                                                                                                                                               |
| ---------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Anonymous visitor browsing the front page**  | **No**                                                      | `main.index` renders no form, emits no flash, writes nothing to the session. `get_flashed_messages()` on an empty session is a read-only no-op.                   |
| **Anonymous visitor on the registration page** | **Yes — `session`**                                         | `GET /register/<slug>` calls `generate_csrf()` (`registration.py:82`), which writes the CSRF token into the session. This is CSRF protection, not bot protection. |
| **Signed-in user**                             | **Yes — `session`**, plus `remember_token` if they opted in | Authentication.                                                                                                                                                   |

Two caveats that flip the front-page answer:

- Arriving at `/?lang=es` writes `session["language"]` and therefore sets the cookie.
- Landing on `/` via a redirect that queued a `flash()` message sets the cookie.

Neither changes the legal conclusion, but both mean _"the front page never sets a cookie"_ is
not a claim we should put in writing on a cookies page. Better to say: "we set a cookie when
you choose a language, sign in, or fill in a form."

### 2.3 Correction: bot protection uses no cookies

`docs/agent/614-bot-protection/plan.md` (status: COMPLETE) and the shipped code confirm the
mechanism is entirely server-side and stateless with respect to the user's device:

1. **Honeypot** — hidden `_opendlp_ttoken_` input (`registration.py:80-94`). A form field.
2. **Form-timing token** — `_timing_token`, an `itsdangerous.TimestampSigner` value embedded
   in the HTML (`registration.py:59-61`). A form field.
3. **Rate limiting** — Redis counters keyed on IP and email
   (`registration_bot_protection_service.py`). Server-side only.
4. **`X-Robots-Tag: noindex`** — a response header.

There is no Turnstile, no reCAPTCHA, no hCaptcha, no altcha. Nothing is written to the device.

This is worth internalising, because it means **we have accidentally built the
privacy-friendly version of bot protection**. Had we chosen Cloudflare Turnstile or reCAPTCHA,
we would be having a much harder conversation: those set third-party cookies and, for
reCAPTCHA, are widely regarded as requiring consent — which is unworkable on a form you need
people to complete. Worth remembering if anyone ever proposes "just add Turnstile".

The one thing the registration page _does_ set a cookie for is **CSRF**, which is squarely
exempt.

### 2.4 Third parties (not a cookie problem, but adjacent)

`base.html:197-216` and `base_public.html:32` load govuk-frontend, Alpine.js and htmx from
`cdn.jsdelivr.net` on **every page, including the front page**.

- jsDelivr does not set cookies on static asset requests, so this is **outside PECR**.
- But it does disclose every visitor's **IP address and referrer** to a third party (Fastly /
  Cloudflare, jsDelivr's providers) on every page load, before any consent or notice.
- That is a UK/EU GDPR transparency question, not a cookie question — and it is arguably a
  bigger real-world privacy exposure than any cookie we set.

Google Fonts are allow-listed in the CSP (`flask_app.py:218-219`) but **not actually used** —
`static/css/application.css` contains no `@import` and no reference to `fonts.gstatic.com`.
Fonts are self-hosted. Good. The CSP allowance is dead config and could be tightened.

**Recommendation (separate issue):** self-host the three CDN assets. They are small, we
already have a static pipeline, and it removes the third-party disclosure entirely. This also
removes a supply-chain risk and a hard dependency on jsDelivr's uptime. I'd treat this as
higher priority than the cookie banner question.

---

## 3. The legal framework

Cookies are governed by **ePrivacy** law, not primarily by GDPR. In the UK that's PECR
regulation 6; in the EU it's Article 5(3) of the ePrivacy Directive as implemented by each
member state. The rule is the same in shape: **you need consent to store or access information
on a user's device, unless an exception applies.**

Importantly, the rule bites on the _storage_, regardless of whether the data is personal.

### 3.1 UK — PECR as amended by the DUAA 2025

The Data (Use and Access) Act 2025 amended PECR with effect from **5 February 2026**; the ICO
published final guidance on **29 April 2026**. There are now **five exceptions**:

| Exception                              | Applies when                                                                      | Extra conditions                                            |
| -------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **Communication**                      | Sole purpose is transmitting a communication (e.g. session-scoped load balancing) | —                                                           |
| **Strictly necessary**                 | Essential to provide the service the user requests                                | —                                                           |
| **Statistical purposes** ("analytics") | Sole purpose is aggregate statistics about use of _your_ service, to improve it   | Clear information **and** a simple, free means of objecting |
| **Appearance**                         | Sole purpose is adapting appearance/functionality to the user's preference        | Clear information **and** a simple, free means of objecting |
| **Emergency assistance**               | Locating a user who needs emergency help                                          | —                                                           |

The ICO's non-exhaustive list of activities meeting **strictly necessary** includes, verbatim:

> - ensuring the security of terminal equipment;
> - preventing or detecting fraud;
> - preventing or detecting technical faults;
> - authenticating the subscriber or user; and
> - recording information or selections the user makes on an online service.

And, from the worked examples:

> "Identifying a user once they have logged in to an online service for the duration of their
> visit to the site … ✔"

> "Session cookies used to store a user's preference can rely on the strictly necessary
> exception, provided they are not linked to a persistent identifier."

Under **appearance**, the ICO gives as an explicit ✔ example:

> "Remembering the language the subscriber or user selects (eg on a multilingual website)."

Crucially, the exception must be judged **from the user's perspective**, and if a technology is
used for more than one purpose, _every_ purpose must independently qualify.

### 3.2 EU — ePrivacy Directive Art. 5(3)

The DUAA relaxations are **UK-only**. The EU has not followed: the ePrivacy Regulation that
would have modernised this was formally **withdrawn by the Commission in February 2025**, so
the 2002/2009 Directive still governs, with only two exceptions:

- **(A)** sole purpose of carrying out transmission; and
- **(B)** strictly necessary to provide a service explicitly requested by the user.

There is **no analytics exception in the EU.** Article 29 Working Party Opinion 04/2012 remains
the canonical reading of exception (B), and expressly exempts:

- user-input cookies (form data, shopping baskets)
- **authentication session cookies**
- **user-security cookies** (e.g. CSRF / brute-force protection)
- multimedia player session cookies
- **session-scoped load-balancing cookies**
- **UI-customisation cookies** (e.g. language choice) — _when session-scoped_

**This matters to us, and more than I first thought.** Two independent facts put us on the EU
footing:

1. **EU users.** `SUPPORTED_LANGUAGES` defaults to `en,es,fr,de` (`config.py:477`) and we ship
   Hungarian translations. People in the EU are a key audience (confirmed).
2. **EU hosting.** The service is hosted in the EU (confirmed). That is an *establishment* in
   the Union, which engages EU law directly rather than merely via the extraterritorial
   targeting test.

The second is the stronger point. Where a service targets EU users from outside, there is at
least an argument about scope. Where it is *established and hosted* in the EU, the ePrivacy
Directive as implemented by that member state applies straightforwardly, and the UK's DUAA
relaxations are simply unavailable.

So: we must satisfy the **stricter EU rule**, and we cannot lean on the UK's new analytics
exception at all. Any future analytics decision has to be made on the EU footing, or with
geo-based logic — which is a genuine complexity cost, and which §7 concludes is not worth
paying.

---

## 4. Applying the law to our two cookies

| Cookie                                             | Purpose                                                            | UK basis                                        | EU basis                                                         | Consent needed?                                 |
| -------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------- |
| `session` — CSRF token on public registration form | "ensuring the security of terminal equipment" / "preventing fraud" | Strictly necessary                              | Strictly necessary (WP29: user-security cookie)                  | **No**                                          |
| `session` — CSRF token on any logged-in form       | Security                                                           | Strictly necessary                              | Strictly necessary                                               | **No**                                          |
| `session` — authentication after login             | "authenticating the subscriber or user"                            | Strictly necessary                              | Strictly necessary (WP29: authentication session cookie)         | **No**                                          |
| `session` — flash messages                         | "recording information or selections the user makes"               | Strictly necessary                              | Strictly necessary (user-input cookie)                           | **No**                                          |
| `session` — `?lang=` language choice               | Remembering a language the user explicitly chose                   | **Appearance** exception → needs info + opt-out | WP29 UI-customisation → strictly necessary **if session-scoped** | **No**, with caveats — see 4.1                  |
| `remember_token` — "remember me"                   | Persistent login                                                   | Not strictly necessary — but see 4.2            | Same                                                             | **No**, the checkbox _is_ the consent — see 4.2 |

### 4.1 The language cookie is the one genuine wrinkle

Two problems, both minor, both fixable without a banner:

- **UK:** the appearance exception carries an information + opt-out duty. The opt-out is
  trivially satisfied: the user can pick a different language, and the value only persists
  because they chose it. But we should say so on the cookies page.
- **EU:** WP29 exempts UI-customisation cookies **when they are session cookies**. Ours rides
  on the 7-day `session` cookie, so it is persistent. WP29 says a persistent
  UI-customisation cookie needs "additional information" to be exempt, not necessarily consent
  — the user has, after all, deliberately clicked a language.

There is a decent argument that a user clicking "Español" has _explicitly requested_ the
service of being shown Spanish, which lands it back in strictly-necessary. I would not lose
sleep over this. But it's the one place where a lawyer might quibble, so it is called out for
the sign-off in D6.

**Decided ([D3](#d3-the-language-cookie-stays-as-it-is-and-gets-documented)):** leave the
behaviour alone, document the reasoning. No code change.

Note also: language selection is the **only way an anonymous front-page visitor can acquire a
cookie**. Everything else requires them to log in or open a form.

### 4.2 "Remember me" — the checkbox is the consent

The ICO and WP29 both take the view that a **persistent** login cookie is _not_ strictly
necessary: the user's reasonable expectation is that the session ends when the browser closes.

But this does not require a banner. The standard, regulator-endorsed answer is that **the
"remember me" checkbox itself constitutes the consent** — it is a specific, informed,
unambiguous, affirmative act, freely given, and unticked by default. That is textbook GDPR-
standard consent.

Requirements to make that hold:

- The checkbox must be **unticked by default** (verify this).
- The label should make the consequence clear — "Keep me signed in for 7 days (sets a cookie
  on this device)" rather than a bare "Remember me".
- The cookies page should describe `remember_token`.

**Action:** confirm the checkbox is unticked by default and reword the label. That is the only
code change the law actually compels.

---

## 5. Do we need a banner? — the reasoning

No, because:

- Every cookie we set is exempt from consent (§4).
- No advertising, ever (stated policy). No analytics today. No cross-site tracking.
- The two exempt-with-conditions items (language, remember-me) are satisfied by _information_
  and by a checkbox respectively, not by a consent gate.

The GOV.UK Design System agrees with this reading:

> "If your service only uses essential or 'strictly necessary' cookies, you may skip the
> banner. However, you must still inform users about these essential cookies through a
> dedicated cookies page linked in your footer."

And the ICO is clear that even where every cookie is exempt, the **transparency duty under
UK GDPR Articles 13/14 still applies** — users must be told what is stored and why.

There is also a positive argument for _not_ having a banner. OpenDLP exists to run democratic
lotteries; its public-facing page is a registration form completed by members of the public who
were invited by post, many of whom are not confident internet users. A consent banner on that
form is friction on the one interaction that matters, in exchange for zero privacy gain. And a
banner that offers no real choice ("Accept" with nothing to reject) is _worse_ than none — the
ICO explicitly criticises consent theatre, and it trains users to click through banners that
do matter elsewhere.

---

## 6. Options

### Option A — Cookies page, no banner _(recommended; **approved**, §9 D1)_

Publish a cookies page **on the docs site** (`docs.sortitionlab.org`), and link to it from the
app footer via a configurable URL — exactly as we already do for the User Data Agreement.
Reword the "remember me" label. Add a line to the privacy notice.

**Decided (§9 D8):** the page is hosted externally, not served by Flask. New config var
`HELP_SITE_COOKIES`, defaulting to `https://docs.sortitionlab.org/data-and-legal/cookies/`,
threaded through in the same way as `HELP_SITE_DATA_AGREEMENT`. Mechanics in §8.2.

**Pros**

- Legally correct for what we do today, in both UK and EU.
- Zero friction on the registration form — the interaction we most care about.
- No new dependency, no new JS, no CSP headaches.
- Follows GOV.UK guidance exactly, and matches our existing design system.
- Hosting it on the docs site matches the established pattern for legal content, keeps legal
  copy out of the deploy cycle, and lets it be corrected without shipping the app.
- Roughly a day of work, mostly content.

**Cons**

- Someone has to keep the cookies page accurate as the app changes — and now that "someone"
  is editing a *different repo*, so drift is likelier, not less likely (§8.2, §8.7).
- The docs site is English-only; an in-app page would have gone through `_()`. See §8.7.
- If we add analytics later, we then have to build the banner anyway (but see §7 — we'd have to
  do that under any option).
- Requires the confidence to _not_ ship a banner, which can feel exposed if a client asks
  "where's your cookie banner?". Mitigation: the cookies page answers that question, and we can
  point at the GOV.UK precedent.

### Option B — GOV.UK cookie banner now, with only an "essential cookies" message

Ship the GOV.UK cookie banner component in its "we only use essential cookies" form.

**Pros**

- Visibly signals that we've thought about it. Reassuring to institutional clients.
- The scaffolding exists if analytics arrive later.

**Cons**

- **Not recommended by GOV.UK for essential-only services.** We'd be adding a banner the
  guidance says to skip.
- It is consent theatre: nothing to accept or reject. Actively bad practice.
- Friction on the public registration form, hurting completion rates for the users we most
  need to reach.
- Still needs the cookies page anyway, so it is strictly _additional_ work, not alternative.

### Option C — A Flask consent library

**Assessment: don't.** The landscape is thin.

| Library                                             | State                                                 | Verdict                                                                          |
| --------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------- |
| `Flask-Consent`                                     | 11 stars, 12 commits, 3 tags, no recent activity      | Effectively unmaintained. A toy.                                                 |
| `flask-cookies`                                     | Built to wire up **Google Tag Manager** consent modes | Solves a problem we do not have and never will                                   |
| Commercial CMPs (CookieYes, Usercentrics, OneTrust) | Mature                                                | Third-party JS that phones home; ironic on a privacy tool; costs money; CSP pain |

**Pros of a library:** categories and opt-out plumbing for free, _if_ we ever need them.

**Cons:** every option either is unmaintained, is built around ad-tech we reject, or introduces
the exact third-party tracking we are trying to avoid. Against our "boring technology with a
track record" rule, none of these qualify. And the thing they'd save us — a signed cookie
storing a preferences dict, plus a `has_consent(category)` helper — is genuinely about 60 lines
of code we could own outright.

If we ever need a banner, **implement it directly** using the GOV.UK component. That is the
boring, mature, well-documented choice here; the "library" is the design system.

### Option D — Full geo-aware consent management

Detect UK vs EU visitors and apply the DUAA analytics exception only to UK users.

**Pros**

- Maximises analytics coverage under UK law.

**Cons**

- Only worth anything _if_ we adopt analytics **and** decide the UK relaxation is worth
  exploiting. Speculative on both counts — and §9 now settles both against it.
- Geo-IP adds a dependency, and misclassification creates the legal exposure it was meant to
  avoid.
- Complexity is disproportionate for a project with no advertising and no commercial analytics
  motive.
- **The service is hosted in the EU** (§3.2). Geo-gating the *user* does not help when the
  *controller and the hosting* are established in the EU — EU law applies to the service, not
  merely to whichever visitors happen to be in the Union.

**Verdict: rejected, not merely premature.** The commitment to cookieless analytics (§9 D2)
removes the only scenario in which this would have paid for itself, and the EU hosting removes
the legal basis it was built on.

---

## 7. If we add analytics later

> **Decision (§9 D2): if analytics is ever added, it will be cookieless and self-hosted —
> Path 1 below.** The rest of this section records why, and what would have to be true for
> that to change.

This is the decision that would change everything, so it's worth pre-computing.

The choice is **not** "analytics or no analytics" — it's "which analytics".

**Path 1 — Cookieless, self-hosted analytics (Plausible, Umami, GoatCounter, Matomo in
cookieless mode).** These set **no cookies at all** and store no device identifier.

- No PECR trigger at all, because nothing is stored on or read from the device.
- **Still no banner needed, in the UK or the EU.**
- Self-hosting keeps the data ours; no third-party disclosure.
- This is what I'd argue for. It preserves the current, comfortable position, and the
  data quality is entirely adequate for "which pages do people bounce from".

**Path 2 — Google Analytics.** Sets cookies, is a third party, is used for advertising by
Google.

- UK: does **not** qualify for the DUAA statistical exception, because that exception requires
  the data not be used by the third party for its own purposes.
- EU: unambiguously requires prior opt-in consent.
- ⇒ We would need a real banner, real category logic, and (given our EU users) an
  opt-in-by-default-off gate. Plus a legitimate argument to have inside the Sortition
  Foundation about whether shipping Google tracking on a democratic-participation tool is
  consistent with the project's values.

**Path 3 — Self-hosted analytics that _does_ set a first-party cookie** (e.g. Matomo with
cookies on).

- UK: likely fits the new statistical-purposes exception → **information + opt-out**, no
  opt-in banner.
- EU: **no analytics exception exists** → opt-in consent required.
- ⇒ Because we serve EU users, we would be building a full consent banner anyway. The UK
  relaxation buys us nothing unless we also build geo-logic (Option D).

**The asymmetry is stark.** Path 1 costs a banner-free life. Paths 2 and 3 both cost a full
consent mechanism, because we have EU users *and* EU hosting (§3.2). So if analytics is ever
wanted, **Path 1 is overwhelmingly the right call**, and it happens to be the one most aligned
with what this project is for.

This is now settled rather than advisory (§9 D2). The practical consequence for the work in §8:
the cookies page can state plainly that we use no analytics cookies, and that commitment should
be recorded in `docs/personal-data.md` so a future contributor reaching for Google Analytics
discovers the constraint before they discover the lawyer.

---

## 8. Proposed implementation

Option A is approved (§9 D1), with the cookies page hosted on the docs site (§9 D8). The work is
small, and mostly content.

**Progress:** items 2, 3, 4 and 7 are done. Item 6 is in progress. Item 1 is in the docs repo,
not this one. Item 5 has no in-app target — there is no privacy notice template in the app
(§8.10).

1. **Cookies page on the docs site** — authored at
   `https://docs.sortitionlab.org/data-and-legal/cookies/`, in the docs repo, not here. Content:
   a table of Name / Purpose / Expires, two rows. Explain that the session cookie covers security
   (CSRF), sign-in, form messages and language choice; explain `remember_token`; state plainly
   that there is no advertising and no analytics.
2. **`HELP_SITE_COOKIES` config var** — threaded through exactly as `HELP_SITE_DATA_AGREEMENT`
   is. Mechanics and the gotchas in §8.2.
3. **Footer links** — `base.html` has a footer and takes a one-line addition.
   **`base_public.html` has no footer at all** — this needs building. See §8.3; it is the only
   item here with real work in it.
4. **"Remember me" label** — confirm it is unticked by default; reword so the cookie
   consequence is explicit. This is the only code change the law actually compels (§4.2).
5. **Privacy notice** — add a cookies paragraph pointing at the docs-site page.
6. **`docs/personal-data.md`** — a permanent reference doc, and the most important item on this
   list. See §8.4–§8.6.
7. **Tests** — a test asserting `GET /` emits **no** `Set-Cookie`, and context-processor tests
   for the new URL. Note we *lose* the ability to test the page's content, because it is no
   longer ours (§8.7). The `GET /` test is now the only executable check in the whole scheme; it
   locks in the property this analysis rests on, and will fail loudly
   the day someone adds a `flash()` to the front page.

### 8.1 Hosting the page on the docs site

The User Data Agreement is already an external page linked from the app by a configurable URL.
The cookies page follows the same pattern. This is the right call: it keeps legal copy out of the
deploy cycle, so a wording fix from a lawyer does not require a release, and it puts all the
"data and legal" pages in one place for a reader.

### 8.2 Threading `HELP_SITE_COOKIES` through

Traced from the existing `HELP_SITE_DATA_AGREEMENT`. Five files, plus tests:

| File | Change |
|---|---|
| `src/opendlp/config.py:441-444` | Add `self.HELP_SITE_COOKIES: str = os.environ.get("HELP_SITE_COOKIES", "https://docs.sortitionlab.org/data-and-legal/cookies/")` alongside `HELP_SITE_HOME` / `HELP_SITE_DATA_AGREEMENT`. |
| `src/opendlp/entrypoints/context_processors.py:131-134` | Convert `get_help_site_urls()` to return a `NamedTuple` (§8.2.1) and add the third URL. |
| `src/opendlp/entrypoints/context_processors.py:156,165` | Use attribute access and expose `help_site_cookies` in `inject_template_globals()`. |
| `env.example:89-91` | Add `HELP_SITE_COOKIES=...` under the existing "External help site URLs" comment. |
| `docs/configuration.md:200-210` | Add to the same block; update the prose, which currently says the URLs feed the header "Help" link and footer "User Data Agreement" link. |

#### 8.2.1 `get_help_site_urls()` returns a NamedTuple

**Decided (§9 D9).** Today it returns a positional `tuple[str, str]`:

```python
@cache
def get_help_site_urls() -> tuple[str, str]:
    flask_config = config.get_config()
    return flask_config.HELP_SITE_HOME, flask_config.HELP_SITE_DATA_AGREEMENT
```

Two positional strings is survivable; three is where positional unpacking starts inviting
silent transposition bugs — the elements are all `str`, so swapping two would type-check, pass
mypy, and quietly render the wrong link. Replace with a `typing.NamedTuple`:

```python
class HelpSiteUrls(NamedTuple):
    home: str
    data_agreement: str
    cookies: str


@cache
def get_help_site_urls() -> HelpSiteUrls:
    flask_config = config.get_config()
    return HelpSiteUrls(
        home=flask_config.HELP_SITE_HOME,
        data_agreement=flask_config.HELP_SITE_DATA_AGREEMENT,
        cookies=flask_config.HELP_SITE_COOKIES,
    )
```

and at the call site (`context_processors.py:156`), replace the tuple unpacking with attribute
access: `help_site_urls.home`, `.data_agreement`, `.cookies`.

Notes:

- `NamedTuple` is `typing` stdlib — boring, no new dependency. It is immutable and hashable, so
  it remains compatible with the `@cache` decorator.
- There is exactly **one call site** (`context_processors.py:156`), so this is a contained
  change, not a sprawling refactor. That is what makes it worth doing now rather than "later".
- It stays tuple-compatible, so nothing that treats the result as a sequence breaks.
- `src/` currently contains no other `NamedTuple`, so this introduces the idiom. Given it is
  stdlib and the alternative is a bare 3-tuple of same-typed strings, I think that is fine — but
  worth a reviewer's eye, since "match the surrounding style" is a house rule.

#### 8.2.2 Tests

- `tests/unit/test_context_processors.py:132-137` hard-codes the two default URLs and must gain
  an assertion for `help_site_cookies`.
- **Correction to an earlier draft of this document:** `tests/unit/test_dashboard_feature_flags.py:90`
  is *not* affected by the NamedTuple change. It never calls `get_help_site_urls()`; it passes
  `help_site_data_agreement=` straight into `render_template_string` as a template variable. It
  only needs touching if `backoffice/components/footer.html` gains a cookies link that the test's
  rendered template then requires.
- `get_help_site_urls` is `@cache`d and, unlike `_get_file_hash` / `get_opendlp_version` /
  `get_service_account_email`, has no `cache_clear()` call in the test suite. Any test that wants
  to vary `HELP_SITE_COOKIES` via the environment will need one. Worth knowing before writing the
  tests, not after.

### 8.3 `base_public.html` has no footer — the one piece of real work

`templates/base.html:175` already has a footer with the `help_site_data_agreement` link; adding a
cookies link there is one line.

**`templates/base_public.html` has no footer whatsoever.** It goes from `<main>` (line 27-29)
straight to `</body>` (line 43). There is no `govuk-footer` markup in the file at all.

This matters more than it sounds. `base_public.html` is the template behind the **public
registration form** — which is:

- the one page an anonymous member of the public actually lands on;
- the page that **does** set a cookie (`generate_csrf()`, §2.2); and
- therefore the single page on the site that most needs a cookies link.

GOV.UK is explicit that the cookies page must be linked from the footer. So this task requires
**adding a footer to `base_public.html`**, not just adding a link to an existing one.

**Decided (§9 D11):** add a minimal GOV.UK footer, carrying the cookies link and the User Data
Agreement link, and nothing else. The public page should stay uncluttered — it is the one page
where added visual noise costs us completions from people we reached by post.

Because this is a visible change to the most sensitive template we have, the rendered page wants
its own look rather than being waved through as "add a link". Check it against the GOV.UK footer
component and `docs/agent/component_accessibility.md`.

### 8.4 The documentation problem

The conclusion "no banner needed" is only valid while its premises hold. Those premises are
invisible in the code: nothing in `config.py` announces that adding Google Analytics would
oblige us to build a consent mechanism. A future contributor — or a future us — will reach for
an analytics snippet and have no idea they have just walked into PECR.

Worse, the person about to break a rule usually reads only the doc for the area they are
working in. Someone adding a language cookie reads `docs/translations.md`. Someone swapping the
honeypot for Turnstile reads `docs/bot-protection.md`. Neither has any reason to open a doc
about cookies. **A central doc nobody is routed to is a doc that does not exist.**

So the design has two halves: one canonical doc, and a set of tripwires in the docs people
actually read.

### 8.5 `docs/personal-data.md` — the hub

**On the name.** The suggestion was `user-data.md`. I'd argue against it, on a specific
codebase-local ground: *User* is a domain term here — `domain/users.py`, an aggregate with
roles and passwords. But the most sensitive personal data we hold belongs to **registrants**,
who are explicitly *not* `User`s (see `CLAUDE.md`: "Users/Organisers are separate aggregates
from Assembly/Registrants"). A doc called `user-data.md` invites a reader to conclude it does
not govern the registration pool, which is exactly backwards. `personal-data.md` is the UK/EU
GDPR term of art, and it correctly spans cookies (device identifiers), log lines, registrants,
users, and the IP addresses in our rate-limit keys.

**What it contains.** A hub, covering:

- **Principles** — the standing constraints, which are the actual load-bearing content:
  - no advertising, ever;
  - no analytics that sets a cookie or reads the device — if analytics is added it must be
    cookieless and self-hosted (§7 Path 1, decided in §9 D2);
  - no third-party cookies; no cross-site or cross-device tracking;
  - bot protection stays server-side (no Turnstile / reCAPTCHA / hCaptcha);
  - never log raw PII;
  - no long-term copies of personal data that cannot be found and blanked.
- **Cookies** — canonical, and deliberately so. The §2.1 table, the legal conclusion and its
  statutory basis (strictly necessary; appearance), and the language-cookie reasoning (§9 D3).
  The public page on the docs site is a *copy* of this table written for a lay audience; this
  file is the source of truth, and must say so, naming the published URL and instructing anyone
  who edits the table to update the published page (§8.9).
- **The English-only trade-off** — record that the published cookies page is not translated, that
  this was a deliberate decision (§9 D10) taken to keep legal copy out of the deploy cycle, and
  that translating it is the remedy if the language mix of registrants makes it bite. Written
  down so a future reader finds a decision rather than an oversight.
- **The EU footing** — EU users *and* EU hosting, so the UK DUAA relaxations do not apply
  (§3.2). The single fact most likely to be forgotten and most likely to cause an error.
- **Logging PII** — the *principle* and the why, linking to `docs/agent/code_quality_rules.md`
  for the code-level rules.
- **GDPR / right to be forgotten** — the blank-don't-delete strategy, and the prohibition on
  long-term file storage. Currently in `AGENTS.md`.
- **"What would change the answer"** — a short, blunt list: *if you are about to do any of the
  following, this doc is now wrong and you must revisit issue #656.* Covers each principle
  above, plus adding any new persistent cookie, plus adding a third-party script.
- **Legal sign-off status** (§9 D6), so nobody assumes more assurance than we have.
- A pointer back to this research doc for the full reasoning.

**What it does *not* do: absorb `code_quality_rules.md`'s logging section.** That section is
code-level how-to — use `structlog`, pass `user_id` not `email`, hash with `hash_email`, beware
`error=str(e)` — with good/bad examples. Three reasons to leave it where it is:

1. `sf-code-review` already routes reviewers to `code_quality_rules.md`. Moving the rules breaks
   a working path.
2. Copying them creates two sources of truth that will drift. The next person to update one will
   not know about the other.
3. It is the right *altitude* split. `personal-data.md` answers "what may I do, and why";
   `code_quality_rules.md` answers "how do I write the log call". Hub states the principle and
   links; the how-to stays put.

Note that `code_quality_rules.md:39-40` *already* justifies the logging rule by reference to
GDPR erasure. The unifying thread is latent in the text; the hub just makes it explicit.

For the same reason, the `AGENTS.md` sections on "Logging (PII / secrets)" and "GDPR and the
right to be forgotten" should shrink to short pointers at `personal-data.md` rather than being
deleted or duplicated. `AGENTS.md` is loaded into every agent's context, so it should carry the
one-line rule and the link, not the full treatment. (`CLAUDE.md` is a symlink to `AGENTS.md`,
so this is one edit, not two.)

Add `personal-data.md` to the *Further Documentation* list in `AGENTS.md`.

### 8.6 Tripwires — links from the docs people actually read

Each of these is two or three sentences: state the assumption that currently holds, say what
would break it, link to the hub. They are not summaries of the hub; they are alarms.

| Doc | Assumption to state | Why it's the right place |
|---|---|---|
| `docs/bot-protection.md` | Current protection is honeypot + signed timing token + Redis IP counters, and **sets no cookies and stores nothing on the device**. Turnstile/reCAPTCHA/hCaptcha would introduce third-party cookies and a consent requirement. Also: rate-limit keys contain **IP addresses**, which are personal data, retained only for the counter TTL. | It has a *Related documentation* section already. Anyone replacing the honeypot reads this file first. |
| `docs/translations.md` | Language detection order (line 99-105) has "Session preference (persisted across requests)" as step 2 — **this is the one cookie an anonymous front-page visitor can acquire**. It rides the 7-day session cookie. Relies on the *appearance* exception / explicit user choice. | Anyone touching locale persistence, or adding a dedicated `lang` cookie, reads this. Step 3 ("user account language preference — future feature") is a DB field, not a cookie, and is fine. |
| `docs/analytics.md` *(new)* | **We have no analytics, deliberately.** If you are adding it, it must be cookieless and self-hosted (Plausible / Umami / GoatCounter / Matomo-cookieless). Google Analytics is ruled out. Anything that sets a cookie or reads the device requires a full opt-in consent banner, because we are hosted in the EU. | A doc for a thing that does not exist is exactly right here: it is a tripwire. The person who greps `docs/` for "analytics" before adding it is the person we need to catch. |

Two further candidates, weaker, worth a line each if cheap:

- `docs/configuration.md` — where `SESSION_*` / `REMEMBER_COOKIE_*` are documented; a pointer
  saves someone lengthening a cookie lifetime without thought.
- `docs/frontend_security.md` — the CSP allowlist is where a third-party script gets waved
  through (§2.4).

### 8.7 `sf-code-review` — make it a standing check

Add a bullet to *Things to Check* in `.claude/skills/sf-code-review/SKILL.md`:

> - Does the change touch cookies, sessions, logging of personal data, analytics, third-party
>   scripts, or data retention? If so, check it against `docs/personal-data.md` — especially the
>   "what would change the answer" list.

This is the piece that makes the whole structure self-enforcing rather than aspirational. The
tripwires catch someone who reads the docs; the review check catches someone who doesn't.

Worth being honest about the limit: the skill's instructions say "if the diff is big, consider
giving each of the Things to Check to a subagent", so this bullet must be self-contained enough
to hand to a subagent with no other context. Phrasing it as "check the diff against this named
file" rather than "consider privacy implications" is deliberate.

### 8.8 Scope and sequencing

Explicitly **not** in scope: any banner, any consent cookie, any JS.

**Sequencing gate (§9 D6):** the draft implementation can proceed now, but the branch must not
merge until someone legally qualified has signed off the conclusion. Practically: build it,
open the PR, mark it draft or block the merge, and get the sign-off in parallel.
`docs/personal-data.md` should carry the sign-off status so the record travels with the code.

Separately, and I'd argue more urgently: **self-host the jsDelivr assets** (§2.4). Hamish is
raising this himself (§9 D7); it is out of scope for this issue.

### 8.9 Risks

**A hub that rots.** The obvious failure mode is that `personal-data.md` becomes a grab-bag
nobody maintains, and the tripwires point at something stale. Mitigations, in order of how much
I trust them:

1. **The `sf-code-review` bullet** (§8.7) — the only one with teeth, because it runs on every
   review.
2. **The `GET /` no-cookie test** (§8 item 7) — turns one premise into a build failure rather
   than a document.
3. Keeping the hub short, and linking rather than copying, so there is less to rot.

**A cookies page that rots, in another repo.** Hosting on the docs site (§9 D8) trades one
maintenance problem for a slightly worse one. The page must accurately list the cookies we set;
that list now lives outside the repo where the cookies are defined, in a codebase with no
knowledge of `config.py`. Nothing fails when they diverge, and an inaccurate cookies page is a
compliance failure in a way that an inaccurate help page is not.

Two mitigations, both cheap:

- Make `docs/personal-data.md` the **canonical source of the cookie table** (§8.5), and have the
  docs-site page be a copy of it written for a public audience. Then "is the docs site right?"
  reduces to "is `personal-data.md` right?", which the review check (§8.7) already asks.
- Have `personal-data.md` name the docs-site URL and say explicitly: *if you change the cookie
  table here, update the published page too.*

**Loss of translation.** An in-app page would have gone through `_()` and been translated
alongside everything else. The docs site is English-only. So a Hungarian-speaking registrant on
the registration form gets a footer link to an English cookies page. Not a legal defect —
PECR/GDPR require "clear and comprehensive information", with no explicit language mandate, and
nothing here requires consent anyway — but it is a real accessibility regression for exactly the
audience the public form exists to serve. **Accepted deliberately** (§9 D10), and to be recorded
as such in `docs/personal-data.md` so it reads as a decision rather than an oversight.

**The counter-argument to the whole structure**, honestly stated: five documents referring to one
another is more machinery than a two-cookie app deserves. I think it survives on the grounds that
the cost of the tripwires is a few sentences each, and the failure they prevent — shipping Google
Analytics onto a democratic-participation tool hosted in the EU, with no consent mechanism — is
bad enough to be worth a few sentences.

### 8.10 Two things found during implementation

**There is no privacy notice in the app.** Item 5 of the list above assumed one existed. Nothing
under `templates/` mentions privacy; the notice, if there is one, lives on the docs site. So
"add a cookies paragraph to the privacy notice" is a docs-repo task, not a code task, and it is
recorded here rather than silently dropped.

**`REMEMBER_COOKIE_DURATION = 7 days` is set only in `FlaskProductionConfig`** (`config.py:569`),
not in `FlaskBaseConfig`. Outside production the cookie inherits Flask-Login's default of **365
days**. Production is what the public sees, so the "7 days" on the cookies page and on the
remember-me label is accurate for real users, and nothing here is a compliance defect.

But it is a trap. Anyone reading `FlaskBaseConfig` to learn the cookie's lifetime gets the wrong
answer, and a future non-production deployment (a demo or staging instance with real people on
it) would quietly hand out year-long cookies. Moving the setting to `FlaskBaseConfig` would fix
this in one line. It is deliberately **not** done here, because it is outside this issue's
scope — it is flagged in `docs/personal-data.md` and worth its own issue.

**A third, smaller one:** the backoffice footer (`templates/backoffice/components/footer.html`)
also needed the cookies link. §8.3 only named `base.html` and `base_public.html`. The backoffice
is where signed-in users spend their time, so all three footers now carry it. This is the case
§8.2.2 anticipated, and `tests/unit/test_dashboard_feature_flags.py` was updated accordingly.

---

## 9. Decisions

All six open questions raised by this research have been answered by Hamish. Recorded here so
the reasoning survives the branch.

### D1. Option A is approved — cookies page, no banner

Hamish independently read the material and accepts the conclusion. No client or funder
commitment assumes a banner exists.

### D2. If analytics arrives, it will be cookieless and self-hosted

Hamish was already inclined towards cookieless self-hosted analytics, and is happy to commit on
this basis. This turns §7 Path 1 from a recommendation into a **standing constraint**, which is
what makes the "no banner" answer durable rather than a snapshot: the conclusion cannot be
quietly invalidated by someone dropping in a GA snippet, because the constraint is now written
down (§8.5), routed to from `docs/analytics.md` (§8.6), and checked on every code review (§8.7).

Corollary: **Option D (geo-aware consent) is rejected outright**, not deferred.

### D3. The language cookie stays as it is, and gets documented

Agreed: rely on "the user explicitly chose Español, so it forms part of the service they
requested", and document the reasoning rather than re-engineering the session. No code change.
It goes in `docs/personal-data.md` with its rationale, and is flagged from `docs/translations.md`
(§8.6), so that the argument is on record if it is ever
challenged, rather than being reconstructed from scratch under pressure.

### D4. We are firmly on the EU footing — users *and* hosting

Confirmed: people in the EU are a key audience, **and the service is hosted in the EU**.

The hosting fact is new to this analysis and strengthens it. An EU establishment engages EU law
directly, so we are not relying on a scope argument about who our visitors are. Consequences,
now settled rather than assumed:

- The UK DUAA relaxations (statistical purposes, appearance) are **unavailable to us**.
- Every cookie must clear the narrower two-exception ePrivacy test, which §4 shows they all do.
- Any cookie-setting analytics would require **prior opt-in consent**, with no UK escape hatch.

§3.2 has been updated accordingly. This is the fact most likely to be forgotten by a future
contributor, so it is called out explicitly in the permanent doc (§8.2).

### D5. Draft implementation proceeds now, with a documentation hub and tripwires

Per §8. Hamish asked that future work be able to find both the assumptions made and what would
change them — a conclusion is only as durable as the record of its premises. That grew into the
structure in §8.4–§8.7:

- a single canonical `docs/personal-data.md` (named for the GDPR term, *not* `user-data.md`,
  because "User" is a domain aggregate here and registrants are not Users — §8.5);
- short tripwire sections in `docs/bot-protection.md`, `docs/translations.md`, and a new
  `docs/analytics.md`, each stating the assumption its area currently relies on and linking to
  the hub (§8.6);
- a standing check in `.claude/skills/sf-code-review/SKILL.md` (§8.7).

The hub links to `docs/agent/code_quality_rules.md` for the code-level logging rules rather than
absorbing them, to avoid two sources of truth (§8.5).

### D6. Legal sign-off is a merge gate, not a start gate

We may need sign-off before merging the branch; a draft implementation can proceed in parallel.
So: build it, open the PR, hold the merge until someone legally qualified has blessed the
conclusion. `docs/personal-data.md` should record the sign-off status, so nobody downstream
assumes more assurance than we actually have.

I'd still note the asymmetry that motivated the question: the cost of asking is low, and the
cost of being wrong is an ICO complaint against a project whose entire premise is public trust.

### D7. The jsDelivr issue — Hamish will raise it

Out of scope here. Self-hosting govuk-frontend, Alpine and htmx would remove a third-party IP
and referrer disclosure on every page load (§2.4). Not a PECR matter — nothing is stored on the
device — but in my view a larger real-world privacy improvement than anything in this document.

### D8. The cookies page is hosted on the docs site, not served by Flask

Following the User Data Agreement pattern. New config var `HELP_SITE_COOKIES`, default
`https://docs.sortitionlab.org/data-and-legal/cookies/`, threaded through `config.py`,
`context_processors.py`, `env.example` and `docs/configuration.md` (§8.2).

This simplifies the app — no route, no template, no i18n for the page — and keeps legal copy out
of the deploy cycle. It creates two consequences worth naming rather than discovering later:

1. **We can no longer test the page's contents**, because they aren't ours. The mitigation is to
   make `docs/personal-data.md` the canonical cookie table and treat the published page as a
   rendering of it (§8.9). After this, the `GET /` no-`Set-Cookie` assertion is the *only*
   executable check in the entire scheme, which raises its value considerably.
2. **The page will be English-only** where an in-app page would have been translated. Accepted
   and noted (§9 D10).

One implementation detail the pattern hides, in §8.2: `get_help_site_urls()` returns a positional
tuple, which becomes a `NamedTuple` (§9 D9).

### D9. `get_help_site_urls()` becomes a NamedTuple

Agreed to make the change rather than defer it. Design in §8.2.1.

The reasoning that makes this worth doing *now* rather than filing for later: with three
same-typed strings, positional unpacking gets a transposition bug past both mypy and the type
checker silently — you would find out when a footer link pointed at the wrong page. There is
exactly one call site, `NamedTuple` is `typing` stdlib (no new dependency), and it stays hashable
so `@cache` keeps working. Small, contained, and it removes a real class of error.

Two things a reviewer should look at: it introduces the `NamedTuple` idiom to `src/`, which has
none today; and `get_help_site_urls` has no `cache_clear()` in the test suite, unlike its
siblings, which matters if a test wants to vary the URL via the environment (§8.2.2).

### D10. The English-only cookies page is accepted, and noted

Agreed: accept it, note it. The docs site is not translated; a Hungarian- or Spanish-speaking
registrant on the public form gets a footer link to an English page.

Not a legal defect — the information duty is "clear and comprehensive", with no language mandate,
and none of our cookies require consent in the first place. But it is a real accessibility
regression for exactly the audience the public registration form exists to reach: people invited
by post who may not be confident in English.

So it must be **written down rather than quietly accepted**. `docs/personal-data.md` should record
that the published cookies page is English-only, that this was a deliberate trade for keeping
legal copy out of the deploy cycle, and that translating it is the obvious remedy if the language
mix of registrants ever makes it bite. That way the next person to look at this finds a decision,
not an oversight.

### D11. Add a minimal GOV.UK footer to `base_public.html`

Agreed. `base_public.html` has no footer at all — it runs from `<main>` (lines 27-29) straight to
`</body>` (line 43), with no `govuk-footer` markup anywhere (§8.3).

Scope: a minimal GOV.UK footer carrying the cookies link and the User Data Agreement link, and
nothing else. The public registration form should stay uncluttered — it is the one page where
added visual noise costs us completions from people we reached by post.

This is the only item in the plan with meaningful implementation work, and it lands on the most
sensitive template we have, so it deserves its own careful review of the rendered page rather
than being waved through as "add a link".

---

## 10. Sources

**Primary**

- [ICO — What are the exceptions? (storage and access technologies)](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/what-are-the-exceptions/) — the five exceptions, worked examples, "simple means of objecting"
- [ICO — Cookies and similar technologies (PECR guide)](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/cookies-and-similar-technologies/)
- [ICO — Guidance on the use of cookies and similar technologies (PDF)](https://ico.org.uk/media2/kz0doybw/guidance-on-the-use-of-cookies-and-similar-technologies-1-0.pdf)
- [Article 29 Working Party, Opinion 04/2012 on Cookie Consent Exemption (WP194)](https://ec.europa.eu/justice/article-29/documentation/opinion-recommendation/files/2012/wp194_en.pdf) — the canonical EU list of exempt cookie types

**Design system**

- [GOV.UK Design System — Cookie banner](https://design-system.service.gov.uk/components/cookie-banner/)
- [GOV.UK Design System — Cookies page](https://design-system.service.gov.uk/patterns/cookies-page/)

**DUAA 2025 analysis**

- [Bird & Bird — Current UK cookie laws: insights from the final ICO guidance](https://www.twobirds.com/en/insights/2026/current-uk-cookie-laws-insights-from-the-final-ico-guidance)
- [Brodies — Storage and access technologies: ICO publishes updated guidance](https://brodies.com/insights/ip-technology-and-data/storage-and-access-technologies-ico-publishes-updated-guidance-on-the-use-of-cookies-and-other-tracking-technologies/)
- [Stevens & Bolton — The DUAA 2025: cookies, what is changing](https://www.stevens-bolton.com/insights/102mqbh/the-data-use-and-access-act-2025-cookies-what-is-changing-and-what-you-need-t/)
- [Clifford Chance — UK ICO's updated guidance for new exceptions to cookie consents](https://www.cliffordchance.com/insights/resources/blogs/talking-tech/en/articles/2025/09/uk-ico-s-updated-guidance-for-new-exceptions-to-cookie-consents-.html)
- [Burges Salmon — Key insights from the ICO's updated draft cookies guidance following DUAA](https://www.burges-salmon.com/articles/102l7bs/key-insights-from-the-icos-updated-draft-cookies-guidance-following-duaa/)

**EU / UK divergence**

- [Cognisys — Is there a difference between UK and EU GDPR? (2026)](https://cognisys.co.uk/blog/is-there-a-difference-between-uk-and-eu-gdpr-what-changed-in-2026/)
- [CookieChimp — Do analytics cookies require consent? The 2026 answer](https://cookiechimp.com/blog/do-analytics-cookies-require-consent)

**Libraries assessed**

- [Flask-Consent (GitHub)](https://github.com/02JanDal/Flask-Consent) — 11 stars, 12 commits; unmaintained
- [flask-cookies (GitHub)](https://github.com/cccnrc/flask-cookies) — Google Tag Manager oriented
