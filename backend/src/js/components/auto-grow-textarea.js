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
    grow: function () {
      var el = this.$el;
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
    },
  };
}
