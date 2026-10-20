// ABOUTME: Alpine component for a suggestion row that writes its change into inputs on the page
// ABOUTME: Accept fills the named inputs and the comment in one click; Undo puts them back

/**
 * Build the state for one suggestion row in "apply" mode.
 *
 * The row is given, as data attributes, the inputs its suggestion changes and
 * the values to put in them (`data-apply`, a JSON map of input id to value),
 * and the input its comment goes into (`data-comment-target`). Accepting
 * writes all of them at once and fires `input` on each, so whatever listens -
 * a category's totals, the page's unsaved-changes guard - hears of it as if it
 * had been typed. Nothing is sent anywhere; the page's own Save does that.
 *
 * Two suggestions can share a comment input - a minimum and a maximum on one
 * value. The second one accepted adds its comment to the first rather than
 * replacing it, so neither reason is lost.
 *
 * @returns {Object} Alpine component state
 */
export function suggestionRow() {
  return {
    accepted: false,
    previous: {},
    written: {},
    commentWasSuggested: false,

    accept: function () {
      if (this.accepted) return;
      var apply = parseApply(this.$root.getAttribute("data-apply"));
      var previous = {};
      var written = {};

      Object.keys(apply).forEach(function (id) {
        var field = document.getElementById(id);
        if (!field) return;
        previous[id] = field.value;
        written[id] = String(apply[id]);
        setValue(field, written[id]);
      });

      var commentId = this.$root.getAttribute("data-comment-target");
      var commentField = commentId ? document.getElementById(commentId) : null;
      var comment = this.$refs.comment ? this.$refs.comment.value.trim() : "";
      if (commentField && comment) {
        previous[commentId] = commentField.value;
        this.commentWasSuggested =
          commentField.getAttribute("data-suggestion-comment") === "true";
        written[commentId] = combineComment(commentField, comment);
        setValue(commentField, written[commentId]);
        commentField.setAttribute("data-suggestion-comment", "true");
      }

      this.previous = previous;
      this.written = written;
      this.accepted = true;
    },

    /**
     * Put back what Accept replaced - but only in an input still holding what
     * Accept wrote. One the user has typed over since is theirs, not ours.
     */
    undo: function () {
      var previous = this.previous;
      var written = this.written;
      var commentId = this.$root.getAttribute("data-comment-target");
      var commentWasSuggested = this.commentWasSuggested;
      Object.keys(previous).forEach(function (id) {
        var field = document.getElementById(id);
        if (!field || field.value !== written[id]) return;
        setValue(field, previous[id]);
        if (id === commentId && !commentWasSuggested) {
          field.removeAttribute("data-suggestion-comment");
        }
      });
      this.previous = {};
      this.written = {};
      this.accepted = false;
    },
  };
}

function parseApply(raw) {
  if (!raw) return {};
  try {
    return JSON.parse(raw) || {};
  } catch (e) {
    // A malformed map has nothing usable in it; accepting it changes nothing.
    return {};
  }
}

function combineComment(field, comment) {
  var current = field.value.trim();
  if (current && field.getAttribute("data-suggestion-comment") === "true") {
    return current + "; " + comment;
  }
  return comment;
}

function setValue(field, value) {
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}
