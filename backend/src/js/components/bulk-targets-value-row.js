// ABOUTME: Alpine component for one editable value row in the bulk targets editor
// ABOUTME: Owns that row's pending-delete flag and its request to re-link min/max to the percentage

/**
 * Build the state for one value row of the bulk targets editor.
 *
 * Nothing here touches the server. Deleting marks the row so that "Save all"
 * removes it, rather than firing its own request - a round trip would throw
 * away every other edit on the page. A row the user added and then deleted has
 * nothing to mark, so it simply leaves the DOM.
 *
 * @param {Object} [options] - configuration
 * @param {boolean} [options.isNew=false] - whether this row was added client-side
 * @param {boolean} [options.deleted=false] - whether the row is already marked
 *   for deletion, as it is when a rejected save redisplays the form
 * @returns {Object} Alpine component state
 */
export function bulkTargetsValueRow(options) {
  var isNew = Boolean(options && options.isNew);

  return {
    deleted: Boolean(options && options.deleted),
    relink: false,
    isNew: isNew,

    get rowClass() {
      return this.deleted ? "is-pending-delete" : "";
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

    usePercentage: function () {
      this.relink = true;
      if (this.$refs.relinkField) this.$refs.relinkField.value = "true";
      this.$root.dispatchEvent(bubblingChange());
    },
  };
}

/**
 * The event a row fires so the category around it can redo its totals.
 *
 * @returns {CustomEvent} a bubbling "targets-changed" event
 */
function bubblingChange() {
  return new CustomEvent("targets-changed", { bubbles: true });
}
