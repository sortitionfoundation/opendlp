// ABOUTME: JavaScript utilities for form confirmations, clipboard, downloads, and print
// ABOUTME: Provides event-driven handlers for common UI interactions without inline handlers

// Handle select elements that navigate on change via data-navigate-base-url
document.addEventListener("change", function (e) {
  var baseUrl = e.target.dataset.navigateBaseUrl;
  if (baseUrl) {
    var paramName = e.target.dataset.navigateParam || "value";
    var url = baseUrl;
    if (e.target.value) {
      url += "?" + paramName + "=" + encodeURIComponent(e.target.value);
    }
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

  // Check for clipboard copy via data-copy-target
  const copyTarget = e.target.dataset.copyTarget;
  if (copyTarget) {
    const copyMessage = e.target.dataset.copyMessage || "Copied!";
    copyToClipboard(copyTarget, copyMessage);
  }

  // Check for backup codes download
  if (e.target.dataset.downloadBackupCodes !== undefined) {
    downloadBackupCodes();
  }
});

// Copy text to clipboard with fallback for older browsers
async function copyToClipboard(elementId, successMessage) {
  const element = document.getElementById(elementId);
  const text = element.textContent || element.value;

  try {
    await navigator.clipboard.writeText(text);
    alert(successMessage);
  } catch (err) {
    // Fallback for older browsers
    fallbackCopyToClipboard(text, successMessage);
  }
}

function fallbackCopyToClipboard(text, successMessage) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    document.execCommand("copy");
    alert(successMessage);
  } catch (err) {
    alert("Failed to copy to clipboard");
  }

  document.body.removeChild(textarea);
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
