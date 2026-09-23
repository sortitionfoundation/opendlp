// ABOUTME: Unsaved-input guard for the server-rendered set-up and question dialogs
// ABOUTME: Composes editGuard; the dirty flag rides a hidden input through each HTMX re-render

import { editGuard } from "./edit-guard.js";

/**
 * Build the state for a fragment dialog that should not lose what was typed.
 *
 * The dialog closes through links - the X, Cancel and the backdrop, which is
 * also what Escape clicks (see init/dialog-escape.js). Each is wired to
 * guardLeave(), so a dirty dialog asks through editGuard's discard dialog
 * instead of closing.
 *
 * The dialog is re-rendered by the server on every type or method choice, and
 * each re-render is a fresh component. So the dirty flag is also written to a
 * hidden input (x-ref="dirtyInput", name="dirty") that the re-rendering request
 * carries, and the server echoes it back for init() to read. `input` fires
 * before `change`, so the flag is set before HTMX serialises the form for the
 * change it triggers on.
 *
 * initEditGuard() is not called: its beforeunload listener lives on window and
 * would outlive the dialog, still reading this component's flag after HTMX had
 * swapped the dialog away.
 *
 * @returns {Object} Alpine component state
 */
export function dialogLeaveGuard() {
  return Object.assign({}, editGuard(), {
    init: function () {
      var input = this.$refs.dirtyInput;
      if (input && input.value === "1") {
        this.editDirty = true;
      }
    },

    markDialogDirty: function () {
      this.markEditDirty();
      if (this.$refs.dirtyInput) {
        this.$refs.dirtyInput.value = "1";
      }
    },
  });
}
