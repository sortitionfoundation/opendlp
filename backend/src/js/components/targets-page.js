// ABOUTME: Alpine component for the targets page - which mode it is showing, and adding a target
// ABOUTME: A new target is cloned client-side; nothing exists until the form is saved

import {
  applyPlaceholder,
  renumberSortOrder,
} from "../lib/bulk-targets-dom.js";
import { editGuard } from "./edit-guard.js";

// The blank row the template carries. addValue() issues new-1 onwards, so the
// row that arrives with the block takes the one id it will never reach.
var FIRST_ROW_ID = "new-0";

/**
 * Build the state for the targets page.
 *
 * The read-only view and the edit form are the same page: `editingAll` decides
 * which of them is on screen, and both are already in the DOM. So "Add target"
 * is one button with one handler wherever it is clicked from - it names the
 * target in a dialog, clones a blank block into the form, and switches to it.
 * Nothing is sent to the server, so no unsaved edit elsewhere on the page is
 * lost, and the target exists only once "Save all" goes through.
 *
 * That last part is what the edit guard is here for. The edits live only in
 * this page until it is saved, and every link on it - the assembly tabs, the
 * way back to the dashboard, the header and the footer - would take them away
 * without a word. So this page asks editGuard to intercept links, which a page
 * that already funnels leaving through one control does not need to.
 *
 * @param {Object} [options] - configuration
 * @param {boolean} [options.editingAll=false] - whether the page opens in edit mode,
 *   as it does when a rejected save redisplays the form
 * @returns {Object} Alpine component state
 */
export function targetsPage(options) {
  return Object.assign({}, editGuard({ guardLinks: true }), {
    editingAll: Boolean(options && options.editingAll),
    addTargetOpen: false,
    newCategoryName: "",
    newCategoryCount: 0,

    init: function () {
      this.initEditGuard();
    },

    openAddTarget: function () {
      this.newCategoryName = "";
      this.addTargetOpen = true;
      var self = this;
      // The dialog's body is mounted by x-if, so its field only exists once
      // the flag above has been acted on.
      this.$nextTick(function () {
        if (self.$refs.newTargetName) self.$refs.newTargetName.focus();
      });
    },

    cancelAddTarget: function () {
      this.addTargetOpen = false;
      this.newCategoryName = "";
      // Back to the control that opened it, so a keyboard user is where they were.
      if (this.$refs.addTargetButton) this.$refs.addTargetButton.focus();
    },

    confirmAddTarget: function () {
      var name = this.newCategoryName.trim();
      if (!name) return;

      var block = this.addCategory(name);
      this.addTargetOpen = false;
      this.newCategoryName = "";
      // The new target only exists in the edit form, so that is where we go -
      // and it exists only in the page, so leaving now would lose it.
      this.editingAll = true;
      this.markEditDirty();
      this.revealCategory(block);
    },

    /**
     * Clone a blank category block into the form under the given name.
     *
     * The block takes a "new-<n>" id, the shape save_all_parser reads as
     * "create this one", and arrives with the single blank value row its
     * template carries.
     *
     * @param {string} name - the category name to fill in
     * @returns {Element} the block that was appended
     */
    addCategory: function (name) {
      this.newCategoryCount += 1;
      var fragment = this.$refs.categoryTemplate.content.cloneNode(true);
      var block = fragment.firstElementChild;
      applyPlaceholder(block, "__CAT__", "new-" + this.newCategoryCount);
      applyPlaceholder(block, "__ROW__", FIRST_ROW_ID);

      var nameInput = block.querySelector("[data-category-name]");
      if (nameInput) {
        // Both, so the value survives and locators keyed on the attribute find it.
        nameInput.value = name;
        nameInput.setAttribute("value", name);
      }

      this.$refs.categories.appendChild(fragment);
      renumberSortOrder(this.$refs.categories);
      return block;
    },

    /**
     * Bring a newly added block into view, ready to be filled in.
     *
     * Waits a tick because the block is only shown once `editingAll` has been
     * acted on, and an element that is still display:none cannot be scrolled to.
     *
     * @param {Element} block - the category block to reveal
     */
    revealCategory: function (block) {
      this.$nextTick(function () {
        var input = block.querySelector('[data-field="value"]');
        // Focused without its own scroll, so the smooth one below is what runs.
        if (input) input.focus({ preventScroll: true });
        if (block.scrollIntoView) {
          block.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    },
  });
}
