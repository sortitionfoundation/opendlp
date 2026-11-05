// ABOUTME: Unit tests for the bulkTargetsValueRow Alpine component
// ABOUTME: Covers deletion and its undo, min/max following the percentage, and re-linking them

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  bulkTargetsValueRow,
  minMaxForPercentage,
} from "./bulk-targets-value-row.js";

function rowState({
  isNew = false,
  deleted = false,
  manual = false,
  relink = false,
  percentage = "",
  min = "",
  max = "",
  panelSize = "30",
} = {}) {
  document.body.innerHTML = `
    <form data-number-to-select="${panelSize}"
          data-recalculated-message="Min {min} and max {max}, from the percentage">
    <table><tbody id="rows">
      <tr id="row" data-value-row="true" data-deleted="false">
        <td>
          <input type="hidden" id="deleted" value="false" />
          <input type="hidden" id="relink" value="false" />
          <input type="hidden" id="manual" value="false" />
        </td>
        <td><input id="percentage" data-field="percentage" value="${percentage}" /></td>
        <td><input id="min" data-field="min" value="${min}" /></td>
        <td><input id="max" data-field="max" value="${max}" /></td>
      </tr>
    </tbody></table>
    </form>`;
  const state = bulkTargetsValueRow({
    isNew: isNew,
    deleted: deleted,
    manual: manual,
    relink: relink,
  });
  state.$root = document.getElementById("row");
  state.$refs = {
    deletedField: document.getElementById("deleted"),
    relinkField: document.getElementById("relink"),
    manualField: document.getElementById("manual"),
  };
  state.init();
  return state;
}

function typeInto(id, value) {
  document.getElementById(id).value = value;
}

