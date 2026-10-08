# Public pages redesign — GOV.UK → OpenDLP design system

The public-facing pages still run on GOV.UK Frontend while the backoffice has moved
to the OpenDLP design system (design tokens + Tailwind + Pines UI, showcased at
`/backoffice/showcase`). This document is the concept and migration plan for retiring
GOV.UK from the **public account journey** — signup, login, password flows, landing.
The signup page (ticket **1053**, branch `1053-signup-redesign`) is the first chunk.

**Terminology + scope boundary (clarified with Hamish, 2026-10-08):** the
*signup/account-creation* form (organisers creating an OpenDLP account) is not the
same as the *registration* forms (assembly respondents registering for an assembly,
`templates/register/*`). The **respondent registration forms stay on the GOV.UK
design system long term** — it is the most usable for the widest range of people,
and respondents are the widest-range audience this product has. They are out of
scope for this migration, permanently, not deferred.

- **Figma (public design):** https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=5570-7007&m=dev
  (signup frame; further public frames live in the same file)
- **Current working branch:** `1053-signup-redesign`, based on the (unmerged)
  `919-google-login` branch — the unified SSO + email registration form (draft PR #322).
- **Worktree:** `/Users/macintosh/Sites/opendlp-worktree-1053-signup-redesign`

## The concept (agreed 2026-10-02)

GOV.UK Frontend is retired from the public **account** pages **incrementally, page
by page** (the respondent registration forms are exempt — see the scope boundary
above). During the transition users will see two design systems across one journey —
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
- GOV.UK is **not** fully deleted at the end: the respondent registration forms
  keep it for good (see scope boundary above), so `base_public.html`,
  `css/application.css` and `js/vendor/govuk-frontend.js` live on for that journey.
  What eventually goes is GOV.UK on the *account* pages: `base.html` (once nothing
  extends it) and whichever `govuk_*` macros only those pages used.

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

(The error pages `errors/400|403|404|413|500.html` are seen by both audiences and
**stay GOV.UK** with the respondent journey — decided 2026-10-08.)

**Respondent registration journey (`base_public.html`, chrome-less)** — **stays
GOV.UK long term, out of scope** (see the scope boundary at the top; decided with
Hamish on PR #331):

- `register/form.html`, `register/closed.html`, `register/thank_you.html`,
  `register/thank_you_default.html`
- These keep `base_public.html` and the GOV.UK assets indefinitely. Multi-reg-page
  work continues on them in GOV.UK style (branch
  `830-multiple-reg-pages-frontend-stable`).

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
5. ~~Error pages~~ — **stay GOV.UK** (decided 2026-10-08): respondents see them,
   so the same widest-audience argument applies as for the registration forms.
6. **Partial teardown** — once the account journey has migrated: delete
   `base.html` (when nothing extends it) and the `govuk_*` macros only the account
   pages used. `base_public.html`, `css/application.css`,
   `js/vendor/govuk-frontend.js` and the GOV.UK agent docs **stay** — the
   respondent registration forms keep using them for good.

Each phase is a normal ticket/PR; this document gets a session-log entry and an
updated inventory as pages move over.

## Shared infrastructure (built in phase 1, reused by every phase)

### `templates/public/base.html` (built, 2026-10-02)

The `templates/public/` folder marks the post-GOV.UK public design; migrated pages
extend `public/base.html` **and must live in this folder**: `tailwind.config.js`
scans only `templates/backoffice/` and `templates/public/`, so a migrated page kept
under e.g. `templates/auth/` would have its utility classes purged from the CSS
build. Migrating a page therefore also moves its template (e.g.
`auth/register.html` → `public/register.html`) and updates the route's
`render_template` call.

The layout `extends "backoffice/base.html"` — despite its name that template is the
design-system shell (token CSS, compiled Tailwind, CSP Alpine, shared JS incl.
`utilities.js`), and extending it keeps the asset list in one place; giving it a
neutral name is teardown-phase work. On top of the shell the public layout adds:

- Minimal public header via the existing `navigation()` macro (Sortition logo →
  `main.index`, help icon → `help_site_home`, no account menu) — exactly the Figma
  public chrome.
- Centered content column (`max-w-xl`), page background `--color-bg-secondary`
  (inherited from the shell, matches the Figma).
- Flash messages via `floating_alerts()` (design-system alerts, aria-live).
- `footer(show_data_agreement=true)` — the footer macro gained an optional User
  Data Agreement link (public pages show it; backoffice keeps it in the account
  menu).
- Skip-link (`sr-only focus:not-sr-only`) and `site_banner_text` banner parity
  (banner comes from the shell).
- Blocks: `title`, `content`; per-page scripts (e.g. Turnstile) go in the inherited
  `head` block. htmx comes along from the shell — unused by plain form posts,
  accepted for the single-source asset list.
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

1. ~~Build `templates/public/base.html`~~ — **done 2026-10-02** (see shared
   infrastructure above).
2. ~~Migrate `auth/register.html` → `templates/public/register.html`~~ — **done
   2026-10-02**. Decisions made during the migration:
   - **SSO buttons moved to the top of the form** (Figma order), above the shared
     invite field; `test_register_page_orders_sso_before_shared_and_email_fields`
     (renamed) asserts the new order. The hidden email default-submit stays first
     in the form, so Enter still never starts OAuth.
   - The SSO buttons are `button(variant="secondary", leading_icon=brand_*())` with
     visible labels "Google"/"Microsoft" and aria-labels "Create an Account with
     Google/Microsoft" (kept for BDD/component-test selectors and accessibility).
   - **First/Last name moved under "Tell us a little about yourself"** (per Figma;
     they are optional in the form). They render always; the survey questions stay
     gated by `show_questions`. Existing section msgids kept to avoid
     retranslation.
   - Survey fields render via `templates/public/_survey_fields.html` (design-system
     twin of the deleted GOV.UK macro), full-width in spec order — the Figma's
     org-name/org-size two-column pairing was skipped to keep the macro generic
     over `SIGNUP_SURVEY_QUESTIONS`.
   - `process_plan` renders as a **radio group** (the form's field type); the Figma
     shows a select — follow-up only if product wants the field type changed.
   - **No beta-notice checkbox**: the form has no such field; needs a product
     decision + backend field first (resolved open question).
   - No `0/200` char counter on the textarea yet (field allows 2000 chars; Figma
     shows 200) — polish follow-up.
   - Dot-arch illustration vendored as `static/img/join-arch.svg` from
     sortitionfoundation.org (the Figma node is literally named
     `img_join-home.svg`; Figma asset export was unavailable without edit access).
   - Old `templates/auth/register.html` and
     `templates/components/signup_survey_fields.html` deleted;
     `govuk_password_input.html` stays (other auth pages still use it).
   - New msgids: "Create an account to OpenDLP", "Open Democratic Lottery",
     "Create an account with", "OR" (catalogues regenerated). The h1 copy is taken
     verbatim from the Figma — the "to OpenDLP" grammar is a design-copy question.

   The original section-by-section intent, for reference:
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

### Open questions (remaining)

- h1 copy "Create an account to OpenDLP" — taken verbatim from Figma; grammar
  ("to" vs "on"/"for") is a design-copy call.
- Beta-notice checkbox: needs a product decision + a form/backend field before it
  can render.
- Textarea char counter and org-name/org-size two-column pairing — visual polish
  follow-ups if wanted.
- `process_plan` field type: radio (current form) vs select (Figma).

## Session log

- **2026-10-08 (judgment calls + fixes)** — Gergő decided: error pages **stay
  GOV.UK** (respondents see them); the Figma's beta-notice checkbox is **dropped
  from the design** (the data agreement covers consent — Figma frame to be
  updated); the comment limit **stays 2000** (the frame's 0/200 to be corrected);
  the ~70 KB unused JS payload on the public page is **accepted for now** — the
  proper fix belongs to the future neutral shared base layout. Implemented on the
  branch: all validation errors per field now render (errors | join, replacing
  first_error at the signup call sites), the char counter server-renders the real
  initial count, and the chooser/name/org grids stack on small screens with the
  chooser column count following the enabled provider count.

- **2026-10-08 (approved review fixes)** — The three fixes Hamish approved on
  PR #331: process_plan choices reworded to answer the new question ("Planning
  one within the next 3 months/year"; keys unchanged); hint/error
  aria-describedby + aria-invalid wiring added to the `input()`, `textarea()`
  and `checkbox()` macros (design-system-wide fix — `select()`/`radio_group()`
  still unwired, noted for the macro-cleanup follow-up); chooser labels
  "Google"/"Microsoft" wrapped in `_()` again.

- **2026-10-08 (scope boundary)** — Per Hamish's PR #331 review and Gergő's
  clarification: *registration* forms (assembly respondents, `templates/register/*`)
  stay GOV.UK **long term** — usability for the widest audience; only the
  *signup/account* journey migrates to the design system. Plan reworded throughout:
  respondent journey moved from "phase 6" to permanently out of scope, and the
  teardown phase became partial (GOV.UK assets live on for respondent pages).

- **2026-10-06 (Hamish's review feedback)** — Applied from sc-1053 comments:
  title → "Create an account" (Hamish's preference; "to OpenDLP" grammar), the
  subtitle spells out "Open Democratic Lottery Platform" (existing msgid), and
  the required star moved from the Data Agreement legend to the checkbox label
  (the `checkbox()` macro gained a `required` arg). The optional invite-code
  field is now **hidden under open signup** unless a code is in play (arrived
  via `/auth/register/<code>`, submitted, or errored) — the full invite-URL
  flow (disabled prefilled field, maybe email too, admin copy-URL feature) is
  a follow-up branch, elaborated in `docs/agent/invite-url-signup/plan.md`.

- **2026-10-05 (names required)** — Gergő reversed the earlier "keep optional"
  decision: First/Last name are now **required** (per the Figma's asterisks).
  `DataRequired()` added to both fields, `relax_for_oauth()` extended to relax
  them for the Google/Microsoft paths (provider supplies names), the obsolete
  "Optional — your first/last name" descriptions removed (this also resolves the
  review finding about their dropped hints), `required=true` asterisks on the
  template inputs, and the BDD registration steps now fill the name fields.
  Full unit+component+e2e (3320) and the 15 registration BDD scenarios pass.

- **2026-10-05 (Figma v2 field sync)** — The Figma frame gained field changes;
  mapped them onto the working form (Gergő confirmed the four conflicts):
  - **Survey spec** (`SIGNUP_SURVEY_QUESTIONS` — single source, keys unchanged so
    stored answers survive): `location` relabelled "Which country are you in?"
    (stays free text — a country dropdown is a follow-up pending a country-data
    source decision) and moved after `organisation_size`; `organisation_size`
    relabelled "Size of the organisation"; `process_plan` changed RADIO → SELECT
    and relabelled "Where are you in your plans for running a deliberative
    process?" (choices unchanged). Reworded msgids lose their HU translations
    until retranslated.
  - **Field order**: email → password → confirm → First/Last name (names moved
    below the passwords, still inside the email-only reveal, still optional —
    the Figma's required marks were declined to avoid a backend validation
    change); organisation name + size pair in a two-column grid (handled in
    `public/_survey_fields.html`, which now exposes a single-field
    `survey_field()` macro).
  - **Char counter**: live `n/2000 characters` under the comment textarea via a
    new `charCount` Alpine component (`src/js/components/char-count.js`, in the
    backoffice bundle) + `maxlength`; the max comes from the field's Length
    validator, NOT the Figma's 200 — tightening the limit would be a backend
    change nobody asked for.
  - **Kept against the Figma** (decisions): the method chooser (Figma still
    draws the pre-chooser SSO-on-top + OR layout), the invite-code field (absent
    from the frame but functionally required), optional names, free-text country.
    Beta-notice checkbox still unrendered (no form field).

- **2026-10-05 (rebase + chooser port)** — `919-google-login` was rebased onto newer
  main and gained `68b0ec55`: a **signup-method chooser** (user testing found the
  combined form confusing) — Google / Microsoft / Email toggle buttons at the top;
  choosing one reveals only that method's fields and its submit button at the foot;
  progressive enhancement via the CSP-safe `registrationMethod` Alpine component;
  the route passes `selected_method` so error re-renders reopen the submitted
  method. This branch was rebased onto it (`--onto`, six commits replayed) and the
  chooser **ported into the redesigned page**, superseding step 2's "SSO submits at
  the top + OR divider" layout (and that part of the Figma frame). Port decisions:
  - Chooser options are `button(variant="secondary")` with
    `.registration-method-option` + an `[aria-pressed="true"]` style in
    `static/backoffice/src/main.css`; the chooser is `x-cloak` (no-JS shows all
    fields and all submits — same fallback as the base branch's version).
  - First/Last name moved into the email-only reveal (the provider supplies them
    for SSO) — they are no longer under "Tell us about yourself", which now renders
    only when `show_questions`.
  - `registrationMethod` is registered in the **backoffice** Alpine bundle (the
    public layout loads that one) and removed from the GOV.UK bundle; the base
    branch's GOV.UK chooser SCSS (`.js-only`, `.registration-method-*` in
    `application.scss`) was removed as dead once the old template went.
  - Footer: upstream main (`d58890cb`) added the User Data Agreement link
    unconditionally, so the `show_data_agreement` footer arg from step 1 was
    dropped during the rebase.
  - Verified: 82 register component/e2e tests + 15 BDD scenarios pass; chooser
    toggling confirmed in the browser with fake OAuth client IDs (local env has
    none, so BDD never renders the chooser — browser check is the only live
    coverage of the toggle; the CSP Alpine vendor build does evaluate the
    `method === '...'` bindings).

- **2026-10-02 (step 2)** — Register page migrated to
  `templates/public/register.html` on the public layout; route updated; GOV.UK
  register template + survey macro deleted; ordering test updated to SSO-first;
  catalogues regenerated. Verified: register-related component/e2e suites pass
  (83 tests), visual check against the Figma on a local run (invite-required
  variant; SSO buttons verified by tests — local env has no OAuth client IDs).
  BDD: all 15 scenarios in `test_login.py` + `test_email_confirmation.py` pass —
  after fixing a latent bug the migration surfaced: the decorative
  `.checkbox-box`/`.radio-circle`/`.switch-track` spans swallowed pointer events,
  so Playwright's `check()` on the native input timed out; fixed with
  `pointer-events: none` on the decorative layers in
  `static/backoffice/src/main.css`. Remaining verification debt: accessibility
  pass pending.
- **2026-10-02 (later)** — Phase 1 step 1 done: `templates/public/base.html` created
  (extends the design-system shell, reuses `navigation()`/`floating_alerts()`/
  `footer()`); `tailwind.config.js` now also scans `templates/public/`; footer macro
  gained `show_data_agreement`. Smoke-tested: renders with zero `govuk` strings and
  all design-system assets present; `sr-only`/`max-w-xl` utilities confirmed in the
  rebuilt CSS. Next: step 2, migrate the register page to
  `templates/public/register.html`.
- **2026-10-02** — Branch + worktree created from `919-google-login` (`dd783dbd`);
  `npm ci` + `generated_version.txt` done. Evaluated the Figma signup frame vs
  `/backoffice/showcase`: same design system, differences are page chrome only.
  Concept agreed: per-layout design system, GOV.UK fully absent from migrated pages,
  incremental page-by-page migration starting with signup. This plan written.
  Implementation not started.
  Side observation: on the live showcase, the Input section's *preview* rendered
  blank while its DOM was fully present (likely a lazy-render quirk when jumping via
  the section dropdown) — unrelated, worth a look sometime.
