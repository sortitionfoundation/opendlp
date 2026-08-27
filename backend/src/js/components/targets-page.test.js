// ABOUTME: Unit tests for the targetsPage Alpine component
// ABOUTME: Covers the add-target dialog and cloning a category from the blank block template

import { beforeEach, describe, expect, it, vi } from "vitest";

import { targetsPage } from "./targets-page.js";

const BLOCK_TEMPLATE = `
  <template id="category-template">
    <div id="bulk-category-__CAT__">
      <input type="hidden" data-sort-order="true" name="cat[__CAT__][sort_order]" value="" />
      <label for="bulk-name-__CAT__">Category Name</label>
      <input data-category-name="true" id="bulk-name-__CAT__" name="cat[__CAT__][name]" value="" />
      <table><tbody>
        <tr data-value-row="true">
          <td><input data-field="value" id="bulk-__CAT__-__ROW__-value" name="cat[__CAT__][values][__ROW__][value]" value="" /></td>
        </tr>
        <template>
          <tr>
            <td><input data-field="value" id="bulk-__CAT__-__ID__-value" name="cat[__CAT__][values][__ID__][value]" value="" /></td>
          </tr>
        </template>
      </tbody></table>
    </div>
  </template>`;

function pageState(existing = "", options = {}) {
  document.body.innerHTML = `
    <div>
      <button id="add-target-button">Add target</button>
      <input id="new-target-name" />
      <form>
        <div id="categories">${existing}</div>
        ${BLOCK_TEMPLATE}
      </form>
    </div>`;
  const state = targetsPage(options);
  state.$refs = {
    categories: document.getElementById("categories"),
    categoryTemplate: document.getElementById("category-template"),
    addTargetButton: document.getElementById("add-target-button"),
    newTargetName: document.getElementById("new-target-name"),
  };
  // Alpine's, reduced to what these tests need: run the callback now.
  state.$nextTick = (fn) => fn();
  return state;
}

function existingBlock(id, sortOrder) {
  return `<div id="bulk-category-${id}"><input type="hidden" data-sort-order="true" value="${sortOrder}" /></div>`;
}

beforeEach(() => {
  document.body.innerHTML = "";
  Element.prototype.scrollIntoView = vi.fn();
});

