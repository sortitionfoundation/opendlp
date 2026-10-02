# Public pages redesign — GOV.UK → OpenDLP design system

The public-facing pages still run on GOV.UK Frontend while the backoffice has moved
to the OpenDLP design system (design tokens + Tailwind + Pines UI, showcased at
`/backoffice/showcase`). This document is the concept and migration plan for retiring
GOV.UK from the **public** pages. The signup page (ticket **1053**, branch
`1053-signup-redesign`) is the first chunk; later chunks migrate the remaining public
pages until the GOV.UK assets can be deleted.

- **Figma (public design):** https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=5570-7007&m=dev
  (signup frame; further public frames live in the same file)
- **Current working branch:** `1053-signup-redesign`, based on the (unmerged)
  `919-google-login` branch — the unified SSO + email registration form (draft PR #322).
- **Worktree:** `/Users/macintosh/Sites/opendlp-worktree-1053-signup-redesign`

## The concept (agreed 2026-10-02)

GOV.UK Frontend is retired from the public pages **incrementally, page by page**.
During the transition users will see two design systems across one public journey —
an accepted trade-off; we prefer shipping page-sized chunks over a big-bang restyle.

The mechanism is **one design system per layout**:

- A new public base layout (`templates/public/base.html`, created in phase 1) loads
  the design-system assets (token CSS + compiled Tailwind + CSP Alpine) and **no
  GOV.UK CSS/JS at all**.
- The existing GOV.UK bases (`base.html`, `base_public.html`) keep serving the
  not-yet-migrated pages unchanged.
- A page migrates by switching which base it extends and swapping its `govuk-*`
  markup for design-system component macros. **Never mix the two stylesheets on one
  page** — they fight each other.
- When the last public page has migrated, the GOV.UK bases, `css/application.css`
  (GOV.UK build), `js/vendor/govuk-frontend.js` and the `govuk_*` component macros
  are deleted.

### One design system, not two (evaluation, 2026-10-02)

The Figma public frames are built from the *same* design system as the backoffice,
not a separate public one. Design variables extracted from the signup frame are the
backoffice token set: `brand-400 #90003f` (primary button), the `neutral-100…800`
scale, the Lato type ramp (`Display-lg`, `Heading-lg`, `Body-sm`, `caption`),
`radius/sm: 4`. Consequences:

- **Reuse the backoffice component macros** (`templates/backoffice/components/`) on
  public pages — the `backoffice/` path is just a template name, importable from
  anywhere. If the name grates once several public pages use them, moving the shared
  ones to `templates/components/` is a mechanical rename, deliberately deferred.
- **No separate public component set and no new showcase tab** — the components are
  identical; a public tab would duplicate the system.
- **No common-ancestor/skin abstraction** — early abstraction for what is a single
  visual language. Any real visual delta between public and backoffice (e.g. page
  background) is a scope class overriding a handful of semantic CSS custom
  properties, never a component fork.
- What is genuinely public-only is **page chrome and small molecules**: minimal
  header (logo + help icon, no account menu), centered narrow content column,
  illustration assets, "OR" divider, password-requirements checklist. These live in
  the public layout / page templates, inline at first, promoted to shared macros only
  when a second page needs them.

## GOV.UK surface inventory (branch point `dd783dbd`)

Templates still extending a GOV.UK base, grouped by journey:

**Public account journey (`base.html`)** — the subject of this plan:

- `auth/register.html` ← phase 1 (ticket 1053)
- `auth/login.html`, `auth/verify_2fa.html`
- `auth/forgot_password.html`, `auth/reset_password.html`
- `auth/confirm_email.html`, `auth/resend_confirmation.html`
- `main/index.html` (public landing)
- `errors/400|403|404|413|500.html` (seen by both audiences)

**Respondent journey (`base_public.html`, chrome-less)** — public, but a distinct
audience (invited assembly respondents, often on mobile):

- `register/form.html`, `register/closed.html`, `register/thank_you.html`,
  `register/thank_you_default.html`
- Multi-reg-page work exists on branch `830-multiple-reg-pages-frontend-stable`;
  coordinate before restyling these.

**Legacy authenticated pages (`base.html`)** — *not* this plan's scope: they are
superseded by the backoffice redesign and leave GOV.UK by being replaced, not
restyled (`main/dashboard.html` + old dashboard behind `FF_OLD_DEFAULT_DASHBOARD`,
`main/create_assembly.html`, `main/view_assembly_base.html`, `profile/*`, `admin/*`).

## Phasing

1. **Phase 1 — signup page (ticket 1053, in progress):** create
   `templates/public/base.html` + migrate `auth/register.html`. Details below.
2. **Login + 2FA verify** — same layout; shares the SSO-buttons molecule with signup.
3. **Password flows** (forgot/reset) and **email confirmation pages** — small forms,
   mostly `input()` + primary button; retire `govuk_password_input.html` when the
   last user goes.
4. **Public landing** (`main/index.html`).
5. **Error pages** — trivial, but wait until the layout is proven; they render in
   failure modes, keep them dependency-light.
6. **Respondent journey** (`register/*`) — own design pass (distinct audience,
   mobile-first); align with the 830 multiple-reg-pages work. May warrant its own
   Figma review before migrating.
7. **Teardown** — delete `base_public.html`, GOV.UK blocks in `base.html` (or the
   file itself once nothing extends it), `css/application.css` GOV.UK build,
   `js/vendor/govuk-frontend.js`, `govuk_*` macros, and the GOV.UK agent docs
   (`govuk_components.md`, parts of `frontend_design_system.md`).

Each phase is a normal ticket/PR; this document gets a session-log entry and an
updated inventory as pages move over.

## Shared infrastructure (built in phase 1, reused by every phase)

### `templates/public/base.html`

The `templates/public/` folder marks the post-GOV.UK public design; migrated pages
extend `public/base.html`. Modelled on `templates/backoffice/base.html`:

- Head: favicon, viewport, title block, `backoffice/dist/main.css`,
  `backoffice/tokens/primitive.css`, `backoffice/tokens/semantic.css`,
  `backoffice/js/alpine-components.js`, `js/vendor/alpine-csp.js` (deferred),
  `js/utilities.js` (password toggle lives there). htmx only if a page needs it —
  plain form posts don't. No `application.css`, no `govuk-frontend.js`.
- Minimal public header per Figma: Sortition Foundation logo (left → `main.index`),
  help icon (right → help site), white background, bottom border.
- Centered content column (signup frame is ~480px wide), page background via
  semantic token (`--color-bg-secondary`, same as backoffice — matches the Figma).
- Flash-message rendering (design-system alert component).
- Slim footer carrying the legally required links from `base_public.html`
  (User Data Agreement, Cookies).
- Skip-link and `site_banner_text` banner parity with the existing bases.
- Blocks: `title`, `content`, `extra_head`, `extra_js` (Turnstile needs `extra_js`).
- CSP-compliant throughout (`csp_nonce` on scripts, CSP Alpine build, no inline
  handlers) — see `docs/frontend_security.md`.

### Component macros and the WTForms adapter pattern

All macros in `templates/backoffice/components/input.html` (`input()`, `textarea()`,
`select()`, `checkbox()`, `radio_group()`, `file_input()`, `switch()`) take primitive
args; adapt WTForms fields at the call site:

```jinja
{{ input(name=form.email.name, value=form.email.data or "",
         error=first_error(form.email.errors), label=form.email.label.text,
         type="email", required=true) }}
```

`button()` in `components/button.html` covers primary/secondary/full-width/icon
variants; `attrs` carries e.g. `name="action" value="google"` for SSO submit buttons.
Password `input()`s render a Show/Hide toggle (`data-toggle-password`), implemented
in `src/js/init/document-actions.js`, bundled into `js/utilities.js`.

Figma element → existing component mapping (from the signup frame, holds for the
other public frames):

| Figma element | Existing component |
|---|---|
| Full-width crimson primary button | `button(variant="primary", full_width=true)` |
| Google / Microsoft SSO buttons | `button(variant="secondary", leading_icon=...)` + `components/brand_marks.html` |
| Inputs (label, required `*`, hint, error) | `input()` |
| Password with show/hide toggle | `input(type="password")` |
| Selects | `select()` |
| Textarea (char counter in Figma) | `textarea()` (counter would be a small addition) |
| Checkboxes | `checkbox()` |

### Build note

`static/backoffice/dist/main.css` is a **built artifact** (gitignored). A fresh
worktree needs `npm ci` in `backend/`, the CSS build (`just run` builds it), and a
`generated_version.txt` before running or testing.

## Phase 1 — signup page (ticket 1053)

### Page-specific current state

`templates/auth/register.html` extends `base.html`, fully `govuk-*` markup.
Behaviour to preserve through the re-skin:

- hidden first submit button (`name="action" value="email"`, visually hidden,
  `tabindex="-1"`, `aria-hidden`) so Enter defaults to the email path instead of the
  OAuth submit buttons — see the comment in the template;
- submit buttons: `name="action"` with values `email` / `google` / `microsoft` (BDD
  steps target the email submit button — the base commit `dd783dbd` just pointed
  them there; keep these attributes);
- `feature('open_signup')` switches the invite-code copy (optional vs required);
- `show_questions` gates the survey block; `password_help` is injected HTML;
- Cloudflare Turnstile widget when `config.TURNSTILE_SITE_KEY` (approved exception,
  `/auth/register` only — keep pre-clearance off);
- `form.hidden_tag()` (CSRF) and `novalidate` stay.

`templates/components/signup_survey_fields.html` renders `form.survey_fields()` by
WTForms field type (RadioField / SelectField / TextAreaField / default input) in
GOV.UK markup — needs a design-system twin emitting `input()`/`select()`/
`textarea()`/`radio_group()`.

`templates/components/govuk_password_input.html` stays for the other auth pages until
phase 3; not used on the redesigned page.

### Steps

1. Build `templates/public/base.html` (see shared infrastructure above).
2. Migrate `auth/register.html`, arranged per the Figma frame:
   1. Dot-arch illustration (asset to export from Figma → `static/img/`), title
      "Create an account to OpenDLP" + subtitle, "Already have an account? —
      Sign in" row (Figma puts it above the form; current page has it below —
      follow Figma).
   2. "Create and account with" SSO section: Google + Microsoft side-by-side
      secondary buttons with brand marks, shown only when the provider is
      configured.
   3. "OR" divider (inline molecule).
   4. Invite code (`input()`, hint depends on `feature('open_signup')`).
   5. Email, password + confirm (`input(type="password")`), password-requirements
      checklist (`password_help`) in design-system typography under the password
      field.
   6. "Tell us about yourself" — new design-system `signup_survey_fields` twin;
      first/last name + org fields in the Figma's two-column grid.
   7. Data Agreement heading + `checkbox()` rows (accept + beta notice per Figma —
      beta-notice only if the form actually has such a field).
   8. Turnstile, then full-width primary "Create Account" submit
      (`name="action" value="email"`), preserving the hidden default-submit trick.
