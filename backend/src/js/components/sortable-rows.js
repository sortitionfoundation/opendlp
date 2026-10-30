// ABOUTME: Alpine component letting the questions list's rows be dragged into a new order
// ABOUTME: Sortable.js moves the rows; when one lands somewhere new the reorder form posts the order

import Sortable from "sortablejs";

// The form, outside the table, that each row's hidden "item" input belongs to
// through its form attribute - so it posts the rows in their current order.
export const REORDER_FORM_ID = "reorder-form";

/**
 * Put on the <tbody>: `x-data="sortableRows"`.
 *
 * Dragging is a pointer shortcut. A row is picked up only by its
 * [data-drag-handle], which is aria-hidden: the row menu's move commands are
 * the keyboard and screen reader route (WCAG 2.2, 2.5.7 Dragging Movements).
 * The reorder form swaps in the redrawn list, which mounts a fresh component.
 *
 * @returns {Object} Alpine component state
 */
export function sortableRows() {
  return {
    sortable: null,

    init: function () {
      this.sortable = Sortable.create(this.$el, {
        handle: "[data-drag-handle]",
        animation: 150,
        onEnd: function (event) {
          if (event.oldIndex === event.newIndex) return;
          var form = document.getElementById(REORDER_FORM_ID);
          if (form) form.requestSubmit();
        },
      });
    },

    destroy: function () {
      if (this.sortable) this.sortable.destroy();
    },
  };
}
