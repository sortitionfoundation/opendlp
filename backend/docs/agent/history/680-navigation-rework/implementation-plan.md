# 680 — Navigation Rework: Implementation Plan & Enhanced Spec

**Branch:** `680-navigation-rework`
**Source ticket:** App frame / Assembly detail layout / Footer / Other (Shortcut)
**Figma file:** `WaG38I99ccF8RMy1655fA2` (OpenDLP – UI)

| Design | Node | Link |
|---|---|---|
| App frame (top bar + account dropdown) | `1802:1579` | [figma](https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=1802-1579&m=dev) |
| Assembly detail (page header + sticky tabs) | `2898:2685` | [figma](https://www.figma.com/design/WaG38I99ccF8RMy1655fA2/OpenDLP---UI?node-id=2898-2685&m=dev) |
| Page header component | `2898:2686` | (child of above) |

> Note: the ticket's "Page header" link (`1652:5674`) turned out to be just a **showcase section label** ("Page header" text at 96px), not the component. The real page-header design is the assembly-detail header at `2898:2686`.

---

## 0. Scope decisions (locked with the team — override anything below on conflict)

1. **No status chip in this ticket.** The page header is **back arrow + H1 title only**. The status chip **and** the status-based filtering/toggle on the assembly dashboard are a **separate ticket** — do not build a chip/badge component or dashboard status filter here.
2. **Both the top bar and the page-header+tabs are sticky.** Top bar pinned at `top:0`; page header + tab bar pinned directly beneath it.
3. **Footer removal is deferred.** Keep the footer as-is for now; removing it and relocating its links (GitHub → About OpenDLP, Cookies, version, etc.) is to be discussed with the team and done as the **final, optional step** of this implementation. Because the About OpenDLP page is part of that deferred step, the account dropdown ships **without** "About Open DLP" for now — its live items are My account, Switch to site admin, User Data Agreement, Sign out.

---

## 1. Goals (from the ticket)

**App frame**
- Remove the centre/top navigation links; keep the logo on the left.
- Right side: a **Help** icon → knowledge hub (`democraticlottery.org/knowledge-hub`, does not exist yet) and an **Account** dropdown.
- Account dropdown contains only actions that already work.
- "Switch to site admin" opens in a **new tab** (old design still lives there).

**Assembly detail**
- Replace the breadcrumb with a **Page header** (back arrow + title + status chip).
- Make the page header **including the tab navigation sticky**.
- Remove the "Back to Dashboard" button at the bottom of assembly details.

**Footer**
- Remove the footer entirely; its content moves into the account dropdown.
- GitHub link moves onto the "About OpenDLP" page.

**Global**
- Retire the breadcrumb **everywhere** (all pages). Keep **one instance in the showcase** as the design-system demo.

---

## 2. Design analysis (decoded, with real tokens)

The project renders icons as **inline SVGs** (`viewBox="0 0 24 24"`, `stroke="currentColor"`) written per-component — there is no icon sprite or icon macro. All Figma icons are from **MynaUI** (`icons.mynaui.com`), which use the same stroke style, so we source SVGs from there.

All referenced tokens already exist in `static/backoffice/tokens/{primitive,semantic}.css`:

| Figma value | Primitive token | Semantic alias |
|---|---|---|
| `#90003F` brand-400 | `--color-brand-400` | `--color-primary-action`, `--color-button-primary-bg` |
| `#F7F7F8` neutral-50 | `--color-neutral-50` | — |
| `#E1E2E5` neutral-200 | `--color-neutral-200` | `--color-borders-dividers` |
| `#2F3442` neutral-700 | `--color-neutral-700` | — |
| `#1F2330` neutral-800 | `--color-neutral-800` | `--color-navigation-bars` |

### 2a. Top bar (`1802:1579`)
- White bar, `border-b` using `--color-borders-dividers`, `~px-40 py-8`.
- **Left:** Sortition Foundation **landscape** logo, `h-8` (≈32px). Wraps `logo_href`.
- **Right** (flex, `justify-end`, gap ≈24px):
  - **Help**: `question-circle` icon (24px), icon-only link → knowledge hub (new tab).
  - **Account**: **avatar** (32px rounded circle, brand/navy fill, white initials e.g. "AS") + `chevron-down`, opens the dropdown.
- The old centre links (Dashboard / Site Admin / Sortition Lab / Help) are **gone** from the bar.

### 2b. Account dropdown (`1803:5919`)
White menu, `rounded-4`, shadow, ~4px padding, items `px-8 py-4`, text 13px `--color-neutral-700`, 16px leading icons, thin dividers (`--color-borders-dividers`).

| # | Item | Icon (MynaUI) | Destination | Notes |
|---|---|---|---|---|
| 1 | My account | `user` | `profile.view` | |
| 2 | Switch to site admin | `arrow-up-down` | `admin.index` | **new tab** (`target=_blank rel=noopener`), role-gated (`admin`/`global-organiser`) |
| — | *divider* | | | |
| 3 | User Data Agreement | `brand-trello` | `help_site_data_agreement` | moved from footer |
| 4 | About Open DLP | `folder-two` | About page (new/existing) | now hosts GitHub etc. |
| — | *divider* | | | |
| 5 | Sign out | `upload`/logout | `auth.logout` | |

Items dropped vs. today's chrome: **Sortition Lab** (top nav) and **Cookies / Sortition Foundation / version** (footer) — see Open Decisions §7.

### 2c. Page header (`2898:2686`) — replaces breadcrumb on assembly pages
- Flex row, `gap-16`, `items-center`.
- **Back arrow** (`arrow_back`, 24px, Material style) → back one level (dashboard for assembly detail).
- **H1 title**: Lato SemiBold, 22px, leading-32, `--color-neutral-800` — the assembly title.
- **Status chip**: `bg --color-brand-400`, `px-8 py-2`, `rounded-8`, text 13px Lato Medium, `--color-neutral-50`. Shows assembly status ("Active" in the mock; real values TEST / PUBLISHED / CLOSED — see §7).
- **Below** the header sits the **sticky tab bar** (existing `assembly_tabs`).

### 2d. Sticky region (`2898:2685`)
Page header + tab bar remain pinned below the top bar while page content scrolls.

---

## 3. New UI elements to build (inventory)

Per the ticket workflow — **build in the showcase first, then rebuild the layout**. New/first-class components:

1. **Avatar** (`components/avatar.html`) — circular initials badge, size + fill variants. New.
2. **Account menu** (`components/account_menu.html`) — avatar+chevron trigger → dropdown with icon rows and dividers, role-gated items, new-tab support. Reuses the Alpine open/close + `role="menu"` pattern from `dropdown_button.html`.
3. **Status chip / badge** (`components/chip.html`) — small rounded label with status→variant colour mapping. New (no chip/badge macro exists today).
4. **Page header** (`components/page_header.html`) — back arrow + H1 + optional chip + optional actions slot. New (pages currently hand-roll `<h1>`).
5. **New top bar** — simplified `navigation()` variant (logo left; help + account right). Modify `components/navigation.html` (or add a variant) rather than fork.
6. **Icon set** — inline SVGs sourced from MynaUI: `question-circle`, `user`, `arrow-up-down`, `brand-trello`, `folder-two`, `upload`(logout), `arrow_back`, `chevron-down`. Keep the project convention (inline per use); optionally collect nav icons into a small `components/_nav_icons.html` set of `{% macro %}` helpers to avoid duplication.

---

## 4. Phase 1 — Showcase implementation

For each new component add a demo file under `templates/backoffice/showcase/` and register it in `templates/backoffice/showcase.html` (Components tab + the "Jump to section" `<select>`), using the existing `showcase_section` / `showcase_example` / `showcase_tokens` wrappers.

1. `showcase/avatar_component.html` — sizes (24/32/40), initials, fill variants.
2. `showcase/account_menu_component.html` — live account dropdown (open state, keyboard, dividers, role-gated item shown with a note).
3. `showcase/chip_component.html` — all status variants side by side.
4. `showcase/page_header_component.html` — back arrow + title + chip, with/without actions.
5. Update `showcase/navigation_component.html` to show the **new** simplified top bar (keep the old snippet only if useful for comparison).
6. **Breadcrumb**: keep `showcase/breadcrumb_component.html` as the surviving demo instance (ticket: "keep an instance in showcase").

**Accessibility (required, per `docs/agent/component_accessibility.md`):**
- Account menu: `aria-haspopup="menu"`, `aria-expanded`, `role="menu"`/`menuitem`, Escape + click-outside close, visible focus ring, avatar trigger has `aria-label`.
- Help icon link: `aria-label` (icon-only).
- Back arrow: real `<a>`/`<button>` with `aria-label` ("Back to dashboard").
- Chip: not a control — decorative/text; ensure contrast (white on brand-400 passes).

---

## 5. Phase 2 — Layout rebuild

**`components/navigation.html`** — reduce to: logo (left) + help icon + account menu (right). Drop `nav_items` centre rendering (or keep the arg but render nothing when empty). Compose `avatar` + `account_menu`.

**`base_page.html`** — rewire the frame:
- Replace the current `navigation(...)` call/args with the new signature (logo_href, help_href, account items, current user for avatar/role gating).
- Remove `{{ footer() }}` and its import.
- Remove the `breadcrumb_section` block/slot (see §6).
- Add a **sticky page-header slot**: a new `{% block page_header %}` rendered inside a sticky container so assembly pages can inject `page_header` + `assembly_tabs`.

**Avatar initials** — compute from the user's display name (fallback to email local-part), e.g. a `initials` helper or Jinja filter. Log/PII: initials are derived at render time, never logged.

**Help destination** — point at the knowledge hub. Recommend a config var (e.g. `KNOWLEDGE_HUB_URL`, default `https://democraticlottery.org/knowledge-hub`) alongside existing `help_site_*` config, so the not-yet-live URL is centralised.

---

## 6. Phase 3 — Retirements & sticky

**Retire breadcrumbs** — remove the `{% block breadcrumb_section %}` from all pages that define it, drop the empty slot from `base_page.html`, and keep the macro `components/breadcrumbs.html` + `showcase/breadcrumb_component.html` for the showcase demo only. Pages to edit (18):
`assembly_details`, `assembly_data`, `assembly_targets`, `assembly_respondents`, `assembly_selection`, `assembly_members`, `assembly_registration`, `assembly_edit_respondent`, `assembly_view_respondent`, `create_assembly`, `edit_assembly`, `respondent_field_schema/view`, `respondents/confirm_upload_diff`, `dev_dashboard`, `patterns`, `service_docs`, `showcase` (keep demo section), and any other `block breadcrumb_section` holder found by grep.

**Assembly detail** (`assembly_details.html` and sibling assembly pages):
- Replace the breadcrumb with `page_header(title=assembly.title, back_href=dashboard, chip=status_chip(assembly.status))`.
- Remove the bottom "Back to Dashboard" button (keep "Edit Assembly"); the back arrow now serves that role.
- Move `assembly_tabs` into the sticky page-header region.

**Sticky** — wrap page header + tab bar in a `position: sticky; top: <top-bar height>` container with a background and a bottom border so content scrolls under it cleanly. Decide whether the **top bar** is also sticky (`top:0`) or scrolls away; set `z-index` layering accordingly (top bar > sticky header > content). Verify against the mock's intent.

**Footer removal** — delete the `footer()` call + import; relocate its links:
- GitHub → **About OpenDLP** page.
- User Data Agreement → account dropdown (done in §2b).
- Cookies / Sortition Foundation / version → About page (recommended; confirm §7). **Cookies must stay reachable** for the no-cookie-banner posture (`docs/personal-data.md`).

---

## 7. Open decisions (recommended defaults in **bold**)

1. **Where do Cookies, Sortition Foundation link, and the version string go** now the footer is gone? → **On the "About OpenDLP" page**, together with GitHub. (Cookies must remain reachable.)
2. **Does an "About OpenDLP" page already exist**, or do we create one? → Audit; **create a simple static page** if missing (hosts GitHub, version, Sortition Foundation, Cookies).
3. **Sortition Lab** top-nav link — the new design drops it. → **Remove** it (can live on the About/knowledge hub later).
4. **How users return to the dashboard** without the top "Dashboard" link / bottom button → **logo → dashboard** (global) + **page-header back arrow** (contextual).
5. **Status chip colours** — the mock shows brand-400 for "Active". Real statuses are TEST / PUBLISHED / CLOSED (see registration lifecycle). → Define a **status→variant map** in `chip.html` (e.g. TEST=neutral, PUBLISHED=brand, CLOSED=muted); confirm exact palette with design.
6. **Help URL** — `democraticlottery.org/knowledge-hub` doesn't exist yet. → Ship it behind a **config var** so it's one-line to update; opens in a new tab.
7. **Top bar sticky or not** — ticket only says the *page header + tabs* must be sticky. → **Top bar sticky at `top:0`**, page header sticky beneath it (cleanest), unless design says the bar should scroll away.

---

## 8. File-change checklist

**New**
- `templates/backoffice/components/avatar.html`
- `templates/backoffice/components/account_menu.html`
- `templates/backoffice/components/chip.html`
- `templates/backoffice/components/page_header.html`
- `templates/backoffice/showcase/{avatar,account_menu,chip,page_header}_component.html`
- (optional) `templates/backoffice/components/_nav_icons.html`
- (maybe) About OpenDLP page template + route

**Modified**
- `templates/backoffice/components/navigation.html` (simplified top bar)
- `templates/backoffice/base_page.html` (nav wiring, drop footer, drop breadcrumb slot, add sticky page-header slot)
- `templates/backoffice/showcase.html` (register new demos; keep breadcrumb demo)
- `templates/backoffice/showcase/navigation_component.html` (new top bar)
- `templates/backoffice/assembly_details.html` (+ sibling assembly pages: page header, sticky tabs, remove back button)
- 18 page templates: remove `block breadcrumb_section` (§6)
- `config.py` (KNOWLEDGE_HUB_URL / help URL)

**Kept (demo only)**
- `templates/backoffice/components/breadcrumbs.html`
- `templates/backoffice/showcase/breadcrumb_component.html`

**Removed**
- `templates/backoffice/components/footer.html` (after relocating links)

---

## 9. Cross-cutting requirements

- **i18n**: all new user-facing strings via `_()` / `_l()`; run `just translate-regen` after. New strings: "My account", "Switch to site admin", "User Data Agreement", "About OpenDLP", "Sign out", "Help", "Back to dashboard", status labels.
- **CSP / Alpine**: account menu must follow the CSP-safe Alpine patterns (`x-data` flat props, no string args in `@click`) — see `/backoffice/dev/patterns` and `docs/frontend_security.md`.
- **ABOUTME**: every new template file starts with the 2-line ABOUTME comment.
- **Icons**: source exact SVGs from MynaUI; don't hand-draw paths.
- **Testing**: update/extend BDD (`tests/bdd/`) for nav — account dropdown open/close, help link, page header + sticky, breadcrumb removal, footer removal. Keyboard + ARIA checks per accessibility guide. Run `just test-nobdd && just test-bdd-headless` (never concurrently).

---

## 9a. Implementation status (delivered on this branch)

**Done:** avatar, account_menu, page_header, `_nav_icons`, reworked `navigation` top bar (all with showcase demos + registration); `base_page.html` sticky chrome + account-menu wiring + `KNOWLEDGE_HUB_URL` config/context var; page header + sticky tabs on all assembly pages; removed the "Back to Dashboard" button; breadcrumbs retired across 18 pages (macro + showcase demo kept); removed the retired `Breadcrumb has correct semantic structure` a11y scenario + its step defs. Footer kept (removal deferred). Chip out of scope.

**Testing notes / caveats:**
- Component + unit suites: green across all changed pages; mypy clean on the Python changes.
- **BDD requires `FF_OLD_DEFAULT_DASHBOARD=true` in the spawned server's env.** The repo `.env` sets it to `false`; the `test_server` fixture does `os.environ.copy()` and does not force it, and Flask auto-loads `.env`. Without the export, post-login redirects to `/backoffice/dashboard` while the BDD `_login` helper waits for `/dashboard`, timing out ~75% of scenarios. Run BDD as: `FF_OLD_DEFAULT_DASHBOARD=true FF_DASHBOARD_SWITCH_LINKS=true just test-bdd-headless`. This is pre-existing infra behaviour, unrelated to the nav rework.
- `just translate-regen` still to be run for the new gettext strings.
- **BDD test updates for the redesign:** removed 5 `*displays breadcrumbs` scenarios + the `Breadcrumb has correct semantic structure` a11y scenario (and their now-unused step defs). Replaced the CSP-fragile `page.wait_for_function("window.scrollY > 0")` scroll checks with a CSP-safe CDP poll (`_wait_until_scrolled`). **Skipped** `Entering edit mode preserves the scroll position` (`@skip` + TODO): the Edit control is now top-anchored under the sticky header, so "scroll down then click Edit" legitimately returns to the top — the scenario's premise no longer holds. The `?scroll=` restore mechanism still works; the team should write a layout-appropriate replacement.

## 10. Suggested sequencing

1. Icons + `avatar` + `chip` (leaf components) → showcase demos.
2. `account_menu` (uses avatar + icons) → showcase demo.
3. `page_header` (uses chip + back arrow) → showcase demo.
4. New `navigation()` top bar → showcase demo.
5. Rebuild `base_page.html` (nav wiring, sticky slot, drop footer/breadcrumb slot).
6. Assembly pages: page header + sticky tabs, remove back button.
7. Retire breadcrumbs across the 18 pages.
8. About OpenDLP page (GitHub + relocated footer links).
9. i18n regen, BDD, accessibility pass, verify in-browser.