3. Verify:
   - Visual pass against the Figma frame (the dev server in the main checkout holds
     :5000 — run the worktree on another port, and use `localhost` vs `127.0.0.1`
     to dodge the shared logged-in session cookie).
   - BDD registration steps (run with `FF_OLD_DEFAULT_DASHBOARD=true`; the ~11
     auth/OAuth/2FA failures locally are pre-existing).
   - `just test-js`, `just check`, `just translate-regen` + `translate-check` for
     new/changed strings.
   - Accessibility pass per `docs/agent/component_accessibility.md` (focus order
     with the hidden submit, checklist semantics, SSO button names).

### Out of scope for phase 1

- Every other public page (see phasing), backend/form field changes, email
  templates, removing any GOV.UK asset.
- New fields visible in the Figma but absent from the 919 `RegistrationForm` —
  render what exists; service-layer additions are Hamish's side
  (cf. `docs/agent/919-registration-form/backend_plan.md`).

### Open questions

- Layout/folder naming: `templates/public/base.html` proposed — confirm.
- Dot-arch illustration: export from Figma, or does an asset already exist?
- Char counter on the "anything else" textarea (Figma shows `0/200`)? Needs a tiny
  Alpine component if so.
- Beta-notice checkbox in the Figma: does the 919 form have the field? If not, a
  product decision is needed before rendering it.

## Session log

- **2026-10-02** — Branch + worktree created from `919-google-login` (`dd783dbd`);
  `npm ci` + `generated_version.txt` done. Evaluated the Figma signup frame vs
  `/backoffice/showcase`: same design system, differences are page chrome only.
  Concept agreed: per-layout design system, GOV.UK fully absent from migrated pages,
  incremental page-by-page migration starting with signup. This plan written.
  Implementation not started.
  Side observation: on the live showcase, the Input section's *preview* rendered
  blank while its DOM was fully present (likely a lazy-render quirk when jumping via
  the section dropdown) — unrelated, worth a look sometime.
