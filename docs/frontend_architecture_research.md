# Frontend Architecture Research

This document captures research on accessible design libraries for the OpenDLP frontend POC.

## Tech Stack Decision

**Chosen stack:** Flask + Jinja templates + Alpine.js

This matches the backend stack and avoids introducing a separate build pipeline or JS framework.

## Requirements

- Pure HTML + Alpine.js (no React/Vue/Svelte)
- Fully accessible (WCAG compliant)
- Works with Jinja templates
- No complex build step required

## Design Library Options

### 1. Headless UI (Alpine.js version)

**Source:** https://headlessui.com/

- From the Tailwind Labs team
- Fully accessible, unstyled primitives (modals, dropdowns, tabs, listboxes, etc.)
- Has an official Alpine.js port
- You bring your own styles
- Handles ARIA attributes, keyboard navigation, focus management

**Pros:**
- Maximum styling control
- Battle-tested accessibility
- Maintained by Tailwind team

**Cons:**
- Requires more styling work
- Fewer pre-built components

### 2. Pines UI

**Source:** https://devdojo.com/pines

- Built specifically for Alpine.js + Tailwind CSS
- Copy-paste components (similar to shadcn philosophy)
- Accessible by design
- No build step - works with CDN

**Pros:**
- Designed for Alpine.js from the ground up
- Pre-styled, ready to use
- Good component variety

**Cons:**
- Smaller community than Headless UI
- Less battle-tested

### 3. daisyUI

**Source:** https://daisyui.com/

- Tailwind CSS plugin
- Works with plain HTML - no JS framework required
- Alpine.js handles interactivity separately
- Good accessibility defaults
- Themeable

**Pros:**
- Very easy to get started
- Nice default themes
- Large component library

**Cons:**
- Accessibility is good but not as rigorous as Headless UI
- Interactivity components need separate Alpine.js implementation

### 4. Flowbite

**Source:** https://flowbite.com/

- Has vanilla HTML + Alpine.js component variants
- Well-documented accessibility features
- Both free and pro components

**Pros:**
- Good documentation
- Alpine.js examples available

**Cons:**
- Some advanced components are paid
- Can feel heavier than alternatives

## Recommendation

For the OpenDLP project, consider:

| Approach | Library | Best For |
|----------|---------|----------|
| Maximum accessibility control | Headless UI Alpine | Complex interactive components |
| Faster development | Pines UI | Rapid prototyping, full pages |
| Simple styling | daisyUI | Basic components, theming |

**Suggested combination:**
- Use **Headless UI Alpine** for complex interactive components (modals, dropdowns, comboboxes)
- Use **daisyUI** or **Pines UI** for basic styling and layout components
- Both work with Tailwind CSS as the styling foundation

## Considerations for GOV.UK Styling

The backend currently uses GOV.UK Design System styling. Options for the frontend:

1. **Continue with GOV.UK** - Use GOV.UK Frontend with Alpine.js for interactivity
2. **Tailwind + accessible library** - More flexibility, may diverge from backend styling
3. **Hybrid** - GOV.UK base styles with Headless UI for complex components

## Architecture Decision

**Hybrid approach chosen:**

| Area | Design System | CSS Foundation | Use Case |
|------|---------------|----------------|----------|
| Public-facing | GOV.UK Design System | GOV.UK Frontend | Citizen registration, public info pages |
| Back-office | Pines UI | Tailwind CSS | Organiser dashboard, admin tools |

**Rationale:**
- Public pages need official, trustworthy appearance for citizens
- Back-office benefits from modern, flexible UI for complex workflows
- Both use Alpine.js for interactivity
- Clear separation prevents style conflicts

## Deployment Architecture Decision

**Single Flask app with folder separation** (chosen over microservices for POC phase):

```
backend/
  src/opendlp/
    entrypoints/
      public/              # GOV.UK blueprints (existing routes)
      backoffice/          # Pines UI blueprints (new)
    templates/
      public/              # GOV.UK templates (existing)
      backoffice/          # Pines templates (new)
    static/
      govuk/               # GOV.UK Frontend assets (existing)
      backoffice/          # Tailwind + Pines assets (new)
```

**Why this approach:**
- Achieves design system separation without microservices complexity
- Auth works out of the box (flask-login, Redis sessions)
- No REST API layer needed initially
- Frontend devs work only in `backoffice/` folders
- **Future-ready:** Clean folder boundaries make extraction to separate service straightforward later

**Migration path to microservices (if needed later):**
1. Add REST API endpoints exposing service layer methods
2. Extract `backoffice/` folders to separate Flask app
3. Backoffice app calls REST API instead of services directly
4. Add separate Docker service

## Design System Foundation

**Component showcase approach:** Custom Flask route (`/backoffice/showcase`) instead of Storybook - keeps tooling simple, no extra dependencies.

**Design token structure:**

```
static/backoffice/
  tokens/
    primitive.css    # Raw values: --color-blue-500, --spacing-4, --font-size-sm
    semantic.css     # Purpose-based: --color-primary, --color-surface, --color-text
  components/
    button.css       # Component tokens + styles (uses semantic tokens)
    card.css
```

**Token hierarchy:**
- **Primitive tokens:** Raw design values (colors, spacing, typography scales)
- **Semantic tokens:** Purpose-based aliases referencing primitives
- **Component tokens:** Live within component files, reference semantic tokens

