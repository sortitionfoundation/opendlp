/**
 * ABOUTME: Alpine.js data components for backoffice design system
 * ABOUTME: Registers reusable Alpine.data() components like autocomplete and focus restoration
 */


/**
 * Focus restoration for keyboard navigation
 *
 * When a component navigates to a new URL with keyboard focus, it can add
 * #focus=<focusId> to the URL. On page load, this handler finds the element
 * with data-focus-id="<focusId>" and restores focus to it.
 *
 * Usage:
 *   1. Add data-focus-id="myElement" to any focusable element
 *   2. When navigating, append #focus=myElement to the URL (if element had focus)
 *   3. On page load, focus is automatically restored
 */
document.addEventListener("DOMContentLoaded", function () {
    var hash = window.location.hash;
    if (hash.startsWith("#focus=")) {
        var focusId = hash.substring(7);
        var el = document.querySelector('[data-focus-id="' + focusId + '"]');
        if (el) {
            el.focus();
        }
    }
});

document.addEventListener("alpine:init", function () {
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
    /**
   * Task progress polling component
   *
   * Polls a JSON endpoint for task progress updates and stops when task reaches
   * a terminal state (completed, failed, cancelled).
   *
   * Usage:
   *   <div x-data="taskPoller({ progressUrl: '/api/task/123/progress', pollIntervalMs: 2000 })">
   *     <div x-show="status === 'running'">Running...</div>
   *     <ul>
   *       <template x-for="msg in logMessages" :key="msg">
   *         <li x-text="msg"></li>
   *       </template>
   *     </ul>
   *     <div x-show="status === 'completed'">Done!</div>
   *     <div x-show="status === 'failed'" x-text="errorMessage"></div>
   *   </div>
   *
   * Options:
   *   - progressUrl: URL to poll for progress (required)
   *   - pollIntervalMs: Polling interval in milliseconds (default: 2000)
   *   - initialStatus: Initial status value (default: 'pending')
   *
   * The progress URL should return JSON:
   *   { status, log_messages, error_message, completed_at, has_report, redirect_url }
   *   - redirect_url: Optional URL to redirect to (e.g., after load task completes)
   */
    Alpine.data("taskPoller", function (options) {
        var progressUrl = options.progressUrl || "";
        var pollIntervalMs = options.pollIntervalMs || 2000;
        var initialStatus = options.initialStatus || "pending";

        return {
            status: initialStatus,
            logMessages: [],
            errorMessage: "",
            completedAt: null,
            hasReport: false,
            redirectUrl: "",
            pollTimer: null,
            isPolling: false,

            init: function () {
                var self = this;
                // Start polling if we have a progress URL and status is not terminal
                if (progressUrl && !self.isTerminalStatus(self.status)) {
                    self.startPolling();
                }
            },

            destroy: function () {
                this.stopPolling();
            },

            isTerminalStatus: function (status) {
                return ["completed", "failed", "cancelled"].indexOf(status) !== -1;
            },

            startPolling: function () {
                var self = this;
                if (self.isPolling) {
                    return;
                }
                self.isPolling = true;

                // Immediate first fetch
                self.fetchProgress();

                // Set up interval
                self.pollTimer = setInterval(function () {
                    self.fetchProgress();
                }, pollIntervalMs);
            },

            stopPolling: function () {
                var self = this;
                if (self.pollTimer) {
                    clearInterval(self.pollTimer);
                    self.pollTimer = null;
                }
                self.isPolling = false;
            },

            fetchProgress: function () {
                var self = this;

                fetch(progressUrl, {
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
                    self.status = data.status || "unknown";
                    self.logMessages = data.log_messages || [];
                    self.errorMessage = data.error_message || "";
                    self.completedAt = data.completed_at;
                    self.hasReport = data.has_report || false;
                    self.redirectUrl = data.redirect_url || "";

                    // Handle redirect if provided
                    if (self.redirectUrl) {
                        self.stopPolling();
                        window.location.href = self.redirectUrl;
                        return;
                    }

                    // Stop polling on terminal states
                    if (self.isTerminalStatus(self.status)) {
                        self.stopPolling();
                    }
                })
                    .catch(function (error) {
                    console.error("Task progress fetch error:", error);
                    // Don't stop polling on transient errors
                });
            },
        };
    });


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
                    url += "?" + paramName + "=" + encodeURIComponent(this.selected);
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
});
