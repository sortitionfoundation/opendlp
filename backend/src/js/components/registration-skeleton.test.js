// ABOUTME: Tests for the form skeleton preview slice of the registration page controller
// ABOUTME: Covers the fetch, the plain/styled toggle and copying the shown markup

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { registrationSkeleton } from "./registration-skeleton.js";

const OPTIONS = {
  csrfToken: "csrf-123",
  skeletonUrl: "/assembly/1/registration/skeleton",
  messages: {
    skeletonFetchFailed: "An error occurred while fetching the form skeleton",
    copied: "Copied to clipboard",
    copyFailed: "Failed to copy to clipboard",
  },
};

let fetchMock;
let writeText;

/**
 * showToast lives in the toast slice and only exists once the slices are
 * composed, so a slice under test gets a spy in its place.
 */
function skeleton() {
  const state = registrationSkeleton(OPTIONS);
  state.showToast = vi.fn();
  return state;
}

function jsonResponse(body) {
  return { json: () => Promise.resolve(body) };
}

beforeEach(() => {
  fetchMock = vi.fn();
  writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("navigator", { clipboard: { writeText: writeText } });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchSkeleton", () => {
  it("requests the skeleton with the CSRF token", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ html: "<p>", html_govuk: "<p>" }),
    );

    await skeleton().fetchSkeleton();

    expect(fetchMock).toHaveBeenCalledWith(
      "/assembly/1/registration/skeleton",
      {
        method: "GET",
        headers: { "X-CSRFToken": "csrf-123" },
      },
    );
  });

  it("opens the modal on the plain view with both renderings held", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ html: "<input>", html_govuk: "<div class='govuk'>" }),
    );
    const state = skeleton();

    await state.fetchSkeleton();

    expect(state.skeletonModalOpen).toBe(true);
    expect(state.skeletonView).toBe("plain");
    expect(state.skeletonHtmlPlain).toBe("<input>");
    expect(state.skeletonHtmlStyled).toBe("<div class='govuk'>");
    expect(state.skeletonLoading).toBe(false);
  });

  it("shows the server's message and stays closed when it reports a problem", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "No form HTML yet" }));
    const state = skeleton();

    await state.fetchSkeleton();

    expect(state.showToast).toHaveBeenCalledWith("No form HTML yet", "error");
    expect(state.skeletonModalOpen).toBe(false);
    expect(state.skeletonLoading).toBe(false);
  });

  it("reports a request that never got through, and stops loading", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = skeleton();

    await state.fetchSkeleton();

    expect(state.showToast).toHaveBeenCalledWith(
      "An error occurred while fetching the form skeleton",
      "error",
    );
    expect(state.skeletonLoading).toBe(false);
  });

  it("marks itself loading while the request is in flight, so the button disables", () => {
    let resolveFetch;
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const state = skeleton();

    const pending = state.fetchSkeleton();
    expect(state.skeletonLoading).toBe(true);

    resolveFetch(jsonResponse({ html: "", html_govuk: "" }));
    return pending;
  });
});

describe("the plain / GOV.UK styled toggle", () => {
  it("switches to the styled view and back", () => {
    const state = skeleton();

    state.showStyledSkeleton();
    expect(state.skeletonView).toBe("styled");

    state.showPlainSkeleton();
    expect(state.skeletonView).toBe("plain");
  });

  it("closes the modal", () => {
    const state = skeleton();
    state.skeletonModalOpen = true;

    state.closeSkeletonModal();

    expect(state.skeletonModalOpen).toBe(false);
  });
});

describe("copySkeletonToClipboard", () => {
  it("copies whichever rendering is on screen", async () => {
    const state = skeleton();
    state.skeletonHtmlPlain = "<input>";
    state.skeletonHtmlStyled = "<div class='govuk'>";

    await state.copySkeletonToClipboard();
    expect(writeText).toHaveBeenCalledWith("<input>");

    state.showStyledSkeleton();
    await state.copySkeletonToClipboard();
    expect(writeText).toHaveBeenLastCalledWith("<div class='govuk'>");
  });

  it("confirms the copy", async () => {
    const state = skeleton();

    await state.copySkeletonToClipboard();

    expect(state.showToast).toHaveBeenCalledWith(
      "Copied to clipboard",
      "success",
    );
  });

  it("reports a clipboard the browser refused", async () => {
    writeText.mockRejectedValue(new Error("Denied"));
    const state = skeleton();

    await state.copySkeletonToClipboard();

    expect(state.showToast).toHaveBeenCalledWith(
      "Failed to copy to clipboard",
      "error",
    );
  });
});
