// ABOUTME: Close handlers, focus and auto-scroll for .progress-modal elements
// ABOUTME: Re-runs after HTMX swaps so polling updates keep working

/**
 * Set up every .progress-modal currently in the document.
 *
 * Reads state from data-can-close and data-close-url on the modal element.
 */
export function setupProgressModals() {
  document.querySelectorAll(".progress-modal").forEach(function (modal) {
    var canClose = modal.dataset.canClose === "true";
    var closeUrl = modal.dataset.closeUrl;
    var modalId = modal.id;

    // Auto-scroll any message log to the bottom
    var messages = modal.querySelector("[id$='-messages'], #modal-messages");
    if (messages) {
      messages.scrollTop = messages.scrollHeight;
    }

    // Focus the modal panel so Firefox dispatches keyboard events
    var panel = document.getElementById(modalId + "-panel");
    if (panel) {
      panel.focus();
    }

    // Close handler for X button
    var closeBtn = document.getElementById(modalId + "-close-btn");
    if (closeBtn) {
      closeBtn.onclick = canClose
        ? function () {
            window.location.href = closeUrl;
          }
        : null;
    }

    // Close handler for backdrop
    var backdrop = document.getElementById(modalId + "-backdrop");
    if (backdrop) {
      backdrop.onclick = canClose
        ? function () {
            window.location.href = closeUrl;
          }
        : null;
    }
  });
}

/**
 * Wire up progress modal setup, the Escape key handler and the HTMX re-run.
 *
 * Runs setup after DOM ready and after every HTMX swap, so it works even when
 * the modal transitions from "running" to "finished" via HTMX polling.
 */
export function initProgressModals() {
  // Escape key: find any closeable progress modal and navigate to its close URL.
  // Uses window (not document) for reliable Firefox support.
  window.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var modal = document.querySelector(
        '.progress-modal[data-can-close="true"]',
      );
      if (modal && modal.dataset.closeUrl) {
        e.preventDefault();
        window.location.href = modal.dataset.closeUrl;
      }
    }
  });

  // Run after DOM is ready (script may load in <head> before body exists)
  document.addEventListener("DOMContentLoaded", setupProgressModals);

  // Re-run after HTMX swaps (covers polling updates)
  document.addEventListener("htmx:afterSwap", function (e) {
    if (
      e.detail.target &&
      e.detail.target.classList.contains("progress-modal")
    ) {
      setupProgressModals();
    }
  });
}
