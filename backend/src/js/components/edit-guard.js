// ABOUTME: Shared unsaved-changes guard - the dirty flag, the discard dialog and the leave paths
// ABOUTME: Merged as a flat slice into a page component; see registration-edit-guard.js and targets-page.js

/**
 * Build the unsaved-changes slice of a page component.
 *
 * A page that can hold edits the server has not seen yet owns two problems:
 * noticing that it is dirty, and catching every way out of the page before the
 * edits go with it. This slice answers both, and renders its dialog from
 * `components/leave_guard_modal.html`.
 *
 * There are two kinds of way out. `beforeunload` is the backstop for the ones
 * the page cannot dress up - close the tab, reload, the back button - and gets
 * the browser's own wording. In-app links are caught before they navigate and
 * diverted to our dialog, which can say what is at stake. A page whose
 * navigation is already funnelled through one guarded control does not need
 * that second part, so it is opt-in.
 *
 * @param {Object} [options] - configuration
 * @param {boolean} [options.guardLinks=false] - intercept in-app link clicks
 *   anywhere on the page, rather than only those wired to guardLeave()
 * @returns {Object} a flat slice of Alpine component state
 */
export function editGuard(options) {
  var guardLinks = Boolean(options && options.guardLinks);

  return {
    editDirty: false,
    leaveModalOpen: false,
    leaveUrl: "",
    leaveGuardSuppressed: false,

    /**
     * Start guarding. Called from the host component's own init().
     *
     * Kept separate from init() because Object.assign merges these slices flat:
     * a slice that claimed init() would take it from every page that uses it.
     */
    initEditGuard: function () {
      var self = this;

      window.addEventListener("beforeunload", function (event) {
        if (!self.wouldLoseEdits()) return;
        event.preventDefault();
        event.returnValue = "";
      });

      if (!guardLinks) return;
      // Capture, so the click is stopped before anything else acts on it.
      document.addEventListener(
        "click",
        function (event) {
          var link = self.leaveLinkFrom(event);
          if (!link) return;
          event.preventDefault();
          self.openLeaveModal(link.href);
        },
        true,
      );
    },

    /** Whether leaving right now would take unsaved edits with it. */
    wouldLoseEdits: function () {
      return this.editDirty && !this.leaveGuardSuppressed;
    },

    /**
     * The link this click would navigate by, if it is one worth guarding.
     *
     * Skips everything that does not replace the page under the edits: a click
     * with a modifier or a non-primary button, a link that opens elsewhere or
     * downloads, a jump within this page, and anything opting out.
     *
     * @param {MouseEvent} event - the captured click
     * @returns {HTMLAnchorElement|null} the link, or null to let the click be
     */
    leaveLinkFrom: function (event) {
      if (!this.wouldLoseEdits()) return null;
      if (event.defaultPrevented || event.button !== 0) return null;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return null;
      }

      var target = event.target;
      var link = target && target.closest ? target.closest("a[href]") : null;
      if (!link) return null;
      if (link.hasAttribute("download")) return null;
      if (link.hasAttribute("data-no-leave-guard")) return null;
      if (link.target && link.target !== "_self") return null;

      var href = link.getAttribute("href");
      if (!href || href.charAt(0) === "#") return null;
      return link;
    },

    markEditDirty: function () {
      this.editDirty = true;
    },

    /** Called on the form's submit, so saving never trips the guard. */
    allowLeave: function () {
      this.leaveGuardSuppressed = true;
    },

    /**
     * Wired to an individual leave-link. Clean state falls through to normal
     * navigation.
     *
     * @param {MouseEvent} event - the click on the link
     */
    guardLeave: function (event) {
      if (!this.editDirty) return;
      event.preventDefault();
      this.openLeaveModal(event.currentTarget.href);
    },

    openLeaveModal: function (url) {
      var self = this;
      self.leaveUrl = url;
      self.leaveModalOpen = true;
      self.$nextTick(function () {
        if (self.$refs.keepEditingBtn) self.$refs.keepEditingBtn.focus();
      });
    },

    closeLeaveModal: function () {
      this.leaveModalOpen = false;
      this.leaveUrl = "";
    },

    discardAndLeave: function () {
      if (!this.leaveUrl) return;
      this.leaveGuardSuppressed = true;
      window.location.assign(this.leaveUrl);
    },
  };
}
