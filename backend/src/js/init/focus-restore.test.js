// ABOUTME: Tests for restoring focus from the #focus= hash, and reloading for one that arrives late
// ABOUTME: Covers the same-page #focus= link, which changes only the hash and would not load otherwise

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { reloadOnFocusHash, restoreFocusFromHash } from "./focus-restore.js";

let realLocation;

function stubLocation(href) {
  const url = new URL(href);
  window.location = {
    href: url.href,
    hash: url.hash,
    search: url.search,
    pathname: url.pathname,
    reload: vi.fn(),
  };
}

beforeEach(() => {
  realLocation = window.location;
  delete window.location;
  document.body.innerHTML = "";
});

afterEach(() => {
  window.location = realLocation;
  vi.restoreAllMocks();
});

describe("reloadOnFocusHash", () => {
  it("reloads when a #focus= hash arrives, so a dialog's close link really closes it", () => {
    stubLocation("https://example.org/target-sources#focus=ts-row-1");

    reloadOnFocusHash();

    expect(window.location.reload).toHaveBeenCalled();
  });

  it("leaves any other jump within the page alone", () => {
    stubLocation("https://example.org/target-sources#section-2");

    reloadOnFocusHash();

    expect(window.location.reload).not.toHaveBeenCalled();
  });
});

describe("restoreFocusFromHash", () => {
  it("focuses the element the hash names and strips the hash", () => {
    stubLocation("https://example.org/target-sources#focus=ts-row-1");
    document.body.innerHTML =
      '<button data-focus-id="ts-row-1">Set up</button>';
    const replaceState = vi
      .spyOn(window.history, "replaceState")
      .mockImplementation(() => {});

    restoreFocusFromHash();

    expect(document.activeElement.dataset.focusId).toBe("ts-row-1");
    expect(replaceState).toHaveBeenCalledWith(
      null,
      "",
      "https://example.org/target-sources",
    );
  });
});