describe("targetsPage", () => {
  describe("the add-target dialog", () => {
    it("starts closed", () => {
      expect(pageState().addTargetOpen).toBe(false);
    });

    it("opens on an empty name and focuses the field", () => {
      const state = pageState();
      state.newCategoryName = "left over";
      state.openAddTarget();

      expect(state.addTargetOpen).toBe(true);
      expect(state.newCategoryName).toBe("");
      expect(document.activeElement).toBe(state.$refs.newTargetName);
    });

    it("gives focus back to the button when cancelled", () => {
      const state = pageState();
      state.openAddTarget();
      state.newCategoryName = "Age";
      state.cancelAddTarget();

      expect(state.addTargetOpen).toBe(false);
      expect(state.newCategoryName).toBe("");
      expect(document.activeElement).toBe(state.$refs.addTargetButton);
    });

    it("adds nothing when the name is empty", () => {
      const state = pageState();
      state.addTargetOpen = true;
      state.confirmAddTarget();

      expect(state.$refs.categories.children.length).toBe(0);
      // Still open, because there is nothing to close on.
      expect(state.addTargetOpen).toBe(true);
    });

    it("adds nothing when the name is only spaces", () => {
      const state = pageState();
      state.newCategoryName = "   ";
      state.confirmAddTarget();

      expect(state.$refs.categories.children.length).toBe(0);
    });

    it("closes, switches to the edit form and clears the name", () => {
      const state = pageState();
      state.addTargetOpen = true;
      state.newCategoryName = "Age";
      state.confirmAddTarget();

      expect(state.addTargetOpen).toBe(false);
      expect(state.editingAll).toBe(true);
      expect(state.newCategoryName).toBe("");
    });

    it("brings the new block into view with its value box focused", () => {
      const state = pageState();
      state.newCategoryName = "Age";
      state.confirmAddTarget();

      const added = state.$refs.categories.lastElementChild;
      expect(added.scrollIntoView).toHaveBeenCalled();
      expect(document.activeElement).toBe(
        added.querySelector('[data-field="value"]'),
      );
    });
  });

  describe("cloning a category block", () => {
    it("appends a block named for the new category", () => {
      const state = pageState();
      const added = state.addCategory("Age");

      expect(added.id).toBe("bulk-category-new-1");
      expect(added.querySelector("[data-category-name]").name).toBe(
        "cat[new-1][name]",
      );
      expect(added.querySelector("[data-category-name]").value).toBe("Age");
    });

    it("trims the name it was given", () => {
      const state = pageState();
      state.newCategoryName = "  Age  ";
      state.confirmAddTarget();

      expect(
        state.$refs.categories.querySelector("[data-category-name]").value,
      ).toBe("Age");
    });

    it("carries one blank value row, under an id addValue will not reissue", () => {
      const state = pageState();
      const added = state.addCategory("Age");

      const rows = added.querySelectorAll("[data-value-row]");
      expect(rows.length).toBe(1);
      expect(rows[0].querySelector("[data-field]").name).toBe(
        "cat[new-1][values][new-0][value]",
      );
    });

    it("gives each added category its own id", () => {
      const state = pageState();
      state.addCategory("Age");
      state.addCategory("Region");

      const ids = Array.from(state.$refs.categories.children).map(
        (el) => el.id,
      );
      expect(ids).toEqual(["bulk-category-new-1", "bulk-category-new-2"]);
    });

    it("points the block's labels at the fields they name", () => {
      const state = pageState();
      const added = state.addCategory("Age");

      expect(added.querySelector("label").htmlFor).toBe("bulk-name-new-1");
      expect(added.querySelector("[data-category-name]").id).toBe(
        "bulk-name-new-1",
      );
    });

    it("substitutes the category id inside the block's own row template", () => {
      const state = pageState();
      state.addCategory("Age");

      const rowTemplate = state.$refs.categories.querySelector("template");
      const rowInput = rowTemplate.content.querySelector("input");
      expect(rowInput.name).toBe("cat[new-1][values][__ID__][value]");
    });

    it("re-issues sort order across every block", () => {
      const state = pageState(
        existingBlock("a", "10") + existingBlock("b", "20"),
      );
      state.addCategory("Age");

      const orders = Array.from(
        state.$refs.categories.querySelectorAll("[data-sort-order]"),
      ).map((el) => el.value);
      expect(orders).toEqual(["10", "20", "30"]);
    });
  });

  describe("the unsaved-changes guard", () => {
    it("starts clean", () => {
      expect(pageState().editDirty).toBe(false);
    });

    it("is wired up when the page starts, links and all", () => {
      const listeners = vi.spyOn(document, "addEventListener");
      const windowListeners = vi.spyOn(window, "addEventListener");
      pageState().init();

      expect(listeners.mock.calls.some((c) => c[0] === "click")).toBe(true);
      expect(
        windowListeners.mock.calls.some((c) => c[0] === "beforeunload"),
      ).toBe(true);
    });

    it("counts a target added from the read-only view as an edit to lose", () => {
      const state = pageState();
      state.newCategoryName = "Age";
      state.confirmAddTarget();

      expect(state.editDirty).toBe(true);
    });

    it("is not tripped by opening and cancelling the dialog", () => {
      const state = pageState();
      state.openAddTarget();
      state.newCategoryName = "Age";
      state.cancelAddTarget();

      expect(state.editDirty).toBe(false);
    });
  });

  describe("which mode the page opens in", () => {
    it("is the read-only view by default", () => {
      expect(pageState().editingAll).toBe(false);
    });

    it("is the edit form when a rejected save says so", () => {
      expect(pageState("", { editingAll: true }).editingAll).toBe(true);
    });
  });
});
