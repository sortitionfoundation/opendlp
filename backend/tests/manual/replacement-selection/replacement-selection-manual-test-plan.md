# Replacement Selection - Manual Test Plan

**Last Updated:** 2026-03-05
**Related Spec:** [selection-tab-spec.md](../../../docs/agent/selection-tab-spec.md) (Phase 3)

## Overview

This document provides manual test cases for the Replacement Selection feature in the backoffice UI. Replacement selection allows organisers to select additional participants from the remaining pool when original selections decline or cannot participate.

The replacement selection flow:
1. User clicks "Check Spreadsheet" to validate replacement data
2. System validates the spreadsheet has required tabs including "Already Selected"
3. System calculates min/max available replacements
4. User enters number of replacements to select
5. User clicks "Run Replacements" to execute selection
6. Progress is shown via polling, results written to spreadsheet

---

## Prerequisites

### 1. Test Environment

- [ ] Local development server running (`uv run flask run --debug --port=5001`)
- [ ] Celery worker running for background tasks
- [ ] Redis running for task queue
- [ ] Admin user account available
- [ ] Google Service Account configured

### 2. Test Google Sheets

Create a spreadsheet with these tabs for replacement testing:

#### Required Tabs for Replacement Selection:
- **Respondents** - All participant data (same format as initial selection)
- **Categories** - Selection categories/targets
- **Already Selected** - Contains IDs of participants from initial selection (critical!)
- **Remaining** - (Optional) Remaining participants after initial selection

**Template data for Already Selected tab:**
| ID |
|----|
| 1 |
| 2 |
| 3 |

Share with the service account email (Editor permission for write operations).

### 3. Initial Selection Completed

- [ ] Assembly exists with Google Sheet configuration
- [ ] Initial selection has been run successfully
- [ ] "Already Selected" tab populated with selected participant IDs

---

## Test Cases

### TC-RS-01: Navigate to Replacement Selection Page

**Precondition:** Assembly exists with gsheet configuration

**Steps:**
1. Navigate to assembly Selection tab
2. Locate "Replacement Selection" card
3. Click "Go to Replacement Selection" button

**Expected Results:**
- [ ] Navigates to `/backoffice/assembly/<id>/replacement`
- [ ] Page title shows assembly name
- [ ] Breadcrumbs show: Dashboard > [Assembly Title] > Replacement Selection
- [ ] "Check Spreadsheet" button visible
- [ ] "Back to Selection" button visible

---

### TC-RS-02: Replacement Page - No GSheet Configured

**Precondition:** Assembly exists WITHOUT gsheet configuration

**Steps:**
1. Navigate directly to `/backoffice/assembly/<id>/replacement`

**Expected Results:**
- [ ] Warning alert: "Please use the Data tab to tell us about your data, before running a selection."
- [ ] "Configure Data Source" button visible
- [ ] "Back to Selection" button visible
- [ ] No replacement form visible

---

### TC-RS-03: Check Spreadsheet - Happy Path

**Precondition:** Assembly with valid gsheet configuration, initial selection completed, "Already Selected" tab populated

**Steps:**
1. Navigate to replacement selection page
2. Click "Check Spreadsheet" button
3. Observe progress display

**Expected Results:**
- [ ] Task starts (redirects to URL with run_id)
- [ ] Progress card appears with spinner
- [ ] Log messages appear showing validation progress
- [ ] Task completes successfully
- [ ] Page redirects to show form with min/max values
- [ ] "Available replacements: X to Y participants" message displayed

---

### TC-RS-04: Check Spreadsheet - Missing Already Selected Tab

**Precondition:** Assembly with gsheet configuration, "Already Selected" tab does NOT exist

**Steps:**
1. Navigate to replacement selection page
2. Click "Check Spreadsheet" button

**Expected Results:**
- [ ] Task starts and shows progress
- [ ] Task fails with error message
- [ ] Error indicates missing "Already Selected" tab
- [ ] User can return to fix configuration

---

### TC-RS-05: Check Spreadsheet - Empty Already Selected Tab

**Precondition:** Assembly with gsheet configuration, "Already Selected" tab exists but is empty

**Steps:**
1. Navigate to replacement selection page
2. Click "Check Spreadsheet" button

**Expected Results:**
- [ ] Task completes (empty already selected is valid)
- [ ] Min/max values reflect full participant pool
- [ ] Form appears with replacement count input

---

### TC-RS-06: Number to Select Form - Valid Input

**Precondition:** Check Spreadsheet completed successfully, min=1, max=50 available

