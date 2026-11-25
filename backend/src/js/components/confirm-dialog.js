// ABOUTME: Alpine component for an action that is confirmed in an alert dialog before it is taken
// ABOUTME: Opening moves focus to the dialog's safe action and unticks its box; cancelling gives focus back to the opener

/**
 * Build the state for one confirmed action: the button that asks, and the
 * controlled_alert_dialog() it opens.
 *
 * The dialog is drawn with open_expr="isOpen" and close_expr="cancel()". Its
 * safe action carries x-ref="safeAction" and takes the focus when the dialog
 * opens, as the registration editor's close confirmation does; the opener
 * carries x-ref="opener" and gets the focus back when the dialog is cancelled.
 * The action itself submits a form, so choosing it needs nothing here.
 *
 * An action that needs a box ticked first, as archiving a project with a
 * published registration page does, binds the checkbox with x-model="ticked"
 * and the action's :disabled to "!ticked". The checkbox posts with the form,
 * so what is sent is what the box shows. Every opening starts unticked, so a
 * tick left from an earlier opening never confirms on its own.
 *
 * Usage:
 *   <div x-data="confirmDialog">
 *     <button type="button" x-ref="opener" @click="open()">Archive project</button>
 *     {% call controlled_alert_dialog(..., open_expr="isOpen", close_expr="cancel()") %}
 *       <form method="post" ...>
 *         <input type="checkbox" name="force" value="1" x-model="ticked"> (only where one is needed)
 *         <button type="submit" :disabled="!ticked">Archive project</button>
 *         <button type="button" x-ref="safeAction" @click="cancel()">Keep it active</button>
 *       </form>
 *     {% endcall %}
 *   </div>
 *
 * @returns {Object} Alpine component state
 */
export function confirmDialog() {
  return {
    isOpen: false,
    ticked: false,

    open: function () {
      var self = this;
      self.ticked = false;
      self.isOpen = true;
      self.$nextTick(function () {
        if (self.$refs.safeAction) self.$refs.safeAction.focus();
      });
    },

    cancel: function () {
      var self = this;
      self.isOpen = false;
      self.$nextTick(function () {
        if (self.$refs.opener) self.$refs.opener.focus();
      });
    },
  };
}
