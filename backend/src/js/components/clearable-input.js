// ABOUTME: Alpine component for a text input with a clear (×) button that shows once it holds text
// ABOUTME: Clearing empties the input and either refocuses it or resubmits its form

/**
 * Build the clearableInput component state.
 *
 * Wrap an input and a clear button in an element with
 * x-data="clearableInput" and @input="update()"; show the button with
 * x-show="hasText" and call clear() from its @click. init() picks up any
 * server-rendered value, such as a search term the page was filtered on.
 *
 * With data-clear-submits="true" on the wrapper, clearing resubmits the
 * input's form - for a filter form, where an empty field means "no filter".
 * Otherwise clearing moves focus back to the now-empty input.
 *
 * @returns {Object} Alpine component state
 */
export function clearableInput() {
  return {
    hasText: false,

    init: function () {
      this.update();
    },

    input: function () {
      return this.$root.querySelector("input");
    },

    update: function () {
      var field = this.input();
      this.hasText = Boolean(field && field.value.length > 0);
    },

    clear: function () {
      var field = this.input();
      if (!field) {
        return;
      }
      field.value = "";
      this.hasText = false;
      if (this.$root.dataset.clearSubmits === "true" && field.form) {
        field.form.requestSubmit();
        return;
      }
      field.focus();
    },
  };
}