**Steps:**
1. After successful check, observe the form
2. Enter a valid number (e.g., 5) in "Number of people to select" field
3. Verify field attributes

**Expected Results:**
- [ ] Input field has min/max attributes matching calculated values
- [ ] Input field shows default value (min_select)
- [ ] "Run Replacements" button enabled
- [ ] "Re-check Spreadsheet" button available

---

### TC-RS-07: Number to Select - Below Minimum

**Precondition:** Check Spreadsheet completed, min=5

**Steps:**
1. Enter 2 in "Number of people to select" field
2. Click "Run Replacements"

**Expected Results:**
- [ ] Browser validation prevents submission (HTML5 min attribute)
- [ ] Or form submits and server returns error message
- [ ] User prompted to enter valid number

---

### TC-RS-08: Number to Select - Above Maximum

**Precondition:** Check Spreadsheet completed, max=50

**Steps:**
1. Enter 100 in "Number of people to select" field
2. Click "Run Replacements"

**Expected Results:**
- [ ] Browser validation prevents submission (HTML5 max attribute)
- [ ] Or form submits and server returns error message
- [ ] User prompted to enter valid number

---

### TC-RS-09: Number to Select - Zero or Negative

**Precondition:** Check Spreadsheet completed

**Steps:**
1. Enter 0 (or -5) in "Number of people to select" field
2. Click "Run Replacements"

**Expected Results:**
- [ ] Browser validation prevents submission
- [ ] Or server returns error: "Number of people to select must be greater than zero"
- [ ] Form stays on page

---

### TC-RS-10: Run Replacements - Happy Path

**Precondition:** Check Spreadsheet completed, valid number entered

**Steps:**
1. Enter valid number (within min/max range)
2. Click "Run Replacements" button
3. Observe progress display

**Expected Results:**
- [ ] Task starts (redirects to URL with run_id)
- [ ] Progress card shows with spinner
- [ ] Log messages show selection progress
- [ ] Status transitions: pending → running → completed
- [ ] Task completes successfully
- [ ] Results written to Google Sheet
- [ ] "Back to Replacement Selection" button appears

---

### TC-RS-11: Run Replacements - Cancel During Execution

**Precondition:** Replacement task started and running

**Steps:**
1. Start a replacement selection task
2. While task shows PENDING or RUNNING status
3. Click "Cancel Task" button

**Expected Results:**
- [ ] Task status changes to CANCELLED
- [ ] Flash message: "Task has been cancelled"
- [ ] Can start new task after cancellation
- [ ] Partial results NOT written to sheet

---

### TC-RS-12: Progress Polling - Automatic Updates

**Precondition:** Replacement task running

**Steps:**
1. Start a replacement task
2. Watch the progress card without refreshing
3. Count updates over 10 seconds

**Expected Results:**
- [ ] Progress updates every 2 seconds (Alpine.js polling)
- [ ] Log messages accumulate in display
- [ ] Spinner animates while running
- [ ] Polling stops when task completes

---

### TC-RS-13: Progress Polling - Page Refresh

**Precondition:** Replacement task running

**Steps:**
1. Start a replacement task
2. While task is running, press F5 to refresh browser
3. Observe behavior

**Expected Results:**
- [ ] Page reloads showing current task state
- [ ] Polling resumes automatically
- [ ] Log messages preserved from task
- [ ] No duplicate tasks created

---

### TC-RS-14: Automatic Redirect After Load Completes

**Precondition:** User clicks "Check Spreadsheet"

**Steps:**
1. Click "Check Spreadsheet" button
2. Observe behavior when task completes

**Expected Results:**
- [ ] Progress polling detects completion
- [ ] Page automatically redirects to URL with min/max params
- [ ] Form with number input appears
- [ ] No manual refresh needed

---

### TC-RS-15: Run Replacements - Write Permission Error

**Precondition:** Google Sheet shared with view-only access (not edit)

**Steps:**
1. Complete "Check Spreadsheet" successfully
2. Enter valid number
3. Click "Run Replacements"

**Expected Results:**
- [ ] Task starts normally
- [ ] Task fails when attempting to write
- [ ] Error message indicates permission issue
- [ ] Helpful guidance about edit access

---

### TC-RS-16: Re-check Spreadsheet After Configuration Change

**Precondition:** Check Spreadsheet completed, then gsheet config changed

**Steps:**
1. Complete "Check Spreadsheet" on replacement page
2. Note the min/max values
3. Modify the Google Sheet (add/remove participants)
4. Click "Re-check Spreadsheet" button
5. Compare new min/max values

