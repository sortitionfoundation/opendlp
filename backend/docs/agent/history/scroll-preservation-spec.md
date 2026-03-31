# Scroll Preservation Specification

**Status:** Not yet implemented
**Created:** 2026-03-04
**Purpose:** Reusable scroll position preservation across page reloads

---

## Problem Statement

When server-side navigation causes full page reloads (pagination, form submissions, tab switching), the browser scrolls to the top, disrupting user experience. This is especially problematic when:

- Paginating through long lists at the bottom of the page
- Submitting forms that redirect back to the same page
- Switching tabs that trigger server-side navigation
- Any action that reloads the page while user is scrolled down

**User Pain Point:** "I click 'Next Page' on the history table at the bottom, and suddenly I'm back at the top. Where did my content go?"

---

## Solution Overview

A lightweight, reusable scroll preservation system that:

1. **Captures** scroll position when user clicks navigation elements
2. **Persists** position via URL query parameter (testable, shareable)
3. **Restores** exact scroll position on page load
4. **Cleans up** immediately after restoration to prevent unwanted behavior on manual scrolls or reloads

### Key Design Principle

**Ephemeral State:** The `scroll` parameter exists only during the navigation transition. Once the page loads and scroll is restored, it's immediately removed from the URL.

---

## Architecture

### Component Structure

```
alpine-scroll-manager.js
├── Global Restoration (IIFE - runs before Alpine)
│   ├── Read scroll param from URL
│   ├── Restore scroll position
│   └── Clean URL (replaceState)
│
├── Alpine Magic Helper: $preserveScroll
│   └── Add scroll param to URLs
│
├── Alpine Directive: x-scroll-preserve-links (optional)
│   └── Auto-apply to all links in container
│
└── Manual Scroll Cleanup (IIFE)
    └── Remove scroll param if user scrolls manually
```

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ User Action: Click pagination/form/link                         │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ $preserveScroll() magic helper                                  │
│ • Captures: window.scrollY                                      │
│ • Generates: ?page=2&scroll=1250                                │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ Browser navigates to new URL                                     │
│ URL: /assembly/123/selection?page=2&scroll=1250                 │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ Page Load - Global Restoration (before Alpine init)             │
│ 1. Read URLSearchParams: scroll=1250                            │
│ 2. window.scrollTo(0, 1250)                                     │
│ 3. history.replaceState() → clean URL                           │
│    Result: /assembly/123/selection?page=2                       │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ User Experience:                                                 │
│ • Page loads at exact scroll position ✓                         │
│ • URL is clean (no scroll param) ✓                              │
│ • Bookmarking works correctly ✓                                 │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ If user manually scrolls:                                        │
│ • Debounced scroll listener fires (150ms)                       │
│ • Double-checks URL for scroll param                            │
│ • Removes if present (safety net)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### File: `backend/static/js/alpine-scroll-manager.js`

