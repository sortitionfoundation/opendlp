// ABOUTME: Alpine component for one row of the backoffice registration pages list
// ABOUTME: Owns the row's actions menu and the delete confirmation that guards it

/**
 * Build the state for one registration page row.
 *
 * Deleting a page is permanent - there is no archive and no undo - so the menu
 * item only arms a confirmation dialog. Opening it dismisses the menu (the two
 * surfaces would otherwise overlap) and moves focus to the safe "Keep it"
 * action; cancelling hands focus back to the kebab the user came from.
 *
 * @returns {Object} Alpine component state
 */
export function registrationPageRow() {
  return {
    open: false,
    confirmDeleteOpen: false,

    toggleMenu: function () {
      this.open = !this.open;
    },

    closeMenu: function () {
      this.open = false;
    },

    openConfirmDelete: function () {
      var self = this;
      self.open = false;
      self.confirmDeleteOpen = true;
      self.$nextTick(function () {
        if (self.$refs.keepPageBtn) self.$refs.keepPageBtn.focus();
      });
    },

    cancelConfirmDelete: function () {
      var self = this;
      self.confirmDeleteOpen = false;
      self.$nextTick(function () {
        if (self.$refs.menuToggle) self.$refs.menuToggle.focus();
      });
    },
  };
}