**Expected Results:**
- [ ] New load task starts
- [ ] New min/max values reflect sheet changes
- [ ] Form updates with new constraints

---

### TC-RS-17: Multiple Replacement Rounds

**Precondition:** First replacement selection completed

**Steps:**
1. Run replacement selection for 5 participants
2. Verify results written to sheet
3. Return to replacement page
4. Click "Check Spreadsheet" again
5. Verify updated min/max values
6. Run another replacement selection

**Expected Results:**
- [ ] First replacement completes successfully
- [ ] "Already Selected" tab updated with new selections
- [ ] Second check shows reduced available pool
- [ ] Can run multiple replacement rounds
- [ ] Each round writes to separate output tab (timestamped)

---

### TC-RS-18: Unauthorized Access

**Precondition:** User without assembly access

**Steps:**
1. Attempt to access `/backoffice/assembly/<assembly_id>/replacement` directly

**Expected Results:**
- [ ] Redirected to dashboard
- [ ] Error flash: "You don't have permission to view this assembly"

---

### TC-RS-19: Nonexistent Assembly

**Steps:**
1. Attempt to access `/backoffice/assembly/<invalid_uuid>/replacement`

**Expected Results:**
- [ ] Redirected to dashboard
- [ ] Error flash: "Assembly not found"

---

### TC-RS-20: Invalid Run ID in URL

**Precondition:** Assembly exists

**Steps:**
1. Navigate to `/backoffice/assembly/<id>/replacement/<invalid_run_id>`

**Expected Results:**
- [ ] Error handled gracefully
- [ ] Flash message about invalid task
- [ ] Redirect to replacement page (without run_id)

---

## Edge Cases

### TC-RS-21: Very Large Number of Replacements

**Precondition:** Large participant pool (1000+ participants)

**Steps:**
1. Complete Check Spreadsheet
2. Enter maximum allowed number
3. Run replacement selection

**Expected Results:**
- [ ] Task handles large selection
- [ ] Progress updates show reasonably
- [ ] Task completes (may take longer)
- [ ] Results written correctly

---

### TC-RS-22: Single Replacement Available

**Precondition:** Only 1 unselected participant remaining

**Steps:**
1. Complete Check Spreadsheet
2. Verify min=1, max=1
3. Run replacement selection for 1

**Expected Results:**
- [ ] Single participant selected
- [ ] Results written to sheet
- [ ] No errors

---

### TC-RS-23: No Replacements Available

**Precondition:** All participants already selected

**Steps:**
1. Complete Check Spreadsheet

**Expected Results:**
- [ ] Task completes
- [ ] min=0, max=0 (or appropriate message)
- [ ] Form may not allow submission
- [ ] Message indicates no replacements available

---

### TC-RS-24: Concurrent Browser Tabs

**Steps:**
1. Open replacement page in Tab A
2. Open same replacement page in Tab B
3. Start Check Spreadsheet in Tab A
4. Try to start Check Spreadsheet in Tab B

**Expected Results:**
- [ ] Both tabs show same task progress
- [ ] No duplicate tasks created
- [ ] Polling works in both tabs

---

## Browser Compatibility

Quick verification:

- [ ] Chrome - all features work
- [ ] Firefox - all features work
- [ ] Safari - all features work
- [ ] Mobile browser - responsive layout works

---

## Debugging Checklist

If replacement selection isn't working:

- [ ] Celery worker is running (`celery -A opendlp.tasks.celery worker`)
- [ ] Redis is running (check connection)
- [ ] Google Sheet is shared with service account (Editor access for writes)
- [ ] "Already Selected" tab exists with correct format
- [ ] Browser console shows no JavaScript errors
- [ ] Alpine.js taskPoller component is loaded
- [ ] Progress polling endpoint returns valid JSON
- [ ] Task health check is updating stale tasks

---

## Success Criteria

- All test cases pass
- No JavaScript console errors
- Progress updates smoothly without jarring
- Automatic redirect works after load task
- Cancel functionality stops running tasks
- Results correctly written to Google Sheet
- Multiple replacement rounds work correctly

---

## Related Documentation

- [Selection Tab Spec](../../../docs/agent/selection-tab-spec.md)
- [Google Sheet Configuration Tests](../backoffice-gsheet/gsheet-manual-test-plan.md)
- [Service Layer Sortition](../../../src/opendlp/service_layer/sortition.py)
