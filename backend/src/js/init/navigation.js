// ABOUTME: Document-level handlers for data-driven navigation without inline handlers
// ABOUTME: Powers data-navigate-base-url selects and data-row-url clickable table rows

import { urlSetParam } from "../lib/url-utils.js";

/**
 * Wire up the document-level navigation handlers.
 *
 * Idempotent only in the sense that it should be called once per page load;
 * it attaches listeners to `document`.
 */
export function initNavigation() {
  // Handle select elements that navigate on change via data-navigate-base-url
  // Optionally preserves scroll position with data-navigate-preserve-scroll attribute
  document.addEventListener("change", function (e) {
    var baseUrl = e.target.dataset.navigateBaseUrl;
    if (baseUrl) {
      var paramName = e.target.dataset.navigateParam || "value";
      var preserveScroll = e.target.hasAttribute(
        "data-navigate-preserve-scroll",
      );
      var url = baseUrl;

      // Add parameter value using URL utilities (handles existing query params correctly)
      if (e.target.value) {
        url = urlSetParam(url, paramName, e.target.value);
      }

      // Add scroll parameter if preservation is enabled
      if (preserveScroll) {
        var currentScroll = Math.round(window.scrollY);
        url = urlSetParam(url, "scroll", currentScroll.toString());
      }

      window.location.href = url;
    }
  });

  // Make table rows with data-row-url navigate when clicked.
  // Clicks on links, buttons, or other interactive elements are left alone, so
  // per-row links (e.g. View / Edit) keep working. A drag-selection is also
  // ignored so users can still highlight cell text without being navigated away.
  document.addEventListener("click", function (e) {
    var row = e.target.closest("[data-row-url]");
    if (!row) return;
    if (e.target.closest("a, button, input, select, textarea, label")) return;
    if (window.getSelection && window.getSelection().toString()) return;
    var url = row.dataset.rowUrl;
    if (e.metaKey || e.ctrlKey || e.shiftKey) {
      window.open(url, "_blank");
    } else {
      window.location.href = url;
    }
  });
}
