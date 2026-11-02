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
 * The comment is added after whatever the comment input already holds, never
 * put in place of it - so neither what the organiser wrote there nor the
 * comment of another suggestion accepted on the same value is lost. The server
 * joins comments the same way when it accepts a suggestion itself.
 *
 * @returns {Object} Alpine component state
 */
export function suggestionRow() {
  return {
    accepted: false,
    previous: {},
    written: {},

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
        written[commentId] = appendComment(commentField.value, comment);
        setValue(commentField, written[commentId]);
      }

      this.previous = previous;
      this.written = written;
      this.accepted = true;
    },

    /**
     * Accept from the row's own button. The button is hidden once accepted, so
     * focus moves to Undo rather than falling back to the page. Accepting every
     * row at once leaves focus alone - it is not this row's button that was used.
     */
    acceptFromButton: function () {
      var self = this;
      self.accept();
      self.$nextTick(function () {
        if (self.$refs.undoBtn) self.$refs.undoBtn.focus();
      });
    },

    /** Undo from the row's own button, handing focus back to Accept. */
    undoFromButton: function () {
      var self = this;
      self.undo();
      self.$nextTick(function () {
        if (self.$refs.acceptBtn) self.$refs.acceptBtn.focus();
      });
    },

    /**
     * Put back what Accept replaced - but only in an input still holding what
     * Accept wrote. One the user has typed over since is theirs, not ours.
     */
    undo: function () {
      var previous = this.previous;
      var written = this.written;
      Object.keys(previous).forEach(function (id) {
        var field = document.getElementById(id);
        if (!field || field.value !== written[id]) return;
        setValue(field, previous[id]);
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

// The same separator as COMMENT_SEPARATOR in service_layer/target_suggestions.py.
var COMMENT_SEPARATOR = "; ";

function appendComment(existing, addition) {
  var current = existing.trim();
  return current ? current + COMMENT_SEPARATOR + addition : addition;
}

function setValue(field, value) {
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}