```javascript
/**
 * ABOUTME: Global scroll position preservation for page reloads
 * ABOUTME: Preserves scroll on navigation, restores on load, then cleans URL
 *
 * Usage:
 *   <a :href="$preserveScroll('/some/url')">Link</a>
 *   <form :action="$preserveScroll('/submit')" method="post">
 *   <div x-scroll-preserve-links><!-- auto-apply to all links --></div>
 *
 * Philosophy:
 *   - Scroll parameter is EPHEMERAL (exists only during transition)
 *   - URL-based state (testable, shareable, bookmarkable)
 *   - Zero configuration required
 *   - CSP-safe (no inline scripts)
 */

// =============================================================================
// Part 1: Global Scroll Restoration (runs before Alpine initializes)
// =============================================================================

(function() {
  const urlParams = new URLSearchParams(window.location.search);
  const scrollPos = urlParams.get('scroll');

  if (scrollPos) {
    const restoreScroll = () => {
      // Restore scroll position
      window.scrollTo(0, parseInt(scrollPos, 10));

      // Immediately clean URL (remove scroll parameter)
      const url = new URL(window.location.href);
      url.searchParams.delete('scroll');
      window.history.replaceState({}, '', url.toString());
    };

    // Execute as early as possible
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', restoreScroll);
    } else {
      // DOM already loaded, restore immediately
      requestAnimationFrame(restoreScroll);
    }
  }
})();

// =============================================================================
// Part 2: Alpine.js Magic Helper
// =============================================================================

document.addEventListener('alpine:init', () => {
  /**
   * Magic: $preserveScroll
   *
   * Adds current scroll position to a URL for preservation across page reload.
   *
   * @param {string} url - The URL to navigate to
   * @returns {string} URL with scroll parameter appended
   *
   * @example
   * <a :href="$preserveScroll('/page?foo=bar')">Link</a>
   * Result: /page?foo=bar&scroll=1250
   */
  Alpine.magic('preserveScroll', () => {
    return (url) => {
      if (!url) return url;

      const currentScroll = Math.round(window.scrollY);
      const separator = url.includes('?') ? '&' : '?';
      return `${url}${separator}scroll=${currentScroll}`;
    };
  });

  /**
   * Directive: x-scroll-preserve-links
   *
   * Auto-applies scroll preservation to all links within an element.
   * Links can opt-out with data-no-scroll-preserve attribute.
   *
   * @example
   * <nav x-scroll-preserve-links>
   *   <a href="/page1">Auto-preserved</a>
   *   <a href="/page2" data-no-scroll-preserve>Not preserved</a>
   * </nav>
   */
  Alpine.directive('scroll-preserve-links', (el) => {
    el.addEventListener('click', (e) => {
      const link = e.target.closest('a[href]');

      // Skip if no link, or link opts out
      if (!link || link.hasAttribute('data-no-scroll-preserve')) {
        return;
      }

      // Skip external links and hash links
      const href = link.getAttribute('href');
      if (href.startsWith('http') || href.startsWith('#')) {
        return;
      }

      // Add scroll parameter
      const currentScroll = Math.round(window.scrollY);
      const separator = href.includes('?') ? '&' : '?';
      link.setAttribute('href', `${href}${separator}scroll=${currentScroll}`);
    }, true); // Use capture phase to run before navigation
  });
});

// =============================================================================
// Part 3: Manual Scroll Cleanup (safety net)
// =============================================================================

(function() {
  let scrollTimeout;
  let justRestored = true; // Ignore first scroll event after restoration

  const cleanupScrollParam = () => {
    const url = new URL(window.location.href);
    if (url.searchParams.has('scroll')) {
      url.searchParams.delete('scroll');
      window.history.replaceState({}, '', url.toString());
    }
  };

  window.addEventListener('scroll', () => {
    // Skip cleanup immediately after restoration
    if (justRestored) {
      justRestored = false;
      return;
    }

    // Debounce: wait for scroll to settle
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(cleanupScrollParam, 150);
  }, { passive: true }); // Passive listener for better performance
})();
```

---

## Usage Examples

### 1. Pagination Links (Manual)

```html
{# Template: pagination controls #}
<nav aria-label="Pagination">
  {% if page > 1 %}
    <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly_selection',
                                            assembly_id=assembly.id,
                                            page=page-1) }}')"
       class="pagination-prev">
      Previous
    </a>
  {% endif %}

  {% for p in range(1, total_pages + 1) %}
    <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly_selection',
                                            assembly_id=assembly.id,
                                            page=p) }}')"
       class="pagination-link {{ 'active' if p == page }}">
      {{ p }}
    </a>
  {% endfor %}

  {% if page < total_pages %}
    <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly_selection',
                                            assembly_id=assembly.id,
                                            page=page+1) }}')"
       class="pagination-next">
      Next
    </a>
  {% endif %}
</nav>
```

### 2. Form Submissions

```html
{# Form that redirects back to same page after submission #}
<form :action="$preserveScroll('{{ url_for('backoffice.start_selection_load',
                                            assembly_id=assembly.id) }}')"
      method="post">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button type="submit">Check Spreadsheet</button>
</form>
```

### 3. Tab Navigation

```html
{# Tabs that cause server-side navigation #}
<nav class="tabs">
  <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly', assembly_id=assembly.id) }}')"
     class="tab-link">
    Details
  </a>
  <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly_data', assembly_id=assembly.id) }}')"
     class="tab-link">
    Data
  </a>
  <a :href="$preserveScroll('{{ url_for('backoffice.view_assembly_selection', assembly_id=assembly.id) }}')"
     class="tab-link active">
    Selection
  </a>
</nav>
```

### 4. Auto-Apply to Container

```html
{# Auto-apply to all links in a section #}
<section x-scroll-preserve-links>
  <h2>Recent Activity</h2>

  {# All these links automatically get scroll preservation #}
  <a href="/activity/1">Activity 1</a>
  <a href="/activity/2">Activity 2</a>
  <a href="/activity/3">Activity 3</a>

  {# Opt-out if needed #}
  <a href="/external" data-no-scroll-preserve>External Link</a>
</section>
```

