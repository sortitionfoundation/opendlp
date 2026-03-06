# Replacement Selection - Manual Test Report

**Test Date:** 2026-05-03
**Tester:** Claude (Automated Manual Testing)
**Environment:** Local development server (http://127.0.0.1:5001)
**Browser:** Chrome
**Assembly Under Test:** "My second assembly" (ID: 1e494a8e-6354-4229-b29c-afcf3ac80ebb)
**Secondary Assembly:** "test" (ID: 995a67f1-355a-420c-ac63-6cde93df3642) - No GSheet configured

---

## Summary

| Metric | Count |
|--------|-------|
| Total Test Cases | 24 |
| Passed | 3 |
| Failed | 2 |
| Blocked (Infrastructure) | 16 |
| Skipped | 3 |
| Bugs Found | 2 |

### Key Finding
The Google Sheets integration is non-functional in the current test environment. The "Check Spreadsheet" task fails with `FileNotFoundError`, which blocks 16 of 24 test cases that depend on successful spreadsheet validation. The UI components (navigation, breadcrumbs, buttons, error states) that could be tested independently are generally well-implemented.

---

## Bugs Found

### BUG-001: Invalid Run ID causes infinite polling with console errors (TC-RS-20)
- **Severity:** Medium
- **URL:** `/backoffice/assembly/<id>/replacement/00000000-0000-0000-0000-000000000000`
- **Description:** When navigating to a replacement page with a valid UUID format run_id that doesn't correspond to an actual task, the page shows a "Task Progress" card stuck in "Pending" state with "Processing..." spinner. The Alpine.js polling component generates continuous "Network response was not ok" errors every ~2 seconds in the browser console, and never stops or shows an error to the user.
- **Expected:** Graceful error handling - flash message about invalid task, redirect to replacement page without run_id.
- **Actual:** Page displays indefinitely polling progress card; console fills with repeated fetch errors.
- **Impact:** Poor user experience, unnecessary network requests, console spam.

### BUG-002: Error details not persisted on failed task page revisit
- **Severity:** Low
- **Description:** When a "Check Spreadsheet" task fails (e.g., FileNotFoundError), the error details are shown during initial polling but are lost on page revisit. On revisit, only "Status: Failed" is displayed without the original error message ("Task failed with exception: FileNotFoundError...").
- **Expected:** Error message should be persisted and visible when revisiting the failed task page.
- **Actual:** Only "Status: Failed" shown; "Messages" section shows only "Waiting for task to start..."
- **Impact:** Users who refresh or revisit the page lose context about why the task failed.

---

## Test Case Results

### TC-RS-01: Navigate to Replacement Selection Page ✅ PASS

**Steps Executed:**
1. Navigated to assembly Selection tab
2. Located "Replacement Selection" card
3. Clicked "Go to Replacement Selection" button

**Results:**
- [x] Navigates to `/backoffice/assembly/1e494a8e-6354-4229-b29c-afcf3ac80ebb/replacement`
- [x] Page title shows assembly name ("My second assembly")
- [x] Breadcrumbs show: Dashboard > My second assembly > Replacement Selection
- [x] "Check Spreadsheet" button visible
- [x] "Back to Selection" button visible
- [x] "Back to Dashboard" button also visible
- [x] Page subtitle: "Select replacement participants from remaining pool"

---

### TC-RS-02: Replacement Page - No GSheet Configured ✅ PASS

**Assembly Used:** "test" (ID: 995a67f1-355a-420c-ac63-6cde93df3642)

**Steps Executed:**
1. Navigated directly to `/backoffice/assembly/995a67f1-.../replacement`

**Results:**
- [x] Warning alert: "Please configure a Google Spreadsheet in the Data tab before running replacement selection."
- [x] "Configure Data Source" button visible (links to `/data` tab correctly)
- [x] "Back to Selection" button visible
- [x] No replacement form visible (no "Check Spreadsheet" button)

---

### TC-RS-03: Check Spreadsheet - Happy Path ❌ BLOCKED (Infrastructure)

**Steps Executed:**
1. Navigated to replacement selection page
2. Clicked "Check Spreadsheet" button
3. Observed progress display

**Results:**
- [x] Task starts (redirects to URL with run_id: `/replacement/c701d842-...`)
- [x] Progress card appears with "Task Progress" heading
- [x] Task type shown: "Load replacement google spreadsheet"
- [ ] ~~Task completes successfully~~ — Task FAILED with FileNotFoundError
- [ ] ~~Page redirects to show form with min/max values~~
- [ ] ~~"Available replacements: X to Y participants" message displayed~~

**Error:** "Task failed with exception: FileNotFoundError. Please contact the administrators if this problem persists."

**Root Cause:** Google Sheet referenced by the assembly is not accessible (likely deleted or service account lacks access).

**Partial Observations:**
- The task did start successfully and redirect to a run_id URL
- Progress card appeared with spinner during execution
- Status transitioned from Pending to Failed
- Error message was shown during initial polling
- "Back to Replacement Selection" button appeared after failure

---

### TC-RS-04: Check Spreadsheet - Missing Already Selected Tab ⏭️ BLOCKED

**Reason:** Cannot test because the Check Spreadsheet task fails at the Google Sheets file access level (FileNotFoundError) before it can validate individual tab existence.

---

### TC-RS-05: Check Spreadsheet - Empty Already Selected Tab ⏭️ BLOCKED

**Reason:** Same as TC-RS-04 - cannot reach tab validation step.

---

### TC-RS-06: Number to Select Form - Valid Input ⏭️ BLOCKED

**Reason:** The number input form only appears after a successful "Check Spreadsheet" task completes. Since the task fails with FileNotFoundError, the form never appears. Manually adding `?min_select=1&max_select=50` URL parameters does NOT trigger the form display - it's server-side controlled.

---

### TC-RS-07: Number to Select - Below Minimum ⏭️ BLOCKED

**Reason:** Depends on TC-RS-06 (form must be visible).

---

### TC-RS-08: Number to Select - Above Maximum ⏭️ BLOCKED

**Reason:** Depends on TC-RS-06 (form must be visible).

---

### TC-RS-09: Number to Select - Zero or Negative ⏭️ BLOCKED

**Reason:** Depends on TC-RS-06 (form must be visible).

---

### TC-RS-10: Run Replacements - Happy Path ⏭️ BLOCKED

**Reason:** Depends on successful Check Spreadsheet and form display.

---

### TC-RS-11: Run Replacements - Cancel During Execution ⏭️ BLOCKED

**Reason:** Depends on successful Run Replacements task.

**Partial Observation:** A "Cancel Task" button IS visible on the progress page when a task is in Pending/Running state (observed during the invalid run_id test).

---

### TC-RS-12: Progress Polling - Automatic Updates ⏭️ PARTIAL

**Reason:** Full flow blocked, but polling behavior was observed.

**Partial Observations:**
- Alpine.js polling component IS active (observed via console errors on invalid run_id)
- Polling interval appears to be ~2 seconds (consistent with spec)
- Polling fetches from a progress endpoint
- Spinner animates during "Processing..." state

---

### TC-RS-13: Progress Polling - Page Refresh ⏭️ BLOCKED

**Reason:** Depends on a running task to test refresh behavior.

**Partial Observation:** Revisiting a completed (failed) task shows the final state correctly, but error details are lost (see BUG-002).

---

### TC-RS-14: Automatic Redirect After Load Completes ⏭️ BLOCKED

**Reason:** The load task never completes successfully, so redirect cannot be verified.

---

### TC-RS-15: Run Replacements - Write Permission Error ⏭️ BLOCKED

**Reason:** Cannot reach the Run Replacements step.

---

### TC-RS-16: Re-check Spreadsheet After Configuration Change ⏭️ BLOCKED

**Reason:** Initial check fails, so re-check comparison is not meaningful.

---

### TC-RS-17: Multiple Replacement Rounds ⏭️ BLOCKED

**Reason:** Cannot complete even one replacement round.

---

### TC-RS-18: Unauthorized Access ✅ PASS (with note)

**Steps Executed:**
1. Logged out of the application
2. Attempted to access `/backoffice/assembly/<id>/replacement` directly

**Results:**
- [x] Redirected to login page (`/auth/login?next=...`)
- [x] Flash message: "Please sign in to access this page."
- [x] After login, correctly redirected back to the replacement page

**Note:** The test case expected redirect to dashboard with "You don't have permission to view this assembly" - this would require a second user account without assembly access. The unauthenticated access test passes (redirects to login). Testing with an authenticated user who lacks assembly permission was not possible with the available test accounts.

---

### TC-RS-19: Nonexistent Assembly ✅ PASS (with minor note)

**Steps Executed:**
1. Navigated to `/backoffice/assembly/00000000-0000-0000-0000-000000000000/replacement`

**Results:**
- [x] Redirected to dashboard
- [x] Error flash: "Assembly not found" (red error banner)

**Additional Test - Invalid UUID Format:**
- Navigated to `/backoffice/assembly/invalid-uuid-here/replacement`
- Result: 404 "Page Not Found" error page (different handling from valid-but-nonexistent UUID)
- This is acceptable behavior but inconsistent with the valid UUID case.

---

### TC-RS-20: Invalid Run ID in URL ❌ FAIL

**Steps Executed:**
1. Navigated to `/backoffice/assembly/<id>/replacement/00000000-0000-0000-0000-000000000000`

**Results:**
- [ ] ~~Error handled gracefully~~ — Page gets stuck in "Pending" state
- [ ] ~~Flash message about invalid task~~ — No flash message shown
- [ ] ~~Redirect to replacement page (without run_id)~~ — No redirect occurs

**Actual Behavior:**
- Page shows "Task Progress" card with "Status: Pending" and "Processing..." spinner
- Polling continues indefinitely every ~2 seconds
- Console fills with "Task progress fetch error: Error: Network response was not ok" errors
- "Cancel Task" button is visible but for a non-existent task
- User has no clear indication that the run_id is invalid

**Additional Test - Non-UUID Run ID:**
- Navigated to `/backoffice/assembly/<id>/replacement/invalid-run-id`
- Result: 404 "Page Not Found" — This is handled by URL routing (UUID format validation)

See **BUG-001** for details.

---

### TC-RS-21: Very Large Number of Replacements ⏭️ BLOCKED

**Reason:** Cannot reach the replacement execution step.

---

### TC-RS-22: Single Replacement Available ⏭️ BLOCKED

**Reason:** Cannot reach the Check Spreadsheet completion step.

---

### TC-RS-23: No Replacements Available ⏭️ BLOCKED

**Reason:** Cannot reach the Check Spreadsheet completion step.

---

### TC-RS-24: Concurrent Browser Tabs ⏭️ SKIPPED

**Reason:** Would require a working task flow to meaningfully test concurrent behavior.

---

## Browser Compatibility

- [x] Chrome - Tested (primary browser used)
- [ ] Firefox - Not tested
- [ ] Safari - Not tested
- [ ] Mobile browser - Not tested

---

## JavaScript Console Observations

- **No baseline JS errors** on the replacement page when loaded normally
- **Continuous errors** when polling for invalid/non-existent run_id (BUG-001)
- Alpine.js taskPoller component loads and initializes correctly
- Polling endpoint: Fetches task progress via API (returns non-ok response for invalid tasks)

---

## UI/UX Observations

1. **Breadcrumb navigation** works correctly across all tested pages
2. **Assembly tab navigation** (Details, Data, Selection, Team Members) is consistent on replacement pages
3. **Warning state** for no GSheet configured is well-designed with clear actionable buttons
4. **Error state** for failed tasks shows status but could benefit from persisting error details (BUG-002)
5. **Button styling** is consistent - primary actions in dark red, secondary in outlined style
6. **Page subtitle** changes appropriately: "Select replacement participants from remaining pool"
7. **Task Progress card** displays task type, status, and messages section

---

## Recommendations

1. **Fix BUG-001 (High Priority):** Add error handling for invalid/non-existent run_ids in the progress polling component. Should detect repeated fetch failures and either redirect to the replacement page or show an error message.

2. **Fix BUG-002 (Low Priority):** Persist error details (exception message) in task records so they can be displayed on page revisit.

3. **Fix Infrastructure:** Ensure the Google Sheet referenced by "My second assembly" is accessible to the service account so the full test suite can be executed.

4. **Re-run blocked tests:** Once the Google Sheets infrastructure is working, re-execute TC-RS-03 through TC-RS-17 and TC-RS-21 through TC-RS-23.

5. **Add second test user:** Create a test user without assembly access to properly test TC-RS-18 (permission-based access control).

---

## Environment Issues

The primary blocker for this test execution was the Google Sheets integration:

- **Error:** `FileNotFoundError` when attempting to load the replacement google spreadsheet
- **Impact:** 16 of 24 test cases could not be executed
- **Likely Cause:** The Google Sheet referenced in the assembly configuration has been deleted, moved, or the service account no longer has access
- **Resolution:** Verify the Google Sheet URL in the Data tab configuration, ensure it exists, and share it with the service account email with Editor permissions

---

*Report generated: 2026-05-03 08:30 UTC*
