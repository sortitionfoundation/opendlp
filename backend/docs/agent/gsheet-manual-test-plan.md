# Google Sheet Configuration - Manual Test Plan

**Last Updated:** 2026-02-25
**Related Spec:** [csv-upload-and-gsheet-flow-redesign-spec.md](csv-upload-and-gsheet-flow-redesign-spec.md)

## Overview

This document provides manual test cases for the Google Sheet configuration feature in the backoffice UI. These tests complement the automated BDD tests by covering scenarios that require real Google Sheets integration, permission setup, and edge cases that are difficult to automate.

---

## Prerequisites

### 1. Test Environment

- [ ] Local development server running (`just run`)
- [ ] Admin user account available
- [ ] Google Service Account email noted (shown in the configuration form hint)

### 2. Test Google Sheets

Create the following test spreadsheets in Google Drive:

#### Sheet A: Valid Configuration (Happy Path)
Create a spreadsheet with these tabs:
- **Respondents** - Sample participant data with columns: `ID`, `Name`, `Email`, `Address`, `City`, `PostCode`
- **Categories** - Selection categories/targets
- **Selected** - Empty tab for tracking selected participants

Share with the service account email (Viewer permission is sufficient).

**Template data for Respondents tab:**
| ID | Name | Email | Address | City | PostCode |
|----|------|-------|---------|------|----------|
| 1 | Alice Smith | alice@example.com | 123 Main St | London | SW1A 1AA |
| 2 | Bob Jones | bob@example.com | 456 Oak Ave | Manchester | M1 1AA |
| 3 | Carol White | carol@example.com | 789 Elm Rd | Birmingham | B1 1AA |

#### Sheet B: Minimal Configuration
Create a spreadsheet with:
- Only **Respondents** tab with minimal data (ID column only)
- Share with service account

#### Sheet C: Not Shared (Permission Test)
Create a spreadsheet but DO NOT share with service account.

#### Sheet D: Edge Cases
Create a spreadsheet with:
- Tab names with special characters: `Data (2024)`, `Category/Target`
- Empty tabs
- Tab with only headers (no data rows)
- Very long tab name (50+ characters)

---

## Test Cases

### TC-01: Happy Path - Create New Configuration

**Precondition:** Assembly exists without gsheet configuration

**Steps:**
1. Navigate to Backoffice Dashboard
2. Click on an assembly card
3. Click the "Data" tab
4. Verify data source selector is enabled
5. Select "Google Spreadsheet" from dropdown
6. Enter URL of Sheet A (valid configuration)
7. Fill in tab names:
   - Respondents Tab: `Respondents`
   - Categories Tab: `Categories`
   - Already Selected Tab: `Selected`
8. Select team preset (e.g., "UK Team") or configure custom columns
9. Uncheck "Check Same Address" (or provide address columns if checked)
10. Click "Save Configuration"

**Expected Results:**
- [ ] Success flash message: "Google Spreadsheet configuration created successfully"
- [ ] Redirected to VIEW mode (readonly form)
- [ ] Data source selector is now disabled/locked
- [ ] "Edit Configuration" button visible
- [ ] URL displayed as clickable link

---

### TC-02: Happy Path - Edit Existing Configuration

**Precondition:** Assembly has existing gsheet configuration (from TC-01)

**Steps:**
1. Navigate to assembly data page
2. Click "Edit Configuration" button
3. Verify form fields are now editable
4. Change the "Respondents Tab" value to `Respondents`
5. Click "Save Configuration"

**Expected Results:**
- [ ] Success flash message: "Google Spreadsheet configuration updated successfully"
- [ ] Redirected back to VIEW mode
- [ ] Updated value is displayed

---

### TC-03: Happy Path - Delete Configuration

**Precondition:** Assembly has existing gsheet configuration

**Steps:**
1. Navigate to assembly data page (VIEW mode)
2. Click "Delete" button
3. Confirm the browser dialog

**Expected Results:**
- [ ] Success flash message: "Google Spreadsheet configuration removed successfully"
- [ ] Data source selector is now enabled (unlocked)
- [ ] No gsheet form displayed
- [ ] Can select different data source

---

### TC-04: Validation - Missing URL

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Leave URL field empty
3. Fill other required fields
4. Click "Save Configuration"

**Expected Results:**
- [ ] Form does NOT submit (browser validation)
- [ ] URL field shows required validation message
- [ ] Stays on same page

---

### TC-05: Validation - Invalid URL Format

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Enter invalid URL: `not-a-valid-url`
3. Click "Save Configuration"

**Expected Results:**
- [ ] Error message displayed: "Invalid URL" or similar
- [ ] Form stays on page with error highlighted

---

### TC-06: Validation - Non-Google-Sheets URL

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Enter valid URL but not Google Sheets: `https://example.com/spreadsheet`
3. Click "Save Configuration"

**Expected Results:**
- [ ] Error message about invalid Google Sheets URL
- [ ] Form stays on page

---

### TC-07: Validation - Check Same Address Without Columns

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Enter valid Google Sheets URL
3. Select "Custom configuration" for team
4. Check "Check Same Address" checkbox
5. Leave "Address Columns" field empty
6. Click "Save Configuration"

**Expected Results:**
- [ ] Error message: "You must specify address columns when 'Check Same Address' is enabled"
- [ ] Form stays on page

---

### TC-08: Permission Error - Sheet Not Shared

**Precondition:** Sheet C exists (not shared with service account)

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Enter URL of Sheet C (not shared)
3. Fill in valid tab names
4. Click "Save Configuration"

