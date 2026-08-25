// ABOUTME: Tests for the API fixture loader, and the guarantee every fixture matches a schema
// ABOUTME: This is the JS half of the drift prevention - the Python half is tests/api_fixtures.py

import { describe, expect, it } from "vitest";

import { fixtureNames, loadApiFixture } from "./api-fixtures.js";

// Every recorded fixture, paired with the schema it must satisfy. A new fixture
// with no entry here fails the completeness test below rather than going unchecked.
const FIXTURE_SCHEMAS = {
  "registration-image-upload": "registration-image",
  "registration-image-alt-update": "registration-image",
  "registration-document-upload": "registration-document",
  "image-upload-error": "error",
  "respondent-field-spec": "respondent-field-spec",
};

describe("every recorded fixture", () => {
  it("is listed here, so none goes unvalidated", () => {
    expect(fixtureNames().sort()).toEqual(Object.keys(FIXTURE_SCHEMAS).sort());
  });

  for (const [name, schemaName] of Object.entries(FIXTURE_SCHEMAS)) {
    it(`validates ${name} against the ${schemaName} schema`, () => {
      expect(() => loadApiFixture(name, schemaName)).not.toThrow();
    });
  }
});

describe("loadApiFixture", () => {
  it("returns the parsed response body", () => {
    const body = loadApiFixture(
      "registration-image-upload",
      "registration-image",
    );
    expect(body.image.alt).toBe("Assembly logo");
    expect(body.image.width).toBeGreaterThan(0);
  });

  it("throws when the fixture does not match the schema it is checked against", () => {
    expect(() =>
      loadApiFixture("registration-image-upload", "error"),
    ).toThrowError(/does not match schema "error"/);
  });

  it("throws for a fixture that was never recorded", () => {
    expect(() => loadApiFixture("no-such-fixture", "error")).toThrow();
  });
});
