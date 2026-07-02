# Stepper component — manual test plan

Hand this plan to the Chrome Claude extension. Complete each item and tick it off with
✅ / ❌ / ⚠️ (partial). Note any surprises, unexpected screenshots, or console errors
next to the item.

## Environment

- **Base URL**: `http://127.0.0.1:5615`
- **Login**: use an admin account (developer tools tabs are admin-only).
- **Browser**: Chrome, latest.
- **Preconditions**: at least one assembly exists whose Registration page has been
  created. If not, create one from an assembly's *Details* tab first.

## Report format

For each test, report:

- ✅ / ❌ / ⚠️
- One-line observation (what you saw)
- Screenshot **only** when the outcome is unexpected
- Any console errors or accessibility-tree warnings from DevTools

---

## Part A — Stepper showcase page

**URL**: `http://127.0.0.1:5615/backoffice/dev/patterns?tab=stepper`

### A1 — Page renders

- [ ] The Patterns page loads without a 500 error.
- [ ] The "Stepper" tab is present in the tab bar and is currently selected.
- [ ] The blue info banner (🪜 Stepper) is visible at the top.

### A2 — Tabs-mode example (first card)

- [ ] Three steps render horizontally: **1 Registration page**, **2 Auto-reply email**, **3 Preview and publish**.
- [ ] Step 1 has a **green** pill with a **checkmark** icon (done state).
- [ ] Step 2 has a **brand-color** (dark red / brand-400) pill with the number **2** and the label is **bold** (active state).
- [ ] Step 3 has a **gray** pill with the number **3** (inactive state).
- [ ] Connector lines are visible between the pills and stretch to fill the row.

### A3 — Wizard-mode example (second card)

- [ ] Three steps render: **1 Sign the agreement** (done), **2 Verify your email** (active), **3 Choose a plan** (dimmed/disabled).
- [ ] Step 3 appears at reduced opacity and has no hover cursor when hovered.
- [ ] Clicking step 3 does **not** navigate (the URL should not change).

### A4 — State reference (third card)

- [ ] Four rows are visible with labels: *active*, *inactive*, *done*, *error*.
- [ ] The error step shows a **red** pill with an **`!`** and the label is red.

### A5 — Keyboard navigation (tabs mode)

Use the first card's tabs-mode stepper. The stepper opts into **manual activation**:
arrow / Home / End only move focus, they should **not** navigate. Enter/Space
activates.

- [ ] Tab into the stepper — the outline appears **only** on the active step (step 2).
- [ ] Press **→ (Right arrow)** — focus moves to the next step and its outline appears. **The URL must not change.**
- [ ] Press **← (Left arrow)** — focus moves back. **The URL must not change.**
- [ ] Press **Home** — focus jumps to step 1. **URL unchanged.**
- [ ] Press **End** — focus jumps to step 3. **URL unchanged.**
- [ ] Press **Enter** on a focused step — the URL updates to include `&step=<key>` and the page navigates. Focus is preserved and visible on the destination step.

### A6 — Focus behaviour (mouse vs keyboard)

- [ ] Click any step with the mouse. Expected: the URL updates, and **no visible outline** appears on the clicked step after navigation.
- [ ] Now press **Tab** to move focus back into the stepper. Expected: the visible outline **does** appear on the focused step.

### A6b — Suspected route-change / focus-preservation bug

Hypothesis: because each step is a real navigation (a link click that reloads the
page), the stepper uses the `x-focus-preserve` directive. On a **keyboard** click
(Enter on a focused step), the directive appends `#focus=<step-id>` to the URL and
the destination page programmatically calls `.focus()` on the matching element via
the `DOMContentLoaded` handler — this correctly re-shows the outline for keyboard
users. But on browsers/OSes where a **mouse** click *also* focuses the link first
(Windows Chrome, Firefox on any OS), `document.activeElement === el` becomes true
for a mouse click too, the same `#focus=` hash is appended, and after navigation the
programmatic `.focus()` may re-match `:focus-visible` on the destination page —
producing a visible outline that the user did **not** trigger with the keyboard.

Report the following for **each** of Chrome (macOS), Chrome (Windows), and Firefox
(any OS) you can reach — even if just one browser, note which:

- **Browser + OS**: _____
- [ ] After a **mouse click** on step 2, inspect the URL bar before the fragment is
      cleaned up. Does it briefly include `#focus=reg-steps-tab-two` (or similar)?
      Yes / No.
- [ ] After a mouse click has completed navigation, is a visible focus outline
      shown on the newly-active step **without** any keyboard input first? Yes / No.
