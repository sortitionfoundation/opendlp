# Stepper component — Manual Test Run Results

**Environment:** Chrome (macOS), logged in as Admin User, base URL `http://127.0.0.1:5615`
**Assembly used for Part B:** Blabla (`76aca524-69ed-4b5e-9e72-6aa5a473b63e`) — has a Published registration page
**Date:** 2026-07-01

---

## Part A — Stepper showcase page

**URL:** `http://127.0.0.1:5615/backoffice/dev/patterns?tab=stepper`

### A1 — Page renders
- ✅ Patterns page loads, no 500.
- ✅ "Stepper" tab present and selected (bold + underlined).
- ✅ Blue 🪜 Stepper info banner visible at top.

### A2 — Tabs-mode example
- ✅ Three steps horizontal: 1 Registration page / 2 Auto-reply email / 3 Preview and publish.
- ✅ Step 1 = green pill + checkmark (done).
- ✅ Step 2 = brand dark-red pill "2", label bold (active).
- ✅ Step 3 = gray pill "3" (inactive).
- ✅ Connector lines present and stretch to fill the row.

### A3 — Wizard-mode example
- ✅ 1 Sign the agreement (done/green), 2 Verify your email (active/red), 3 Choose a plan (dimmed).
- ✅ Step 3 at reduced opacity, default (non-pointer) cursor on hover.
- ✅ Clicking step 3 did not change the URL. DOM confirms it renders as a `<span>` (not a link), so it is genuinely non-navigable.

### A4 — State reference
- ✅ Four rows: active, inactive, done, error.
- ✅ Error step = red pill with "!" and red label.

### A5 — Keyboard navigation (tabs mode)
- ✅ Tab into stepper lands on the active step (step 2) only; outline appears there. Roving tabindex confirmed in DOM (active tab `tabindex="0"`, others `-1`).
- ✅ → moves to next step; ← moves back; Home → step 1; End → step 3.
- ✅ Enter navigates and the URL includes `&step=<key>`.
- ⚠️ **Implementation note:** every arrow/Home/End/Enter press is a *real page navigation* (the URL's `step=` changes and the page reloads), not in-page focus movement. Focus is re-applied after reload via a `#focus=` hash, but re-showing of the outline was **inconsistent**: it reliably reappeared after → (URL gained `#focus=…`), but after ←, Home and End the URL had no `#focus=` hash and no visible outline was restored. Functionally focus/selection lands on the right step; the visible outline is just not always preserved.

### A6 — Focus behaviour (mouse vs keyboard)
- ✅ Mouse click updates the URL; on the showcase page no outline appeared on the clicked step after navigation.
- ✅ Pressing Tab afterwards does show the outline on the focused step.

### A6b — Route-change / focus-preservation
- **Browser + OS tested:** Chrome (macOS) only — Windows Chrome and Firefox are not reachable from this environment, so those rows are unverified.
- Mouse click → `#focus=` fragment in URL? **No** on macOS Chrome (final URL was e.g. `?section=email` / `&step=two` with no `#focus=` hash).
- Visible outline after mouse-click navigation without keyboard? **Yes, intermittently.** On the *real* registration page a pure mouse click on a freshly-loaded page repeatedly produced a focus outline on the destination step (clearest on step 2). It did **not** appear on the showcase page and was inconsistent for step 3. See Issue #1.
- Keyboard (Tab→Enter) outline on destination? ✅ Yes (expected).
- `document.activeElement` after a mouse click: it is **the clicked link (`<A>`)**. Control test: arriving at the same URL by typing it in the address bar leaves `activeElement = <body>` with no outline. So the outline only appears when arriving via a link click, because the destination link is re-focused — exactly the precondition the hypothesis describes.

### A7 — Screen-reader semantics (verified via DOM inspection)
- ✅ Tabs mode: container `role="tablist"`; each step `role="tab"`; `aria-selected="true"` on the active step, `"false"` on the others.
- ✅ Wizard mode: container `role="list"`; active step has `aria-current="step"`; disabled step is a `<span>` with `aria-disabled="true"` and is not in the tab order.
- ⚠️ Minor: the tabs-mode `<tablist>` container had no `aria-label` on the rendered showcase example (the macro is called with `aria_label="Registration setup steps"` in the code sample, but the attribute wasn't present on the element). Low impact, but worth confirming the label is emitted.

---

## Part B — Assembly Registration tab

**URL:** `http://127.0.0.1:5615/backoffice/assembly/76aca524-69ed-4b5e-9e72-6aa5a473b63e/registration`

- **B1** ✅ Loads (no 500); three-step stepper above "Registration Form HTML"; step 1 active (red pill, bold), steps 2/3 gray.
- **B2** ✅ No `?section=` → HTML editor + Assets panel visible; "Published" status badge renders next to the title.
- **B3** ✅ Click step 2 → `?section=email`; editor/Assets hidden; "Auto-reply email" placeholder with the exact "Coming soon — …after registering." copy; step 2 active, step 1 inactive.
- **B4** ✅ Click step 3 → `?section=preview`; "Preview and publish" placeholder with a Coming-soon message; step 3 active, 1 & 2 inactive.
- **B5** ✅ Click step 1 → `?section=form`; editor + Assets panel back; "Show Form Skeleton" modal opens correctly → Alpine controller re-initialised.
- **B6** ✅ Direct URL `?section=email` → email placeholder, step 2 active; `?section=preview` → preview, step 3 active; `?section=nonsense` → falls back to the form with step 1 active (URL keeps `nonsense` but content is the form).
- **B7** ⚠️ **Not tested — blocked.** Both existing assemblies (Blabla, and Citizens' Assembly on AI) already have a Registration page created, so there is no "not
