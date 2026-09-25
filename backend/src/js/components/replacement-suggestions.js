// ABOUTME: Alpine component for the replacement dialog's suggested target relaxations
// ABOUTME: Accepting a suggestion writes it into its input; a suggestion hides once the input matches it

/**
 * The dialog marks every suggestion element with data-suggestion-for (the id
 * of the input it concerns) and data-suggestion-value. Accept buttons carry
 * the same two attributes and call accept($el); the CSP Alpine build cannot
 * pass literal arguments, so the data attributes are how the values arrive.
 *
 * Usage:
 *   <div x-data="replacementSuggestions" @input="refresh()">
 *     <span data-suggestion-for="max-123" data-suggestion-value="3">...</span>
 *     <button @click="accept($el)" data-suggestion-for="max-123" data-suggestion-value="3">Accept</button>
 *     <button @click="acceptAll()">Accept all</button>
 *     <input id="max-123" ...>
 *   </div>
 */
export function replacementSuggestions() {
  return {
    init: function () {
      this.refresh();
    },

    accept: function ($el) {
      this.apply($el.dataset.suggestionFor, $el.dataset.suggestionValue);
    },

    acceptAll: function () {
      var self = this;
      this.$root
        .querySelectorAll("[data-suggestion-for][data-suggestion-value]")
        .forEach(function (element) {
          self.apply(
            element.dataset.suggestionFor,
            element.dataset.suggestionValue,
          );
        });
    },

    apply: function (inputId, value) {
      var input = this.$root.querySelector("#" + CSS.escape(inputId));
      if (!input) return;
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      this.refresh();
    },

    /**
     * Hide every suggestion whose input already holds the suggested value.
     * Once nothing is left to accept, the list gives way to the accepted note.
     */
    refresh: function () {
      var root = this.$root;
      var remaining = 0;
      root
        .querySelectorAll("[data-suggestion-for]")
        .forEach(function (element) {
          var input = root.querySelector(
            "#" + CSS.escape(element.dataset.suggestionFor),
          );
          var done = !!input && input.value === element.dataset.suggestionValue;
          element.hidden = done;
          if (!done) remaining += 1;
        });
      root.querySelectorAll("[data-suggestions-list]").forEach(function (list) {
        list.hidden = remaining === 0;
      });
      root
        .querySelectorAll("[data-suggestions-accepted]")
        .forEach(function (note) {
          note.hidden = remaining > 0;
        });
    },
  };
}
