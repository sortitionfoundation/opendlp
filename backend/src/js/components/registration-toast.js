// ABOUTME: Toast state for the registration page controller, plus the copy-with-feedback button
// ABOUTME: One of the slices composed into registrationPageController

const TOAST_DURATION_MS = 3000;

/**
 * Build the toast slice of the registration page controller.
 *
 * @param {Object} messages - translated strings, rendered server-side
 * @param {string} messages.copied - confirmation for a copy with no message of its own
 * @param {string} messages.copyFailed - shown when the clipboard write is refused
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationToast(messages) {
  return {
    toastVisible: false,
    toastMessage: "",
    toastType: "success",

    showToast: function (message, type) {
      var self = this;
      self.toastMessage = message;
      self.toastType = type;
      self.toastVisible = true;
      setTimeout(function () {
        self.toastVisible = false;
      }, TOAST_DURATION_MS);
    },

    // Reads the text and confirmation from data-copy-text / data-copy-msg on the
    // triggering element. The CSP Alpine build's expression parser does not support
    // literal arguments in a method call, so `copyToClipboard('some text')` in an
    // @click would not run - the data attributes are how the value gets across.
    copyToClipboard: function ($el) {
      var self = this;
      var text = $el.dataset.copyText;
      var message = $el.dataset.copyMsg;
      if (!text) return Promise.resolve();

      return navigator.clipboard.writeText(text).then(
        function () {
          self.showToast(message || messages.copied, "success");
        },
        function () {
          self.showToast(messages.copyFailed, "error");
        },
      );
    },
  };
}
