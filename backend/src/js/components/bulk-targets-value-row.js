// ABOUTME: Alpine component for one editable value row in the bulk targets editor
// ABOUTME: Owns the row's pending-delete flag, and whether its min/max follow the percentage

/**
 * Seats added to the top of a range when the percentage divides exactly.
 * Mirrors SLACK_SEATS in opendlp/domain/targets.py.
 */
var SLACK_SEATS = 1;

/**
 * Build the state for one value row of the bulk targets editor.
 *
 * Nothing here touches the server. Deleting marks the row so that saving
 * removes it, rather than firing its own request - a round trip would throw
 * away every other edit on the page. A row the user added and then deleted has
 * nothing to mark, so it simply leaves the DOM.
 *
 * Min and max follow the percentage until someone types into either of them:
 * from then on they are the row's own, and the percentage leaves them alone.
 * "Recalculate" hands them back to the percentage. The save works out for
 * itself which numbers were typed by hand, by comparing them with the ones the
 * percentage gives - so the numbers filled in here must be those exactly.
 *
 * @param {Object} [options] - configuration
 * @param {boolean} [options.isNew=false] - whether this row was added client-side
 * @param {boolean} [options.deleted=false] - whether the row is already marked
 *   for deletion, as it is when a rejected save redisplays the form
 * @param {boolean} [options.manual=false] - whether min and max were set by hand
 * @param {boolean} [options.relink=false] - whether min and max have been handed
 *   back to the percentage, as a rejected save redisplays a row it was asked to
 * @returns {Object} Alpine component state
 */
export function bulkTargetsValueRow(options) {
  var isNew = Boolean(options && options.isNew);

  return {
    deleted: Boolean(options && options.deleted),
    manual: Boolean(options && options.manual),
    relink: Boolean(options && options.relink),
    hasPercentage: false,
    isNew: isNew,

    init: function () {
      this.hasPercentage = numberIn(this.$root, "percentage") !== null;
    },

    get rowClass() {
      return this.deleted ? "is-pending-delete" : "";
    },

    /** Min and max are worked out from the percentage. */
    get showsCalculated() {
      return this.hasPercentage && !this.manual;
    },

    /** Min and max were typed in, and the percentage leaves them alone. */
    get showsManual() {
      return this.hasPercentage && this.manual;
    },

    /** There is a percentage for typed-in min and max to go back to. */
    get canRelink() {
      return this.hasPercentage && this.manual;
    },

    remove: function () {
      if (this.isNew) {
        var root = this.$root;
        var parent = root.parentElement;
        root.remove();
        if (parent) parent.dispatchEvent(bubblingChange());
        return;
      }
      this.deleted = true;
      this.$root.setAttribute("data-deleted", "true");
      if (this.$refs.deletedField) this.$refs.deletedField.value = "true";
      this.$root.dispatchEvent(bubblingChange());
    },

    undoRemove: function () {
      this.deleted = false;
      this.$root.setAttribute("data-deleted", "false");
      if (this.$refs.deletedField) this.$refs.deletedField.value = "false";
      this.$root.dispatchEvent(bubblingChange());
    },

    /**
     * The percentage was typed into. Runs before the category redoes its
     * totals, as the event bubbles up to it, so the totals see the new numbers.
     */
    percentageChanged: function () {
      var percentage = numberIn(this.$root, "percentage");
      this.hasPercentage = percentage !== null;
      if (percentage !== null && !this.manual) this.fillMinMax(percentage);
      this.syncFields();
    },

    /** Min or max was typed into - or written in by accepting a suggestion. */
    minMaxEdited: function () {
      this.manual = true;
      this.relink = false;
      this.syncFields();
    },

    usePercentage: function () {
      var percentage = numberIn(this.$root, "percentage");
      if (percentage === null) return;
      this.manual = false;
      this.relink = true;
      this.fillMinMax(percentage);
      this.syncFields();
      this.$root.dispatchEvent(bubblingChange());
      // The button disables itself, which would drop focus to the page. The
      // percentage rather than min or max, where typing would break the link.
      var input = this.$root.querySelector('[data-field="percentage"]');
      if (input) input.focus();
    },

    fillMinMax: function (percentage) {
      var range = minMaxForPercentage(percentage, numberToSelect(this.$root));
      setField(this.$root, "min", range[0]);
      setField(this.$root, "max", range[1]);
    },

    /**
     * Carry the row's state in its hidden fields. Re-linking needs a
     * percentage to link to, so without one the save is not asked to.
     */
    syncFields: function () {
      if (this.$refs.relinkField) {
        this.$refs.relinkField.value =
          this.relink && this.hasPercentage ? "true" : "false";
      }
      if (this.$refs.manualField) {
        this.$refs.manualField.value = this.manual ? "true" : "false";
      }
    },
  };
}

/**
 * Min/max seats implied by a percentage of the panel. The same arithmetic as
 * min_max_for_percentage in opendlp/domain/targets.py, step for step, so the
 * two agree to the last seat: floor and ceil of the exact share, widened at
 * the top when it divides exactly. A panel size not yet set gives 0 and 0.
 *
 * @param {number} percentage - the population share, 0 to 100
 * @param {number} panelSize - the number of people to select
 * @returns {number[]} [min, max]
 */
export function minMaxForPercentage(percentage, panelSize) {
  if (!(panelSize > 0)) return [0, 0];
  var exact = (percentage * panelSize) / 100;
  var low = Math.floor(exact);
  var high = Math.ceil(exact);
  if (low === high && high > 0) high = Math.min(high + SLACK_SEATS, panelSize);
  return [low, high];
}

/**
 * The panel size, from the form the row sits in.
 *
 * @param {Element} row - the row
 * @returns {number} the panel size, or 0 when it is not given
 */
function numberToSelect(row) {
  var holder = row.closest("[data-number-to-select]");
  if (!holder) return 0;
  var parsed = Number(holder.getAttribute("data-number-to-select"));
  return isNaN(parsed) ? 0 : parsed;
}

/**
 * Read one numeric input out of a row.
 *
 * @param {Element} row - the row to look in
 * @param {string} field - the data-field name of the input
 * @returns {number|null} the value, or null when blank or not a number
 */
function numberIn(row, field) {
  var input = row.querySelector('[data-field="' + field + '"]');
  if (!input || !input.value.trim()) return null;
  var parsed = Number(input.value);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Write a number into one of the row's inputs. No input event: that would
 * read as the number having been typed by hand.
 *
 * @param {Element} row - the row
 * @param {string} field - the data-field name of the input
 * @param {number} value - the number to write
 */
function setField(row, field, value) {
  var input = row.querySelector('[data-field="' + field + '"]');
  if (input) input.value = String(value);
}

/**
 * The event a row fires so the category around it can redo its totals.
 *
 * @returns {CustomEvent} a bubbling "targets-changed" event
 */
function bubblingChange() {
  return new CustomEvent("targets-changed", { bubbles: true });
}
