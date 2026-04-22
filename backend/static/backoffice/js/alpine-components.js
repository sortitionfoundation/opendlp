/**
 * ABOUTME: Alpine.js data components for backoffice design system
 * ABOUTME: Registers reusable Alpine.data() components like autocomplete and focus restoration
 */


/* ========================================
   FOCUS PRESERVATION SYSTEM
   ========================================

   Preserves keyboard focus across page reloads by encoding the focused element's
   ID in the URL hash. This improves keyboard navigation UX when dropdowns or
   other controls trigger page reloads.

   Components:
   1. DOMContentLoaded handler - restores focus on page load
   2. $focusUrl magic - returns URL with focus hash appended
   3. focusPreserve directive - auto-preserves focus on link clicks

   Usage:
     Option A: Magic helper (for custom navigation)
       <select data-focus-id="my-select" @change="window.location.href = $focusUrl('/page?param=value')">

     Option B: Directive (for simple links)
       <a href="/page" data-focus-id="my-link" x-data x-focus-preserve>Link</a>

     Option C: With urlSelect component (built-in support)
       <div x-data="urlSelect({...})">
         <select data-focus-id="my-select" x-model="selected" @change="navigate($event)">
       </div>
   ======================================== */

/**
 * Focus restoration on page load
 *
 * Checks for #focus=<focusId> in the URL hash and restores focus to the
 * element with matching data-focus-id attribute.
 */
document.addEventListener("DOMContentLoaded", function () {
    var hash = window.location.hash;
    if (hash.startsWith("#focus=")) {
        var focusId = hash.substring(7);
        var el = document.querySelector('[data-focus-id="' + focusId + '"]');
        if (el) {
            el.focus();
            // Clean up the URL hash after restoring focus
            if (window.history.replaceState) {
                var cleanUrl = window.location.href.split("#")[0];
                window.history.replaceState(null, "", cleanUrl);
            }
        }
    }
});

