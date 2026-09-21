// ABOUTME: Alpine component for a row's "more actions" menu behind a kebab button
// ABOUTME: A WAI-ARIA menu button: arrow keys move between items, Escape closes just the menu

var ITEM_SELECTOR = '[role="menuitem"]:not([disabled])';

/**
 * Build the state for a kebab actions menu, following the WAI-ARIA menu button
 * pattern (https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/).
 *
 * The template gives the toggle x-ref="menuToggle" and the role="menu" element
 * x-ref="menu", and every menuitem tabindex="-1": the menu is one Tab stop, and
 * the arrow keys move within it.
 *
 * Bind on the element wrapping the toggle and menu (not on window):
 *   @keydown.escape="closeOnEscape"  - when the menu is open the key press stops
 *       there, so dialog-escape.js - listening on window - does not also close
 *       the dialog the row lives in; focus returns to the kebab. With the menu
 *       shut, Escape carries on to the dialog as usual.
 *   @focusout="closeOnFocusOut"      - tabbing out of the menu closes it.
 * Bind @keydown="onToggleKeydown" on the toggle and @keydown="onMenuKeydown" on
 * the menu.
 *
 * @returns {Object} Alpine component state
 */
export function rowActionsMenu() {
  return {
    open: false,

    items: function () {
      if (!this.$refs.menu) return [];
      return Array.prototype.slice.call(
        this.$refs.menu.querySelectorAll(ITEM_SELECTOR),
      );
    },

    /**
     * Focus the item at an index, wrapping past either end.
     *
     * @param {number} index - may be -1 (last) or items.length (first)
     */
    focusItem: function (index) {
      var items = this.items();
      if (!items.length) return;
      var count = items.length;
      items[((index % count) + count) % count].focus();
    },

    /**
     * Open the menu and, once it is displayed, focus one of its items.
     *
     * @param {number} index - 0 for the first item, -1 for the last
     */
    openAndFocus: function (index) {
      var self = this;
      this.open = true;
      // x-show has not revealed the menu yet, and a hidden item cannot take focus.
      this.$nextTick(function () {
        self.focusItem(index);
      });
    },

    toggleMenu: function () {
      if (this.open) {
        this.open = false;
        return;
      }
      this.openAndFocus(0);
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

    closeOnFocusOut: function (event) {
      if (!this.open) return;
      // No relatedTarget means focus went nowhere: a click on something that does
      // not take focus, which in Safari includes the kebab itself. Clicks are
      // click.outside's business, and closing here would let the kebab's own
      // click reopen the menu.
      if (!event.relatedTarget) return;
      if (this.$el.contains(event.relatedTarget)) return;
      this.open = false;
    },

    /** Arrow keys on the kebab open the menu: down to the first item, up to the last. */
    onToggleKeydown: function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        this.openAndFocus(0);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        this.openAndFocus(-1);
      }
    },

    onMenuKeydown: function (event) {
      var items = this.items();
      var current = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown") {
        event.preventDefault();
        this.focusItem(current + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        this.focusItem(current === -1 ? -1 : current - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        this.focusItem(0);
      } else if (event.key === "End") {
        event.preventDefault();
        this.focusItem(-1);
      }
    },
  };
}
