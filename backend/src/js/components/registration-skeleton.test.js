// ABOUTME: Tests for the skeleton preview slice of the registration page controller
// ABOUTME: Covers the form fetch, the plain/styled toggle and writing the shown markup into the form

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadApiFixture } from "../test-support/api-fixtures.js";
import { SET_VALUE_EVENT } from "../lib/code-editor-events.js";
import { registrationSkeleton } from "./registration-skeleton.js";

const OPTIONS = {
  csrfToken: "csrf-123",
  skeletonUrl: "/assembly/1/registration/skeleton",
  messages: {
    skeletonFetchFailed: "An error occurred while fetching the form skeleton",
  },
};

let fetchMock;

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
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const SKELETON = loadApiFixture(
  "registration-skeleton",
  "registration-skeleton",
);

describe("fetchFormSkeleton", () => {
  it("requests the skeleton with the CSRF token", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SKELETON));

    await skeleton().fetchFormSkeleton();

    expect(fetchMock).toHaveBeenCalledWith(
      "/assembly/1/registration/skeleton",
      {
        method: "GET",
        headers: { "X-CSRFToken": "csrf-123" },
      },
    );
  });

  it("opens the modal on the accessible view with both form renderings held", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SKELETON));
    const state = skeleton();

    await state.fetchFormSkeleton();

    expect(state.skeletonModalOpen).toBe(true);
    expect(state.skeletonView).toBe("styled");
    expect(state.skeletonHtmlPlain).toBe(SKELETON.html);
    expect(state.skeletonHtmlStyled).toBe(SKELETON.html_govuk);
    expect(state.skeletonLoading).toBe(false);
  });

  it("shows the server's message and stays closed when it reports a problem", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "No form HTML yet" }));
    const state = skeleton();

    await state.fetchFormSkeleton();

    expect(state.showToast).toHaveBeenCalledWith("No form HTML yet", "error");
    expect(state.skeletonModalOpen).toBe(false);
    expect(state.skeletonLoading).toBe(false);
  });

  it("reports a request that never got through, and stops loading", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = skeleton();

    await state.fetchFormSkeleton();

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

    const pending = state.fetchFormSkeleton();
    expect(state.skeletonLoading).toBe(true);

    resolveFetch(jsonResponse(SKELETON));
    return pending;
  });
});

describe("the plain / GOV.UK styled toggle", () => {
  it("starts on the styled view and switches to plain and back", () => {
    const state = skeleton();
    expect(state.skeletonView).toBe("styled");

    state.showPlainSkeleton();
    expect(state.skeletonView).toBe("plain");

    state.showStyledSkeleton();
    expect(state.skeletonView).toBe("styled");
  });

  it("closes the modal", () => {
    const state = skeleton();
    state.skeletonModalOpen = true;

    state.closeSkeletonModal();

    expect(state.skeletonModalOpen).toBe(false);
  });
});

describe("useSkeletonAsForm", () => {
  let textarea;

  beforeEach(() => {
    document.body.innerHTML = '<textarea id="html_content"></textarea>';
    textarea = document.getElementById("html_content");
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  /** A skeleton slice holding both renderings, with the modal open. */
  function openSkeleton() {
    const state = skeleton();
    state.markEditDirty = vi.fn();
    state.$nextTick = (callback) => callback();
    state.$refs = {};
    state.skeletonHtmlPlain = "<input>";
    state.skeletonHtmlStyled = "<div class='govuk'>";
    state.skeletonModalOpen = true;
    return state;
  }

  it("writes the shown rendering into an empty form and closes the modal", () => {
    const state = openSkeleton();

    state.useSkeletonAsForm();

    expect(textarea.value).toBe("<div class='govuk'>");
    expect(state.skeletonModalOpen).toBe(false);
    expect(state.skeletonReplaceConfirmOpen).toBe(false);
    expect(state.markEditDirty).toHaveBeenCalled();
  });

  it("writes the plain rendering when that is on screen", () => {
    const state = openSkeleton();
    state.showPlainSkeleton();

    state.useSkeletonAsForm();

    expect(textarea.value).toBe("<input>");
  });

  it("asks the editor over the textarea to show the new content", () => {
    const state = openSkeleton();
    const listener = vi.fn();
    textarea.addEventListener(SET_VALUE_EVENT, listener);

    state.useSkeletonAsForm();

    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].detail).toEqual({
      value: "<div class='govuk'>",
    });
  });

  it("asks first when the form already has HTML, with only the question open", () => {
    textarea.value = "<p>mine</p>";
    const state = openSkeleton();
    const keepFormBtn = { focus: vi.fn() };
    state.$refs = { keepFormBtn: keepFormBtn };

    state.useSkeletonAsForm();

    expect(textarea.value).toBe("<p>mine</p>");
    expect(state.skeletonReplaceConfirmOpen).toBe(true);
    expect(state.skeletonModalOpen).toBe(false);
    expect(keepFormBtn.focus).toHaveBeenCalled();
    expect(state.markEditDirty).not.toHaveBeenCalled();
  });

  it("treats a form of only whitespace as empty", () => {
    textarea.value = "  \n ";
    const state = openSkeleton();

    state.useSkeletonAsForm();

    expect(state.skeletonReplaceConfirmOpen).toBe(false);
    expect(textarea.value).toBe("<div class='govuk'>");
  });

  it("replaces the form once the question is confirmed", () => {
    textarea.value = "<p>mine</p>";
    const state = openSkeleton();
    state.useSkeletonAsForm();

    state.confirmReplaceFormWithSkeleton();

    expect(textarea.value).toBe("<div class='govuk'>");
    expect(state.skeletonReplaceConfirmOpen).toBe(false);
    expect(state.skeletonModalOpen).toBe(false);
    expect(state.markEditDirty).toHaveBeenCalled();
  });

  it("goes back to the skeleton, form untouched, when the question is cancelled", () => {
    textarea.value = "<p>mine</p>";
    const state = openSkeleton();
    state.useSkeletonAsForm();

    state.cancelReplaceFormWithSkeleton();

    expect(textarea.value).toBe("<p>mine</p>");
    expect(state.skeletonReplaceConfirmOpen).toBe(false);
    expect(state.skeletonModalOpen).toBe(true);
  });
});