**Expected Results:**
- [ ] Configuration saves (URL validation passes)
- [ ] When user tries to run selection later, permission error will occur
- [ ] (Note: URL validation doesn't verify access permissions at save time)

---

### TC-09: Edge Case - Special Characters in Tab Names

**Precondition:** Sheet D exists with special character tab names

**Steps:**
1. Create new gsheet configuration
2. Enter URL of Sheet D
3. Enter tab name with special characters: `Data (2024)`
4. Save configuration

**Expected Results:**
- [ ] Configuration saves successfully
- [ ] Tab name stored correctly with special characters

---

### TC-10: Edge Case - Very Long Tab Name

**Precondition:** Sheet D exists with long tab name

**Steps:**
1. Create new gsheet configuration
2. Enter URL of Sheet D
3. Enter tab name with 50+ characters
4. Save configuration

**Expected Results:**
- [ ] Configuration saves (or shows appropriate length validation)
- [ ] Tab name displayed correctly in VIEW mode

---

### TC-11: Cancel Edit - No Changes Saved

**Precondition:** Assembly has existing gsheet configuration

**Steps:**
1. Navigate to assembly data page
2. Click "Edit Configuration"
3. Change URL to something different
4. Click "Cancel" button (not Save)

**Expected Results:**
- [ ] Redirected to VIEW mode
- [ ] Original URL still displayed (changes discarded)
- [ ] No flash message about changes

---

### TC-12: Data Source Locking

**Precondition:** Assembly has existing gsheet configuration

**Steps:**
1. Navigate to assembly data page (without source parameter)
2. Observe data source selector

**Expected Results:**
- [ ] Selector shows "Google Spreadsheet" selected
- [ ] Selector is disabled (greyed out)
- [ ] Help text mentions "Data source is locked"
- [ ] Cannot change to CSV while config exists

---

### TC-13: Team Preset Selection

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Navigate to assembly data page with `?source=gsheet`
2. Select "UK Team" preset
3. Verify custom fields are hidden
4. Select "Custom configuration"
5. Verify custom fields appear (ID Column, Address Columns, Columns to Keep)

**Expected Results:**
- [ ] Team presets hide custom configuration fields
- [ ] Custom option shows all configuration fields
- [ ] Switching between presets updates form visibility

---

### TC-14: Warning - Empty Columns to Keep

**Precondition:** Assembly without gsheet configuration

**Steps:**
1. Create new gsheet configuration
2. Select "Custom configuration"
3. Leave "Columns to Keep" field empty
4. Fill all other required fields
5. Save configuration

**Expected Results:**
- [ ] Configuration saves successfully
- [ ] Warning flash message displayed about empty columns
- [ ] (This is a warning, not an error - save still succeeds)

---

### TC-15: Browser Back Button Behavior

**Precondition:** Assembly has gsheet configuration in VIEW mode

**Steps:**
1. From VIEW mode, click "Edit Configuration"
2. Make some changes to form fields
3. Click browser Back button

**Expected Results:**
- [ ] Returns to previous page (VIEW mode or dashboard)
- [ ] No unsaved changes prompt (standard browser behavior)
- [ ] Changes are NOT saved

---

### TC-16: Multiple Assemblies - Independent Configurations

**Steps:**
1. Create Assembly A with gsheet configuration using Sheet A
2. Create Assembly B with gsheet configuration using Sheet B
3. Navigate to Assembly A data page
4. Navigate to Assembly B data page

**Expected Results:**
- [ ] Each assembly shows its own configuration
- [ ] Configurations are independent
- [ ] Editing one doesn't affect the other

---

## Edge Cases Checklist

Quick verification items for exploratory testing:

### URL Handling
- [ ] URL with trailing slash
- [ ] URL with query parameters (`?usp=sharing`)
- [ ] URL with `/edit#gid=0` suffix
- [ ] URL copied from "Share" dialog vs address bar
- [ ] URL from Google Sheets mobile app

### Tab Names
- [ ] Tab names with leading/trailing spaces
- [ ] Tab names with unicode characters
- [ ] Tab names that match sheet name
- [ ] Case sensitivity (Tab vs tab vs TAB)
- [ ] Numeric tab names (`123`)

### Form Behavior
- [ ] Double-click Save button (prevent duplicate submission)
- [ ] Submit with Enter key
- [ ] Form autofill behavior
- [ ] Session timeout during edit

### Browser Compatibility
- [ ] Chrome
- [ ] Firefox
- [ ] Safari
- [ ] Mobile browser (responsive layout)

---

## Known Gotchas

### 1. Service Account Permissions
The service account needs at least **Viewer** access to the spreadsheet. Common issues:
- Sheet shared with wrong email
- Sheet shared with user's personal account instead of service account
- Organization policies blocking external sharing

### 2. Check Same Address Default
The "Check Same Address" checkbox defaults to **checked**. If saving fails with address column validation error, either:
- Uncheck the checkbox, or
- Provide comma-separated column names in "Address Columns" field

### 3. Tab Name Case Sensitivity
Google Sheets tab names ARE case-sensitive. `Respondents` is different from `respondents`.

### 4. URL Validation vs Access Validation
The form validates URL format but does NOT verify the service account can access the sheet. Access errors only appear when running selection.

### 5. Data Source Lock After Config
Once a gsheet configuration exists, the data source selector is locked. To change data source type (e.g., to CSV), you must first delete the existing gsheet configuration.

---

## Test Data Cleanup

After testing, clean up:
1. Delete test assemblies created during testing
2. Remove test Google Sheets or move to archive folder
3. Revoke service account access from test sheets (optional)

---

## Related Documentation

- [Google Sheet Configuration Flow Spec](csv-upload-and-gsheet-flow-redesign-spec.md)
- [Selection Tab Spec](selection-tab-spec.md)
- [Google Service Account Setup](google_service_account.md)
