// ABOUTME: Unit tests for the rowActionsMenu Alpine component
// ABOUTME: Covers the menu button keyboard pattern and the Escape handling that must not reach an enclosing dialog

import { afterEach, describe, expect, it, vi } from "vitest";

import { initDialogEscape } from "../init/dialog-escape.js";
import { rowActionsMenu } from "./row-actions-menu.js";

/**
 * Build a component over real DOM, wired the way the templates wire it.
 * $nextTick runs at once: jsdom has no x-show to wait for.
 */
function buildMenu(itemCount = 3) {
  const items = Array.from(
    { length: itemCount },
    (_unused, index) =>
      `<button type="button" role="menuitem" tabindex="-1" id="item-${index}">Item ${index}</button>`,
  ).join("");
  document.body.innerHTML = `
    <button type="button" id="before">Before</button>
    <div id="wrapper">
      <button type="button" id="toggle">More</button>
      <div role="menu" id="menu">${items}</div>
    </div>
    <button type="button" id="after">After</button>`;
  const state = rowActionsMenu();
  state.$el = document.getElementById("wrapper");
  state.$refs = {
    menuToggle: document.getElementById("toggle"),
    menu: document.getElementById("menu"),
  };
  state.$nextTick = (callback) => callback();
  return state;
}

function key(name) {
  return { key: name, preventDefault: vi.fn(), stopPropagation: vi.fn() };
}

function focused() {
  return document.activeElement.id;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("rowActionsMenu", () => {
  it("starts closed and toggles open and shut", () => {
    const state = buildMenu();
    expect(state.open).toBe(false);

    state.toggleMenu();
    expect(state.open).toBe(true);

    state.toggleMenu();
    expect(state.open).toBe(false);
  });

  it("closes on demand", () => {
    const state = buildMenu();
    state.open = true;

    state.closeMenu();

    expect(state.open).toBe(false);
  });

  it("moves focus to the first item when it opens", () => {
    const state = buildMenu();

    state.toggleMenu();

    expect(focused()).toBe("item-0");
  });

  it("opens on the first item with ArrowDown on the kebab", () => {
    const state = buildMenu();
    const event = key("ArrowDown");

    state.onToggleKeydown(event);

    expect(state.open).toBe(true);
    expect(focused()).toBe("item-0");
    expect(event.preventDefault).toHaveBeenCalled();
  });

  it("opens on the last item with ArrowUp on the kebab", () => {
    const state = buildMenu();

    state.onToggleKeydown(key("ArrowUp"));

    expect(state.open).toBe(true);
    expect(focused()).toBe("item-2");
  });

  it("leaves other keys on the kebab alone", () => {
    const state = buildMenu();
    const event = key("a");

    state.onToggleKeydown(event);

    expect(state.open).toBe(false);
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("moves between items with the arrow keys, wrapping at both ends", () => {
    const state = buildMenu();
    state.toggleMenu();

    state.onMenuKeydown(key("ArrowDown"));
    expect(focused()).toBe("item-1");

    state.onMenuKeydown(key("ArrowDown"));
    state.onMenuKeydown(key("ArrowDown"));
    expect(focused()).toBe("item-0");

    state.onMenuKeydown(key("ArrowUp"));
    expect(focused()).toBe("item-2");
  });

  it("jumps to the ends with Home and End", () => {
    const state = buildMenu();
    state.toggleMenu();

    state.onMenuKeydown(key("End"));
    expect(focused()).toBe("item-2");

    state.onMenuKeydown(key("Home"));
    expect(focused()).toBe("item-0");
  });

  it("skips a disabled item", () => {
    const state = buildMenu();
    document.getElementById("item-1").disabled = true;
    state.toggleMenu();

    state.onMenuKeydown(key("ArrowDown"));

    expect(focused()).toBe("item-2");
  });

  it("copes with a menu of one", () => {
    const state = buildMenu(1);
    state.toggleMenu();

    state.onMenuKeydown(key("ArrowUp"));
    expect(focused()).toBe("item-0");

    state.onMenuKeydown(key("ArrowDown"));
    expect(focused()).toBe("item-0");
  });

  it("closes when focus tabs out of the menu", () => {
    const state = buildMenu();
    state.toggleMenu();

    state.closeOnFocusOut({ relatedTarget: document.getElementById("after") });

    expect(state.open).toBe(false);
  });

  it("stays open while focus moves within the menu", () => {
    const state = buildMenu();
    state.toggleMenu();

    state.closeOnFocusOut({ relatedTarget: document.getElementById("item-1") });

    expect(state.open).toBe(true);
  });

  it("stays open when focus goes nowhere, leaving a click to decide", () => {
    const state = buildMenu();
    state.toggleMenu();

    state.closeOnFocusOut({ relatedTarget: null });

    expect(state.open).toBe(true);
  });

  it("stops Escape at the open menu and hands focus back to the kebab", () => {
    const state = buildMenu();
    state.toggleMenu();
    const event = key("Escape");

    state.closeOnEscape(event);

    expect(state.open).toBe(false);
    expect(event.stopPropagation).toHaveBeenCalled();
    expect(focused()).toBe("toggle");
  });

  it("lets Escape through when the menu is already shut", () => {
    const state = buildMenu();
    const event = key("Escape");

    state.closeOnEscape(event);

    expect(event.stopPropagation).not.toHaveBeenCalled();
    expect(focused()).not.toBe("toggle");
  });
});

describe("rowActionsMenu inside a fragment dialog", () => {
  function pressEscapeOn(element) {
    element.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        bubbles: true,
        cancelable: true,
      }),
    );
  }

  it("closes the menu on the first Escape and the dialog only on the second", () => {
    initDialogEscape();
    const state = buildMenu();
    const backdrop = document.createElement("a");
    backdrop.className = "dialog-backdrop--clickable";
    backdrop.href = "#close";
    const dialogClosed = vi.fn();
    backdrop.addEventListener("click", (event) => {
      event.preventDefault();
      dialogClosed();
    });
    document.body.prepend(backdrop);
    state.$el.addEventListener("keydown", (event) => {
      if (event.key === "Escape") state.closeOnEscape(event);
    });
    state.toggleMenu();

    pressEscapeOn(document.activeElement);

    expect(state.open).toBe(false);
    expect(dialogClosed).not.toHaveBeenCalled();

    pressEscapeOn(document.activeElement);

    expect(dialogClosed).toHaveBeenCalledOnce();
  });
});
