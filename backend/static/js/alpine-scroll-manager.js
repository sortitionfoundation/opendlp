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
