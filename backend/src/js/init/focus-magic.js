// ABOUTME: Alpine magic $focusUrl and directive x-focus-preserve for keyboard focus preservation
// ABOUTME: Encodes the focused element's data-focus-id in the URL hash so a reload can restore it

/**
 * Register the focus-preservation magic and directive on Alpine.
 *
 * Call from an alpine:init listener.
 */
export function registerFocusMagic() {
  /**
   * Focus URL magic helper
   *
   * Returns the given URL with #focus=<focusId> appended if the current
   * element (or a specified element) has keyboard focus and a data-focus-id.
   *
   * Usage:
   *   <button data-focus-id="my-btn" @click="window.location.href = $focusUrl('/page')">
   *   <select data-focus-id="my-select" @change="window.location.href = $focusUrl('/page?q=' + selected)">
   */
  Alpine.magic("focusUrl", function (el) {
    return function (url, element) {
      var targetEl = element || el;
      var focusId = targetEl.dataset ? targetEl.dataset.focusId : null;
      if (focusId && document.activeElement === targetEl) {
        return url + "#focus=" + focusId;
      }
      return url;
    };
  });

  /**
   * Focus preserve directive
   *
   * Automatically appends focus hash to href when a **keyboard-initiated**
   * click activates a link. Gates on `event.detail === 0` — a MouseEvent's
   * `detail` is the click count for real pointer clicks (>= 1), and is 0
   * for clicks synthesised from keyboard activation (Enter/Space on a
   * focused element, or a scripted `.click()` call). This avoids reviving a
   * visible focus outline on the destination page after a mouse click on
   * browsers/OSes that focus links on click (Windows Chrome, Firefox).
   *
   * Usage:
   *   <a href="/page" data-focus-id="my-link" x-data x-focus-preserve>Link</a>
   */
  Alpine.directive("focus-preserve", function (el) {
    el.addEventListener("click", function (event) {
      var focusId = el.dataset.focusId;
      var isKeyboardClick = event.detail === 0;
      if (isKeyboardClick && focusId && el.href) {
        event.preventDefault();
        window.location.href = el.href + "#focus=" + focusId;
      }
    });
  });
}
