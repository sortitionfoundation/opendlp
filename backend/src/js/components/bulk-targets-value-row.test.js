// ABOUTME: Unit tests for the bulkTargetsValueRow Alpine component
// ABOUTME: Covers provisional deletion, its undo, and asking for min/max to be re-linked

import { beforeEach, describe, expect, it, vi } from "vitest";

import { bulkTargetsValueRow } from "./bulk-targets-value-row.js";

function rowState({ isNew = false, deleted = false } = {}) {
  document.body.innerHTML = `
    <table><tbody id="rows">
      <tr id="row" data-value-row="true" data-deleted="false">
        <td>
          <input type="hidden" id="deleted" value="false" />
          <input type="hidden" id="relink" value="false" />
        </td>
      </tr>
    </tbody></table>`;
  const state = bulkTargetsValueRow({ isNew: isNew, deleted: deleted });
  state.$root = document.getElementById("row");
  state.$refs = {
    deletedField: document.getElementById("deleted"),
    relinkField: document.getElementById("relink"),
  };
  return state;
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
    const state = rowState();
    state.usePercentage();
    expect(state.relink).toBe(true);
    expect(state.$refs.relinkField.value).toBe("true");
  });

  it("tells the category around it to redo its totals", () => {
    const state = rowState();
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
