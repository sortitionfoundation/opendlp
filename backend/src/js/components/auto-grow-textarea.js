// ABOUTME: Alpine component for a one-line textarea that grows to fit its text while being edited
// ABOUTME: Shrinks back to one line on blur, leaving the full text in its hover title

/**
 * Build the state for a textarea that is one line tall until it has focus.
 *
 * Put it on the textarea itself, with `rows="1"`:
 * x-data="autoGrowTextarea" @focus="grow()" @input="grow()" @blur="shrink()".
 *
 * While focused the box is as tall as its text, so a note of several lines
 * can be read as it is written. Out of focus it goes back to the one line a
 * table row has room for, and the title carries the whole note for a hover.
 *
 * @returns {Object} Alpine component state
 */
export function autoGrowTextarea() {
  return {
    // The height of one line plus the padding around it, measured on init.
    oneLine: 0,

    init: function () {
      var el = this.$el;
      // A transition would animate the padding as it comes and goes, and grow()
      // would measure the box halfway through.
      el.style.transition = "none";
      var style = window.getComputedStyle(el);
      this.oneLine =
        parseFloat(style.paddingTop) +
        parseFloat(style.paddingBottom) +
        parseFloat(style.lineHeight);
      this.collapse();
    },

    grow: function () {
      var el = this.$el;
      this.expand();
      // Cleared first, or the box could never get shorter than it already is:
      // scrollHeight never reports less than the current height.
      el.style.height = "auto";
      // The height includes the border, which scrollHeight leaves out.
      var border = el.offsetHeight - el.clientHeight;
      el.style.height = el.scrollHeight + border + "px";
    },

    shrink: function () {
      this.$el.style.height = "";
      this.$el.title = this.$el.value;
      this.collapse();
    },

    /**
     * Turn the padding into line height, so the box is as tall as before but a
     * second line starts below its bottom edge. Left in the padding, the top of
     * that line shows, cut in half.
     */
    collapse: function () {
      if (!(this.oneLine > 0)) return;
      var el = this.$el;
      el.style.paddingTop = "0";
      el.style.paddingBottom = "0";
      el.style.lineHeight = this.oneLine + "px";
    },

    expand: function () {
      var el = this.$el;
      el.style.paddingTop = "";
      el.style.paddingBottom = "";
      el.style.lineHeight = "";
    },
  };
}
