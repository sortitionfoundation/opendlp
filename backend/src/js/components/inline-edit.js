// ABOUTME: Alpine component for one value edited in place: the pencil opens a field, the tick or Enter saves it
// ABOUTME: Escape puts the stored value back, leaving the row saves; htmx posts the form and swaps the row back in

/**
 * The event htmx sends the row's form on - its hx-trigger. The form's own
 * submit is cancelled, so a value that has not changed never reaches the server.
 */
export const SAVE_EVENT = "inline-edit-save";

/**
 * Build the state for one row edited in place.
 *
 * The row is a form holding the stored value as text, a field for it, an Edit
 * button (the pencil) and a Save button (the tick). The pencil swaps the text
 * for the field. The tick, Enter, or leaving the row - a click or a Tab
 * elsewhere - saves what was typed; Escape puts the stored value back. The
 * server answers a save with the row rendered afresh, which htmx swaps in, so
 * this component then starts over from the new markup: at rest after a save,
 * still editing, with the reason under the field, after a refusal.
 *
 * The root form may carry data-editing, for a row the server rendered while
 * editing (a refused value). Refs:
 *   field - the input
 *   saved - an unnamed hidden input holding the stored value: what Escape puts
 *           back and what counts as unchanged. Not the field's defaultValue,
 *           which after a refusal is the refused value.
 *   edit - the pencil
 *   returnFocus - a hidden input the server reads. A save made from inside the
 *           row (the tick or Enter) sets it, and the row comes back with the
 *           pencil focused, so a keyboard user keeps their place when the row is
 *           swapped. A save made by leaving the row leaves focus where it went.
 *
 * @returns {Object} Alpine component state
 */
function withBareLineFeeds(text) {
  return String(text).replace(/\r\n/g, "\n");
}

export function inlineEdit() {
  return {
    editing: false,
    saving: false,
    failed: false,

    init: function () {
      this.editing = this.$root.hasAttribute("data-editing");
    },

    savedValue: function () {
      return this.$refs.saved ? this.$refs.saved.value : "";
    },

    /**
     * Whether the field holds something other than the stored value.
     *
     * Line endings are left out of it: a textarea reports its value with bare
     * line feeds, while a value that came through a form post is stored with
     * carriage returns too, and the two are the same text.
     */
    hasChanged: function () {
      var field = this.$refs.field;
      if (!field) return false;
      return (
        withBareLineFeeds(field.value) !== withBareLineFeeds(this.savedValue())
      );
    },

    startEditing: function () {
      var self = this;
      self.editing = true;
      self.$nextTick(function () {
        var field = self.$refs.field;
        if (field) {
          field.focus();
          field.select();
        }
      });
    },

    /** Escape: put the stored value back and stop editing. */
    cancel: function () {
      if (!this.editing || this.saving) return;
      if (this.$refs.field) this.$refs.field.value = this.savedValue();
      this.failed = false;
      this.stopEditing(true);
    },

    /** The form's submit: the tick, or Enter in the field. */
    save: function () {
      this.commit(true);
    },

    /**
     * Focus left the form: save, unless it is only moving within the row.
     *
     * Where focus went is read once the browser has moved it rather than from
     * the event, because the event cannot tell the cases apart: relatedTarget
     * is null for a click on the page around the row, for a click on a button
     * in a browser that does not focus buttons (Safari), and for switching to
     * another window. In the last case focus stays on the field, and nothing is
     * saved.
     *
     * @param {FocusEvent} event - the focusout event
     */
    leave: function (event) {
      var self = this;
      if (!self.editing || self.saving) return;
      var root = self.$root;
      if (event && event.relatedTarget && root.contains(event.relatedTarget)) {
        return;
      }
      setTimeout(function () {
        if (root.contains(document.activeElement)) return;
        self.commit(false);
      }, 0);
    },

    /**
     * Send the field's value, or just stop editing if it has not changed.
     *
     * @param {boolean} returnFocus - focus the pencil once the row is back
     */
    commit: function (returnFocus) {
      if (!this.editing || this.saving) return;
      if (!this.hasChanged()) {
        this.failed = false;
        this.stopEditing(returnFocus);
        return;
      }
      this.saving = true;
      this.failed = false;
      if (this.$refs.returnFocus) {
        this.$refs.returnFocus.value = returnFocus ? "1" : "";
      }
      this.$root.dispatchEvent(new CustomEvent(SAVE_EVENT));
    },

    /**
     * htmx:after-request on the form. An answer htmx swapped in replaces this
     * component, so this only matters when there was none to swap: the network
     * failed, or the server broke. The field stays open with what was typed, and
     * the row says the change was not saved, so it can be tried again.
     *
     * @param {CustomEvent} event - the htmx event, with detail.successful
     */
    requestDone: function (event) {
      if (event && event.detail && event.detail.successful) return;
      this.saving = false;
      this.failed = true;
    },

    stopEditing: function (returnFocus) {
      var self = this;
      self.editing = false;
      if (!returnFocus) return;
      self.$nextTick(function () {
        if (self.$refs.edit) self.$refs.edit.focus();
      });
    },
  };
}
