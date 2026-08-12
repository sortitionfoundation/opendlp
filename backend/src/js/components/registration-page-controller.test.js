// ABOUTME: Tests for the composition of the registration page controller
// ABOUTME: That every slice is present, wired to its config, and survives a missing one

import { describe, expect, it } from "vitest";

import { ID_SENTINEL } from "../lib/url-utils.js";
import { registrationPageController } from "./registration-page-controller.js";

const CONFIG = {
  editMode: true,
  csrfToken: "csrf-123",
  images: [{ id: "image-1", alt: "A logo" }],
  documents: [{ id: "doc-1", label: "Information pack" }],
  urls: {
    skeleton: "/assembly/1/registration/skeleton",
    uploadImage: "/assembly/1/registration/images",
    imageItem: `/assembly/1/registration/images/${ID_SENTINEL}`,
    uploadDocument: "/assembly/1/registration/documents",
    documentItem: `/assembly/1/registration/documents/${ID_SENTINEL}`,
  },
  messages: { copied: "Copied to clipboard" },
};

// Every name the template's Alpine expressions reach for. The page loses the
// binding silently if one goes missing, so they are listed rather than sampled.
const TEMPLATE_API = [
  "allowLeave",
  "cancelConfirmClose",
  "closeDocumentDetailsModalIfAllowed",
  "closeDocumentUploadModalIfAllowed",
  "closeImageDetailsModalIfAllowed",
  "closeImageUploadModalIfAllowed",
  "closeLeaveModal",
  "closeSkeletonModal",
  "copyDocumentSnippet",
  "copyImageSnippet",
  "copySkeletonToClipboard",
  "copyToClipboard",
  "deleteDocument",
  "deleteEditingDocument",
  "deleteEditingImage",
  "deleteImage",
  "discardAndLeave",
  "fetchSkeleton",
  "formatBytes",
  "guardLeave",
  "init",
  "markEditDirty",
  "onDocumentFileSelected",
  "onImageFileSelected",
  "openConfirmClose",
  "openDocumentDetailsModal",
  "openDocumentUploadModal",
  "openImageDetailsModal",
  "openImageUploadModal",
  "showPlainSkeleton",
  "showStyledSkeleton",
  "showToast",
  "submitDocumentEdit",
  "submitDocumentUpload",
  "submitImageEdit",
  "submitImageUpload",
];

describe("the composed controller", () => {
  it("exposes every method the template binds to", () => {
    const state = registrationPageController(CONFIG);

    const missing = TEMPLATE_API.filter(
      (name) => typeof state[name] !== "function",
    );
    expect(missing).toEqual([]);
  });

  it("seeds the asset lists from the server-side render", () => {
    const state = registrationPageController(CONFIG);

    expect(state.images).toEqual(CONFIG.images);
    expect(state.documents).toEqual(CONFIG.documents);
  });

  it("carries the edit mode through to the guard", () => {
    expect(registrationPageController(CONFIG).editMode).toBe(true);
    expect(
      registrationPageController({ ...CONFIG, editMode: false }).editMode,
    ).toBe(false);
  });

  it("builds per-item URLs from the templates the server rendered", () => {
    const state = registrationPageController(CONFIG);

    expect(state.imageItemUrl("image-1")).toBe(
      "/assembly/1/registration/images/image-1",
    );
    expect(state.documentItemUrl("doc-1")).toBe(
      "/assembly/1/registration/documents/doc-1",
    );
  });

  it("formats a byte count for the details panels", () => {
    expect(registrationPageController(CONFIG).formatBytes(2048)).toBe("2.0 KB");
  });

  it("gives the asset slices the toast they call, once composed", () => {
    const state = registrationPageController(CONFIG);

    state.showToast("Image uploaded", "success");

    expect(state.toastVisible).toBe(true);
    expect(state.toastMessage).toBe("Image uploaded");
  });
});

describe("a controller built with no configuration at all", () => {
  // readJsonScript yields {} when the data block is missing or malformed. The
  // page is degraded at that point, but it must not throw during x-data
  // evaluation, which would take Alpine down for the whole tree.
  it("is still constructible", () => {
    expect(() => registrationPageController({})).not.toThrow();
  });

  it("has empty asset lists rather than undefined ones", () => {
    const state = registrationPageController({});

    expect(state.images).toEqual([]);
    expect(state.documents).toEqual([]);
  });

  it("is not in edit mode, so the unload guard stays out of the way", () => {
    expect(registrationPageController({}).editMode).toBe(false);
  });
});
