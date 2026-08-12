// ABOUTME: Unit tests for the autocomplete Alpine component
// ABOUTME: Covers debouncing, the minimum-character gate, keyboard navigation and aria wiring

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { autocomplete } from "./autocomplete.js";

function jsonResponse(data) {
  return { ok: true, json: () => Promise.resolve(data) };
}

function makeComponent(overrides = {}) {
  return autocomplete({ fetchUrl: "/api/search", ...overrides });
}

describe("autocomplete initial state", () => {
  it("starts empty and closed", () => {
    const state = makeComponent();
    expect(state.query).toBe("");
    expect(state.results).toEqual([]);
    expect(state.isOpen).toBe(false);
    expect(state.highlightedIndex).toBe(-1);
  });
});

describe("autocomplete activeDescendantId", () => {
  it("is empty when nothing is highlighted", () => {
    const state = makeComponent({ inputId: "user_search" });
    state.results = [{ id: 1, label: "Ada" }];
    expect(state.activeDescendantId).toBe("");
  });

  it("names the highlighted option", () => {
    const state = makeComponent({ inputId: "user_search" });
    state.results = [{ id: 1, label: "Ada" }];
    state.highlightedIndex = 0;
    expect(state.activeDescendantId).toBe("user_search_option_0");
  });

  it("is empty when the highlight is past the end of the results", () => {
    const state = makeComponent({ inputId: "user_search" });
    state.results = [{ id: 1, label: "Ada" }];
    state.highlightedIndex = 5;
    expect(state.activeDescendantId).toBe("");
  });
});

describe("autocomplete onInput", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("does not search below the minimum character count", () => {
    const state = makeComponent({ minChars: 3 });
    state.query = "ad";
    state.onInput();
    vi.runAllTimers();
    expect(fetch).not.toHaveBeenCalled();
    expect(state.isOpen).toBe(false);
  });

  it("waits for the debounce delay before fetching", () => {
    fetch.mockResolvedValue(jsonResponse([]));
    const state = makeComponent({ debounceMs: 300 });
    state.query = "ada";
    state.onInput();

    vi.advanceTimersByTime(299);
    expect(fetch).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("fetches once for a burst of keystrokes", () => {
    fetch.mockResolvedValue(jsonResponse([]));
    const state = makeComponent({ debounceMs: 300 });

    state.query = "a";
    state.onInput();
    state.query = "ad";
    state.onInput();
    state.query = "ada";
    state.onInput();
    vi.runAllTimers();

    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe("/api/search?q=ada");
  });

  it("clears any earlier selection as soon as the user types", () => {
    const state = makeComponent({ minChars: 3 });
    state.selectedId = "42";
    state.selectedLabel = "Ada";
    state.query = "a";
    state.onInput();
    expect(state.selectedId).toBe("");
    expect(state.selectedLabel).toBe("");
  });

  it("uses the configured parameter name and encodes the query", () => {
    fetch.mockResolvedValue(jsonResponse([]));
    const state = makeComponent({ paramName: "term" });
    state.query = "a b&c";
    state.onInput();
    vi.runAllTimers();
    expect(fetch.mock.calls[0][0]).toBe("/api/search?term=a%20b%26c");
  });
});

describe("autocomplete fetchResults", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the listbox and announces a plural result count", async () => {
    fetch.mockResolvedValue(
      jsonResponse([
        { id: 1, label: "Ada" },
        { id: 2, label: "Grace" },
      ]),
    );
    const state = makeComponent();
    state.query = "a";
    await state.fetchResults();

    expect(state.isOpen).toBe(true);
    expect(state.isLoading).toBe(false);
    expect(state.statusMessage).toBe("2 results available");
  });

  it("announces a single result in the singular", async () => {
    fetch.mockResolvedValue(jsonResponse([{ id: 1, label: "Ada" }]));
    const state = makeComponent();
    await state.fetchResults();
    expect(state.statusMessage).toBe("1 result available");
  });

  it("stays closed and says so when there are no results", async () => {
    fetch.mockResolvedValue(jsonResponse([]));
    const state = makeComponent();
    await state.fetchResults();
    expect(state.isOpen).toBe(false);
    expect(state.statusMessage).toBe("No results found");
  });

  it("closes and clears results when the request fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fetch.mockResolvedValue({ ok: false });
    const state = makeComponent();
    state.results = [{ id: 1, label: "Ada" }];
    state.isOpen = true;

    await state.fetchResults();

    expect(state.results).toEqual([]);
    expect(state.isOpen).toBe(false);
    expect(state.isLoading).toBe(false);
    vi.restoreAllMocks();
  });
});

