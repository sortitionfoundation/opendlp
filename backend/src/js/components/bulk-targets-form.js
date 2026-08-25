// ABOUTME: Alpine component for the bulk targets edit form as a whole
// ABOUTME: Adds a category client-side; nothing exists until the form is saved

import {
  applyPlaceholder,
  renumberSortOrder,
} from "../lib/bulk-targets-dom.js";

/**
 * Build the state for the bulk targets edit form.
 *
 * Adding a category clones a blank block into the page under a "new-<n>" id,
 * the shape save_all_parser reads as "create this one". Like every other change
 * in this form it is provisional: the category exists only once "Save all" goes
 * through, so an accidental one costs a Cancel rather than a delete.
 *
 * @returns {Object} Alpine component state
 */
export function bulkTargetsForm() {
  return {
    newCategoryName: "",
    newCategoryCount: 0,

    addCategory: function () {
      var name = this.newCategoryName.trim();
      if (!name) return;

      this.newCategoryCount += 1;
      var fragment = this.$refs.categoryTemplate.content.cloneNode(true);
      var block = fragment.firstElementChild;
      applyPlaceholder(block, "__CAT__", "new-" + this.newCategoryCount);

      var nameInput = block.querySelector("[data-category-name]");
      if (nameInput) {
        // Both, so the value survives and locators keyed on the attribute find it.
        nameInput.value = name;
        nameInput.setAttribute("value", name);
      }

      this.$refs.categories.appendChild(fragment);
      renumberSortOrder(this.$refs.categories);
      this.newCategoryName = "";
    },
  };
}
