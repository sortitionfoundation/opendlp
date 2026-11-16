// ABOUTME: Unit tests for the passwordRules Alpine component on the sign-up page
// ABOUTME: Which rules tick for which passwords, the pause before the server is asked, and what its answer changes

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { postJson } from "../lib/json-request.js";
import { loadApiFixture } from "../test-support/api-fixtures.js";
import { CHECK_DELAY_MS, passwordRules } from "./password-rules.js";

vi.mock("../lib/json-request.js", () => ({ postJson: vi.fn() }));

// The cases test_security.py runs through the server's validators.
const BROWSER_CHECKS = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../tests/fixtures/password_browser_checks.json",
    ),
    "utf8",
  ),
);

// A recorded answer. Of the two rules the server decides, "not-common" is met
// and "not-similar" is not.
const ANSWER = loadApiFixture("password-check", "password-check");
// A recorded refusal, in the error envelope every JSON route shares.
const REFUSAL = loadApiFixture("image-upload-error", "error");

const SERVER_RULES = ["not-common", "not-similar"];

/**
 * The sign-up form as the page renders it, around a passwordRules component.
 *
 * @param {Object} options - the length range, and whether the page lists the
 *   rules only the server can check
 * @returns {Object} the component, and ways to type and to read a rule
 */
function signUpPage({
  minLength = 10,
  maxLength = 256,
  serverRules = true,
} = {}) {
  const form = document.createElement("form");
  form.innerHTML = `
    <div data-check-url="/auth/password-check" data-csrf-token="csrf-123">
      <input name="email" type="email">
      <input name="password" type="password">
      <ul>
        <li data-password-rule="length" data-live-check="browser"
            data-min-length="${minLength}" data-max-length="${maxLength}"><span></span></li>
        <li data-password-rule="not-numbers-only" data-live-check="browser"><span></span></li>
        ${SERVER_RULES.map(
          (key) =>
            `<li data-password-rule="${key}" data-live-check="server"><span></span></li>`,
        ).join("")}
      </ul>
      <input name="password_confirm" type="password">
      <input name="first_name">
      <input name="last_name">
    </div>`;
  if (!serverRules) {
    form
      .querySelectorAll('[data-live-check="server"]')
      .forEach((rule) => rule.remove());
  }
  document.body.appendChild(form);

  const component = passwordRules();
  component.$el = form.firstElementChild;
  return {
    component,
    form,
    type(name, value) {
      const field = form.elements.namedItem(name);
      field.value = value;
      component.changed({ target: field });
    },
    met(key) {
      const inside = form.querySelector(`[data-password-rule="${key}"] span`);
      return component.met(inside);
    },
  };
}

// Lets every promise that is already settled run its handlers.
function settle() {
  return new Promise((done) => setImmediate(done));
}