describe("autocomplete selectItem", () => {
  it("records the selection and closes the listbox", () => {
    const state = makeComponent();
    state.results = [{ id: 7, label: "Ada" }];
    state.isOpen = true;

    state.selectItem({ id: 7, label: "Ada" });

    expect(state.selectedId).toBe(7);
    expect(state.selectedLabel).toBe("Ada");
    expect(state.query).toBe("Ada");
    expect(state.isOpen).toBe(false);
    expect(state.results).toEqual([]);
    expect(state.highlightedIndex).toBe(-1);
  });

  it("appends the sublabel to the visible query text", () => {
    const state = makeComponent();
    state.selectItem({ id: 7, label: "Ada", sublabel: "ada@example.org" });
    expect(state.query).toBe("Ada - ada@example.org");
  });
});

describe("autocomplete onKeydown", () => {
  function openComponent() {
    const state = makeComponent();
    state.results = [
      { id: 1, label: "Ada" },
      { id: 2, label: "Grace" },
    ];
    state.isOpen = true;
    return state;
  }

  function keyEvent(key) {
    return { key, preventDefault: vi.fn() };
  }

  it("ignores keys while the listbox is closed", () => {
    const state = makeComponent();
    const event = keyEvent("ArrowDown");
    state.onKeydown(event);
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(state.highlightedIndex).toBe(-1);
  });

  it("moves the highlight down", () => {
    const state = openComponent();
    state.onKeydown(keyEvent("ArrowDown"));
    expect(state.highlightedIndex).toBe(0);
    state.onKeydown(keyEvent("ArrowDown"));
    expect(state.highlightedIndex).toBe(1);
  });

  it("stops at the last result rather than wrapping", () => {
    const state = openComponent();
    state.highlightedIndex = 1;
    state.onKeydown(keyEvent("ArrowDown"));
    expect(state.highlightedIndex).toBe(1);
  });

  it("moves the highlight up but not past the first result", () => {
    const state = openComponent();
    state.highlightedIndex = 1;
    state.onKeydown(keyEvent("ArrowUp"));
    expect(state.highlightedIndex).toBe(0);
    state.onKeydown(keyEvent("ArrowUp"));
    expect(state.highlightedIndex).toBe(0);
  });

  it("selects the highlighted result on Enter", () => {
    const state = openComponent();
    state.highlightedIndex = 1;
    state.onKeydown(keyEvent("Enter"));
    expect(state.selectedId).toBe(2);
    expect(state.isOpen).toBe(false);
  });

  it("selects nothing on Enter when no result is highlighted", () => {
    const state = openComponent();
    state.onKeydown(keyEvent("Enter"));
    expect(state.selectedId).toBe("");
    expect(state.isOpen).toBe(true);
  });

  it("closes on Escape", () => {
    const state = openComponent();
    state.highlightedIndex = 1;
    state.onKeydown(keyEvent("Escape"));
    expect(state.isOpen).toBe(false);
    expect(state.highlightedIndex).toBe(-1);
  });
});

describe("autocomplete close", () => {
  it("closes and drops the highlight but keeps the results", () => {
    const state = makeComponent();
    state.results = [{ id: 1, label: "Ada" }];
    state.isOpen = true;
    state.highlightedIndex = 0;

    state.close();

    expect(state.isOpen).toBe(false);
    expect(state.highlightedIndex).toBe(-1);
    expect(state.results).toHaveLength(1);
  });
});
