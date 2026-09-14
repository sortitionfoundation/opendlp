// ABOUTME: Escape-key close for server-rendered fragment dialogs
// ABOUTME: Clicks the topmost clickable dialog backdrop, whose href is the dialog's close URL

/**
 * Close the topmost open fragment dialog when Escape is pressed.
 *
 * Fragment dialogs (the HTMX modals) render a full-screen
 * `a.dialog-backdrop--clickable` whose href closes the dialog; clicking it is
 * exactly what a backdrop click does, so Escape reuses that path rather than
 * duplicating the close logic.
 */
export function initDialogEscape() {
  window.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
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
