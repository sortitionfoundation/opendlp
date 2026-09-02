// ABOUTME: Alpine component for one category block in the bulk targets editor
// ABOUTME: Keeps the totals row live, adds and deletes value rows, and reorders categories

import {
  applyPlaceholder,
  highestNewIndex,
  renumberSortOrder,
} from "../lib/bulk-targets-dom.js";

// Value ids within a category, as save_all_parser names them.
var NEW_VALUE_ID = /\[values\]\[new-(\d+)\]/;

// Matches PERCENTAGE_TOLERANCE in domain/targets.py: the totals row flags the
// same near-100 window the server treats as plausible.
var PERCENTAGE_TOLERANCE = 1.0;

/**
 * Build the state for one category block of the bulk targets editor.
 *
 * Every action is client-side and provisional until the form is saved,
 * so a misplaced click costs nothing and no edit elsewhere on the page is lost.
 *
 * The label for an empty total is read from the block's `data-empty-label`
 * attribute rather than passed in, so a translation containing an apostrophe
 * cannot break the x-data expression it would otherwise sit inside.
 *
 * @param {Object} [options] - configuration
 * @param {boolean} [options.isNew=false] - whether the user added this block client-side
 * @param {boolean} [options.deleted=false] - whether the block is already marked
 *   for deletion, as it is when a rejected save redisplays the form
 * @returns {Object} Alpine component state
 */
export function bulkTargetsCategory(options) {
  var isNew = Boolean(options && options.isNew);

  return {
    deleted: Boolean(options && options.deleted),
    isNew: isNew,
    missingAdded: false,
    newRowCount: 0,
    emptyLabel: "—",
    percentageTotal: "—",
    minTotal: "0",
    maxTotal: "0",
    percentagesPlausible: true,

    init: function () {
      this.emptyLabel = this.$root.dataset.emptyLabel || "—";
      // Start above whatever the server rendered, so a redisplayed form after a
      // rejected save cannot have two rows sharing one id.
      this.newRowCount = highestNewIndex(this.$refs.rows, NEW_VALUE_ID);
      this.recalculate();
    },

    get percentageTotalClass() {
      return this.percentagesPlausible ? "" : "targets-total--implausible";
    },

    markDeleted: function () {
      var container = this.$root.parentElement;
      if (this.isNew) {
        // Never saved, so there is nothing to mark and nothing to undo.
        this.$root.remove();
        renumberSortOrder(container);
        announceChange(container);
        return;
      }
      this.deleted = true;
      if (this.$refs.deletedField) this.$refs.deletedField.value = "true";
      announceChange(container);
    },

    undoDelete: function () {
      this.deleted = false;
      if (this.$refs.deletedField) this.$refs.deletedField.value = "false";
      announceChange(this.$root.parentElement);
    },

    moveUp: function () {
      var previous = this.$root.previousElementSibling;
      if (previous) this.$root.parentElement.insertBefore(this.$root, previous);
      this.renumber();
    },

    moveDown: function () {
      var next = this.$root.nextElementSibling;
      if (next) this.$root.parentElement.insertBefore(next, this.$root);
      this.renumber();
    },

    renumber: function () {
      var container = this.$root.parentElement;
      renumberSortOrder(container);
      announceChange(container);
    },

    addValue: function () {
      var row = this.appendFrom(this.$refs.rowTemplate);
      if (row) {
        var first = row.querySelector("input");
        if (first) first.focus();
      }
      this.recalculate();
      announceChange(this.$root.parentElement);
    },

    addMissingValues: function () {
      this.appendFrom(this.$refs.missingTemplate);
      this.missingAdded = true;
      this.recalculate();
      announceChange(this.$root.parentElement);
    },

    /**
     * Clone a <template> of blank rows into the table, giving each a fresh id.
     *
     * The ids are "new-<n>", the shape save_all_parser reads as "create this
     * one". They only need to be unique within the category.
     *
     * @param {HTMLTemplateElement} template - template holding one or more rows
     * @returns {Element|null} the last row appended, or null if there was none
     */
    appendFrom: function (template) {
      if (!template) return null;
      var fragment = template.content.cloneNode(true);
      var rows = Array.prototype.slice.call(fragment.children);
      var self = this;
      rows.forEach(function (row) {
        self.newRowCount += 1;
        applyPlaceholder(row, "__ID__", "new-" + self.newRowCount);
      });
      this.$refs.rows.appendChild(fragment);
      return rows.length ? rows[rows.length - 1] : null;
    },

    /**
     * Redo the totals row from what is currently typed into the table.
     *
     * A preview of the numbers, not a prediction of them: values re-linked to
     * their percentage still show the min/max they hold now, because the seat
     * counts they will be recalculated to are the server's to work out.
     */
    recalculate: function () {
      var rows = this.$refs.rows.querySelectorAll("[data-value-row]");
      var percentage = 0;
      var anyPercentage = false;
      var min = 0;
      var max = 0;

      for (var i = 0; i < rows.length; i++) {
        if (rows[i].getAttribute("data-deleted") === "true") continue;
        var cellPercentage = numberIn(rows[i], "percentage");
        if (cellPercentage !== null) {
          percentage += cellPercentage;
          anyPercentage = true;
        }
        min += numberIn(rows[i], "min") || 0;
        max += numberIn(rows[i], "max") || 0;
      }

      this.percentageTotal = anyPercentage
        ? String(round2(percentage)) + "%"
        : this.emptyLabel;
      this.percentagesPlausible =
        !anyPercentage || Math.abs(percentage - 100) <= PERCENTAGE_TOLERANCE;
      this.minTotal = String(min);
      this.maxTotal = String(max);
    },
  };
}

/**
 * Tell the page something in the form changed, other than by typing.
 *
 * Fired on the container rather than on the block, because the block's own
 * "targets-changed" handler redoes its totals - which the caller has already
 * done directly. Above that it is what tells the edit guard the page is dirty:
 * adding, deleting and reordering fire no input event of their own.
 *
 * @param {Element} container - the element holding the category blocks
 */
function announceChange(container) {
  if (!container) return;
  container.dispatchEvent(
    new CustomEvent("targets-changed", { bubbles: true }),
  );
}

/**
 * Read one numeric cell out of a row.
 *
 * @param {Element} row - the row to look in
 * @param {string} field - the data-field name of the cell
 * @returns {number|null} the value, or null when blank or not a number
 */
function numberIn(row, field) {
  var input = row.querySelector('[data-field="' + field + '"]');
  if (!input || !input.value.trim()) return null;
  var parsed = Number(input.value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Round to two decimal places, matching the server's percentage_total.
 *
 * @param {number} value - the number to round
 * @returns {number} the rounded number
 */
function round2(value) {
  return Math.round(value * 100) / 100;
}
