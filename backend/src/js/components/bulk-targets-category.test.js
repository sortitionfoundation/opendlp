// ABOUTME: Unit tests for the bulkTargetsCategory Alpine component
// ABOUTME: Covers the live totals row, adding rows from a template, and reordering categories

import { beforeEach, describe, expect, it } from "vitest";

import { bulkTargetsCategory } from "./bulk-targets-category.js";

function valueRow({ percentage = "", min = "", max = "", deleted = false }) {
  return `
    <tr data-value-row="true" data-deleted="${deleted}">
      <td>
        <input data-field="percentage" name="pct" value="${percentage}" />
        <input data-field="min" name="min" value="${min}" />
        <input data-field="max" name="max" value="${max}" />
      </td>
    </tr>`;
}

const BLANK_TEMPLATE = `
  <template id="row-template">
    <tr data-value-row="true" data-deleted="false">
      <td>
        <input id="v-__ID__" name="cat[c][values][__ID__][value]" value="" />
        <input data-field="percentage" name="cat[c][values][__ID__][percentage]" value="" />
        <input data-field="min" name="cat[c][values][__ID__][min]" value="" />
        <input data-field="max" name="cat[c][values][__ID__][max]" value="" />
      </td>
    </tr>
  </template>`;

function categoryState(rows, { missing = "" } = {}) {
  document.body.innerHTML = `
    <div id="categories">
      <div id="block">
        <input type="hidden" id="deleted" value="false" />
        <input type="hidden" data-sort-order="true" value="10" />
        <table><tbody id="rows">${rows}${BLANK_TEMPLATE}${missing}</tbody></table>
      </div>
    </div>`;
  const state = bulkTargetsCategory({ emptyLabel: "None" });
  state.$root = document.getElementById("block");
  state.$refs = {
    rows: document.getElementById("rows"),
    rowTemplate: document.getElementById("row-template"),
    missingTemplate: document.getElementById("missing-template"),
    deletedField: document.getElementById("deleted"),
  };
  state.init();
  return state;
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("bulkTargetsCategory totals", () => {
  it("sums the percentages, mins and maxes on the page", () => {
    const state = categoryState(
      valueRow({ percentage: "50", min: "4", max: "6" }) +
        valueRow({ percentage: "50", min: "4", max: "6" }),
    );
    expect(state.percentageTotal).toBe("100%");
    expect(state.minTotal).toBe("8");
    expect(state.maxTotal).toBe("12");
  });

  it("leaves rows marked for deletion out of the totals", () => {
    const state = categoryState(
      valueRow({ percentage: "60", min: "5", max: "7" }) +
        valueRow({ percentage: "40", min: "3", max: "4", deleted: true }),
    );
    expect(state.percentageTotal).toBe("60%");
    expect(state.minTotal).toBe("5");
    expect(state.maxTotal).toBe("7");
  });

  it("shows the empty label when no value has a percentage", () => {
    const state = categoryState(valueRow({ min: "4", max: "6" }));
    expect(state.percentageTotal).toBe("None");
    expect(state.minTotal).toBe("4");
  });

  it("treats a category with no percentages as plausible", () => {
    const state = categoryState(valueRow({ min: "4", max: "6" }));
    expect(state.percentagesPlausible).toBe(true);
    expect(state.percentageTotalClass).toBe("");
  });

  it("accepts a total within a percentage point of 100", () => {
    const state = categoryState(
      valueRow({ percentage: "50" }) + valueRow({ percentage: "49.5" }),
    );
    expect(state.percentagesPlausible).toBe(true);
  });

  it("flags a total that is further out than that", () => {
    const state = categoryState(
      valueRow({ percentage: "50" }) + valueRow({ percentage: "30" }),
    );
    expect(state.percentagesPlausible).toBe(false);
    expect(state.percentageTotalClass).toBe("targets-total--implausible");
  });

  it("rounds the percentage total to two places", () => {
    const state = categoryState(
      valueRow({ percentage: "33.33" }) +
        valueRow({ percentage: "33.33" }) +
        valueRow({ percentage: "33.33" }),
    );
    expect(state.percentageTotal).toBe("99.99%");
  });

  it("ignores a cell that is not a number", () => {
    const state = categoryState(valueRow({ percentage: "abc", min: "4" }));
    expect(state.percentageTotal).toBe("None");
    expect(state.minTotal).toBe("4");
  });
});

describe("bulkTargetsCategory adding rows", () => {
  it("appends a blank row named for a new value", () => {
    const state = categoryState(valueRow({ percentage: "100" }));
    state.addValue();
    const added = state.$refs.rows.lastElementChild;
    expect(added.querySelector("[name$='[value]']").name).toBe(
      "cat[c][values][new-1][value]",
    );
    expect(added.querySelector("[name$='[value]']").id).toBe("v-new-1");
  });

  it("gives each added row its own id", () => {
    const state = categoryState("");
    state.addValue();
    state.addValue();
    const names = Array.from(
      state.$refs.rows.querySelectorAll("[name$='[value]']"),
    ).map((el) => el.name);
    expect(names).toEqual([
      "cat[c][values][new-1][value]",
      "cat[c][values][new-2][value]",
    ]);
  });

  it("leaves the totals alone when the added row is blank", () => {
    const state = categoryState(valueRow({ percentage: "100", min: "10" }));
    state.addValue();
    expect(state.percentageTotal).toBe("100%");
    expect(state.minTotal).toBe("10");
  });

  it("adds one row per value found in the respondent data", () => {
    const missing = `
      <template id="missing-template">
        <tr data-value-row="true" data-deleted="false">
          <td><input id="v-__ID__" name="cat[c][values][__ID__][value]" value="Other" /></td>
        </tr>
        <tr data-value-row="true" data-deleted="false">
          <td><input id="v-__ID__" name="cat[c][values][__ID__][value]" value="Prefer not to say" /></td>
        </tr>
      </template>`;
    const state = categoryState("", { missing: missing });
    state.addMissingValues();
    const added = Array.from(
      state.$refs.rows.querySelectorAll("[name$='[value]']"),
    );
    expect(added.map((el) => el.value)).toEqual(["Other", "Prefer not to say"]);
    expect(added.map((el) => el.name)).toEqual([
      "cat[c][values][new-1][value]",
      "cat[c][values][new-2][value]",
    ]);
    expect(state.missingAdded).toBe(true);
  });
});

describe("bulkTargetsCategory deletion", () => {
  it("starts deleted when the redisplayed form says it was", () => {
    // A rejected save must not quietly undo the deletions it came back with.
    const state = bulkTargetsCategory({ emptyLabel: "None", deleted: true });
    expect(state.deleted).toBe(true);
  });

  it("marks the whole category for deletion", () => {
    const state = categoryState("");
    state.markDeleted();
    expect(state.deleted).toBe(true);
    expect(state.$refs.deletedField.value).toBe("true");
  });

  it("takes the mark off again", () => {
    const state = categoryState("");
    state.markDeleted();
    state.undoDelete();
    expect(state.deleted).toBe(false);
    expect(state.$refs.deletedField.value).toBe("false");
  });

  it("takes a category the user just added straight out of the DOM", () => {
    document.body.innerHTML = `
      <div id="categories">
        <div id="block-a"><input type="hidden" data-sort-order="true" value="10" /></div>
        <div id="block-b"><input type="hidden" data-sort-order="true" value="20" /></div>
      </div>`;
    const state = bulkTargetsCategory({ isNew: true });
    state.$root = document.getElementById("block-b");
    state.$refs = {};

    state.markDeleted();

    expect(document.getElementById("block-b")).toBeNull();
    expect(document.querySelector("[data-sort-order]").value).toBe("10");
  });
});

describe("bulkTargetsCategory reordering", () => {
  function twoBlocks() {
    document.body.innerHTML = `
      <div id="categories">
        <div id="first"><input type="hidden" data-sort-order="true" value="10" /><tbody id="rows-a"></tbody></div>
        <div id="second"><input type="hidden" data-sort-order="true" value="20" /></div>
      </div>`;
    const state = bulkTargetsCategory({});
    state.$root = document.getElementById("second");
    state.$refs = { rows: document.getElementById("rows-a") };
    return state;
  }

  function order() {
    return Array.from(document.getElementById("categories").children).map(
      (el) => el.id,
    );
  }

  function sortOrders() {
    return Array.from(document.querySelectorAll("[data-sort-order]")).map(
      (el) => el.value,
    );
  }

  it("moves a block above the one before it", () => {
    const state = twoBlocks();
    state.moveUp();
    expect(order()).toEqual(["second", "first"]);
  });

  it("re-issues sort_order across every block after a move", () => {
    const state = twoBlocks();
    state.moveUp();
    expect(sortOrders()).toEqual(["10", "20"]);
    expect(
      document.getElementById("second").querySelector("[data-sort-order]")
        .value,
    ).toBe("10");
  });

  it("does nothing when the block is already first", () => {
    const state = twoBlocks();
    state.$root = document.getElementById("first");
    state.moveUp();
    expect(order()).toEqual(["first", "second"]);
  });

  it("moves a block below the one after it", () => {
    const state = twoBlocks();
    state.$root = document.getElementById("first");
    state.moveDown();
    expect(order()).toEqual(["second", "first"]);
  });

  it("does nothing when the block is already last", () => {
    const state = twoBlocks();
    state.moveDown();
    expect(order()).toEqual(["first", "second"]);
  });
});
