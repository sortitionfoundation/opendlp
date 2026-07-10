# Cookie consent — research

**Issue:** #656
**Status:** Research complete, awaiting decision from Hamish
**Date:** 2026-07-10

---

## TL;DR

**We almost certainly do not need a cookie consent banner today.** Every cookie OpenDLP
currently sets falls within a statutory exception to the consent requirement, in both the UK
and the EU.

What we *do* need is a **cookies page** and a link to it from the footer. That is a
static-content task, not an engineering one.

Two findings worth flagging up front:

1. **The bot protection does not use cookies at all.** The assumption in the issue is wrong
   (details in [§2.3](#23-correction-bot-protection-uses-no-cookies)). It is honeypot form
   fields, a signed timestamp embedded in the HTML, and Redis counters keyed on IP address.
   Nothing is stored on the user's device.
2. **The front page sets no cookie for an anonymous visitor** — verified empirically, not just
   by reading the code. But `/?lang=es` *does* set one, which is the only cookie in the whole
   app that needs anything beyond a plain factual disclosure.

Recommended option: **Option A — cookies page, no banner** (see [§6](#6-options)).

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

| Cookie | Set by | When | Lifetime | Prod attributes |
|---|---|---|---|---|
| `session` | Flask-Session | On CSRF token generation, `flash()`, `?lang=` selection, 2FA, OAuth start | 7 days (`PERMANENT_SESSION_LIFETIME`, `config.py:400`) | `Secure`, `SameSite=Lax`, `HttpOnly` (`config.py:561-562`) |
| `remember_token` | Flask-Login | Only when the user ticks "remember me" at login | 7 days (`config.py:566`) | `Secure`, `SameSite=Lax`, `HttpOnly` (`config.py:564-565`) |

Notes:

- `SESSION_TYPE = "redis"` (`config.py:509`) means the session *payload* lives in Redis, but a
  browser-side cookie carrying the session id is still set. Server-side sessions do not avoid
  the cookie.
- **There is no separate CSRF cookie.** Flask-WTF stores the CSRF secret inside the Flask
  session (`WTF_CSRF_COOKIE` / double-submit mode is not configured). So CSRF protection is a
  *reason the `session` cookie gets set*, not a cookie of its own.
- **There is no language cookie.** The chosen language is stored under the `"language"` key
  *inside* the session (`extensions.py:132`).
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

| Use case | Cookie set? | Why |
|---|---|---|
| **Anonymous visitor browsing the front page** | **No** | `main.index` renders no form, emits no flash, writes nothing to the session. `get_flashed_messages()` on an empty session is a read-only no-op. |
| **Anonymous visitor on the registration page** | **Yes — `session`** | `GET /register/<slug>` calls `generate_csrf()` (`registration.py:82`), which writes the CSRF token into the session. This is CSRF protection, not bot protection. |
| **Signed-in user** | **Yes — `session`**, plus `remember_token` if they opted in | Authentication. |

Two caveats that flip the front-page answer:

- Arriving at `/?lang=es` writes `session["language"]` and therefore sets the cookie.
- Landing on `/` via a redirect that queued a `flash()` message sets the cookie.

Neither changes the legal conclusion, but both mean *"the front page never sets a cookie"* is
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

The one thing the registration page *does* set a cookie for is **CSRF**, which is squarely
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

Importantly, the rule bites on the *storage*, regardless of whether the data is personal.

### 3.1 UK — PECR as amended by the DUAA 2025

The Data (Use and Access) Act 2025 amended PECR with effect from **5 February 2026**; the ICO
published final guidance on **29 April 2026**. There are now **five exceptions**:

| Exception | Applies when | Extra conditions |
|---|---|---|
| **Communication** | Sole purpose is transmitting a communication (e.g. session-scoped load balancing) | — |
| **Strictly necessary** | Essential to provide the service the user requests | — |
| **Statistical purposes** ("analytics") | Sole purpose is aggregate statistics about use of *your* service, to improve it | Clear information **and** a simple, free means of objecting |
| **Appearance** | Sole purpose is adapting appearance/functionality to the user's preference | Clear information **and** a simple, free means of objecting |
| **Emergency assistance** | Locating a user who needs emergency help | — |

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
used for more than one purpose, *every* purpose must independently qualify.

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
- **UI-customisation cookies** (e.g. language choice) — *when session-scoped*

**This matters to us.** `SUPPORTED_LANGUAGES` defaults to `en,es,fr,de` (`config.py:477`) and we
ship Hungarian translations. OpenDLP is plainly intended for EU-based assemblies. So we must
satisfy the **stricter EU rule**, and we cannot lean on the UK's new analytics exception for
EU users. Any future analytics decision has to be made on the EU footing, or with geo-based
logic — which is a genuine complexity cost.

---

## 4. Applying the law to our two cookies

| Cookie | Purpose | UK basis | EU basis | Consent needed? |
|---|---|---|---|---|
| `session` — CSRF token on public registration form | "ensuring the security of terminal equipment" / "preventing fraud" | Strictly necessary | Strictly necessary (WP29: user-security cookie) | **No** |
| `session` — CSRF token on any logged-in form | Security | Strictly necessary | Strictly necessary | **No** |
| `session` — authentication after login | "authenticating the subscriber or user" | Strictly necessary | Strictly necessary (WP29: authentication session cookie) | **No** |
| `session` — flash messages | "recording information or selections the user makes" | Strictly necessary | Strictly necessary (user-input cookie) | **No** |
| `session` — `?lang=` language choice | Remembering a language the user explicitly chose | **Appearance** exception → needs info + opt-out | WP29 UI-customisation → strictly necessary **if session-scoped** | **No**, with caveats — see 4.1 |
| `remember_token` — "remember me" | Persistent login | Not strictly necessary — but see 4.2 | Same | **No**, the checkbox *is* the consent — see 4.2 |

### 4.1 The language cookie is the one genuine wrinkle

Two problems, both minor, both fixable without a banner:

- **UK:** the appearance exception carries an information + opt-out duty. The opt-out is
  trivially satisfied: the user can pick a different language, and the value only persists
  because they chose it. But we should say so on the cookies page.
- **EU:** WP29 exempts UI-customisation cookies **when they are session cookies**. Ours rides
  on the 7-day `session` cookie, so it is persistent. WP29 says a persistent
  UI-customisation cookie needs "additional information" to be exempt, not necessarily consent
  — the user has, after all, deliberately clicked a language.

There is a decent argument that a user clicking "Español" has *explicitly requested* the
service of being shown Spanish, which lands it back in strictly-necessary. I would not lose
sleep over this. But it's the one place where a lawyer might quibble, so it's flagged as an
open question ([Q3](#q3-the-language-cookie)).

Note also: language selection is the **only way an anonymous front-page visitor can acquire a
cookie**. Everything else requires them to log in or open a form.

### 4.2 "Remember me" — the checkbox is the consent

The ICO and WP29 both take the view that a **persistent** login cookie is *not* strictly
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
- The two exempt-with-conditions items (language, remember-me) are satisfied by *information*
  and by a checkbox respectively, not by a consent gate.

The GOV.UK Design System agrees with this reading:

> "If your service only uses essential or 'strictly necessary' cookies, you may skip the
> banner. However, you must still inform users about these essential cookies through a
> dedicated cookies page linked in your footer."

And the ICO is clear that even where every cookie is exempt, the **transparency duty under
UK GDPR Articles 13/14 still applies** — users must be told what is stored and why.

There is also a positive argument for *not* having a banner. OpenDLP exists to run democratic
lotteries; its public-facing page is a registration form completed by members of the public who
were invited by post, many of whom are not confident internet users. A consent banner on that
form is friction on the one interaction that matters, in exchange for zero privacy gain. And a
banner that offers no real choice ("Accept" with nothing to reject) is *worse* than none — the
ICO explicitly criticises consent theatre, and it trains users to click through banners that
do matter elsewhere.

---

## 6. Options

### Option A — Cookies page, no banner *(recommended)*

Add a `/cookies` page listing both cookies, linked from the footer. Reword the "remember me"
label. Add a line to the privacy notice.

**Pros**
- Legally correct for what we do today, in both UK and EU.
- Zero friction on the registration form — the interaction we most care about.
- No new dependency, no new JS, no CSP headaches.
- Follows GOV.UK guidance exactly, and matches our existing design system.
- Roughly a day of work, mostly content.

**Cons**
- Someone has to keep the cookies page accurate as the app changes.
- If we add analytics later, we then have to build the banner anyway (but see §7 — we'd have to
  do that under any option).
- Requires the confidence to *not* ship a banner, which can feel exposed if a client asks
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
- Still needs the cookies page anyway, so it is strictly *additional* work, not alternative.

### Option C — A Flask consent library

**Assessment: don't.** The landscape is thin.

| Library | State | Verdict |
|---|---|---|
| `Flask-Consent` | 11 stars, 12 commits, 3 tags, no recent activity | Effectively unmaintained. A toy. |
| `flask-cookies` | Built to wire up **Google Tag Manager** consent modes | Solves a problem we do not have and never will |
| Commercial CMPs (CookieYes, Usercentrics, OneTrust) | Mature | Third-party JS that phones home; ironic on a privacy tool; costs money; CSP pain |

**Pros of a library:** categories and opt-out plumbing for free, *if* we ever need them.

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
- Only worth anything *if* we adopt analytics **and** decide the UK relaxation is worth
  exploiting. Speculative on both counts.
- Geo-IP adds a dependency, and misclassification creates the legal exposure it was meant to
  avoid.
- Complexity is disproportionate for a project with no advertising and no commercial analytics
  motive.

**Verdict:** premature. Revisit only if analytics is actually adopted (§7).

---

## 7. If we add analytics later

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

**Path 3 — Self-hosted analytics that *does* set a first-party cookie** (e.g. Matomo with
cookies on).

- UK: likely fits the new statistical-purposes exception → **information + opt-out**, no
  opt-in banner.
- EU: **no analytics exception exists** → opt-in consent required.
- ⇒ Because we serve EU users, we would be building a full consent banner anyway. The UK
  relaxation buys us nothing unless we also build geo-logic (Option D).

**The asymmetry is stark.** Path 1 costs a banner-free life. Paths 2 and 3 both cost a full
consent mechanism, because of our EU users. So if analytics is ever wanted, **Path 1 is
overwhelmingly the right call**, and it happens to be the one most aligned with what this
project is for.

---

## 8. Proposed implementation (if Option A is approved)

Small, and mostly content:

1. **`/cookies` page** — new route on the `main` blueprint, template using the GOV.UK table
   component. Columns: Name, Purpose, Expires. Two rows. Explain that the session cookie covers
   security (CSRF), sign-in, form messages and language choice; explain `remember_token`;
   explain there is no advertising and no analytics. Must be i18n'd (`_()`), like everything
   else.
2. **Footer link** — from `base.html` *and* `base_public.html`, so the registration form has it
   too. GOV.UK requires this.
3. **"Remember me" label** — confirm it is unticked by default; reword so the cookie
   consequence is explicit.
4. **Privacy notice** — add a cookies paragraph pointing at `/cookies`.
5. **Tests** — a route test for `/cookies` (200, both cookie names present in the rendered
   body), and a test asserting `GET /` emits **no** `Set-Cookie`. That second test is the
   valuable one: it locks in the property this whole analysis rests on, and will fail loudly
   the day someone adds a `flash()` to the front page.

Explicitly **not** in scope: any banner, any consent cookie, any JS.

Separately, and I'd argue more urgently: **self-host the jsDelivr assets** (§2.4). Happy to
raise that as its own issue.

---

## 9. Open questions for Hamish

### Q1. Do you accept the "no banner" conclusion?

It rests on: no advertising, no analytics, no third-party cookies. All three verified in the
code today. If there's a commitment to a client or funder that assumes a banner exists,
that changes the calculus and I should know.

### Q2. Do we need sign-off from someone legally qualified?

I've read the primary sources and I'm confident in the analysis, but I'm not a lawyer, and
"Claude read the ICO website" is not a defensible position in a DPIA. Given the Sortition
Foundation processes fairly sensitive demographic data about members of the public, does the
organisation have a DPO or retained legal advice that should bless this? The cost of asking is
low; the cost of being wrong is an ICO complaint on a project whose entire premise is public
trust.

### Q3. The language cookie

Are you comfortable relying on "the user explicitly clicked Español, therefore it's part of the
service they requested"? The alternative — making the language preference a session-only cookie
rather than riding the 7-day session — would put it beyond any argument under WP29, at the cost
that users re-pick their language each week. I lean towards leaving it and documenting it.

### Q4. Is analytics actually coming?

You said "might be added at some point". If it's genuinely on the roadmap, I'd rather we commit
to a **cookieless, self-hosted** tool now (§7 Path 1) and design the cookies page around that,
than build a banner later. If it's idle speculation, ignore this.

### Q5. Is the EU exposure real?

I've assumed OpenDLP serves EU assemblies, based on `SUPPORTED_LANGUAGES = en,es,fr,de` plus
Hungarian translations. If in fact it's UK-only for the foreseeable future, the analysis gets
*easier* (the DUAA exceptions become available), but I don't think it changes the
recommendation — Option A works under both regimes, which is precisely its appeal.

### Q6. Should I raise the jsDelivr issue separately?

Self-hosting govuk-frontend, Alpine and htmx removes a third-party IP disclosure on every page
load. I think this is a bigger genuine privacy improvement than anything in this document, and
it's a contained piece of work. Want me to open an issue?

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
