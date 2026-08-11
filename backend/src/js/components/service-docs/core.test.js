// ABOUTME: Tests for the shared machinery of the service docs console
// ABOUTME: Covers executing a service, the loading flag, response panels and the clipboard

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { serviceDocsCore } from "./core.js";

const RESPONSE_KEYS = {
  create_assembly: "create_assembly",
  import_respondents_from_csv: "import_respondents",
  add_registration_image: "add_image",
};

let fetchMock;
let writeText;

function core() {
  return serviceDocsCore({
    executeUrl: "/backoffice/dev/service-docs/execute",
    csrfToken: "csrf-123",
    responseKeys: RESPONSE_KEYS,
  });
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

describe("the loading and response panels", () => {
  it("has one of each per service the server said it can run", () => {
    const state = core();

    expect(Object.keys(state.loading).sort()).toEqual([
      "add_image",
      "create_assembly",
      "import_respondents",
    ]);
    expect(Object.keys(state.responses).sort()).toEqual([
      "add_image",
      "create_assembly",
      "import_respondents",
    ]);
  });

  it("starts idle and empty", () => {
    const state = core();

    expect(state.loading.create_assembly).toBe(false);
    expect(state.responses.create_assembly).toBeNull();
  });

  it("has none at all when the server sent no keys, rather than throwing", () => {
    const state = serviceDocsCore({ executeUrl: "/x", csrfToken: "y" });

    expect(state.loading).toEqual({});
  });
});

describe("executeService", () => {
  it("posts the service name and params as JSON with the CSRF token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "success" }));

    await core().executeService("create_assembly", { title: "An assembly" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backoffice/dev/service-docs/execute",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": "csrf-123",
        },
        body: '{"service":"create_assembly","params":{"title":"An assembly"}}',
      },
    );
  });

  it("puts the result in that service's panel", async () => {
    const body = { status: "success", result: { id: "abc" } };
    fetchMock.mockResolvedValue(jsonResponse(body));
    const state = core();

    await state.executeService("create_assembly", {});

    expect(state.responses.create_assembly).toEqual(body);
    expect(state.loading.create_assembly).toBe(false);
  });

  it("uses the short response key, not the service name", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "success" }));
    const state = core();

    await state.executeService("import_respondents_from_csv", {});

    expect(state.responses.import_respondents).not.toBeNull();
  });

  it("marks the service loading while the request is in flight", () => {
    let resolveFetch;
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const state = core();

    const pending = state.executeService("create_assembly", {});
    expect(state.loading.create_assembly).toBe(true);

    resolveFetch(jsonResponse({ status: "success" }));
    return pending;
  });

  it("clears a previous result before running again, so a stale panel is never shown", () => {
    let resolveFetch;
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    const state = core();
    state.responses.create_assembly = { status: "success", result: "old" };

    const pending = state.executeService("create_assembly", {});
    expect(state.responses.create_assembly).toBeNull();

    resolveFetch(jsonResponse({ status: "success" }));
    return pending;
  });

  it("confirms only a success - a failure is already visible in its panel", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "error", error: "No" }));
    const state = core();

    await state.executeService("create_assembly", {});

    expect(state.toast.show).toBe(false);
    expect(state.responses.create_assembly.error).toBe("No");
  });

  it("shows a request that never got through as a NetworkError in the panel", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = core();

    await state.executeService("create_assembly", {});

    expect(state.responses.create_assembly).toEqual({
      status: "error",
      error: "Failed to fetch",
      error_type: "NetworkError",
    });
    expect(state.loading.create_assembly).toBe(false);
  });

  it("says so rather than throwing when asked for a service the server does not have", async () => {
    const state = core();

    await state.executeService("no_such_service", {});

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.toast.message).toContain("no_such_service");
  });
});

describe("formatResponse", () => {
  it("pretty-prints the response, which x-text cannot do itself", () => {
    const state = core();
    state.responses.create_assembly = { status: "success" };

    expect(state.formatResponse("create_assembly")).toBe(
      '{\n  "status": "success"\n}',
    );
  });

  it("is empty for a service that has not been run", () => {
    expect(core().formatResponse("create_assembly")).toBe("");
  });

  it("says what went wrong rather than blanking the panel on a circular response", () => {
    const state = core();
    const circular = { status: "success" };
    circular.self = circular;
    state.responses.create_assembly = circular;

    expect(state.formatResponse("create_assembly")).toContain(
      "Error formatting",
    );
  });
});

describe("the clipboard", () => {
  it("copies arbitrary text and confirms", async () => {
    const state = core();

    await state.copyToClipboard("respondent_service.py:63");

    expect(writeText).toHaveBeenCalledWith("respondent_service.py:63");
    expect(state.toast.message).toBe("Copied to clipboard!");
  });

  it("copies a response panel as pretty JSON", async () => {
    const state = core();
    state.responses.add_image = { status: "success" };

    await state.copyResponse("add_image");

    expect(writeText).toHaveBeenCalledWith('{\n  "status": "success"\n}');
  });

  it("reports a clipboard the browser refused", async () => {
    writeText.mockRejectedValue(new Error("Denied"));
    const state = core();

    await state.copyToClipboard("anything");

    expect(state.toast.message).toBe("Failed to copy");
    expect(state.toast.type).toBe("error");
  });
});
