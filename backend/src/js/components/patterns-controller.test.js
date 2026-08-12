// ABOUTME: Unit tests for the patterns page controller - toast lifecycle and clipboard copying
// ABOUTME: Also pins that every copy method reaches a non-empty snippet, since a typo is silent

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { patternsController } from "./patterns-controller.js";

// Every copy method, paired with the state property it should place on the clipboard.
// A copy method wired to the wrong (or a misspelled) property would otherwise copy
// undefined with no visible failure - the toast still says "Copied to clipboard!".
const COPY_METHODS = {
  copyUrlSelectCode: "urlSelectCode",
  copyInlineSelectCode: "inlineSelectCode",
  copyFileUploadTemplateCode: "fileUploadTemplateCode",
  copyFileUploadRouteCode: "fileUploadRouteCode",
  copyProgressBarCode: "progressBarCode",
  copyPaginationTemplateCode: "paginationTemplateCode",
  copyPaginationRouteCode: "paginationRouteCode",
  copyScrollPreserveCode: "scrollPreserveCode",
  copyPreserveScrollCode: "preserveScrollCode",
  copyScrollDirectiveCode: "scrollDirectiveCode",
  copyNavigateScrollCode: "navigateScrollCode",
};

function stubClipboard(writeText) {
  vi.stubGlobal("navigator", { clipboard: { writeText } });
}

describe("patternsController initial state", () => {
  it("starts with the toast hidden", () => {
    expect(patternsController().toast).toEqual({
      show: false,
      message: "",
      type: "info",
    });
  });

  it("starts with no demo assembly selected", () => {
    expect(patternsController().demoAssemblyId).toBe("");
  });
});

describe("patternsController snippets", () => {
  for (const property of Object.values(COPY_METHODS)) {
    it(`exposes a non-empty ${property}`, () => {
      const state = patternsController();
      expect(typeof state[property]).toBe("string");
      expect(state[property].length).toBeGreaterThan(0);
    });
  }

  it("keeps Jinja delimiters intact, since the samples are Jinja templates", () => {
    const state = patternsController();
    expect(state.fileUploadTemplateCode).toContain(
      '{% from "backoffice/components/input.html" import file_input %}',
    );
    expect(state.paginationTemplateCode).toContain("{{ pagination(");
  });
});

describe("patternsController copying", () => {
  let writeText;

  beforeEach(() => {
    vi.useFakeTimers();
    writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  for (const [method, property] of Object.entries(COPY_METHODS)) {
    it(`${method} copies ${property} and nothing else`, async () => {
      const state = patternsController();
      await state[method]();
      expect(writeText).toHaveBeenCalledWith(state[property]);
    });
  }

  it("shows a success toast after a successful copy", async () => {
    const state = patternsController();
    await state.copyUrlSelectCode();
    expect(state.toast).toEqual({
      show: true,
      message: "Copied to clipboard!",
      type: "success",
    });
  });

  it("shows an error toast when the clipboard write is rejected", async () => {
    writeText.mockRejectedValue(new Error("denied"));
    const state = patternsController();
    await state.copyUrlSelectCode();
    expect(state.toast).toEqual({
      show: true,
      message: "Failed to copy",
      type: "error",
    });
  });

  it("hides the toast again after three seconds", async () => {
    const state = patternsController();
    await state.copyUrlSelectCode();

    vi.advanceTimersByTime(2999);
    expect(state.toast.show).toBe(true);

    vi.advanceTimersByTime(1);
    expect(state.toast.show).toBe(false);
  });
});

describe("patternsController showToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("replaces an earlier message rather than queueing", () => {
    const state = patternsController();
    state.showToast("First", "info");
    state.showToast("Second", "success");
    expect(state.toast).toEqual({
      show: true,
      message: "Second",
      type: "success",
    });
  });
});
