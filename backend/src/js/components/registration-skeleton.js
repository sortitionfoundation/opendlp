// ABOUTME: Skeleton preview slice of the registration page controller
// ABOUTME: Fetches the generated intro and form markup and holds the plain / GOV.UK styled toggle

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
    // The pair on show: the intro skeleton or the form skeleton, depending on
    // which step's button opened the modal.
    skeletonHtmlPlain: "",
    skeletonHtmlStyled: "",
    skeletonView: "plain",

    // Two entry points rather than one taking the part as an argument: the
    // CSP Alpine build cannot pass a string literal from an @click handler.
    fetchIntroSkeleton: function () {
      return this._fetchSkeleton("intro_html", "intro_html_govuk");
    },

    fetchFormSkeleton: function () {
      return this._fetchSkeleton("html", "html_govuk");
    },

    // Uses fetch directly rather than the lib/json-request helpers: this route
    // reports its problems in the body rather than the status, so the parsed
    // body is the whole answer and an unparsable one has to be an error.
    _fetchSkeleton: function (plainKey, styledKey) {
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
          self.skeletonHtmlPlain = data[plainKey];
          self.skeletonHtmlStyled = data[styledKey];
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