### 5. Mixed Usage

```html
{# Page with multiple scroll-preserved actions #}
<div>
  {# Manual preservation on specific links #}
  <a :href="$preserveScroll('/filter?type=active')">Active Items</a>

  {# Auto-preservation on container #}
  <div x-scroll-preserve-links>
    <a href="/item/1">Item 1</a>
    <a href="/item/2">Item 2</a>
  </div>

  {# Form submission with preservation #}
  <form :action="$preserveScroll('/search')" method="get">
    <input name="q" type="search">
    <button type="submit">Search</button>
  </form>
</div>
```

---

## Route Updates

Routes don't need special handling - the `scroll` parameter is read client-side only. However, for completeness, routes can optionally accept it:

```python
@backoffice_bp.route("/assembly/<uuid:assembly_id>/selection")
@login_required
def view_assembly_selection(assembly_id: uuid.UUID) -> ResponseReturnValue:
    # Get pagination parameters
    page = request.args.get("page", 1, type=int)

    # scroll parameter is optional - used only by client-side JavaScript
    # No need to process it server-side, but can accept it for URL cleanliness
    scroll = request.args.get("scroll", type=int)

    # ... rest of implementation
```

**Note:** The `scroll` parameter is intentionally NOT used server-side. It's purely for client-side restoration and is immediately removed after use.

---

## Integration with Base Template

Add the script to your base template, **before Alpine.js**:

```html
{# templates/backoffice/base_page.html #}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{% block title %}OpenDLP{% endblock %}</title>

  {# Other head content #}
</head>
<body>
  {% block content %}{% endblock %}

  {# JavaScript - Load scroll manager BEFORE Alpine #}
  <script src="{{ url_for('static', filename='js/alpine-scroll-manager.js') }}"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
</body>
</html>
```

---

## Testing Strategy

### Unit Tests (JavaScript)

```javascript
describe('alpine-scroll-manager', () => {
  describe('$preserveScroll magic', () => {
    it('adds scroll parameter to URL without query string', () => {
      window.scrollY = 1250;
      const result = Alpine.magic('preserveScroll')('/page');
      expect(result).toBe('/page?scroll=1250');
    });

    it('adds scroll parameter to URL with existing query string', () => {
      window.scrollY = 500;
      const result = Alpine.magic('preserveScroll')('/page?foo=bar');
      expect(result).toBe('/page?foo=bar&scroll=500');
    });

    it('rounds scroll position to integer', () => {
      window.scrollY = 123.789;
      const result = Alpine.magic('preserveScroll')('/page');
      expect(result).toBe('/page?scroll=124');
    });

    it('handles null/undefined URL', () => {
      const result = Alpine.magic('preserveScroll')(null);
      expect(result).toBe(null);
    });
  });

  describe('scroll restoration', () => {
    it('restores scroll position from URL on load', () => {
      // Set up URL with scroll param
      window.history.replaceState({}, '', '/page?scroll=1250');

      // Trigger restoration logic
      const event = new Event('DOMContentLoaded');
      document.dispatchEvent(event);

      // Verify scroll position
      expect(window.scrollY).toBe(1250);
    });

    it('removes scroll parameter after restoration', (done) => {
      window.history.replaceState({}, '', '/page?scroll=1250');

      const event = new Event('DOMContentLoaded');
      document.dispatchEvent(event);

      setTimeout(() => {
        expect(window.location.search).not.toContain('scroll');
        done();
      }, 100);
    });
  });
});
```

### E2E Tests (Playwright/Pytest)

