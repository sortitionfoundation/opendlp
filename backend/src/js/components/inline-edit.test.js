// ABOUTME: Unit tests for the inlineEdit Alpine component
// ABOUTME: Covers opening, Escape, saving by tick, Enter or leaving the row, and a save that failed outright

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { inlineEdit, SAVE_EVENT } from "./inline-edit.js";

/**
 * A row as the server renders it, holding `saved`, with `typed` in the field,
 * and the component over it with the Alpine magics it reaches for supplied by
 * hand. `editing` renders it as after a refusal.
 */
function row({ saved = "Ada", typed = saved, editing = false } = {}) {
  document.body.innerHTML = `
    <form id="row" ${editing ? "data-editing" : ""}>
      <input type="hidden" id="saved">
      <input type="hidden" id="return-focus" name="return_focus" value="">
      <input id="field" name="first_name">
      <button type="button" id="edit">Edit first name</button>
      <button type="submit" id="tick">Save first name</button>
      <button type="button" id="cancel">Cancel editing first name</button>
    </form>
    <button type="button" id="elsewhere">Change password</button>`;
  const el = (id) => document.getElementById(id);
  el("saved").value = saved;
  el("field").value = typed;

  const state = inlineEdit();
  state.$root = el("row");
  state.$nextTick = (callback) => callback();
  state.$refs = {
    field: el("field"),
    saved: el("saved"),
    edit: el("edit"),
    returnFocus: el("return-focus"),
  };
  state.init();

  const sent = vi.fn();
  el("row").addEventListener(SAVE_EVENT, sent);
  return { state, el, sent };
}

/** Open the row and type `text` over its value. */
function edit(state, el, text) {
  state.startEditing();
  el("field").value = text;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("inlineEdit", () => {
  it("starts at rest", () => {
    const { state } = row();

    expect(state.editing).toBe(false);
    expect(state.saving).toBe(false);
  });

  it("starts editing when the server rendered the row with a refused value", () => {
    const { state } = row({ editing: true, typed: "x".repeat(101) });

    expect(state.editing).toBe(true);
  });

  it("opens the field with its text selected, ready to type over", () => {
    const { state, el } = row();

    state.startEditing();

    expect(state.editing).toBe(true);
    expect(document.activeElement).toBe(el("field"));
    expect(el("field").selectionStart).toBe(0);
    expect(el("field").selectionEnd).toBe("Ada".length);
  });

  describe("Escape", () => {
    it("puts the stored value back, closes the field and returns to the pencil", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");

      state.cancel();

      expect(el("field").value).toBe("Ada");
      expect(state.editing).toBe(false);
      expect(document.activeElement).toBe(el("edit"));
      expect(sent).not.toHaveBeenCalled();
    });

    it("puts back the stored value, not the value the server refused", () => {
      const { state, el } = row({ editing: true, typed: "x".repeat(101) });

      state.cancel();

      expect(el("field").value).toBe("Ada");
    });

    it("does nothing at rest", () => {
      const { state, el } = row();
      el("elsewhere").focus();

      state.cancel();

      expect(document.activeElement).toBe(el("elsewhere"));
    });
  });

  describe("the X", () => {
    it("puts the stored name back and sends nothing, with focus on it from the keyboard", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");
      // Tab takes focus from the field past the tick to the X: still inside the row.
      el("cancel").focus();
      state.leave({ relatedTarget: el("cancel") });
      vi.runAllTimers();

      state.cancel();

      expect(sent).not.toHaveBeenCalled();
      expect(el("field").value).toBe("Ada");
      expect(state.editing).toBe(false);
      expect(document.activeElement).toBe(el("edit"));
    });

    it("sends nothing when pressed with a pointer, which leaves focus in the field", () => {
      // The X cancels its mousedown, so the field keeps focus and never blurs.
      const { state, el, sent } = row();
      edit(state, el, "Grace");

      state.cancel();
      vi.runAllTimers();

      expect(sent).not.toHaveBeenCalled();
      expect(el("field").value).toBe("Ada");
      expect(document.activeElement).toBe(el("edit"));
    });
  });

  describe("the tick or Enter", () => {
    it("sends a changed value and asks for the pencil back", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");

      state.save();

      expect(sent).toHaveBeenCalledTimes(1);
      expect(el("return-focus").value).toBe("1");
      expect(state.saving).toBe(true);
      // The row stays open until the server's answer is swapped in for it.
      expect(state.editing).toBe(true);
    });

    it("sends nothing for an unchanged value, and just closes the field", () => {
      const { state, el, sent } = row();
      state.startEditing();

      state.save();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(false);
      expect(document.activeElement).toBe(el("edit"));
    });

    it("counts the stored value as unchanged after a refusal", () => {
      const { state, el, sent } = row({
        editing: true,
        typed: "x".repeat(101),
      });
      el("field").value = "Ada";

      state.save();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(false);
    });

    it("sends once however often it is pressed while the answer is on its way", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");

      state.save();
      state.save();

      expect(sent).toHaveBeenCalledTimes(1);
    });

    it("sends an emptied field: a name may be left blank", () => {
      const { state, el, sent } = row();
      edit(state, el, "");

      state.save();

      expect(sent).toHaveBeenCalledTimes(1);
    });
  });

  describe("leaving the row", () => {
    it("saves without taking focus back from where it went", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");
      el("elsewhere").focus();

      state.leave({ relatedTarget: el("elsewhere") });
      vi.runAllTimers();

      expect(sent).toHaveBeenCalledTimes(1);
      expect(el("return-focus").value).toBe("");
      expect(document.activeElement).toBe(el("elsewhere"));
    });

    it("saves on a click on the page around the row, which takes focus nowhere", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");
      el("field").blur();

      state.leave({ relatedTarget: null });
      vi.runAllTimers();

      expect(sent).toHaveBeenCalledTimes(1);
    });

    it("does not save when focus only moves to the tick", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");
      el("tick").focus();

      state.leave({ relatedTarget: el("tick") });
      vi.runAllTimers();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(true);
    });

    it("does not save when the window loses focus and the field keeps it", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");

      state.leave({ relatedTarget: null });
      vi.runAllTimers();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(true);
    });

    it("closes an unchanged field without sending it or moving focus", () => {
      const { state, el, sent } = row();
      state.startEditing();
      el("elsewhere").focus();

      state.leave({ relatedTarget: el("elsewhere") });
      vi.runAllTimers();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(false);
      expect(document.activeElement).toBe(el("elsewhere"));
    });

    it("is ignored at rest", () => {
      const { state, el, sent } = row();
      el("elsewhere").focus();

      state.leave({ relatedTarget: el("elsewhere") });
      vi.runAllTimers();

      expect(sent).not.toHaveBeenCalled();
      expect(state.editing).toBe(false);
    });
  });

  describe("a save that failed outright", () => {
    it("ignores an answer htmx swapped in", () => {
      const { state, el } = row();
      edit(state, el, "Grace");
      state.save();

      state.requestDone({ detail: { successful: true } });

      expect(state.failed).toBe(false);
    });

    it("keeps what was typed and says so, so it can be sent again", () => {
      const { state, el, sent } = row();
      edit(state, el, "Grace");
      state.save();

      // A network failure reports no outcome at all, a server error a failed one.
      state.requestDone({ detail: {} });

      expect(state.saving).toBe(false);
      expect(state.failed).toBe(true);
      expect(state.editing).toBe(true);
      expect(el("field").value).toBe("Grace");

      state.save();

      expect(sent).toHaveBeenCalledTimes(2);
      expect(state.failed).toBe(false);
    });
  });
});
