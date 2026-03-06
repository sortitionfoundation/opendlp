# Scroll Position Preservation - Manual Test Plan

**Last Updated:** 2026-03-04
**Related Spec:** [scroll-preservation-spec.md](../../../docs/agent/scroll-preservation-spec.md)

## Overview

This document provides manual test cases for the scroll position preservation system. This system uses the `$preserveScroll` Alpine.js magic helper to maintain scroll position across page reloads, making navigation more user-friendly especially when working with long pages and pagination.

The scroll preservation system:
- Adds scroll position to URLs as a query parameter during navigation
- Restores scroll position immediately on page load
- Removes the scroll parameter from the URL after restoration
- Provides a seamless user experience without jarring scroll jumps

---

## Prerequisites

### 1. Test Environment

- [ ] Local development server running (`just run` or `just start-docker`)
- [ ] Admin user account available
- [ ] Browser with developer console (Chrome/Firefox/Safari)
- [ ] At least one assembly created for testing tab navigation

### 2. Verification Tools

Open browser developer console (F12) for verification commands:
- `window.scrollY` - Check current scroll position
- `window.location.search` - Check URL parameters
- `Alpine.magic('preserveScroll')` - Verify magic helper is loaded

---

## Test Cases

### TC-SP-01: Magic Helper Basic Functionality

**Precondition:** User logged in, on any backoffice page

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/dashboard`
2. Open browser console (F12)
3. Scroll down the page: `window.scrollTo(0, 500)`
4. Execute in console: `Alpine.magic('preserveScroll')('/test/url')`
5. Execute in console: `Alpine.magic('preserveScroll')('/test/url?foo=bar')`

**Expected Results:**
- [ ] First command outputs: `/test/url?scroll=500`
- [ ] Second command outputs: `/test/url?foo=bar&scroll=500`
- [ ] No JavaScript errors in console
- [ ] Magic helper function exists

---

### TC-SP-02: Scroll Restoration from URL Parameter

**Precondition:** User logged in

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/dashboard`
2. Manually edit URL to add `?scroll=800`
3. Press Enter to reload page
4. Wait 300ms
5. Check scroll position in console: `window.scrollY`
6. Check URL in console: `window.location.search`

**Expected Results:**
- [ ] Page scrolls to approximately 800px (±20px tolerance)
- [ ] URL parameter is removed after restoration
- [ ] Final URL is clean: no `scroll=` parameter
- [ ] No JavaScript errors in console

---

### TC-SP-03: Manual Scroll Cleanup

**Precondition:** User logged in

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/dashboard?scroll=1000`
2. Wait for page load and scroll restoration
3. Verify scroll position: `window.scrollY` (should be ~1000)
4. Manually scroll to different position (e.g., 400px)
5. Wait 300ms for debounce
6. Check URL in address bar

**Expected Results:**
- [ ] Initial scroll restored to ~1000px
- [ ] After manual scroll, URL no longer contains `scroll=1000`
- [ ] URL cleanup happens automatically
- [ ] No JavaScript errors

---

### TC-SP-04: Tab Navigation - Scroll Preservation

**Precondition:** User logged in, assembly exists

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/dashboard`
2. Click on any assembly to view details
3. Make page scrollable by running in console:
   ```javascript
   const div = document.createElement('div');
   div.style.height = '2000px';
   div.style.background = 'linear-gradient(to bottom, transparent, #f0f0f0)';
   div.textContent = 'Scroll test area';
   document.querySelector('main').appendChild(div);
   ```
4. Scroll down to 800px: `window.scrollTo(0, 800)`
5. Verify position: `window.scrollY` (should be ~800)
6. Click "Data" tab
7. Wait for page load
8. Verify scroll position: `window.scrollY`
9. Check URL: `window.location.search`

**Expected Results:**
- [ ] Page reloads with scroll preserved (~800px)
- [ ] URL briefly shows `?scroll=800` during navigation
- [ ] URL parameter removed after restoration
- [ ] Scroll position maintained accurately (±20px)
- [ ] No JavaScript errors

---

### TC-SP-05: Tab Navigation - Multiple Tab Switches

**Precondition:** User on assembly details page, page made scrollable (TC-SP-04 step 3)

**Steps:**
1. Scroll to 600px
2. Click "Selection" tab
3. Verify scroll preserved
4. Click "Team Members" tab
5. Verify scroll preserved
6. Click "Details" tab
7. Verify scroll preserved

**Expected Results:**
- [ ] Each tab switch preserves scroll position
- [ ] URL clean after each restoration
- [ ] No cumulative drift in scroll position
- [ ] Smooth experience, no jarring jumps

---

### TC-SP-06: Tab Navigation - Scroll at Top

**Precondition:** User on assembly details page

**Steps:**
1. Ensure page is at top: `window.scrollTo(0, 0)`
2. Verify position: `window.scrollY` (should be 0)
3. Click "Data" tab
4. Verify scroll position

**Expected Results:**
- [ ] Page loads at top (scroll=0)
- [ ] URL may briefly show `?scroll=0` or no parameter
- [ ] URL clean after load
- [ ] No errors

---

### TC-SP-07: Page Reload Without Scroll Parameter