```python
# tests/e2e/test_scroll_preservation.py

def test_pagination_preserves_scroll_position(page, assembly_with_history):
    """Verify scroll position is preserved when paginating."""
    # Navigate to selection page with history
    page.goto(f"/backoffice/assembly/{assembly_with_history.id}/selection")

    # Scroll to specific position
    page.evaluate("window.scrollTo(0, 1250)")

    # Verify current scroll position
    initial_scroll = page.evaluate("window.scrollY")
    assert abs(initial_scroll - 1250) < 10

    # Click pagination "Next"
    page.click('a:has-text("Next")')

    # Wait for navigation to complete
    page.wait_for_load_state('networkidle')

    # Verify scroll position is restored (with small tolerance)
    restored_scroll = page.evaluate("window.scrollY")
    assert abs(restored_scroll - 1250) < 20

    # Verify URL does NOT contain scroll parameter (cleaned up)
    assert "scroll=" not in page.url
    assert "page=2" in page.url


def test_scroll_parameter_is_ephemeral(page, assembly_with_history):
    """Verify scroll parameter is removed immediately after restoration."""
    page.goto(f"/backoffice/assembly/{assembly_with_history.id}/selection")

    # Scroll and trigger navigation
    page.evaluate("window.scrollTo(0, 800)")
    page.click('a:has-text("2")')  # Click page 2

    # Wait for navigation
    page.wait_for_load_state('networkidle')

    # Give JavaScript a moment to clean up
    page.wait_for_timeout(200)

    # Verify scroll parameter is gone
    assert "scroll=" not in page.url

    # Verify scroll position is still correct
    scroll_y = page.evaluate("window.scrollY")
    assert abs(scroll_y - 800) < 20


def test_manual_scroll_removes_parameter(page, assembly_with_history):
    """Verify scroll parameter is removed if user scrolls manually."""
    # Navigate with scroll parameter in URL
    page.goto(f"/backoffice/assembly/{assembly_with_history.id}/selection?page=2&scroll=1000")

    # Wait for restoration
    page.wait_for_timeout(200)

    # Manually scroll
    page.evaluate("window.scrollTo(0, 500)")

    # Wait for debounced cleanup
    page.wait_for_timeout(300)

    # Verify scroll parameter is removed
    assert "scroll=" not in page.url


def test_form_submission_preserves_scroll(page, assembly_with_gsheet):
    """Verify scroll is preserved when submitting forms."""
    page.goto(f"/backoffice/assembly/{assembly_with_gsheet.id}/selection")

    # Scroll down
    page.evaluate("window.scrollTo(0, 600)")

    # Submit form (e.g., "Check Spreadsheet")
    page.click('button:has-text("Check Spreadsheet")')

    # Wait for form submission and redirect
    page.wait_for_load_state('networkidle')

    # Verify scroll position is preserved
    scroll_y = page.evaluate("window.scrollY")
    assert abs(scroll_y - 600) < 20


def test_scroll_preservation_with_tabs(page, assembly):
    """Verify scroll is preserved when switching tabs."""
    page.goto(f"/backoffice/assembly/{assembly.id}/selection")

    # Scroll to position
    page.evaluate("window.scrollTo(0, 400)")

    # Switch to Data tab
    page.click('a:has-text("Data")')
    page.wait_for_load_state('networkidle')

    # Verify scroll preserved
    scroll_y = page.evaluate("window.scrollY")
    assert abs(scroll_y - 400) < 20

    # Verify clean URL
    assert "scroll=" not in page.url


def test_bookmark_url_is_clean(page, assembly_with_history):
    """Verify that bookmarking after scroll preservation gives clean URL."""
    page.goto(f"/backoffice/assembly/{assembly_with_history.id}/selection")

    # Scroll and paginate
    page.evaluate("window.scrollTo(0, 900)")
    page.click('a:has-text("Next")')
    page.wait_for_load_state('networkidle')

    # Wait for cleanup
    page.wait_for_timeout(300)

    # Get current URL (what would be bookmarked)
    current_url = page.url

    # Verify it's clean (has pagination, but no scroll param)
    assert "page=2" in current_url
    assert "scroll=" not in current_url


def test_page_reload_scrolls_to_top(page, assembly_with_history):
    """Verify that F5 reload goes to top (normal browser behavior)."""
    # Navigate to page 2 with scroll preservation
    page.goto(f"/backoffice/assembly/{assembly_with_history.id}/selection")
    page.evaluate("window.scrollTo(0, 1000)")
    page.click('a:has-text("2")')
    page.wait_for_load_state('networkidle')

    # Wait for scroll cleanup
    page.wait_for_timeout(300)

    # Now reload the page (F5 equivalent)
    page.reload()
    page.wait_for_load_state('networkidle')

    # Verify scroll is at top (normal browser behavior)
    scroll_y = page.evaluate("window.scrollY")
    assert scroll_y < 50  # Near top (allow for small variance)
```

---

## Edge Cases & Considerations

### 1. Very Long Pages
- **Scenario:** Page is 10,000px tall, user scrolls to 9,500px
- **Behavior:** Restores to 9,500px correctly
- **Edge Case:** If page content changes and is now only 5,000px tall, browser auto-clamps to max scroll

