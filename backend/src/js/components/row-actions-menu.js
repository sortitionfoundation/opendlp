// ABOUTME: Alpine component for a row's "more actions" menu behind a kebab button
// ABOUTME: Escape closes just the menu, even when the row sits inside a dialog Escape would close

/**
 * Build the state for a kebab actions menu.
 *
 * Bind closeOnEscape to keydown.escape on the element wrapping the toggle and
 * menu (not on window). When the menu is open, the key press stops there, so
 * dialog-escape.js - listening on window - does not also close the dialog the
 * row lives in; focus returns to the kebab. With the menu shut, Escape carries
 * on to the dialog as usual.
 *
 * @returns {Object} Alpine component state
 */
export function rowActionsMenu() {
  return {
    open: false,

    toggleMenu: function () {
      this.open = !this.open;
    },

    closeMenu: function () {
      this.open = false;
    },

    closeOnEscape: function (event) {
      if (!this.open) return;
      event.stopPropagation();
      this.open = false;
      if (this.$refs.menuToggle) this.$refs.menuToggle.focus();
    },
  };
}
