// ABOUTME: Document-level click handlers for confirm, print, copy, download and password toggles
// ABOUTME: Keeps these behaviours attribute-driven so no template needs an inline handler

import { copyButtonText, copyToClipboard } from "../lib/clipboard.js";

// Matches a form that HTMX submits, in either attribute spelling.
const HTMX_FORM_SELECTOR = ["post", "get", "put", "patch", "delete"]
  .map((verb) => `[hx-${verb}], [data-hx-${verb}]`)
  .join(", ");

/**
 * Download the rendered 2FA backup codes as a text file.
 */
export function downloadBackupCodes() {
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

/**
 * Wire up the document-level action handlers.
 */
export function initDocumentActions() {
  // Handle button clicks for confirmations and print
  document.addEventListener("click", function (e) {
    // Check for confirmation. closest() rather than the target itself: the
    // click often lands on the button's label span, not the button. Only
    // clickable controls match: a form carrying data-confirm is handled on
    // submit, so clicks on the fields inside it do not prompt.
    const confirmElement = e.target.closest(
      "button[data-confirm], a[data-confirm]",
    );
    const confirmMsg = confirmElement ? confirmElement.dataset.confirm : "";
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

  // Confirm a form that carries data-confirm when it is submitted. Forms that
  // HTMX submits are ignored: htmx listens for submit on the form itself, which
  // fires before this document-level listener, so the request is already sent
  // by the time a dialog could appear. An HTMX form should put data-confirm on
  // its submit button, or use hx-confirm.
  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form.matches("form[data-confirm]")) return;
    if (form.matches(HTMX_FORM_SELECTOR)) return;
    if (!confirm(form.dataset.confirm)) {
      e.preventDefault();
    }
  });

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
}