### 2. Short Pages (No Scroll)
- **Scenario:** User at scrollY=0 clicks pagination
- **Behavior:** URL gets `?scroll=0`, restores to 0, cleans up
- **Impact:** Minimal overhead, no visual difference

### 3. Fast Navigation (Double Click)
- **Scenario:** User double-clicks pagination quickly
- **Behavior:** Each click captures current scroll, both navigations work
- **Impact:** Works correctly (browser navigation queue handles it)

### 4. Browser Back/Forward
- **Scenario:** User clicks back after scroll-preserved navigation
- **Behavior:** Browser's built-in scroll restoration kicks in (we don't interfere)
- **Impact:** Works as expected, browser handles it

### 5. Anchor Links (#hash)
- **Scenario:** Link has hash: `<a href="/page#section">`
- **Behavior:** Directive skips hash links (checked in code)
- **Impact:** Hash navigation works normally

### 6. External Links
- **Scenario:** Link to external site: `<a href="https://example.com">`
- **Behavior:** Directive skips external links (checked in code)
- **Impact:** External navigation works normally

### 7. JavaScript-Disabled
- **Scenario:** User has JavaScript disabled
- **Behavior:** No scroll preservation, normal browser behavior (scroll to top)
- **Impact:** Graceful degradation, no errors

### 8. Multiple Scroll Parameters
- **Scenario:** URL somehow gets `?scroll=100&scroll=200`
- **Behavior:** URLSearchParams.get() returns first value (100)
- **Impact:** Works correctly, cleanup removes all instances

---

## Performance Considerations

### Memory
- **Footprint:** ~2KB minified/gzipped
- **Runtime:** 3 IIFE closures, 1 event listener (scroll)
- **Impact:** Negligible

### CPU
- **Scroll listener:** Debounced (150ms), passive
- **Per navigation:** Math.round() + string concatenation
- **Impact:** Negligible

### Network
- **URL changes:** Uses `history.replaceState()` (no network request)
- **Impact:** Zero

---

## Browser Compatibility

- **Required APIs:**
  - `URLSearchParams` (ES6) - Supported IE 11+ with polyfill
  - `window.scrollTo()` - Universal support
  - `history.replaceState()` - IE 10+
  - `requestAnimationFrame()` - IE 10+
  - `addEventListener(..., { passive: true })` - Modern browsers (graceful fallback)

- **Alpine.js compatibility:** Requires Alpine 3.x+

---

## Future Enhancements

### Potential Additions (Not in Initial Implementation)

1. **Smooth Scroll Restoration**
   ```javascript
   window.scrollTo({ top: scrollPos, behavior: 'smooth' });
   ```

2. **Scroll Position Storage (Alternative to URL)**
   - Use `sessionStorage` instead of URL param
   - Pros: Cleaner URLs
   - Cons: Not testable via URL, not shareable

3. **Per-Container Scroll Preservation**
   - Preserve scroll position of specific divs (e.g., modal, sidebar)
   - Would need container IDs in URL

4. **Configuration Object**
   ```javascript
   Alpine.store('scrollConfig', {
     debounceMs: 150,
     enabled: true,
     paramName: 'scroll'
   });
   ```

---

## Migration Notes

### Existing Code
If you have existing scroll preservation logic, this can replace it:

**Before:**
```html
<div x-data="scrollPreserver()">
  <a :href="addScrollToUrl('/page')">Link</a>
</div>
```

**After:**
```html
{# No x-data needed! #}
<a :href="$preserveScroll('/page')">Link</a>
```

### Adoption Strategy
1. Implement scroll manager globally
2. Update one page at a time (e.g., selection history first)
3. Test thoroughly on that page
4. Roll out to other pages gradually
5. Remove old scroll preservation code once confirmed working

---

## Summary

This scroll preservation system provides:

✅ **Zero-config** - Works globally, just use `$preserveScroll()`
✅ **Testable** - URL-based state enables E2E testing
✅ **Reusable** - Works with links, forms, buttons, tabs
✅ **Clean URLs** - Ephemeral scroll parameter, auto-cleanup
✅ **Performant** - Minimal overhead, passive listeners
✅ **CSP-safe** - No inline scripts
✅ **Accessible** - Doesn't interfere with browser navigation
✅ **Framework-aligned** - Matches Alpine.js patterns

This matches your existing philosophy of URL-based state (like focus preservation) and provides a consistent, reliable way to maintain scroll position across any server-side navigation in the application.
