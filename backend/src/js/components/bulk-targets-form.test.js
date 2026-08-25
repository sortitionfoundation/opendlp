// ABOUTME: Unit tests for the bulkTargetsForm Alpine component
// ABOUTME: Covers adding a category client-side from the blank block template

import { beforeEach, describe, expect, it } from "vitest";

import { bulkTargetsForm } from "./bulk-targets-form.js";

const BLOCK_TEMPLATE = `
  <template id="category-template">
    <div id="bulk-category-__CAT__">
      <input type="hidden" data-sort-order="true" name="cat[__CAT__][sort_order]" value="" />
      <label for="bulk-name-__CAT__">Category Name</label>
      <input data-category-name="true" id="bulk-name-__CAT__" name="cat[__CAT__][name]" value="" />
      <table><tbody>
        <template>
          <tr>
            <input id="bulk-__CAT__-__ID__-value" name="cat[__CAT__][values][__ID__][value]" value="" />
          </tr>
        </template>
      </tbody></table>
    </div>
  </template>`;

function formState(existing = "") {
  document.body.innerHTML = `
    <form>
      <div id="categories">${existing}</div>
      ${BLOCK_TEMPLATE}
    </form>`;
  const state = bulkTargetsForm();
  state.$refs = {
    categories: document.getElementById("categories"),
    categoryTemplate: document.getElementById("category-template"),
  };
  return state;
}

function existingBlock(id, sortOrder) {
  return `<div id="bulk-category-${id}"><input type="hidden" data-sort-order="true" value="${sortOrder}" /></div>`;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("bulkTargetsForm", () => {
  it("adds nothing when the name box is empty", () => {
    const state = formState();
    state.addCategory();
    expect(state.$refs.categories.children.length).toBe(0);
  });

  it("adds nothing when the name box holds only spaces", () => {
    const state = formState();
    state.newCategoryName = "   ";
    state.addCategory();
    expect(state.$refs.categories.children.length).toBe(0);
  });

  it("appends a block named for a new category", () => {
    const state = formState();
    state.newCategoryName = "Age";
    state.addCategory();

    const added = state.$refs.categories.lastElementChild;
    expect(added.id).toBe("bulk-category-new-1");
    expect(added.querySelector("[data-category-name]").name).toBe(
      "cat[new-1][name]",
    );
    expect(added.querySelector("[data-category-name]").value).toBe("Age");
  });

  it("trims the name it was given", () => {
    const state = formState();
    state.newCategoryName = "  Age  ";
    state.addCategory();
    expect(
      state.$refs.categories.querySelector("[data-category-name]").value,
    ).toBe("Age");
  });

  it("clears the name box afterwards", () => {
    const state = formState();
    state.newCategoryName = "Age";
    state.addCategory();
    expect(state.newCategoryName).toBe("");
  });

  it("gives each added category its own id", () => {
    const state = formState();
    state.newCategoryName = "Age";
    state.addCategory();
    state.newCategoryName = "Region";
    state.addCategory();

    const ids = Array.from(state.$refs.categories.children).map((el) => el.id);
    expect(ids).toEqual(["bulk-category-new-1", "bulk-category-new-2"]);
  });

  it("points the block's labels at the fields they name", () => {
    const state = formState();
    state.newCategoryName = "Age";
    state.addCategory();

    const added = state.$refs.categories.lastElementChild;
    expect(added.querySelector("label").htmlFor).toBe("bulk-name-new-1");
    expect(added.querySelector("[data-category-name]").id).toBe(
      "bulk-name-new-1",
    );
  });

  it("substitutes the category id inside the block's own row template", () => {
    const state = formState();
    state.newCategoryName = "Age";
    state.addCategory();

    const rowTemplate = state.$refs.categories.querySelector("template");
    const rowInput = rowTemplate.content.querySelector("input");
    expect(rowInput.name).toBe("cat[new-1][values][__ID__][value]");
  });

  it("re-issues sort order across every block", () => {
    const state = formState(
      existingBlock("a", "10") + existingBlock("b", "20"),
    );
    state.newCategoryName = "Age";
    state.addCategory();

    const orders = Array.from(
      state.$refs.categories.querySelectorAll("[data-sort-order]"),
    ).map((el) => el.value);
    expect(orders).toEqual(["10", "20", "30"]);
  });
});
