// ABOUTME: Tests for the CSRF-carrying JSON request helpers
// ABOUTME: Covers the headers sent, the parsed result shape, and unparsable bodies

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { deleteResource, patchJson, postFormData } from "./json-request.js";

function jsonResponse(body, ok, status) {
  return {
    ok: ok,
    status: status,
    json: function () {
      return Promise.resolve(body);
    },
  };
}

function unparsableResponse(ok, status) {
  return {
    ok: ok,
    status: status,
    json: function () {
      return Promise.reject(new SyntaxError("Unexpected token <"));
    },
  };
}

let fetchMock;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("postFormData", () => {
  it("posts the body with the CSRF token and no content type", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ image: { id: "a" } }, true, 201),
    );
    const body = new FormData();
    body.append("alt", "A logo");

    await postFormData("/upload", body, "csrf-123");

    expect(fetchMock).toHaveBeenCalledWith("/upload", {
      method: "POST",
      headers: { "X-CSRFToken": "csrf-123" },
      body: body,
    });
  });

  it("resolves with the parsed body and whether the request succeeded", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ image: { id: "a" } }, true, 201),
    );

    const result = await postFormData("/upload", new FormData(), "csrf-123");

    expect(result).toEqual({
      ok: true,
      status: 201,
      data: { image: { id: "a" } },
    });
  });

  it("still reports the failure when an error body is unparsable", async () => {
    fetchMock.mockResolvedValue(unparsableResponse(false, 500));

    const result = await postFormData("/upload", new FormData(), "csrf-123");

    expect(result).toEqual({ ok: false, status: 500, data: {} });
  });

  it("rejects when the network call itself fails, so callers can say so", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      postFormData("/upload", new FormData(), "csrf-123"),
    ).rejects.toThrow("Failed to fetch");
  });
});

describe("patchJson", () => {
  it("sends the payload as JSON with the CSRF token", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ image: { id: "a" } }, true, 200),
    );

    await patchJson("/images/a", { alt: "New alt" }, "csrf-123");

    expect(fetchMock).toHaveBeenCalledWith("/images/a", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": "csrf-123",
      },
      body: '{"alt":"New alt"}',
    });
  });

  it("resolves with the parsed body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "Nope" }, false, 400));

    const result = await patchJson("/images/a", { alt: "x" }, "csrf-123");

    expect(result).toEqual({ ok: false, status: 400, data: { error: "Nope" } });
  });
});

describe("deleteResource", () => {
  it("sends the CSRF token and no body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 200));

    await deleteResource("/images/a", "csrf-123");

    expect(fetchMock).toHaveBeenCalledWith("/images/a", {
      method: "DELETE",
      headers: { "X-CSRFToken": "csrf-123" },
    });
  });

  it("treats an empty response body as success rather than an error", async () => {
    fetchMock.mockResolvedValue(unparsableResponse(true, 204));

    const result = await deleteResource("/images/a", "csrf-123");

    expect(result).toEqual({ ok: true, status: 204, data: {} });
  });
});
