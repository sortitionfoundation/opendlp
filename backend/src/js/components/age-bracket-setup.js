/**
 * ABOUTME: Alpine component for the age ranges and age-calculation date in the target set-up dialog
 * ABOUTME: Shows each target value's ages as its start is typed, and reveals the inputs behind Edit and Change
 *
 * Usage:
 *   <div x-data="ageBracketSetup" data-editing="false" data-changing-date="false"
 *        data-range-text="{first} to {last}" data-over-text="{age} and over"
 *        data-younger-text="Anyone younger than {age} counts as UNKNOWN."
 *        @input="recalc()">
 *     <tr data-age-row>
 *       <input name="bracket_from"> <td data-ages></td>
 *     </tr>
 *     <p x-show="youngerText" x-text="youngerText"></p>
 *     <input name="as_of_day" x-ref="asOfDay">
 *   </div>
 *
 * The inputs stay ordinary form fields that the server reads and re-renders;
 * the component only works out the "Ages" text and toggles what is shown.
 */

/**
 * Fill {name} placeholders in a translated template.
 *
 * @param {string} template - e.g. "{first} to {last}"
 * @param {Object} values - e.g. {first: 16, last: 29}
 * @returns {string}
 */
function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, function (match, name) {
    return name in values ? String(values[name]) : match;
  });
}

/**
 * Build the ageBracketSetup component state.
 *
 * @returns {Object} Alpine component state
 */
export function ageBracketSetup() {
  return {
    editing: false,
    changingDate: false,
    youngerText: "",

    init: function () {
      this.editing = this.$root.dataset.editing === "true";
      this.changingDate = this.$root.dataset.changingDate === "true";
      this.recalc();
    },

    startEditing: function () {
      var root = this.$root;
      this.editing = true;
      this.$nextTick(function () {
        var first = root.querySelector('[name="bracket_from"]');
        if (first) {
          first.focus();
        }
      });
    },

    changeDate: function () {
      var refs = this.$refs;
      this.changingDate = true;
      this.$nextTick(function () {
        if (refs.asOfDay) {
          refs.asOfDay.focus();
        }
      });
    },

    recalc: function () {
      var data = this.$root.dataset;
      var rows = Array.from(this.$root.querySelectorAll("[data-age-row]"));
      var starts = rows.map(function (row) {
        var raw = row.querySelector('[name="bracket_from"]').value.trim();
        return /^\d+$/.test(raw) ? Number(raw) : null;
      });
      var known = starts.filter(function (start) {
        return start !== null;
      });
      var complete =
        known.length === starts.length && new Set(known).size === known.length;

      rows.forEach(function (row, index) {
        var start = starts[index];
        var cell = row.querySelector("[data-ages]");
        if (start === null) {
          cell.textContent = "";
          return;
        }
        var later = known.filter(function (other) {
          return other > start;
        });
        if (later.length === 0) {
          cell.textContent = fill(data.overText, { age: start });
          return;
        }
        var last = Math.min.apply(null, later) - 1;
        cell.textContent =
          last === start
            ? String(start)
            : fill(data.rangeText, { first: start, last: last });
      });

      var youngest = known.length ? Math.min.apply(null, known) : 0;
      this.youngerText =
        complete && youngest > 0
          ? fill(data.youngerText, { age: youngest })
          : "";
    },
  };
}
