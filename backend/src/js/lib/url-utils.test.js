// ABOUTME: Unit tests for the URL query parameter helpers in src/js/lib/url-utils.js
// ABOUTME: Covers relative and absolute URLs, missing parameters and malformed input

import { describe, expect, it } from "vitest";

import {
  urlSetParam,
  urlRemoveParam,
  urlGetParam,
  urlHasParam,
  urlSetParams,
  urlBuild,
} from "./url-utils.js";

describe("urlSetParam", () => {
  it("appends a parameter to a URL that has none", () => {
    expect(urlSetParam("/page", "filter", "active")).toBe(
      "/page?filter=active",
    );
  });

  it("keeps existing parameters when adding a new one", () => {
    expect(urlSetParam("/page?tab=1", "filter", "active")).toBe(
      "/page?tab=1&filter=active",
    );
  });

  it("replaces a parameter that is already present", () => {
    expect(urlSetParam("/page?filter=old", "filter", "new")).toBe(
      "/page?filter=new",
    );
  });

  it("preserves the host on an absolute URL", () => {
    expect(urlSetParam("https://example.org/page", "a", "1")).toBe(
      "https://example.org/page?a=1",
    );
  });

  it("preserves the fragment", () => {
    expect(urlSetParam("/page#section", "a", "1")).toBe("/page?a=1#section");
  });

  it("handles a path with no leading slash", () => {
    expect(urlSetParam("page", "a", "1")).toBe("/page?a=1");
  });

  it("encodes values that need escaping", () => {
    expect(urlSetParam("/page", "q", "a b&c")).toBe("/page?q=a+b%26c");
  });

  it("returns an empty URL unchanged", () => {
    expect(urlSetParam("", "a", "1")).toBe("");
  });
});

describe("urlSetParam on form action URLs", () => {
  // These cases were previously served by a second, divergent urlSetParam in
  // the backoffice bundle. They are the inputs the scroll-preserving form
  // helpers actually pass, so they are pinned here against the one survivor.

  it("adds a scroll parameter to a relative action", () => {
    expect(urlSetParam("/assembly/edit", "scroll", "420")).toBe(
      "/assembly/edit?scroll=420",
    );
  });

  it("adds a scroll parameter to an absolute action", () => {
    expect(
      urlSetParam("https://example.org/assembly/edit?tab=1", "scroll", "420"),
    ).toBe("https://example.org/assembly/edit?tab=1&scroll=420");
  });

  it("returns an empty action unchanged rather than throwing", () => {
    expect(urlSetParam("", "scroll", "420")).toBe("");
  });
});

describe("urlRemoveParam", () => {
  it("removes the named parameter and keeps the others", () => {
    expect(urlRemoveParam("/page?tab=1&filter=active", "filter")).toBe(
      "/page?tab=1",
    );
  });

  it("drops the query string entirely when the last parameter goes", () => {
    expect(urlRemoveParam("/page?filter=active", "filter")).toBe("/page");
  });

  it("leaves the URL alone when the parameter is absent", () => {
    expect(urlRemoveParam("/page?tab=1", "filter")).toBe("/page?tab=1");
  });

  it("returns an empty URL unchanged", () => {
    expect(urlRemoveParam("", "a")).toBe("");
  });
});

describe("urlGetParam", () => {
  it("returns the value of a present parameter", () => {
    expect(urlGetParam("/page?tab=1&filter=active", "filter")).toBe("active");
  });

  it("decodes an encoded value", () => {
    expect(urlGetParam("/page?q=a%20b", "q")).toBe("a b");
  });

  it("returns null when the parameter is absent", () => {
    expect(urlGetParam("/page?tab=1", "filter")).toBeNull();
  });

  it("returns null for an empty URL", () => {
    expect(urlGetParam("", "filter")).toBeNull();
  });
});

describe("urlHasParam", () => {
  it("is true when the parameter is present", () => {
    expect(urlHasParam("/page?filter=active", "filter")).toBe(true);
  });

  it("is true for a parameter present with an empty value", () => {
    expect(urlHasParam("/page?filter=", "filter")).toBe(true);
  });

  it("is false when the parameter is absent", () => {
    expect(urlHasParam("/page?tab=1", "filter")).toBe(false);
  });

  it("is false for an empty URL", () => {
    expect(urlHasParam("", "filter")).toBe(false);
  });
});

describe("urlSetParams", () => {
  it("adds several parameters at once", () => {
    expect(urlSetParams("/page?tab=1", { filter: "active", page: "2" })).toBe(
      "/page?tab=1&filter=active&page=2",
    );
  });

  it("updates parameters that already exist", () => {
    expect(urlSetParams("/page?filter=old", { filter: "new" })).toBe(
      "/page?filter=new",
    );
  });

  it("returns the URL unchanged when given no parameters", () => {
    expect(urlSetParams("/page", null)).toBe("/page");
  });
});

describe("urlBuild", () => {
  it("builds a URL from a base and a parameter object", () => {
    expect(urlBuild("/api/users", { page: "1", sort: "name" })).toBe(
      "/api/users?page=1&sort=name",
    );
  });

  it("returns the base URL when there are no parameters", () => {
    expect(urlBuild("/api/users")).toBe("/api/users");
  });
});