document.addEventListener("alpine:init", function () {
    /**
     * Focus URL magic helper
     *
     * Returns the given URL with #focus=<focusId> appended if the current
     * element (or a specified element) has keyboard focus and a data-focus-id.
     *
     * Usage:
     *   <button data-focus-id="my-btn" @click="window.location.href = $focusUrl('/page')">
     *   <select data-focus-id="my-select" @change="window.location.href = $focusUrl('/page?q=' + selected)">
     *
     * @param {string} url - The base URL to navigate to
     * @param {HTMLElement} [element] - Optional element to check for focus (defaults to $el)
     * @returns {string} URL with focus hash appended if element has focus
     */
    Alpine.magic("focusUrl", function (el) {
        return function (url, element) {
            var targetEl = element || el;
            var focusId = targetEl.dataset ? targetEl.dataset.focusId : null;
            if (focusId && document.activeElement === targetEl) {
                return url + "#focus=" + focusId;
            }
            return url;
        };
    });

    /**
     * Focus preserve directive
     *
     * Automatically appends focus hash to href when clicking a link,
     * if the element has data-focus-id and keyboard focus.
     *
     * Usage:
     *   <a href="/page" data-focus-id="my-link" x-data x-focus-preserve>Link</a>
     */
    Alpine.directive("focus-preserve", function (el) {
        el.addEventListener("click", function (event) {
            var focusId = el.dataset.focusId;
            if (focusId && document.activeElement === el && el.href) {
                event.preventDefault();
                window.location.href = el.href + "#focus=" + focusId;
            }
        });
    });

    /**
     * Confirmation magic helper for form submissions
     *
     * Shows a confirmation dialog before submitting a form. Designed for CSP-safe
     * Alpine.js usage.
     *
     * Usage:
     *   <form x-data @submit.prevent="$confirm('Are you sure?', $el)">
     *
     * @param {string} message - The confirmation message to display
     * @param {HTMLFormElement} formElement - The form element to submit if confirmed
     */
    Alpine.magic("confirm", function () {
        return function (message, formElement) {
            if (confirm(message)) {
                formElement.submit();
            }
        };
    });

    /**
   * Autocomplete search component
   *
   * Usage:
   *   <div x-data="autocomplete({
   *     fetchUrl: '/api/search',
   *     minChars: 2,
   *     debounceMs: 300,
   *     paramName: 'q'
   *   })">
   *     <input type="text" x-model="query" @input="onInput()" @keydown="onKeydown($event)">
   *     <div x-show="isOpen">
   *       <template x-for="(item, index) in results" :key="item.id">
   *         <button @click="selectItem(item)" :class="{ 'highlighted': index === highlightedIndex }">
   *           <span x-text="item.label"></span>
   *         </button>
   *       </template>
   *     </div>
   *     <input type="hidden" :value="selectedId">
   *   </div>
   *
   * Options:
   *   - fetchUrl: URL to fetch results from (required)
   *   - minChars: Minimum characters before searching (default: 2)
   *   - debounceMs: Debounce delay in milliseconds (default: 300)
   *   - paramName: Query parameter name for search term (default: 'q')
   *
   * The fetch URL should return JSON array: [{ id, label, sublabel? }, ...]
   */
    Alpine.data("autocomplete", function (options) {
        var fetchUrl = options.fetchUrl || "";
        var minChars = options.minChars || 2;
        var debounceMs = options.debounceMs || 300;
        var paramName = options.paramName || "q";

        return {
            query: "",
            results: [],
            isOpen: false,
            isLoading: false,
            selectedId: "",
            selectedLabel: "",
            highlightedIndex: -1,
            debounceTimer: null,

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

                var url = fetchUrl + "?" + paramName + "=" + encodeURIComponent(self.query);

                fetch(url, {
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
                    if (self.highlightedIndex >= 0 && self.highlightedIndex < self.results.length) {
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
    });

    /**
   * URL-based select navigation component
   *
   * Navigates to a URL when selection changes. Supports focus restoration
   * for keyboard users via the data-focus-id attribute.
   *
   * Usage:
   *   <div x-data="urlSelect({ baseUrl: '/page', paramName: 'source', initialValue: 'option1' })">
   *     <select x-model="selected" @change="navigate($event)" data-focus-id="my-select">
   *       <option value="option1">Option 1</option>
   *       <option value="option2">Option 2</option>
   *     </select>
   *   </div>
   *
   * Options:
   *   - baseUrl: Base URL to navigate to (required)
   *   - paramName: Query parameter name (default: 'value')
   *   - initialValue: Initial selected value (optional)
   *
   * Focus restoration:
   *   If the element has data-focus-id and has keyboard focus when navigating,
   *   the URL will include #focus=<focusId> to restore focus after page load.
   */
    Alpine.data("urlSelect", function (options) {
        var baseUrl = options.baseUrl || "";
        var paramName = options.paramName || "value";
        var initialValue = options.initialValue || "";

        return {
            selected: initialValue,

            navigate: function (event) {
                // Build URL - skip query param if value is empty
                var url = baseUrl;
                if (this.selected) {
                    // Use & if URL already has query params, otherwise use ?
                    var separator = url.indexOf("?") !== -1 ? "&" : "?";
                    url += separator + paramName + "=" + encodeURIComponent(this.selected);
                }

                // Add focus hash if element has focus (keyboard navigation)
                // Use event.target to get the actual element (not the x-data root)
                var el = event ? event.target : this.$el;
                var focusId = el.dataset.focusId;
                if (focusId && document.activeElement === el) {
                    url += "#focus=" + focusId;
                }

                window.location.href = url;
            },
        };
    });

    /**
     * Modal component for dialogs and overlays
     *
     * Usage:
     *   <div x-data="modal({initialOpen: true, canClose: false, refreshOnClose: true})"
     *        @task-finished.window="setCanClose(true)">
     *     {% call modal(id="my-modal", title="Modal Title") %}
     *       Modal content here
     *     {% endcall %}
     *   </div>
     *
     * Options:
     *   - initialOpen: Whether modal starts open (default: false)
     *   - canClose: Whether modal can be closed (default: true)
     *   - refreshOnClose: Whether to refresh page when closing (default: false)
     *
     * Methods:
     *   - open(): Open the modal
     *   - close(): Close the modal (if canClose is true)
     *   - closeIfAllowed(): Same as close(), for escape key handler
     *   - setCanClose(value): Update whether modal can be closed
     */
    Alpine.data("modal", function (options) {
        var initialOpen = options.initialOpen || false;
        var initialCanClose = options.canClose !== undefined ? options.canClose : true;
        var refreshOnClose = options.refreshOnClose || false;

        return {
            isOpen: initialOpen,
            canClose: initialCanClose,

            open: function () {
                this.isOpen = true;
            },

            close: function () {
                if (this.canClose) {
                    this.isOpen = false;
                    if (refreshOnClose) {
                        window.location.reload();
                    }
                }
            },

            closeIfAllowed: function () {
                this.close();
            },

            setCanClose: function (value) {
                this.canClose = value;
            },
        };
    });

    /**
     * Tabs keyboard navigation component
     *
     * Implements WAI-ARIA compliant keyboard navigation for tabs:
     * - Arrow Left/Right: Move to previous/next tab
     * - Home: Move to first tab
     * - End: Move to last tab
     *
     * Uses automatic activation (focus moves and navigates simultaneously).
     *
     * Usage:
     *   <ul role="tablist" x-data="tabsKeyboard()" @keydown="handleKeydown($event)">
     *     <li role="presentation">
     *       <a role="tab" href="?tab=one" tabindex="0">Tab 1</a>
     *     </li>
     *   </ul>
     */
    Alpine.data("tabsKeyboard", function () {
        return {
            handleKeydown: function (event) {
                var key = event.key;

                // Only handle arrow keys, Home, and End
                if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(key) === -1) {
                    return;
                }

                // Get all focusable tabs (exclude disabled)
                // Use event.currentTarget (the element with @keydown) to find tabs
                var tablist = event.currentTarget;
                var tabs = Array.prototype.slice.call(
                    tablist.querySelectorAll('[role="tab"]:not([aria-disabled="true"])')
                );

                if (tabs.length === 0) {
                    return;
                }

                // Find current tab index
                var currentIndex = tabs.indexOf(document.activeElement);
                if (currentIndex === -1) {
                    return;
                }

                var newIndex;

                if (key === "ArrowLeft") {
                    // Move to previous tab, wrap to end
                    newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
                } else if (key === "ArrowRight") {
                    // Move to next tab, wrap to start
                    newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
                } else if (key === "Home") {
                    newIndex = 0;
                } else if (key === "End") {
                    newIndex = tabs.length - 1;
                }

                if (newIndex !== undefined && newIndex !== currentIndex) {
                    event.preventDefault();
                    var targetTab = tabs[newIndex];
                    targetTab.focus();
                    // Automatic activation - navigate when focus moves
                    targetTab.click();
                }
            },
        };
    });

    /**
     * Progress modal demo for design system showcase
     *
     * Interactive demo component that simulates different task states
     * (running, completed, failed) without actual server polling.
     */
    Alpine.data("progressModalDemo", function () {
        return {
            modalOpen: false,
            taskState: "running",
            messages: [
                "Loading configuration...",
                "Processing data...",
                "Running selection algorithm...",
            ],

            showRunning: function () {
                this.taskState = "running";
                this.modalOpen = true;
            },

            showCompleted: function () {
                this.taskState = "completed";
                this.modalOpen = true;
            },

            showFailed: function () {
                this.taskState = "failed";
                this.modalOpen = true;
            },

            closeModal: function () {
                this.modalOpen = false;
            },

            cancelTask: function () {
                this.taskState = "cancelled";
                this.modalOpen = false;
            },

            canClose: function () {
                return this.taskState !== "running";
            },

            isRunning: function () {
                return this.taskState === "running";
            },
        };
    });
});
