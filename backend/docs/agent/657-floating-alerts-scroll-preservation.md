# Plan: Floating Alerts + Scroll Preservation for Async Operations

**Branch:** 657-assembly-a11y-2
**Status:** Ready for implementation

## Overview

Two related accessibility/UX improvements:
1. **Floating alerts** - Show flash messages at bottom of viewport (not top of page)
2. **Scroll preservation for forms** - Opt-in parameter to preserve scroll after form submission

## Problem

Currently:
- Flash messages appear at top of page content, causing scroll-to-top on every async operation
- Users lose their scroll position after save/delete operations
- Poor UX especially on long pages

## Part 1: Floating Alerts

### Design

- Fixed position at **bottom-right** of viewport
- 1.5rem (24px) offset from edges
- Max width constrained (`max-w-md`)
- Below modals in z-index (`z-30`)
- Always dismissible
- `aria-live="polite"` for screen reader announcements
- Multiple alerts stack vertically with gap

### Changes

**1. Create `templates/backoffice/components/floating_alerts.html`**

New macro that renders flash messages in a fixed-position container:

```html
{% macro floating_alerts() %}
<div id="floating-alerts"
     class="fixed bottom-6 right-6 z-30 flex flex-col gap-3 max-w-md"
     aria-live="polite">
    {% for category, message in get_flashed_messages(with_categories=true) %}
        {{ alert(message, variant=category_to_variant(category), dismissible=true) }}
    {% endfor %}
</div>
{% endmacro %}
```

**2. Update `templates/backoffice/base_page.html`**

- Remove `{{ flash_messages() }}` from inside `<main>` (line 29)
- Add `{{ floating_alerts() }}` after `</main>` but inside the flex container (before footer or after)

**3. Update `templates/backoffice/components/alert.html`**

- Remove `mb-6` margin from alert div when used in floating context (stacking handled by container gap)
- Option: Add `floating=false` parameter to alert macro, skip margin when true

## Part 2: Scroll Preservation for Form Submissions

### Approach: Data Attribute (CSP-safe)

Add `data-preserve-scroll` attribute to forms that should preserve scroll position after page reload.

This integrates with the existing scroll preservation system in `alpine-scroll-manager.js` which already handles the `?scroll=<position>` URL parameter.

**1. Update `static/backoffice/js/alpine-components.js`**

Modify `$confirm` magic to check for data attribute:

```javascript
Alpine.magic("confirm", function () {
    return function (message, formElement) {
        if (confirm(message)) {
            if (formElement.hasAttribute("data-preserve-scroll")) {
                var action = formElement.getAttribute("action") || window.location.href;
                var scrollPos = Math.round(window.scrollY);
                formElement.setAttribute("action", urlSetParam(action, "scroll", scrollPos.toString()));
            }
            formElement.submit();
        }
    };
});
```

**2. Add new directive for non-confirmation forms**

```javascript
Alpine.directive("preserve-scroll-on-submit", function (el) {
    el.addEventListener("submit", function () {
        var action = el.getAttribute("action") || window.location.href;
        var scrollPos = Math.round(window.scrollY);
        el.setAttribute("action", urlSetParam(action, "scroll", scrollPos.toString()));
    });
});
```

### Template Usage Patterns

```html
<!-- With confirmation dialog - add data-preserve-scroll attribute -->
<form method="post" action="{{ url_for('...') }}"
      x-data
      data-preserve-scroll
      @submit.prevent="$confirm('{{ _('Are you sure?') }}', $el)">
    {{ csrf_token_input() }}
    {{ button("Delete", type="submit", variant="danger") }}
</form>

<!-- Without confirmation - use directive -->
<form method="post" action="{{ url_for('...') }}"
      x-data
      x-preserve-scroll-on-submit>
    {{ csrf_token_input() }}
    {{ button("Save", type="submit") }}
</form>
```

## Files to Modify

| File | Action |
|------|--------|
| `templates/backoffice/components/floating_alerts.html` | **Create** - new floating alerts macro |
| `templates/backoffice/components/alert.html` | **Modify** - add floating parameter or remove margin |
| `templates/backoffice/base_page.html` | **Modify** - move flash messages to floating position |
| `static/backoffice/js/alpine-components.js` | **Modify** - enhance `$confirm`, add directive |

## Dependencies

- Existing `alpine-scroll-manager.js` - handles `?scroll=` URL parameter restoration
- Existing `url-utils.js` - provides `urlSetParam()` function

## Verification

### Manual Testing

1. **Floating alerts**:
   - Trigger a flash message (e.g., save an assembly)
   - Alert should appear at bottom-right, not top of page
   - Scroll down on a long page, trigger action → alert visible without scrolling
   - Dismiss alert with close button (mouse and keyboard)
   - Test with screen reader (VoiceOver on Mac: Cmd+F5)

2. **Scroll preservation**:
   - Add `data-preserve-scroll` to a test form
   - Scroll down on page, submit form with confirmation
   - After page reload, scroll position should be restored
   - Without the attribute, scroll should go to top (default behavior)

### Automated Tests

```bash
# Run existing scroll preservation tests
CI=true uv run pytest tests/bdd/test_scroll_preservation.py -v
```

Consider adding BDD scenarios for:
- Floating alert visibility after action
- Form submission with scroll preservation

## Accessibility Considerations

- `role="alert"` on individual alerts (already present)
- `aria-live="polite"` on container - announces new alerts without interrupting
- Dismiss button has `aria-label` for screen readers
- Focus returns to trigger element after dismiss (if applicable)
- Keyboard accessible close button (Enter/Space)
