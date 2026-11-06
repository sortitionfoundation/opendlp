// ABOUTME: Tests for the questions list's drag-to-reorder rows.
// ABOUTME: Sortable.js is replaced with a stand-in, so these check the wiring, not the dragging.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const created = [];
vi.mock("sortablejs", () => ({
  default: {
    create: vi.fn((element, options) => {
      const instance = { element, options, destroy: vi.fn() };
      created.push(instance);
      return instance;
    }),
  },
}));

const { REORDER_FORM_ID, sortableRows } = await import("./sortable-rows.js");

function mount() {
  document.body.innerHTML = `
    <form id="${REORDER_FORM_ID}"></form>
    <table><tbody id="rows"><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>`;
  const component = sortableRows();
  component.$el = document.getElementById("rows");
  component.init();
  return component;
}

beforeEach(() => {
  created.length = 0;
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("sortableRows", () => {
  it("makes the rows draggable by their handles only", () => {
    mount();

    expect(created).toHaveLength(1);
    expect(created[0].element.id).toBe("rows");
    expect(created[0].options.handle).toBe("[data-drag-handle]");
  });

  it("submits the reorder form when a row lands somewhere new", () => {
    mount();
    const form = document.getElementById(REORDER_FORM_ID);
    form.requestSubmit = vi.fn();

    created[0].options.onEnd({ oldIndex: 0, newIndex: 1 });

    expect(form.requestSubmit).toHaveBeenCalledOnce();
  });

  it("leaves the form alone when a row is dropped where it was", () => {
    mount();
    const form = document.getElementById(REORDER_FORM_ID);
    form.requestSubmit = vi.fn();

    created[0].options.onEnd({ oldIndex: 1, newIndex: 1 });

    expect(form.requestSubmit).not.toHaveBeenCalled();
  });

  it("lets go of Sortable when the list is redrawn", () => {
    const component = mount();

    component.destroy();

    expect(created[0].destroy).toHaveBeenCalledOnce();
  });
});
