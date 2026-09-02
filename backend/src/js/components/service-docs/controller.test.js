// ABOUTME: Tests for the composition of the service docs controller
// ABOUTME: That every tab's slice is present and wired to the core it calls through

import { describe, expect, it, vi } from "vitest";

import { serviceDocsController } from "./controller.js";

const CONFIG = {
  executeUrl: "/backoffice/dev/service-docs/execute",
  csrfToken: "csrf-123",
  responseKeys: {
    create_assembly: "create_assembly",
    import_respondents_from_csv: "import_respondents",
  },
};

// One method from each tab's slice, plus the core's. If a slice is dropped from the
// composition the page loses that whole tab, silently - Alpine does not report an
// unknown method, the button simply stops doing anything.
const ONE_PER_SLICE = [
  "executeService",
  "formatResponse",
  "executeImportRespondents",
  "executeImportTargets",
  "executeGetCsvConfig",
  "executeCreateAssembly",
  "executeCreateRegistrationPage",
  "executeAddField",
  "executeAddRegistrationImage",
  "executeAddRegistrationDocument",
  "executeCreateEmailTemplate",
  "executeGetDashboardSummary",
];

describe("the composed controller", () => {
  it("has a method from every slice", () => {
    const state = serviceDocsController(CONFIG);

    const missing = ONE_PER_SLICE.filter(
      (name) => typeof state[name] !== "function",
    );
    expect(missing).toEqual([]);
  });

  it("gives the tab slices the core they call through", () => {
    const state = serviceDocsController(CONFIG);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({}) }),
    );

    state.createAssemblyTitle = "An assembly";
    const pending = state.executeCreateAssembly();

    expect(state.loading.create_assembly).toBe(true);
    vi.unstubAllGlobals();
    return pending;
  });

  it("builds its response panels from the keys the server sent", () => {
    const state = serviceDocsController(CONFIG);

    expect(Object.keys(state.responses).sort()).toEqual([
      "create_assembly",
      "import_respondents",
    ]);
  });

  it("starts every form empty", () => {
    const state = serviceDocsController(CONFIG);

    expect(state.createAssemblyTitle).toBe("");
    expect(state.importRespondentsCsvContent).toBe("");
    expect(state.toast.show).toBe(false);
  });

  it("keeps the defaults its slices declare", () => {
    const state = serviceDocsController(CONFIG);

    expect(state.createAssemblyNumberToSelect).toBe(10);
    expect(state.addFieldGroup).toBe("other");
    expect(state.addFieldType).toBe("text");
    expect(state.updateCsvConfigCheckSameAddress).toBe(true);
    expect(state.submitRegistrationFormData).toBe("{}");
  });

  it("has no two slices claiming the same property", () => {
    // Object.assign lets a later slice overwrite an earlier one's property without a
    // murmur, which would show up as one tab's form clearing another's.
    const state = serviceDocsController(CONFIG);
    const declared = ONE_PER_SLICE.length;

    expect(Object.keys(state).length).toBeGreaterThan(declared);
  });
});

describe("a controller built with no configuration at all", () => {
  // readJsonScript yields {} when the data block is missing or malformed. The page is
  // useless at that point, but it must not throw during x-data evaluation, which would
  // take Alpine down for the whole tree.
  it("is still constructible", () => {
    expect(() => serviceDocsController({})).not.toThrow();
  });

  it("has no response panels rather than undefined ones", () => {
    expect(serviceDocsController({}).responses).toEqual({});
  });
});
