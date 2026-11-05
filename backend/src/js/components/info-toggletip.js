// ABOUTME: Alpine component for the info_icon macro - a button that shows a sentence of explanation
// ABOUTME: A toggletip: click or Enter shows the text and announces it, Escape or a click elsewhere hides it

// Gap between the icon and the bubble, and between the bubble and the viewport edge.
var GAP = 6;
var MARGIN = 8;
// Long enough after emptying the live region that a screen reader notices the
// text arriving, so showing it a second time announces it a second time.
var ANNOUNCE_DELAY_MS = 100;

/**
 * Build the state for a toggletip, after Heydon Pickering's in Inclusive
 * Components (https://inclusive-components.design/tooltips-toggletips/).
 *
 * A tooltip appears on hover or focus, and touch has neither, so the icon is a
 * real button that toggles the text instead. The template gives the button
 * x-ref="button", the bubble holding the text x-ref="bubble" (a popover, so it
 * sits in the top layer and no overflow:hidden card clips it), and an empty
 * role="status" region that x-text binds to `announced`. The bubble is
 * aria-hidden: a screen reader hears the text from the live region, once.
 *
 * The server renders the text as a `title` too, for a browser without
 * JavaScript; binding :title="nativeTitle" removes it, so nobody sees the text
 * twice.
 *
 * Bind on the wrapper:
 *   @keydown.escape="closeOnEscape" - stops the key there when the bubble is
 *       open, so dialog-escape.js does not also close the dialog around it.
 *   @click.outside="close"
 *   @focusout="closeOnFocusOut"     - tabbing away hides the bubble.
 * Bind @click="toggle" on the button.
 *
 * @returns {Object} Alpine component state
 */
export function infoToggletip() {
  return {
    open: false,
    announced: "",
    nativeTitle: null,
    announceTimer: null,
    reposition: null,

    init: function () {
      var self = this;
      this.reposition = function () {
        self.place();
      };
    },

    destroy: function () {
      this.stopFollowing();
      clearTimeout(this.announceTimer);
    },

    toggle: function () {
      if (this.open) {
        this.close();
        return;
      }
      this.show();
    },

    show: function () {
      var self = this;
      var bubble = this.$refs.bubble;
      this.open = true;
      if (bubble.showPopover) {
        bubble.showPopover();
      }
      this.place();
      window.addEventListener("scroll", this.reposition, true);
      window.addEventListener("resize", this.reposition);

      this.announced = "";
      clearTimeout(this.announceTimer);
      this.announceTimer = setTimeout(function () {
        self.announced = bubble.textContent.trim();
      }, ANNOUNCE_DELAY_MS);
    },

    close: function () {
      if (!this.open) return;
      var bubble = this.$refs.bubble;
      this.open = false;
      this.announced = "";
      clearTimeout(this.announceTimer);
      if (bubble.hidePopover) {
        bubble.hidePopover();
      }
      this.stopFollowing();
    },

    closeOnEscape: function (event) {
      if (!this.open) return;
      event.stopPropagation();
      this.close();
      this.$refs.button.focus();
    },

    closeOnFocusOut: function (event) {
      if (!this.open) return;
      // No relatedTarget means focus went nowhere - a click on something that
      // does not take focus. That is click.outside's business.
      if (!event.relatedTarget) return;
      if (this.$el.contains(event.relatedTarget)) return;
      this.close();
    },

    stopFollowing: function () {
      window.removeEventListener("scroll", this.reposition, true);
      window.removeEventListener("resize", this.reposition);
    },

    /**
     * Put the bubble under the icon, or over it when there is no room below,
     * centred on it but kept inside the viewport.
     */
    place: function () {
      var bubble = this.$refs.bubble;
      var anchor = this.$refs.button.getBoundingClientRect();
      var width = bubble.offsetWidth;
      var height = bubble.offsetHeight;
      var viewportWidth = document.documentElement.clientWidth;
      var viewportHeight = document.documentElement.clientHeight;

      var left = anchor.left + anchor.width / 2 - width / 2;
      left = Math.max(MARGIN, Math.min(left, viewportWidth - width - MARGIN));

      var top = anchor.bottom + GAP;
      if (
        top + height > viewportHeight - MARGIN &&
        anchor.top - GAP - height >= MARGIN
      ) {
        top = anchor.top - GAP - height;
      }

      bubble.style.left = left + "px";
      bubble.style.top = top + "px";
    },
  };
}
