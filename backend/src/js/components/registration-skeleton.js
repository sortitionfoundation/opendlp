// ABOUTME: Form skeleton preview slice of the registration page controller
// ABOUTME: Fetches the generated markup and holds the plain / GOV.UK styled toggle

/**
 * Build the skeleton-preview slice of the registration page controller.
 *
 * @param {Object} options - configuration
 * @param {string} options.csrfToken - the CSRF token for the session
 * @param {string} options.skeletonUrl - the route that generates the form skeleton
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationSkeleton(options) {
  var messages = options.messages;

  return {
    skeletonLoading: false,
    skeletonModalOpen: false,
    skeletonHtmlPlain: "",
    skeletonHtmlStyled: "",
    skeletonView: "plain",

    // Uses fetch directly rather than the lib/json-request helpers: this route
    // reports its problems in the body rather than the status, so the parsed
    // body is the whole answer and an unparsable one has to be an error.
    fetchSkeleton: function () {
      var self = this;
      self.skeletonLoading = true;

      return fetch(options.skeletonUrl, {
        method: "GET",
        headers: { "X-CSRFToken": options.csrfToken },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          self.skeletonLoading = false;
          if (data.error) {
            self.showToast(data.error, "error");
            return;
          }
          self.skeletonHtmlPlain = data.html;
          self.skeletonHtmlStyled = data.html_govuk;
          self.skeletonView = "plain";
          self.skeletonModalOpen = true;
        })
        .catch(function () {
          self.skeletonLoading = false;
          self.showToast(messages.skeletonFetchFailed, "error");
        });
    },

    closeSkeletonModal: function () {
      this.skeletonModalOpen = false;
    },

    showPlainSkeleton: function () {
      this.skeletonView = "plain";
    },

    showStyledSkeleton: function () {
      this.skeletonView = "styled";
    },

    copySkeletonToClipboard: function () {
      var self = this;
      var html =
        self.skeletonView === "plain"
          ? self.skeletonHtmlPlain
          : self.skeletonHtmlStyled;

      return navigator.clipboard.writeText(html).then(
        function () {
          self.showToast(messages.copied, "success");
        },
        function () {
          self.showToast(messages.copyFailed, "error");
        },
      );
    },
  };
}
