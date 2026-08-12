/**
 * ABOUTME: Alpine autocomplete component implementing the WAI-ARIA combobox pattern
 * ABOUTME: Debounced fetch, arrow-key navigation, and a live region announcing result counts
 *
 * Usage:
 *   <div x-data="autocomplete({
 *     fetchUrl: '/api/search',
 *     minChars: 2,
 *     debounceMs: 300,
 *     paramName: 'q',
 *     inputId: 'user_search'
 *   })">
 *     <input type="text" x-model="query" @input="onInput()" @keydown="onKeydown($event)"
 *            role="combobox" aria-autocomplete="list" aria-haspopup="listbox"
 *            :aria-expanded="isOpen" :aria-activedescendant="activeDescendantId">
 *     <ul role="listbox" x-show="isOpen">
 *       <template x-for="(item, index) in results" :key="item.id">
 *         <li role="option" :id="'user_search_option_' + index"
 *             :aria-selected="index === highlightedIndex"
 *             @click="selectItem(item)">
 *           <span x-text="item.label"></span>
 *         </li>
 *       </template>
 *     </ul>
 *     <input type="hidden" :value="selectedId">
 *     <div aria-live="polite" class="sr-only" x-text="statusMessage"></div>
 *   </div>
 *
 * The fetch URL should return JSON array: [{ id, label, sublabel? }, ...]
 */

/**
 * Build the autocomplete component state.
 *
 * @param {Object} options - configuration
 * @param {string} options.fetchUrl - URL to fetch results from (required)
 * @param {number} [options.minChars=2] - minimum characters before searching
 * @param {number} [options.debounceMs=300] - debounce delay in milliseconds
 * @param {string} [options.paramName="q"] - query parameter name for the search term
 * @param {string} [options.inputId="autocomplete"] - ID prefix for generated option IDs
 * @returns {Object} Alpine component state
 */
export function autocomplete(options) {
  var fetchUrl = options.fetchUrl || "";
  var minChars = options.minChars || 2;
  var debounceMs = options.debounceMs || 300;
  var paramName = options.paramName || "q";
  var inputId = options.inputId || "autocomplete";

  return {
    query: "",
    results: [],
    isOpen: false,
    isLoading: false,
    selectedId: "",
    selectedLabel: "",
    highlightedIndex: -1,
    debounceTimer: null,
    statusMessage: "",

    // Computed property for aria-activedescendant
    get activeDescendantId() {
      if (
        this.highlightedIndex >= 0 &&
        this.highlightedIndex < this.results.length
      ) {
        return inputId + "_option_" + this.highlightedIndex;
      }
      return "";
    },

    onInput: function () {
      var self = this;

      // Clear previous timer
      if (self.debounceTimer) {
        clearTimeout(self.debounceTimer);
      }

      // Reset selection when typing
      self.selectedId = "";
      self.selectedLabel = "";

      // Check minimum characters
      if (self.query.length < minChars) {
        self.results = [];
        self.isOpen = false;
        return;
      }

      // Debounce the search
      self.debounceTimer = setTimeout(function () {
        self.fetchResults();
      }, debounceMs);
    },

    fetchResults: function () {
      var self = this;
      self.isLoading = true;

      var url =
        fetchUrl + "?" + paramName + "=" + encodeURIComponent(self.query);

      return fetch(url, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Network response was not ok");
          }
          return response.json();
        })
        .then(function (data) {
          self.results = data;
          self.isOpen = data.length > 0;
          self.highlightedIndex = -1;
          self.isLoading = false;
          // Announce results count to screen readers
          if (data.length === 0) {
            self.statusMessage = "No results found";
          } else if (data.length === 1) {
            self.statusMessage = "1 result available";
          } else {
            self.statusMessage = data.length + " results available";
          }
        })
        .catch(function (error) {
          console.error("Autocomplete fetch error:", error);
          self.results = [];
          self.isOpen = false;
          self.isLoading = false;
        });
    },

    selectItem: function (item) {
      this.selectedId = item.id;
      this.selectedLabel = item.label;
      this.query = item.label + (item.sublabel ? " - " + item.sublabel : "");
      this.isOpen = false;
      this.results = [];
      this.highlightedIndex = -1;
    },

    onKeydown: function (event) {
      var self = this;

      if (!self.isOpen) {
        return;
      }

      // Arrow down
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (self.highlightedIndex < self.results.length - 1) {
          self.highlightedIndex++;
        }
      }

      // Arrow up
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (self.highlightedIndex > 0) {
          self.highlightedIndex--;
        }
      }

      // Enter
      if (event.key === "Enter") {
        event.preventDefault();
        if (
          self.highlightedIndex >= 0 &&
          self.highlightedIndex < self.results.length
        ) {
          self.selectItem(self.results[self.highlightedIndex]);
        }
      }

      // Escape
      if (event.key === "Escape") {
        self.isOpen = false;
        self.highlightedIndex = -1;
      }
    },

    close: function () {
      this.isOpen = false;
      this.highlightedIndex = -1;
    },
  };
}
