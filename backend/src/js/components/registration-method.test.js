// ABOUTME: Unit tests for the registrationMethod Alpine component
// ABOUTME: Covers the initial method, its validation, and the method selectors

import { describe, expect, it } from "vitest";

import { registrationMethod } from "./registration-method.js";

describe("registrationMethod", () => {
  it("starts on the given method", () => {
    expect(registrationMethod("google").method).toBe("google");
    expect(registrationMethod("microsoft").method).toBe("microsoft");
    expect(registrationMethod("email").method).toBe("email");
  });

  it("defaults to email when the initial method is missing or unknown", () => {
    expect(registrationMethod("").method).toBe("email");
    expect(registrationMethod(undefined).method).toBe("email");
    expect(registrationMethod("facebook").method).toBe("email");
  });

  it("switches method through the selectors", () => {
    var state = registrationMethod("email");

    state.selectGoogle();
    expect(state.method).toBe("google");

    state.selectMicrosoft();
    expect(state.method).toBe("microsoft");

    state.selectEmail();
    expect(state.method).toBe("email");
  });
});
