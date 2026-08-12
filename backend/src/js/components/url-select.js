/**
 * ABOUTME: Alpine component that navigates to a URL when a select's value changes
 * ABOUTME: Supports focus restoration for keyboard users via the data-focus-id attribute
 *
 * Usage:
 *   <div x-data="urlSelect({ baseUrl: '/page', paramName: 'source', initialValue: 'option1' })">
 *     <select x-model="selected" @change="navigate($event)" data-focus-id="my-select">
 *       <option value="option1">Option 1</option>
 *       <option value="option2">Option 2</option>
 *     </select>
 *   </div>
 *
 * Focus restoration:
 *   If the element has data-focus-id and has keyboard focus when navigating,
 *   the URL will include #focus=<focusId> to restore focus after page load.
 */

/**
 * Build the urlSelect component state.
 *
 * @param {Object} options - configuration
 * @param {string} options.baseUrl - base URL to navigate to (required)
 * @param {string} [options.paramName="value"] - query parameter name
 * @param {string} [options.initialValue=""] - initially selected value
 * @returns {Object} Alpine component state
 */
export function urlSelect(options) {
  var baseUrl = options.baseUrl || "";
  var paramName = options.paramName || "value";
  var initialValue = options.initialValue || "";

  return {
    selected: initialValue,

    navigate: function (event) {
      // Build URL - skip query param if value is empty
      var url = baseUrl;
      if (this.selected) {
        // Use & if URL already has query params, otherwise use ?
        var separator = url.indexOf("?") !== -1 ? "&" : "?";
        url += separator + paramName + "=" + encodeURIComponent(this.selected);
      }

      // Add focus hash if element has focus (keyboard navigation)
      // Use event.target to get the actual element (not the x-data root)
      var el = event ? event.target : this.$el;
      var focusId = el.dataset.focusId;
      if (focusId && document.activeElement === el) {
        url += "#focus=" + focusId;
      }

      window.location.href = url;
    },
  };
}
