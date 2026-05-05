# GOV.UK Frontend v5 → v6 upgrade — outstanding work

This document captures the harder part of the v5.14 → v6.1 upgrade. The trivial swaps (pagination class rename, `package.json` bump, CDN bump) are done in a separate commit. What remains is the header migration described below.

## Background

The v6.0 release of GOV.UK Frontend deliberately strips the GOV.UK header component back to the GOV.UK logo only. All in-header navigation features — service name, nav list, mobile menu toggle and its JS — were removed. GDS now expects services to use the separate **Service navigation** component (introduced in v5.4) for service-level navigation, placed inside the page `<header>` alongside the GOV.UK header.

Confirmed against `v6.1.0` source: the header SCSS only ships `govuk-header`, `__container`, `__container--full-width`, `__logo`, `__homepage-link`, `__logotype`, `__product-name`. There is also no longer a `govuk-header` JS module.

## What breaks in our codebase

`templates/base.html` hand-rolls the page header (we don't use the GOV.UK Nunjucks template/macros). The hand-rolled markup uses classes that no longer exist in v6:

- `govuk-header__link` — used on every nav link (10+)
- `govuk-header__link--homepage` — line 38
- `govuk-header__content` — lines 44, 89
- `govuk-header__menu-button` — lines 46, 91
- `govuk-header__navigation` — lines 49, 94
- `govuk-header__navigation-list` — lines 56, 101
- `govuk-header__navigation-item` — multiple
- `govuk-header__navigation-close` — lines 51, 95

The mobile menu also relies on `data-module="govuk-header"` and `govuk-js-header-toggle`, both of which become no-ops because the JS module has been removed.

`src/scss/application.scss` adds Sortition Foundation overrides for several of these classes (`.govuk-header__navigation-list .govuk-header__link`, `.govuk-header__menu-button`, `.govuk-header__navigation-close`, `.govuk-header__navigation`). Those overrides will need re-pointing at whatever classes we end up with after the migration.

## Plan: migrate header navigation to Service Navigation

The recommended approach. Separates the GOV.UK identity (logo) from the service-level navigation, matching current GDS guidance.

### Step 1 — restructure `templates/base.html`

Inside `<header class="govuk-header" …>`:

- Keep the existing logo block (`govuk-header__logo` containing the Sortition Foundation `<img>`).
- Replace the `govuk-header__content` wrapper and its inner `<nav class="govuk-header__navigation">` with a sibling `<div class="govuk-service-navigation" data-module="govuk-service-navigation">` block.

Skeleton (markup only, copy the v6 Service navigation HTML reference for the exact structure):

```html
<div class="govuk-service-navigation" data-module="govuk-service-navigation">
  <div class="govuk-width-container">
    <div class="govuk-service-navigation__container">
      <nav aria-label="Menu" class="govuk-service-navigation__wrapper">
        <button type="button"
                class="govuk-service-navigation__toggle govuk-js-service-navigation-toggle"
                aria-controls="navigation"
                hidden>
          {{ _("Menu") }}
        </button>
        <ul class="govuk-service-navigation__list" id="navigation">
          <li class="govuk-service-navigation__item">
            <a class="govuk-service-navigation__link" href="…">…</a>
          </li>
          …
        </ul>
      </nav>
    </div>
  </div>
</div>
```

Notes:
- The `govuk-service-navigation__item--active` class (already referenced in `application.scss:62`) is the right hook for marking the current page — keep using it, just make sure templates set it.
- The component handles its own mobile menu via the `govuk-service-navigation` JS module, which is included in `all.bundle.min.js` already. `initAll()` in `base.html` will wire it up — no extra script needed.
- Update `base.html:38` to use `class="govuk-header__homepage-link"` on the logo `<a>` (replaces the old `govuk-header__link govuk-header__link--homepage` pair).

### Step 2 — update SCSS overrides in `src/scss/application.scss`

Re-target the Sortition Foundation customisations that currently hook into the removed header classes:

- `.govuk-header__navigation-list .govuk-header__link { color: $dark-grey … }` (lines 66–77) → equivalent rules on `.govuk-service-navigation__link`.
- `.govuk-header__menu-button` styling (lines 80–88, 95–98) → `.govuk-service-navigation__toggle`.
- `.govuk-header__navigation-close` (lines 90–92) → no equivalent needed; the Service navigation component does not have a separate close button.
- `.govuk-header__navigation` show/hide rules (lines 100–118) → the Service navigation handles this internally via `hidden` and JS state; remove the manual rules unless we still need them as a no-JS fallback.

The existing `.govuk-service-navigation` background-colour and `.govuk-service-navigation__item--active` border-colour rules (lines 53–63) stay.

### Step 3 — verify the logo block

`base.html:36–42` is wrapped in `<div class="govuk-header__logo">`. That class survives in v6, so the wrapper is fine. Just change the inner `<a>`'s class as noted above.

### Step 4 — manual visual test

The header structure is heavily customised (white background, burnt-orange border, Sortition logo) so this needs eyeballing. Test:

- Logged-out home page (nav items: Sign in, Create Account, Sortition Lab, Help).
- Logged-in dashboard (full nav including Site Admin when role allows).
- Mobile width (< 48.0625em) — menu toggle should hide/show the list.
- Active page indicator — `govuk-service-navigation__item--active` purple-red underline still shows.
- Focus styles on nav links still match the rest of the site (saffron-yellow background, dark-grey shadow).

### Step 5 — i18n check

Re-run `just translate-regen` if any new translatable strings appear in the new markup. The likely candidates are the same strings already wrapped (`_("Menu")`, `_("Close menu")` etc.) — Close menu may no longer be needed.

## Out of scope (deferred)

- Replacing deprecated `$govuk-link-colour` / `$govuk-link-hover-colour` in `src/scss/_utilities.scss:25,30` with `govuk-functional-colour(link)` / `govuk-functional-colour(link-hover)`. Still works under v6; needed before v7.
- We are not adopting the GOV.UK rebrand (`govuk-template--rebranded` etc.) — Sortition Foundation has its own branding. No action.