**Precondition:** User on any backoffice page

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/dashboard`
2. Scroll down to 800px
3. Press F5 (reload)
4. Verify scroll position

**Expected Results:**
- [ ] Page reloads and scrolls to top (browser default behavior)
- [ ] URL has no scroll parameter
- [ ] This is expected behavior: scroll only preserved on explicit navigation, not browser reload

---

### TC-SP-08: x-scroll-preserve-links Directive

**Precondition:** User logged in

**Steps:**
1. Navigate to any backoffice page
2. Open console and inject test container:
   ```javascript
   const container = document.createElement('div');
   container.setAttribute('x-scroll-preserve-links', '');
   container.innerHTML = '<a href="/backoffice/dashboard">Test Link</a>';
   document.body.appendChild(container);
   Alpine.initTree(container);
   ```
3. Scroll to 600px
4. Click the "Test Link"
5. Verify navigation

**Expected Results:**
- [ ] Browser navigates to `/backoffice/dashboard?scroll=600`
- [ ] Scroll restored to ~600px
- [ ] URL parameter removed after restoration
- [ ] No JavaScript errors

---

### TC-SP-09: Disable Scroll Preservation

**Precondition:** Developer with ability to modify templates

**Steps:**
1. Modify a tabs() macro call to set `preserve_scroll=false`
2. Reload page
3. Make page scrollable (TC-SP-04 step 3)
4. Scroll to 800px
5. Click a tab
6. Verify behavior

**Expected Results:**
- [ ] Page reloads at top (scroll not preserved)
- [ ] URL never contains scroll parameter
- [ ] Normal browser behavior
- [ ] Feature can be disabled when needed

---

### TC-SP-10: Long Scroll Position (Edge Case)

**Precondition:** User on page with very long content

**Steps:**
1. Navigate to assembly data page with many selection run records
   (Or use TC-SP-04 step 3 with `height: '5000px'`)
2. Scroll to bottom: `window.scrollTo(0, 4500)`
3. Verify position: `window.scrollY`
4. Click a tab
5. Verify scroll restoration

**Expected Results:**
- [ ] Large scroll value (4500px) handled correctly
- [ ] Scroll restored accurately
- [ ] URL parameter shows correct large number
- [ ] No JavaScript errors or overflow issues

---

### TC-SP-11: Rapid Tab Switching

**Precondition:** User on assembly details page, page scrollable

**Steps:**
1. Scroll to 800px
2. Quickly click "Data" tab
3. Immediately click "Selection" tab before page fully loads
4. Let page load
5. Verify final scroll position

**Expected Results:**
- [ ] Final scroll position is preserved
- [ ] No JavaScript errors
- [ ] Navigation completes successfully
- [ ] Browser handles navigation queue correctly

---

### TC-SP-12: Browser Back Button

**Precondition:** User on assembly details page

**Steps:**
1. Scroll to 800px
2. Click "Data" tab
3. Verify scroll preserved
4. Click browser Back button
5. Verify scroll position

**Expected Results:**
- [ ] Browser's native scroll restoration works
- [ ] Scroll position may be at top or browser's cached position
- [ ] This is normal browser behavior (our system doesn't interfere)
- [ ] No JavaScript errors

---

## Integration Testing

### TC-SP-13: Form Submission with Scroll Preservation

**Precondition:** Assembly with Google Sheet configured

**Steps:**
1. Navigate to `http://localhost:5000/backoffice/assembly/<assembly-id>/selection`
2. Make page scrollable if needed
3. Scroll down to bottom of page
4. Note scroll position in console
5. Click "Check Spreadsheet" button
6. Wait for form submission and page reload
7. Verify scroll position

**Expected Results:**
- [ ] Form submits successfully
- [ ] Scroll position approximately preserved
- [ ] URL clean after restoration
- [ ] No JavaScript errors

**Note:** Form preservation requires adding `:action="$preserveScroll(...)"` to forms

---

### TC-SP-14: Pagination with Scroll Preservation

**Precondition:** Assembly with multiple selection run records (old data page)

**Steps:**
1. Navigate to `http://localhost:5000/assemblies/<assembly-id>/data`
2. Scroll down to "Selection Run History" section
3. Note exact scroll position
4. Click "Next" or page number in pagination
5. Verify scroll restoration

**Expected Results:**
- [ ] Page reloads at same scroll position
- [ ] Pagination works correctly
- [ ] URL clean after restoration
- [ ] User doesn't lose their place

**Note:** Pagination links need to use `$preserveScroll()` - this will be implemented in Phase 5 of Selection Tab

---

## Debugging Checklist

If scroll preservation isn't working, verify:

- [ ] `alpine-scroll-manager.js` is loaded (view page source)
- [ ] Script loads BEFORE Alpine.js in the HTML
- [ ] Alpine.js is initialized: `window.Alpine` exists in console
- [ ] Magic helper exists: `Alpine.magic('preserveScroll')` returns function
- [ ] No JavaScript errors in console (check Console tab)
- [ ] Tab links have `:href` binding (inspect element in DevTools)
- [ ] `x-data="{}"` present on tab navigation container

---

## Success Criteria

✅ All test cases pass
✅ No JavaScript console errors
✅ URLs are clean (no scroll parameter) after restoration
✅ User experience feels natural (no jarring jumps)
✅ Scroll position accurately preserved (±20px tolerance)

---

## Automated Testing

After manual testing, run the BDD tests:

```bash
# Run scroll preservation BDD tests
just test-bdd -k scroll_preservation

# Run with browser visible for debugging
CI=false just test-bdd -k scroll_preservation
```

**BDD Scenarios:**
- Scroll position is preserved when clicking pagination
- Scroll position is preserved when submitting a form
- Manual scroll removes scroll parameter
- Page reload without scroll parameter goes to top
- Using $preserveScroll magic helper on links