- [ ] Repeat with the **keyboard** (Tab to a step, press Enter). Outline visible on
      destination? Yes / No (should be **Yes**).
- [ ] Optional: in DevTools Console, run `document.activeElement` immediately
      after a mouse click on the link (before it navigates) — is it the link, or
      is it `<body>`? Report the tagName / class.

If mouse click yields an outline in browsers other than macOS Chrome/Safari, that
confirms the hypothesis: the `focus-preserve` directive should gate on the input
modality (e.g. only append `#focus=` when the click's `event.detail === 0`, which
means a keyboard-generated click) instead of relying on `document.activeElement`.

### A7 — Screen-reader semantics (DevTools → Accessibility panel)

- [ ] In tabs mode, the container element has `role="tablist"`, `aria-label` **is present** on the same element (should equal the value passed to the macro), and each step's link has `role="tab"` with `aria-selected` set to `true` on the active one and `false` on the others.
- [ ] In wizard mode, the container element has `role="list"`, and the active step has `aria-current="step"`. The disabled step has `aria-disabled="true"` and is not in the tab order (`tabindex="-1"` implicitly via `<span>`).

---

## Part B — Assembly Registration tab

**URL**: `http://127.0.0.1:5615/backoffice/assembly/<ASSEMBLY_ID>/registration`

Replace `<ASSEMBLY_ID>` with the UUID of an assembly whose Registration page has
already been created.

### B1 — Page renders and the stepper appears

- [ ] The page loads without a 500 error.
- [ ] Above the "Registration Form HTML" section there is a three-step stepper: **1 Registration page**, **2 Auto-reply email**, **3 Preview and publish**.
- [ ] Step 1 is active (brand-color pill, bold label). Steps 2 and 3 are inactive (gray).

### B2 — Default section is *Registration page*

- [ ] With no `?section=` in the URL (or `?section=form`), the existing HTML editor + Assets panel is visible.
- [ ] The status badge (Test/Published/Closed) still renders next to the section title.

### B3 — Switching to *Auto-reply email*

- [ ] Click **step 2 (Auto-reply email)**. The URL updates to `?section=email`.
- [ ] The HTML editor and Assets panel are hidden.
- [ ] A placeholder card with the heading **"Auto-reply email"** and the message **"Coming soon — you will be able to edit the email respondents receive after registering."** is visible.
- [ ] Step 2 now shows as active (brand-color pill, bold label); step 1 is now inactive.

### B4 — Switching to *Preview and publish*

- [ ] Click **step 3 (Preview and publish)**. The URL updates to `?section=preview`.
- [ ] A placeholder card with the heading **"Preview and publish"** is visible with a "Coming soon" message.
- [ ] Step 3 is active; steps 1 and 2 are inactive.

### B5 — Returning to step 1

- [ ] Click **step 1 (Registration page)**. The URL updates to `?section=form`.
- [ ] The full HTML editor + Assets panel is back and still functional (open a modal like "Show Form Skeleton" to confirm the Alpine controller re-initialised).

### B6 — Direct navigation via URL

- [ ] Manually visit `.../registration?section=email` in the address bar → the email placeholder loads, step 2 is active.
- [ ] Manually visit `.../registration?section=preview` → the preview placeholder loads, step 3 is active.
- [ ] Manually visit `.../registration?section=nonsense` → the page falls back to the form (step 1 active).

### B7 — Stepper does NOT appear when no registration page exists

For this, use an assembly that has **not** had its Registration page created yet.

- [ ] The warning panel "Registration page not created" is shown as before.
- [ ] The three-step stepper is **not** visible on this page (there is nothing to step through yet).

### B8 — Keyboard nav in the real page

- [ ] From the top of the page, Tab through until focus reaches the stepper. Confirm keyboard behaviour matches Part A5 (arrow keys move focus, Enter navigates).
- [ ] Focus outline is only visible on keyboard focus, not on mouse click.

---

## Part C — Cross-cutting

### C1 — No console errors

- [ ] With the DevTools Console open, run through **A2, A5, B3–B5**. Expected: zero uncaught errors or Alpine warnings.

### C2 — CSP compliance

- [ ] In DevTools Console, verify no `Content Security Policy` violations are logged when navigating between sections.

### C3 — Responsive layout

- [ ] Narrow the viewport to ~640px. The stepper should still render horizontally; labels stay on one line (they use `white-space: nowrap`). If wrapping happens, note it as a visual regression.

---

## Summary

At the end of the run, report:

- Total pass / fail / partial counts.
- The three highest-impact issues you found (if any), each with one screenshot.
- Any accessibility concerns from the DevTools Accessibility tree that are not
  already covered above.
