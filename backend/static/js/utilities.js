// ABOUTME: JavaScript utilities for form confirmations, clipboard, downloads, and print
// ABOUTME: Provides event-driven handlers for common UI interactions without inline handlers

// Handle select elements that navigate on change via data-navigate-base-url
// Optionally preserves scroll position with data-navigate-preserve-scroll attribute
// Note: Requires url-utils.js to be loaded before this file
document.addEventListener("change", function (e) {
  var baseUrl = e.target.dataset.navigateBaseUrl;
  if (baseUrl) {
    var paramName = e.target.dataset.navigateParam || "value";
    var preserveScroll = e.target.hasAttribute("data-navigate-preserve-scroll");
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

// Handle button clicks for confirmations and print
document.addEventListener("click", function (e) {
  // Check for confirmation
  const confirmMsg = e.target.dataset.confirm;
  if (confirmMsg && !confirm(confirmMsg)) {
    e.preventDefault();
    return;
  }

  // Check for print
  if (e.target.dataset.print !== undefined) {
    window.print();
  }

  // Check for clipboard copy. The text comes either from a literal
  // data-copy-text attribute or from the textContent/value of the element
  // named by data-copy-target.
  const copyButton = e.target.closest("[data-copy-text], [data-copy-target]");
  if (copyButton) {
    copyToClipboard(copyButtonText(copyButton), copyButton);
  }

  // Check for backup codes download
  if (e.target.dataset.downloadBackupCodes !== undefined) {
    downloadBackupCodes();
  }
});

// Resolve the text a copy button should place on the clipboard. A literal
// data-copy-text wins; otherwise read the element named by data-copy-target.
function copyButtonText(button) {
  if (button.dataset.copyText !== undefined) {
    return button.dataset.copyText;
  }
  const element = document.getElementById(button.dataset.copyTarget);
  return element ? element.textContent || element.value : "";
}

// Copy text to clipboard with fallback for older browsers, then show feedback
// on the originating button.
async function copyToClipboard(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    handleCopySuccess(button);
  } catch (err) {
    // Fallback for older browsers and insecure contexts where the async
    // clipboard API is unavailable
    fallbackCopyToClipboard(text, button);
  }
}

function fallbackCopyToClipboard(text, button) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    document.execCommand("copy");
    handleCopySuccess(button);
  } catch (err) {
    handleCopyFailure(button);
  }

  document.body.removeChild(textarea);
}

// Notify on a successful copy: show the button's own feedback (see
// showCopyFeedback) and dispatch a bubbling "clipboard-copied" event so a
// surrounding component (e.g. an Alpine controller) can show a toast.
function handleCopySuccess(button) {
  showCopyFeedback(button);
  button.dispatchEvent(new CustomEvent("clipboard-copied", { bubbles: true }));
}

// Notify on a failed copy. Pages opting into event-driven feedback
// (data-copy-feedback="none") handle the "clipboard-copy-failed" event; others
// keep the inline alert so the failure is never silent.
function handleCopyFailure(button) {
  button.dispatchEvent(new CustomEvent("clipboard-copy-failed", { bubbles: true }));
  if (button.dataset.copyFeedback !== "none") {
    alert("Failed to copy to clipboard");
  }
}

// Confirm a successful copy. With data-copy-feedback="inline" the button swaps
// its .copy-icon-default / .copy-icon-copied SVGs and aria-label for 2s; with
// data-copy-feedback="none" it shows nothing (the caller listens for the
// clipboard-copied event instead); otherwise it falls back to an alert with the
// button's data-copy-message.
function showCopyFeedback(button) {
  if (button.dataset.copyFeedback === "inline") {
    showInlineCopyFeedback(button);
  } else if (button.dataset.copyFeedback === "none") {
    // No inline feedback; a listener on the clipboard-copied event handles it.
  } else {
    alert(button.dataset.copyMessage || "Copied!");
  }
}

// The "hidden" class (not the hidden attribute) toggles visibility because
// Tailwind's preflight sets svg { display: block } at author level, which
// would override the user-agent [hidden] { display: none } rule.
function showInlineCopyFeedback(button) {
  const defaultIcon = button.querySelector(".copy-icon-default");
  const copiedIcon = button.querySelector(".copy-icon-copied");
  const defaultLabel = button.dataset.copyLabel;
  const copiedLabel = button.dataset.copiedLabel;

  if (defaultIcon) defaultIcon.classList.add("hidden");
  if (copiedIcon) copiedIcon.classList.remove("hidden");
  if (copiedLabel) button.setAttribute("aria-label", copiedLabel);

  setTimeout(function () {
    if (defaultIcon) defaultIcon.classList.remove("hidden");
    if (copiedIcon) copiedIcon.classList.add("hidden");
    if (defaultLabel) button.setAttribute("aria-label", defaultLabel);
  }, 2000);
}

// Progress modal: close handlers (Escape, X button, backdrop) and auto-scroll.
// Reads state from data-can-close and data-close-url on .progress-modal elements.
// Runs after DOM ready and re-runs after every HTMX swap so it works even when
// the modal transitions from "running" to "finished" via HTMX polling.
(function () {
  function setupProgressModals() {
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
})();

// Toggle password visibility via data-toggle-password
document.addEventListener("click", function (e) {
  var btn = e.target.closest("[data-toggle-password]");
  if (!btn) return;
  var targetId = btn.dataset.togglePassword;
  var input = document.getElementById(targetId);
  if (!input) return;
  var isPassword = input.type === "password";
  input.type = isPassword ? "text" : "password";
  btn.textContent = isPassword ? "Hide" : "Show";
  btn.setAttribute(
    "aria-label",
    isPassword ? "Hide password" : "Show password",
  );
});

// Download 2FA backup codes as text file
function downloadBackupCodes() {
  const codesElement = document.getElementById("backup-codes");
  const codes = Array.from(codesElement.children)
    .map((el) => el.textContent)
    .join("\n");
  const blob = new Blob([codes], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "2fa-backup-codes.txt";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
