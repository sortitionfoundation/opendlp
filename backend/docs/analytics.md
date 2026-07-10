# Analytics

**OpenDLP has no analytics. This is deliberate, not an oversight.**

If you are here because you are about to add some, read this first, then read
[docs/personal-data.md](personal-data.md).

## The constraint

Any analytics added to OpenDLP **must be cookieless and self-hosted** — Plausible, Umami,
GoatCounter, or Matomo in cookieless mode. These set no cookies and store no device
identifier, so they trigger no consent requirement in either the UK or the EU, and the data
stays ours.

**Google Analytics is ruled out**, on two independent grounds: it requires prior opt-in
consent from our EU users, and shipping Google tracking on a democratic-participation tool is
not consistent with what this project is for.

**Anything that sets a cookie or reads the device requires a full opt-in consent banner.**
We are hosted in the EU, and there is no analytics exception under EU ePrivacy law — the UK's
2025 relaxation does not reach us. That is true even of a self-hosted tool, if it sets a
first-party cookie.

## Why this is written down

The "we need no cookie banner" conclusion in [docs/personal-data.md](personal-data.md) rests on
having no analytics cookies. Dropping in a snippet would invalidate it silently: nothing would
fail, no test would go red, and we would be out of compliance without anyone noticing.

So the constraint lives here, where someone who greps `docs/` for "analytics" will find it
before they find the lawyer.

Full reasoning, including what each analytics path would cost us:
[docs/agent/656-cookies/research.md §7](agent/656-cookies/research.md).

## Related documentation

- [docs/personal-data.md](personal-data.md) — cookies, logging, and erasure
- [docs/frontend_security.md](frontend_security.md) — the CSP allowlist, which is where a
  third-party script gets waved through
