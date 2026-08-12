// ABOUTME: Tests for reading a server-rendered application/json configuration block
// ABOUTME: Covers the missing-block and malformed-JSON cases the page has to survive

import { afterEach, describe, expect, it, vi } from "vitest";

import { readJsonScript } from "./json-script.js";

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

function addBlock(id, contents) {
  const script = document.createElement("script");
  script.type = "application/json";
  script.id = id;
  script.textContent = contents;
  document.body.appendChild(script);
}

describe("readJsonScript", () => {
  it("parses the contents of the block with the given id", () => {
    addBlock("page-data", '{"editMode": true, "images": [{"id": "a"}]}');

    expect(readJsonScript("page-data")).toEqual({
      editMode: true,
      images: [{ id: "a" }],
    });
  });

  it("returns an empty object when there is no such block", () => {
    expect(readJsonScript("absent")).toEqual({});
  });

  it("returns an empty object when the block is not valid JSON", () => {
    vi.spyOn(console, "error").mockImplementation(function () {});
    addBlock("page-data", "{not json");

    expect(readJsonScript("page-data")).toEqual({});
  });

  it("says which block failed to parse, so the page is debuggable", () => {
    const logged = vi
      .spyOn(console, "error")
      .mockImplementation(function () {});
    addBlock("page-data", "{not json");

    readJsonScript("page-data");

    expect(logged.mock.calls[0][0]).toContain("page-data");
  });
});
