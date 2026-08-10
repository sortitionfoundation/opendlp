/**
 * ABOUTME: Restores keyboard focus and scroll position after a backoffice page reload
 * ABOUTME: Reads #focus=<focusId> from the hash and ?scroll=<position> from the query
 *
 * Preserving focus across a reload improves keyboard navigation when a dropdown
 * or other control triggers a page load. Both markers are ephemeral: each is
 * stripped from the URL as soon as it has been used.
 *
 * Focus is written by the $focusUrl magic and the x-focus-preserve directive
 * (init/focus-magic.js); scroll is written by the $confirm magic and the
 * x-preserve-scroll-on-submit directive (init/form-confirm.js).
 */

/**
 * Restore focus to the element named by the #focus= hash, then clean the hash.
 */
export function restoreFocusFromHash() {
  var hash = window.location.hash;
  if (!hash.startsWith("#focus=")) return;

  var focusId = hash.substring(7);
  var el = document.querySelector('[data-focus-id="' + focusId + '"]');
  if (!el) return;

  el.focus();
  // Clean up the URL hash after restoring focus
  if (window.history.replaceState) {
    var cleanUrl = window.location.href.split("#")[0];
    window.history.replaceState(null, "", cleanUrl);
  }
}

/**
 * Restore the scroll position named by ?scroll=, then clean the query string.
 */
export function restoreScrollFromQuery() {
  var urlParams = new URLSearchParams(window.location.search);
  var scrollPos = urlParams.get("scroll");
  if (scrollPos === null) return;

  var scrollY = parseInt(scrollPos, 10);
  if (isNaN(scrollY)) return;

  window.scrollTo(0, scrollY);
  // Clean up the URL after restoring scroll
  if (window.history.replaceState) {
    urlParams.delete("scroll");
    var newSearch = urlParams.toString();
    var scrolledUrl =
      window.location.pathname +
      (newSearch ? "?" + newSearch : "") +
      window.location.hash;
    window.history.replaceState(null, "", scrolledUrl);
  }
}

/**
 * Run both restorations once the DOM is ready.
 */
export function initFocusRestore() {
  document.addEventListener("DOMContentLoaded", function () {
    restoreFocusFromHash();
    restoreScrollFromQuery();
  });
}