**Initial atoms (POC):**
- Button (based on Pines UI, customized with tokens)
- Card (based on Pines UI, customized with tokens)

## Implementation Plan

Step-by-step iterations with manual validation checkpoints. Each iteration includes a visual or console-based "hello world" to prove the step works before moving on.

---

### Iteration 1: Folder Structure + Hello World Route

**Goal:** Create the backoffice folder structure and prove it works with a minimal route.

**Changes:**
- Create `src/opendlp/entrypoints/backoffice/__init__.py`
- Create `src/opendlp/entrypoints/backoffice/routes.py` with blueprint
- Register blueprint in Flask app (with `/backoffice` prefix)
- Create `src/opendlp/templates/backoffice/hello.html` (plain HTML, no styling)
- Create `/backoffice/hello` route that renders the template
- Create `src/opendlp/static/backoffice/.gitkeep`

**Visual validation:**
- [ ] Visit `http://localhost:5000/backoffice/hello`
- [ ] See "Hello from Backoffice!" text in browser
- [ ] Existing GOV.UK pages still work
- [ ] No import errors in terminal

---

### Iteration 2: Tailwind Build Pipeline

**Goal:** Set up Tailwind CSS compilation and prove it loads in browser.

**Changes:**
- Add `package.json` in backend root with Tailwind dependencies
- Create `tailwind.config.js` scoped to backoffice templates
- Create `static/backoffice/src/main.css` (Tailwind input file)
- Add npm scripts to build CSS
- Update `hello.html` to load compiled CSS
- Add a Tailwind-styled element (e.g., blue background, white text)

**Visual validation:**
- [ ] `npm install` succeeds
- [ ] `npm run build:css` produces output file
- [ ] Visit `/backoffice/hello`
- [ ] See styled element (proves Tailwind is loading)
- [ ] Browser DevTools shows Tailwind classes applied

---

### Iteration 3: Design Tokens

**Goal:** Create token files and prove they're working in browser.

**Changes:**
- Create `static/backoffice/tokens/primitive.css` with color palette
- Create `static/backoffice/tokens/semantic.css` referencing primitives
- Import tokens into Tailwind input file
- Update `hello.html` to use CSS custom properties from tokens
- Add test elements: one using `var(--color-primary)`, one using `var(--color-surface)`

**Visual validation:**
- [ ] Rebuild CSS succeeds
- [ ] Visit `/backoffice/hello`
- [ ] See elements styled with token colors (not Tailwind defaults)
- [ ] Browser DevTools → Computed shows `--color-primary` resolving correctly

---

### Iteration 4: Base Layout + Alpine.js

**Goal:** Create proper base template with Alpine.js and prove interactivity works.

**Changes:**
- Create `templates/backoffice/base.html` (full HTML document, loads CSS + Alpine.js)
- Create `templates/backoffice/showcase.html` extending base
- Rename route from `/backoffice/hello` to `/backoffice/showcase`
- Add Alpine.js toggle demo: button that shows/hides text
- Remove temporary `hello.html`

**Visual validation:**
- [ ] Visit `/backoffice/showcase`
- [ ] Page has proper document structure (check view source)
- [ ] Click toggle button → text appears/disappears
- [ ] Console log: `console.log('Alpine.js loaded')` on page load
- [ ] No console errors

---

### Iteration 5: Button Atom

**Goal:** Create Button component with Pines UI base, customized with tokens.

**Changes:**
- Create `templates/backoffice/components/button.html` (Jinja macro)
- Add Button section to showcase page
- Render variants: primary, secondary, outline, disabled
- Buttons use semantic tokens for colors

**Visual validation:**
- [ ] Visit `/backoffice/showcase`
- [ ] See all button variants rendered
- [ ] Hover states work (color changes)
- [ ] Focus states visible (keyboard navigate with Tab)
- [ ] Disabled button looks different and isn't clickable
- [ ] Colors match semantic tokens (not Tailwind defaults)

---

### Iteration 6: Card Atom

**Goal:** Create Card component with tokens, compose with Button.

**Changes:**
- Create `templates/backoffice/components/card.html` (Jinja macro)
- Add Card section to showcase page
- Render variants: basic card, card with header, card with actions (using Button)

**Visual validation:**
- [ ] Visit `/backoffice/showcase`
- [ ] See all card variants rendered
- [ ] Card with actions contains working Button components
- [ ] Card colors use semantic tokens
- [ ] Cards have proper spacing/shadows

---

### Iteration 7: Documentation + Cleanup

**Goal:** Polish showcase as living documentation, update project docs.

**Changes:**
- Add "How to Use" code snippets to showcase (copy-paste examples)
- Add section headers and descriptions to showcase page
- Update `backend/CLAUDE.md` with backoffice development instructions
- Update this research doc with completion status

**Visual validation:**
- [ ] Showcase page is self-documenting (developer can learn from it)
- [ ] Code snippets are visible and correct
- [ ] Full app smoke test: GOV.UK pages + backoffice pages all work

---

## Status

| Iteration | Status | Notes |
|-----------|--------|-------|
| 1. Folder Structure | **Complete** | BDD test added: `test_backoffice.py` |
| 2. Tailwind Build | Not started | |
| 3. Design Tokens | Not started | |
| 4. Blueprint + Layout | Not started | |
| 5. Button Atom | Not started | |
| 6. Card Atom | Not started | |
| 7. Documentation | Not started | |
