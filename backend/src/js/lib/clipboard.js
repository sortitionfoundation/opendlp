// ABOUTME: Clipboard copy helpers with feedback for data-copy-text / data-copy-target buttons
// ABOUTME: Falls back to execCommand where the async clipboard API is unavailable

/**
 * Resolve the text a copy button should place on the clipboard.
 *
 * A literal data-copy-text wins; otherwise read the element named by
 * data-copy-target.
 *
 * @param {HTMLElement} button - the button that was clicked
 * @returns {string} the text to copy
 */
export function copyButtonText(button) {
  if (button.dataset.copyText !== undefined) {
    return button.dataset.copyText;
  }
  const element = document.getElementById(button.dataset.copyTarget);
  return element ? element.textContent || element.value : "";
}

/**
 * Copy text to the clipboard, then show feedback on the originating button.
 *
 * @param {string} text - the text to copy
 * @param {HTMLElement} button - the button to show feedback on
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    showCopyFeedback(button);
  } catch (err) {
    // Fallback for older browsers and insecure contexts where the async
    // clipboard API is unavailable
    fallbackCopyToClipboard(text, button);
  }
}

/**
 * Copy via a hidden textarea and document.execCommand.
 *
 * @param {string} text - the text to copy
 * @param {HTMLElement} button - the button to show feedback on
 */
export function fallbackCopyToClipboard(text, button) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    document.execCommand("copy");
    showCopyFeedback(button);
  } catch (err) {
    alert("Failed to copy to clipboard");
  }

  document.body.removeChild(textarea);
}

/**
 * Confirm a successful copy.
 *
 * With data-copy-feedback="inline" the button swaps its .copy-icon-default /
 * .copy-icon-copied SVGs and aria-label for 2s; otherwise fall back to an
 * alert with the button's data-copy-message.
 *
 * @param {HTMLElement} button - the button to show feedback on
 */
export function showCopyFeedback(button) {
  if (button.dataset.copyFeedback === "inline") {
    showInlineCopyFeedback(button);
  } else {
    alert(button.dataset.copyMessage || "Copied!");
  }
}

/**
 * Swap a copy button's icons and aria-label for 2 seconds.
 *
 * The "hidden" class (not the hidden attribute) toggles visibility because
 * Tailwind's preflight sets svg { display: block } at author level, which
 * would override the user-agent [hidden] { display: none } rule.
 *
 * @param {HTMLElement} button - the button to show feedback on
 */
export function showInlineCopyFeedback(button) {
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
