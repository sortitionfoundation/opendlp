// ABOUTME: Alpine component that ticks the sign-up page's password rules while the password is typed
// ABOUTME: Decides the length and digits rules itself, and asks the server's validators about the other two

import { postJson } from "../lib/json-request.js";

// How long typing has to pause before the server is asked about its rules.
export var CHECK_DELAY_MS = 400;

// The fields the server compares the password with, by name: the sign-up
// form's names, which are also the keys the endpoint reads.
var PERSONAL_FIELDS = ["email", "first_name", "last_name"];

// NumericPasswordValidator refuses a password for which Python's
// str.isdigit() is true: digits alone, of any script, superscripts included.
// Every such character is in \p{N}. So are a few numbers that are not digits
// (½, Ⅻ): for those the rule stays unticked though the server would accept
// the password, which is the safe way to be wrong.
var NUMBERS_ONLY = /^\p{N}+$/u;

/**
 * Whether a rule the browser checks is met by the password.
 *
 * The validators count what Python's len() counts, code points, so an emoji
 * is one character here too, not the two UTF-16 units of String.length. A
 * length rule without its numbers, or a rule this does not know, is never met.
 *
 * @param {HTMLElement} rule - the rule's list item, with its data attributes
 * @param {string} password - the password typed so far, not empty
 * @returns {boolean} whether the password meets the rule
 */
function browserRuleMet(rule, password) {
  switch (rule.dataset.passwordRule) {
    case "length": {
      var count = Array.from(password).length;
      return (
        count >= parseInt(rule.dataset.minLength, 10) &&
        count <= parseInt(rule.dataset.maxLength, 10)
      );
    }
    case "not-numbers-only":
      return !NUMBERS_ONLY.test(password);
    default:
      return false;
  }
}

/**
 * Build the passwordRules component state.
 *
 * Put x-data="passwordRules" and @input="changed($event)" on an element inside
 * the form that holds the password field, the fields named in PERSONAL_FIELDS
 * and the list of rules, with data-check-url (the password check endpoint)
 * and data-csrf-token. Each rule's list item carries data-password-rule, its
 * key, and data-live-check: "browser" for a rule decided here on every
 * keystroke, "server" for one the endpoint decides. An element inside a rule
 * asks met($el) whether the password meets that rule.
 *
 * The endpoint is asked once typing pauses for CHECK_DELAY_MS, and again when
 * the email or a name changes. Until its answer about what the fields hold
 * now arrives - and when none does: a network error, the rate limit - the
 * server's rules are not met. An empty password meets nothing.
 *
 * @returns {Object} Alpine component state
 */
export function passwordRules() {
  return {
    password: "",
    // The endpoint's verdicts by rule key, for the fields as they are now;
    // null while an answer is awaited, and after one that failed.
    serverResults: null,
    checkTimer: null,
    // Counts the changes, so that an answer about older values is dropped.
    changeCount: 0,

    init: function () {
      // A browser may have put a value back in the field: the back button,
      // or autofill before the page's script ran.
      this.password = this.fieldValue("password");
      this.scheduleCheck();
    },

    changed: function (event) {
      var name = event.target.name;
      if (name !== "password" && PERSONAL_FIELDS.indexOf(name) === -1) {
        return;
      }
      this.password = this.fieldValue("password");
      this.scheduleCheck();
    },

    scheduleCheck: function () {
      this.serverResults = null;
      this.changeCount += 1;
      clearTimeout(this.checkTimer);
      if (
        this.password === "" ||
        this.$el.querySelector('[data-live-check="server"]') === null
      ) {
        return;
      }
      var self = this;
      var change = this.changeCount;
      this.checkTimer = setTimeout(function () {
        self.check(change);
      }, CHECK_DELAY_MS);
    },

    check: function (change) {
      var self = this;
      var payload = { password: this.password };
      PERSONAL_FIELDS.forEach(function (name) {
        payload[name] = self.fieldValue(name);
      });
      return postJson(
        this.$el.dataset.checkUrl,
        payload,
        this.$el.dataset.csrfToken,
      )
        .then(function (response) {
          if (
            change === self.changeCount &&
            response.ok &&
            response.data &&
            response.data.rules
          ) {
            self.serverResults = response.data.rules;
          }
        })
        .catch(function () {
          // The request never reached the server. Its rules stay unticked
          // until the next change asks again.
        });
    },

    met: function (el) {
      var rule = el.closest("[data-password-rule]");
      if (rule === null || this.password === "") {
        return false;
      }
      if (rule.dataset.liveCheck === "browser") {
        return browserRuleMet(rule, this.password);
      }
      if (rule.dataset.liveCheck === "server") {
        return (
          this.serverResults !== null &&
          this.serverResults[rule.dataset.passwordRule] === true
        );
      }
      return false;
    },

    fieldValue: function (name) {
      var form = this.$el.closest("form");
      var field = form ? form.elements.namedItem(name) : null;
      return field && typeof field.value === "string" ? field.value : "";
    },
  };
}
