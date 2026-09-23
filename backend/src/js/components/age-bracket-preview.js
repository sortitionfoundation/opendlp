/**
 * ABOUTME: Alpine component previewing the labels an age-bracket derivation will generate
 * ABOUTME: Mirrors AgeBracketRule.bracket_labels() and flags labels the target's values don't contain
 *
 * Usage:
 *   <div x-data="ageBracketPreview" data-fallback="UNKNOWN"
 *        data-target-values='["16-24","25-39","40+"]' @input="recalc()">
 *     <input name="min_age"> <input name="max_age"> <input name="boundaries">
 *     <strong x-text="previewText"></strong>
 *     <p x-show="mismatchLabels"><span x-text="mismatchLabels"></span></p>
 *   </div>
 *
 * The inputs stay ordinary form fields (the server round-trips them); the
 * component only reads them, so everything still works with JS off.
 */

/**
 * Build the ageBracketPreview component state.
 *
 * @returns {Object} Alpine component state
 */
export function ageBracketPreview() {
  return {
    previewText: "",
    mismatchLabels: "",

    init: function () {
      this.recalc();
    },

    recalc: function () {
      var root = this.$root;
      var value = function (name) {
        var el = root.querySelector('[name="' + name + '"]');
        return el ? el.value : "";
      };
      var toInt = function (raw) {
        return /^\d+$/.test(raw.trim()) ? Number(raw) : NaN;
      };
      var minAge = toInt(value("min_age"));
      var maxAge = toInt(value("max_age"));
      var fallback = root.dataset.fallback || "UNKNOWN";
      var targetValues;
      try {
        targetValues = JSON.parse(root.dataset.targetValues || "[]");
      } catch {
        targetValues = [];
      }
      var boundaries = value("boundaries")
        .split(/[,;]/)
        .map(function (part) {
          return part.trim();
        })
        .filter(Boolean)
        .map(Number);

      var invalid =
        !Number.isInteger(minAge) ||
        !Number.isInteger(maxAge) ||
        maxAge <= minAge ||
        boundaries.some(function (boundary) {
          return (
            !Number.isInteger(boundary) ||
            boundary <= minAge ||
            boundary >= maxAge
          );
        });
      if (invalid) {
        this.previewText = "";
        this.mismatchLabels = "";
        return;
      }

      var unique = Array.from(new Set(boundaries)).sort(function (a, b) {
        return a - b;
      });
      var edges = [minAge].concat(unique, [maxAge]);
      var labels = ["under-" + minAge];
      for (var i = 0; i < edges.length - 1; i++) {
        labels.push(edges[i] + "-" + (edges[i + 1] - 1));
      }
      labels.push(maxAge + "+");

      this.previewText = labels.concat([fallback]).join(", ");
      if (targetValues.length === 0) {
        this.mismatchLabels = "";
        return;
      }
      var targetSet = new Set(targetValues);
      this.mismatchLabels = labels
        .filter(function (label) {
          return !targetSet.has(label);
        })
        .join(", ");
    },
  };
}