function minMax() {
  return [
    document.getElementById("min").value,
    document.getElementById("max").value,
  ];
}

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("bulkTargetsValueRow", () => {
  it("starts undeleted and linked", () => {
    const state = rowState();
    expect(state.deleted).toBe(false);
    expect(state.relink).toBe(false);
    expect(state.rowClass).toBe("");
  });

  it("starts deleted when the redisplayed form says it was", () => {
    // A rejected save must not quietly undo the deletions it came back with.
    const state = rowState({ deleted: true });
    expect(state.deleted).toBe(true);
    expect(state.rowClass).toBe("is-pending-delete");
  });

  it("marks an existing row for deletion rather than removing it", () => {
    const state = rowState();
    state.remove();
    expect(document.getElementById("row")).not.toBeNull();
    expect(state.deleted).toBe(true);
    expect(state.$root.getAttribute("data-deleted")).toBe("true");
    expect(state.$refs.deletedField.value).toBe("true");
    expect(state.rowClass).toBe("is-pending-delete");
  });

  it("takes a row the user just added straight out of the DOM", () => {
    const state = rowState({ isNew: true });
    state.remove();
    expect(document.getElementById("row")).toBeNull();
  });

  it("restores a row marked for deletion", () => {
    const state = rowState();
    state.remove();
    state.undoRemove();
    expect(state.deleted).toBe(false);
    expect(state.$root.getAttribute("data-deleted")).toBe("false");
    expect(state.$refs.deletedField.value).toBe("false");
  });

  it("records a request to re-link min and max to the percentage", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    state.usePercentage();
    expect(state.relink).toBe(true);
    expect(state.manual).toBe(false);
    expect(state.$refs.relinkField.value).toBe("true");
    expect(state.$refs.manualField.value).toBe("false");
  });

  it("fills min and max back in from the percentage on re-linking", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    state.usePercentage();
    expect(minMax()).toEqual(["15", "16"]);
    expect(state.showsCalculated).toBe(true);
  });

  it("moves focus to the percentage on re-linking", () => {
    // The Recalculate button disables itself, which would drop focus to the
    // page. Not to min or max: typing there would break the link again.
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    state.usePercentage();
    expect(document.activeElement).toBe(document.getElementById("percentage"));
  });

  it("has nothing to re-link to without a percentage", () => {
    const state = rowState({ manual: true, min: "1", max: "2" });
    expect(state.canRelink).toBe(false);
    state.usePercentage();
    expect(state.relink).toBe(false);
    expect(minMax()).toEqual(["1", "2"]);
  });

  it("recalculates min and max as the percentage is typed", () => {
    const state = rowState({ percentage: "50", min: "15", max: "16" });
    typeInto("percentage", "25");
    state.percentageChanged();
    expect(minMax()).toEqual(["7", "8"]);
    expect(state.showsCalculated).toBe(true);
    expect(state.showsManual).toBe(false);
  });

  it("fills min and max in on a new row once a percentage is typed", () => {
    const state = rowState({ isNew: true });
    expect(state.showsCalculated).toBe(false);
    typeInto("percentage", "33.3");
    state.percentageChanged();
    expect(minMax()).toEqual(["9", "10"]);
    expect(state.showsCalculated).toBe(true);
  });

  it("leaves hand-set min and max alone when the percentage changes", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    typeInto("percentage", "25");
    state.percentageChanged();
    expect(minMax()).toEqual(["1", "2"]);
    expect(state.showsManual).toBe(true);
  });

  it("stops following the percentage once min or max is typed into", () => {
    const state = rowState({ percentage: "50", min: "15", max: "16" });
    typeInto("min", "12");
    state.minMaxEdited();
    expect(state.manual).toBe(true);
    expect(state.$refs.manualField.value).toBe("true");
    expect(state.canRelink).toBe(true);

    typeInto("percentage", "25");
    state.percentageChanged();
    expect(minMax()).toEqual(["12", "16"]);
  });

  it("drops a pending re-link when min or max is typed into again", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    state.usePercentage();
    state.minMaxEdited();
    expect(state.relink).toBe(false);
    expect(state.$refs.relinkField.value).toBe("false");
  });

  it("does not ask the save to re-link once the percentage is cleared", () => {
    // Re-linking with nothing to link to would fail the whole row on save.
    const state = rowState({
      relink: true,
      percentage: "50",
      min: "15",
      max: "16",
    });
    typeInto("percentage", "");
    state.percentageChanged();
    expect(state.$refs.relinkField.value).toBe("false");
    expect(state.showsCalculated).toBe(false);
    expect(state.showsManual).toBe(false);
    expect(minMax()).toEqual(["15", "16"]);
  });

  it("says what min and max were recalculated to", () => {
    // Otherwise a screen reader user is not told the numbers beside them moved.
    const state = rowState({ percentage: "" });
    typeInto("percentage", "50");
    state.percentageChanged();
    expect(state.announcement).toBe("Min 15 and max 16, from the percentage");
  });

  it("says nothing while min and max are left alone", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    typeInto("percentage", "60");
    state.percentageChanged();
    expect(state.announcement).toBe("");
  });

  it("says what min and max were recalculated to on re-linking", () => {
    const state = rowState({
      manual: true,
      percentage: "50",
      min: "1",
      max: "2",
    });
    state.usePercentage();
    expect(state.announcement).toBe("Min 15 and max 16, from the percentage");
  });

  it("gives 0 and 0 while the panel size is not set", () => {
    const state = rowState({ panelSize: "0" });
    typeInto("percentage", "50");
    state.percentageChanged();
    expect(minMax()).toEqual(["0", "0"]);
  });

  it("tells the category around it to redo its totals", () => {
    const state = rowState({ manual: true, percentage: "50" });
    const seen = vi.fn();
    document.getElementById("rows").addEventListener("targets-changed", seen);
    state.remove();
    state.undoRemove();
    state.usePercentage();
    expect(seen).toHaveBeenCalledTimes(3);
  });

  it("still tells the category when a new row removes itself", () => {
    const state = rowState({ isNew: true });
    const seen = vi.fn();
    document.getElementById("rows").addEventListener("targets-changed", seen);
    state.remove();
    expect(seen).toHaveBeenCalledTimes(1);
  });
});

describe("minMaxForPercentage", () => {
  // Worked out by min_max_for_percentage in opendlp/domain/targets.py. The
  // save compares the form's numbers with that function's, so they must agree.
  it.each([
    [50, 30, [15, 16]],
    [25, 30, [7, 8]],
    [33.3, 30, [9, 10]],
    [10, 10, [1, 2]],
    [100, 30, [30, 30]],
    [0, 30, [0, 0]],
    [12.5, 40, [5, 6]],
    [0.1, 24, [0, 1]],
    [51.2, 100, [51, 52]],
  ])(
    "gives %s%% of %s as %j, as the server does",
    (percentage, panelSize, expected) => {
      expect(minMaxForPercentage(percentage, panelSize)).toEqual(expected);
    },
  );
});
