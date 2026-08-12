// ABOUTME: Shared machinery for the service docs console - execute, toast, clipboard, formatting
// ABOUTME: Every per-tab slice calls executeService(); this is the only slice that talks to the server

const TOAST_DURATION_MS = 3000;

/**
 * Build the core slice of the service docs controller.
 *
 * `loading` and `responses` are keyed by the short response key the server sends over in
 * its data block, so a service added to dev.py's handler table arrives here with its
 * panel already wired - there is no second list to keep in step. They are nested objects
 * rather than flat properties because nothing binds them with `x-model`; the CSP Alpine
 * build reads `loading.add_field` in an `x-show` quite happily.
 *
 * @param {Object} options - configuration
 * @param {string} options.executeUrl - the dev route that runs a service
 * @param {string} options.csrfToken - the CSRF token for the session
 * @param {Object} options.responseKeys - service name -> response key, from SERVICE_RESPONSE_KEYS
 * @returns {Object} a slice of Alpine component state
 */
export function serviceDocsCore(options) {
  var responseKeys = options.responseKeys || {};

  var loading = {};
  var responses = {};
  Object.keys(responseKeys).forEach(function (serviceName) {
    loading[responseKeys[serviceName]] = false;
    responses[responseKeys[serviceName]] = null;
  });

  return {
    toast: { show: false, message: "", type: "info" },
    loading: loading,
    responses: responses,

    showToast: function (message, type) {
      var self = this;
      self.toast = { show: true, message: message, type: type || "info" };
      setTimeout(function () {
        self.toast.show = false;
      }, TOAST_DURATION_MS);
    },

    /**
     * Run a service on the server and show its result in that service's panel.
     *
     * Unlike the production JSON routes, this one reports failure in the body with a
     * status field rather than an HTTP status, so the whole parsed body is the answer
     * and there is no `response.ok` to consult.
     */
    executeService: function (serviceName, params) {
      var self = this;
      var key = responseKeys[serviceName];
      if (!key) {
        // Only reachable if a slice names a service dev.py does not have, which the
        // component test for the data block is there to catch first.
        self.showToast("Unknown service: " + serviceName, "error");
        return Promise.resolve();
      }

      self.loading[key] = true;
      self.responses[key] = null;

      return fetch(options.executeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": options.csrfToken,
        },
        body: JSON.stringify({ service: serviceName, params: params }),
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          self.responses[key] = data;
          if (data.status === "success") {
            self.showToast("Service executed successfully", "success");
          }
        })
        .catch(function (error) {
          self.responses[key] = {
            status: "error",
            error: error.message,
            error_type: "NetworkError",
          };
        })
        .finally(function () {
          self.loading[key] = false;
        });
    },

    copyToClipboard: function (text) {
      var self = this;
      return navigator.clipboard.writeText(text).then(
        function () {
          self.showToast("Copied to clipboard!", "success");
        },
        function () {
          self.showToast("Failed to copy", "error");
        },
      );
    },

    /** Stringify a response for x-text, which cannot call JSON.stringify itself. */
    formatResponse: function (key) {
      var data = this.responses[key];
      if (!data) return "";
      try {
        return JSON.stringify(data, null, 2);
      } catch (e) {
        return "Error formatting: " + e.message;
      }
    },

    /** Copy a response panel's JSON. Saves every tab writing the stringify out again. */
    copyResponse: function (key) {
      return this.copyToClipboard(JSON.stringify(this.responses[key], null, 2));
    },
  };
}
