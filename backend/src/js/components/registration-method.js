// ABOUTME: Alpine component for choosing a signup method on the registration form
// ABOUTME: Tracks the selected method so email-only fields and the matching submit button show or hide

/**
 * Build the registrationMethod component state.
 *
 * The registration form offers three ways to sign up - email, Google and
 * Microsoft - from one form. This tracks which one the user picked so the
 * template can reveal the email-only fields and the matching submit button,
 * and hide the rest. The method is also carried in the submitted `action`
 * field, so the server already knows which path to take without this component.
 *
 * @param {string} initialMethod - the method selected when the page rendered
 * @returns {Object} Alpine component state
 */
export function registrationMethod(initialMethod) {
  var methods = ["email", "google", "microsoft"];
  return {
    method: methods.indexOf(initialMethod) !== -1 ? initialMethod : "email",

    selectEmail: function () {
      this.method = "email";
    },

    selectGoogle: function () {
      this.method = "google";
    },

    selectMicrosoft: function () {
      this.method = "microsoft";
    },
  };
}
