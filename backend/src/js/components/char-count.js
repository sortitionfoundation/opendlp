// ABOUTME: Alpine component for a live character counter on a textarea
// ABOUTME: Tracks the length of the wrapped textarea so templates can show count/max

/**
 * Build the charCount component state.
 *
 * Wrap a textarea and a `<span x-text="count">` in an element with
 * x-data="charCount" and @input="update()". init() picks up any
 * server-rendered value, e.g. after a validation error re-render.
 *
 * @returns {Object} Alpine component state
 */
export function charCount() {
  return {
    count: 0,

    init: function () {
      this.update();
    },

    update: function () {
      var textarea = this.$el.querySelector("textarea");
      this.count = textarea ? textarea.value.length : 0;
    },
  };
}
