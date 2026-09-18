// ABOUTME: Escape-key close for server-rendered fragment dialogs
// ABOUTME: Clicks the topmost clickable dialog backdrop, whose href is the dialog's close URL

/**
 * Close the topmost open fragment dialog when Escape is pressed.
 *
 * Fragment dialogs (the HTMX modals) render a full-screen
 * `a.dialog-backdrop--clickable` whose href closes the dialog; clicking it is
 * exactly what a backdrop click does, so Escape reuses that path rather than
 * duplicating the close logic.
 *
 * A component that uses Escape for itself - a menu or a dropdown inside a
 * dialog - keeps the key from closing the dialog too by calling
 * preventDefault() or stopPropagation() on it, from a listener on its own
 * element. A listener on window cannot rely on that: it may run after this one.
 * Escape that ends an IME composition belongs to the composition and is ignored.
 */
export function initDialogEscape() {
  window.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
      return;
    }
    if (event.defaultPrevented || event.isComposing) {
      return;
    }
    var backdrops = document.querySelectorAll("a.dialog-backdrop--clickable");
    if (!backdrops.length) {
      return;
    }
    event.preventDefault();
    backdrops[backdrops.length - 1].click();
  });
}