function deferred() {
  let answer;
  const promise = new Promise((done) => {
    answer = done;
  });
  return { promise, answer };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  postJson.mockReset();
  postJson.mockResolvedValue({ ok: true, status: 200, data: ANSWER });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("passwordRules with nothing typed", () => {
  it("meets no rule and asks the server nothing", async () => {
    const page = signUpPage();
    page.component.init();

    for (const key of ["length", "not-numbers-only", ...SERVER_RULES]) {
      expect(page.met(key)).toBe(false);
    }
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    expect(postJson).not.toHaveBeenCalled();
  });

  it("never ticks an element outside a rule", () => {
    const page = signUpPage();
    page.component.init();
    page.type("password", "Kx7#mQ2vLp");

    expect(page.component.met(page.form.querySelector("input"))).toBe(false);
  });
});

describe("passwordRules on the rules the browser checks", () => {
  it("ticks them at once, without waiting for the server", () => {
    const page = signUpPage();
    page.component.init();

    page.type("password", "Kx7#mQ2vLp");

    expect(page.met("length")).toBe(true);
    expect(page.met("not-numbers-only")).toBe(true);
    expect(postJson).not.toHaveBeenCalled();
  });

  it("ticks the length only within the range the page gives", () => {
    const page = signUpPage({ minLength: 4, maxLength: 6 });
    page.component.init();

    const ticks = ["abc", "abcd", "abcdef", "abcdefg"].map((password) => {
      page.type("password", password);
      return page.met("length");
    });

    expect(ticks).toEqual([false, true, true, false]);
  });

  it("never ticks the length without its numbers", () => {
    const page = signUpPage();
    const length = page.form.querySelector('[data-password-rule="length"]');
    length.removeAttribute("data-min-length");
    length.removeAttribute("data-max-length");
    page.component.init();

    page.type("password", "Kx7#mQ2vLp");

    expect(page.met("length")).toBe(false);
  });

  it("ticks not numbers only once anything but a digit is typed", () => {
    const page = signUpPage();
    page.component.init();

    page.type("password", "4719305826");
    expect(page.met("not-numbers-only")).toBe(false);
    page.type("password", "4719305826!");
    expect(page.met("not-numbers-only")).toBe(true);
  });

  it("leaves a number that is not a digit unticked, the safe side of the server", () => {
    // Python's isdigit() is false for "½", so the server would accept it;
    // the browser counts it as a number and leaves the rule unticked.
    const page = signUpPage();
    page.component.init();

    page.type("password", "½½½½½½½½½½");

    expect(page.met("not-numbers-only")).toBe(false);
  });

  it("never ticks a rule it does not know", () => {
    const page = signUpPage();
    page.form
      .querySelector('[data-password-rule="not-numbers-only"]')
      .setAttribute("data-password-rule", "not-a-palindrome");
    page.component.init();

    page.type("password", "Kx7#mQ2vLp");

    expect(page.met("not-a-palindrome")).toBe(false);
  });

  it.each(BROWSER_CHECKS.cases)(
    "agrees with the server's validators on $why",
    ({ typed, rules }) => {
      const page = signUpPage({
        minLength: BROWSER_CHECKS.min_length,
        maxLength: BROWSER_CHECKS.max_length,
      });
      page.component.init();

      page.type("password", typed);

      expect({
        length: page.met("length"),
        "not-numbers-only": page.met("not-numbers-only"),
      }).toEqual(rules);
    },
  );
});

describe("passwordRules on the rules the server checks", () => {
  it("asks once typing has paused", async () => {
    const page = signUpPage();
    page.component.init();

    page.type("password", "a");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS - 1);
    expect(postJson).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(postJson).toHaveBeenCalledTimes(1);
  });

  it("waits again while typing goes on, then asks about the latest password", async () => {
    const page = signUpPage();
    page.component.init();

    page.type("password", "ann");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS - 100);
    page.type("password", "ann.smith");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS - 100);
    expect(postJson).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(100);
    expect(postJson).toHaveBeenCalledTimes(1);
    expect(postJson.mock.calls[0][1].password).toBe("ann.smith");
  });

  it("sends the password with the email and names, to the page's URL with its token", async () => {
    const page = signUpPage();
    page.component.init();

    page.type("email", "ann.smith@example.org");
    page.type("first_name", "Ann");
    page.type("last_name", "Smith");
    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);

    expect(postJson).toHaveBeenCalledWith(
      "/auth/password-check",
      {
        password: "ann.smith.example", // pragma: allowlist secret
        email: "ann.smith@example.org",
        first_name: "Ann",
        last_name: "Smith",
      },
      "csrf-123",
    );
  });

  it("ticks them by the server's answer", async () => {
    const page = signUpPage();
    page.component.init();

    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    expect(page.met("not-common")).toBe(true);
    expect(page.met("not-similar")).toBe(false);
  });

  it("leaves them unticked while the answer is awaited", async () => {
    const reply = deferred();
    postJson.mockReturnValue(reply.promise);
    const page = signUpPage();
    page.component.init();

    page.type("password", "ann.smith.example");
    expect(page.met("not-common")).toBe(false);
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();
    expect(postJson).toHaveBeenCalledTimes(1);
    expect(page.met("not-common")).toBe(false);

    reply.answer({ ok: true, status: 200, data: ANSWER });
    await settle();
    expect(page.met("not-common")).toBe(true);
  });

  it("unticks them as soon as the password changes again", async () => {
    const page = signUpPage();
    page.component.init();
    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();
    expect(page.met("not-common")).toBe(true);

    page.type("password", "ann.smith.example1");

    expect(page.met("not-common")).toBe(false);
  });

  it("drops an answer about a password that has changed since it was asked", async () => {
    const reply = deferred();
    postJson.mockReturnValueOnce(reply.promise);
    const page = signUpPage();
    page.component.init();
    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);

    page.type("password", "password123");
    reply.answer({ ok: true, status: 200, data: ANSWER });
    await settle();

    expect(page.met("not-common")).toBe(false);
  });

  it("leaves them unticked when the server refuses to answer", async () => {
    postJson.mockResolvedValue({ ok: false, status: 429, data: REFUSAL });
    const page = signUpPage();
    page.component.init();

    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    expect(SERVER_RULES.map(page.met)).toEqual([false, false]);
  });

  it("leaves them unticked when the request fails", async () => {
    postJson.mockRejectedValue(new TypeError("Failed to fetch"));
    const page = signUpPage();
    page.component.init();

    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    expect(SERVER_RULES.map(page.met)).toEqual([false, false]);
  });

  it("asks again when the email or a name changes", async () => {
    const page = signUpPage();
    page.component.init();
    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    for (const name of ["email", "first_name", "last_name"]) {
      page.type(name, "ann");
      expect(page.met("not-common")).toBe(false);
      await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
      await settle();
    }

    expect(postJson).toHaveBeenCalledTimes(4);
    expect(postJson.mock.calls[3][1]).toMatchObject({
      email: "ann",
      first_name: "ann",
      last_name: "ann",
    });
  });

  it("does not ask when the password confirmation changes", async () => {
    const page = signUpPage();
    page.component.init();
    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    page.type("password_confirm", "ann.smith.example!");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);

    expect(postJson).toHaveBeenCalledTimes(1);
    expect(page.met("not-common")).toBe(true);
  });

  it("does not ask while the password is empty, whatever else changes", async () => {
    const page = signUpPage();
    page.component.init();

    page.type("email", "ann.smith@example.org");
    page.type("first_name", "Ann");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);

    expect(postJson).not.toHaveBeenCalled();
  });

  it("does not ask when the page lists no rule for the server", async () => {
    const page = signUpPage({ serverRules: false });
    page.component.init();

    page.type("password", "ann.smith.example");
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);

    expect(postJson).not.toHaveBeenCalled();
  });

  it("asks about a password that is already in the field when it starts", async () => {
    const page = signUpPage();
    page.form.elements.namedItem("password").value = "ann.smith.example";

    page.component.init();
    expect(page.met("length")).toBe(true);
    await vi.advanceTimersByTimeAsync(CHECK_DELAY_MS);
    await settle();

    expect(postJson).toHaveBeenCalledTimes(1);
    expect(page.met("not-common")).toBe(true);
  });
});
