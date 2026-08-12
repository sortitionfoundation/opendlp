// ABOUTME: Tests for the PDF document assets slice of the registration page controller
// ABOUTME: Upload, label edit, delete and snippet copy, against recorded API fixtures

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadApiFixture } from "../test-support/api-fixtures.js";
import { ID_SENTINEL } from "../lib/url-utils.js";
import { registrationDocuments } from "./registration-documents.js";

const UPLOADED = loadApiFixture(
  "registration-document-upload",
  "registration-document",
);
const UPLOAD_ERROR = loadApiFixture("image-upload-error", "error");

const MESSAGES = {
  labelRequired: "Label is required",
  uploadFailed: "Upload failed",
  documentUploaded: "Document uploaded",
  documentUploadNetworkError: "Network error while uploading the document",
  confirmDeleteDocument: "Delete this document?",
  deleteDocumentFailed: "Failed to delete document",
  documentDeleted: "Document deleted",
  deleteDocumentNetworkError: "Network error while deleting the document",
  updateDocumentFailed: "Failed to update document",
  documentUpdated: "Document updated",
  updateDocumentNetworkError: "Network error while updating the document",
  noPublicUrl: "No public URL available yet",
  snippetCopied: "Snippet copied to clipboard",
  copyFailed: "Failed to copy to clipboard",
};

let fetchMock;
let writeText;

function documents(seeded) {
  const state = registrationDocuments({
    csrfToken: "csrf-123",
    documents: seeded || [],
    uploadDocumentUrl: "/assembly/1/registration/documents",
    documentItemUrlTemplate: `/assembly/1/registration/documents/${ID_SENTINEL}`,
    messages: MESSAGES,
  });
  state.showToast = vi.fn();
  return state;
}

function jsonResponse(body, ok, status) {
  return { ok: ok, status: status, json: () => Promise.resolve(body) };
}

function fileEvent(name) {
  return { target: { files: name ? [new File(["x"], name)] : [] } };
}

beforeEach(() => {
  fetchMock = vi.fn();
  writeText = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("navigator", { clipboard: { writeText: writeText } });
  vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the upload modal", () => {
  it("opens empty, even after a previous attempt left values behind", () => {
    const state = documents();
    state.documentFileName = "old.pdf";
    state.documentLabel = "old label";
    state.documentUploadError = "old error";

    state.openDocumentUploadModal();

    expect(state.documentUploadModalOpen).toBe(true);
    expect(state.documentFile).toBeNull();
    expect(state.documentFileName).toBe("");
    expect(state.documentLabel).toBe("");
    expect(state.documentUploadError).toBe("");
  });

  it("cannot be dismissed mid-upload, which would strand the request", () => {
    const state = documents();
    state.openDocumentUploadModal();
    state.documentUploading = true;

    state.closeDocumentUploadModalIfAllowed();

    expect(state.documentUploadModalOpen).toBe(true);
  });

  it("shows the chosen file's name and clears any earlier error", () => {
    const state = documents();
    state.documentUploadError = "Upload failed";

    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    expect(state.documentFileName).toBe("info-pack.pdf");
    expect(state.documentFile).not.toBeNull();
    expect(state.documentUploadError).toBe("");
  });
});

describe("submitDocumentUpload", () => {
  it("uploads with no label at all - unlike alt text, a label is optional", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = documents();
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    await state.submitDocumentUpload();

    expect(fetchMock.mock.calls[0][1].body.get("label")).toBe("");
    expect(state.documents).toEqual([UPLOADED.document]);
  });

  it("posts the file and the trimmed label", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = documents();
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));
    state.documentLabel = "  Information pack  ";

    await state.submitDocumentUpload();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/assembly/1/registration/documents");
    expect(init.body.get("label")).toBe("Information pack");
    expect(init.body.get("document").name).toBe("info-pack.pdf");
  });

  it("closes the modal and confirms", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = documents();
    state.openDocumentUploadModal();
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    await state.submitDocumentUpload();

    expect(state.documentUploadModalOpen).toBe(false);
    expect(state.showToast).toHaveBeenCalledWith(
      "Document uploaded",
      "success",
    );
    expect(state.documentUploading).toBe(false);
  });

  it("replaces the existing row when the server recognises the bytes", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 200));
    const state = documents([UPLOADED.document]);
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    await state.submitDocumentUpload();

    expect(state.documents).toEqual([UPLOADED.document]);
  });

  it("shows the server's rejection in the modal, which stays open", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOAD_ERROR, false, 400));
    const state = documents();
    state.openDocumentUploadModal();
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    await state.submitDocumentUpload();

    expect(state.documentUploadError).toBe(UPLOAD_ERROR.error);
    expect(state.documentUploadModalOpen).toBe(true);
    expect(state.documents).toEqual([]);
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = documents();
    state.onDocumentFileSelected(fileEvent("info-pack.pdf"));

    await state.submitDocumentUpload();

    expect(state.documentUploadError).toBe(
      "Network error while uploading the document",
    );
    expect(state.documentUploading).toBe(false);
  });

  it("does nothing when no file has been chosen", async () => {
    const state = documents();

    await state.submitDocumentUpload();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("deleteDocument", () => {
  it("asks first, and does nothing when the organiser says no", async () => {
    globalThis.confirm.mockReturnValue(false);
    const state = documents([UPLOADED.document]);

    await state.deleteDocument(UPLOADED.document);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.documents).toEqual([UPLOADED.document]);
  });

  it("deletes the document by its own URL and drops it from the list", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 200));
    const state = documents([UPLOADED.document]);

    await state.deleteDocument(UPLOADED.document);

    expect(fetchMock.mock.calls[0][0]).toBe(
      `/assembly/1/registration/documents/${UPLOADED.document.id}`,
    );
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(state.documents).toEqual([]);
    expect(state.showToast).toHaveBeenCalledWith("Document deleted", "success");
    expect(state.documentBeingDeletedId).toBe("");
  });

  it("keeps the document when the server refuses, and says why", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: "Still in use" }, false, 409),
    );
    const state = documents([UPLOADED.document]);

    await state.deleteDocument(UPLOADED.document);

    expect(state.documents).toEqual([UPLOADED.document]);
    expect(state.showToast).toHaveBeenCalledWith("Still in use", "error");
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = documents([UPLOADED.document]);

    await state.deleteDocument(UPLOADED.document);

    expect(state.showToast).toHaveBeenCalledWith(
      "Network error while deleting the document",
      "error",
    );
  });
});

describe("the details modal", () => {
  it("opens on the document, seeded with its current label", () => {
    const state = documents([UPLOADED.document]);

    state.openDocumentDetailsModal(UPLOADED.document);

    expect(state.documentDetailsModalOpen).toBe(true);
    expect(state.editingDocument).toBe(UPLOADED.document);
    expect(state.editingDocumentLabel).toBe(UPLOADED.document.label);
  });

  it("forgets the document when dismissed", () => {
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);

    state.closeDocumentDetailsModalIfAllowed();

    expect(state.documentDetailsModalOpen).toBe(false);
    expect(state.editingDocument).toBeNull();
    expect(state.editingDocumentLabel).toBe("");
  });

  it("cannot be dismissed while the edit is saving", () => {
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);
    state.documentEditing = true;

    state.closeDocumentDetailsModalIfAllowed();

    expect(state.documentDetailsModalOpen).toBe(true);
  });
});

describe("submitDocumentEdit", () => {
  it("refuses a blank label - once there is a details form, the label is required", async () => {
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);
    state.editingDocumentLabel = "   ";

    await state.submitDocumentEdit();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.documentEditError).toBe("Label is required");
  });

  it("patches the trimmed label to the document's own URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 200));
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);
    state.editingDocumentLabel = "  Information pack  ";

    await state.submitDocumentEdit();

    expect(fetchMock).toHaveBeenCalledWith(
      `/assembly/1/registration/documents/${UPLOADED.document.id}`,
      expect.objectContaining({
        method: "PATCH",
        body: '{"label":"Information pack"}',
      }),
    );
  });

  it("replaces the row in place and closes the modal", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 200));
    const state = documents([{ ...UPLOADED.document, label: "Old" }]);
    state.openDocumentDetailsModal(state.documents[0]);
    state.editingDocumentLabel = "Information pack";

    await state.submitDocumentEdit();

    expect(state.documents).toEqual([UPLOADED.document]);
    expect(state.documentDetailsModalOpen).toBe(false);
    expect(state.editingDocument).toBeNull();
    expect(state.showToast).toHaveBeenCalledWith("Document updated", "success");
  });

  it("shows the server's rejection in the modal, which stays open", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOAD_ERROR, false, 400));
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);
    state.editingDocumentLabel = "Something";

    await state.submitDocumentEdit();

    expect(state.documentEditError).toBe(UPLOAD_ERROR.error);
    expect(state.documentDetailsModalOpen).toBe(true);
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);
    state.editingDocumentLabel = "Something";

    await state.submitDocumentEdit();

    expect(state.documentEditError).toBe(
      "Network error while updating the document",
    );
    expect(state.documentEditing).toBe(false);
  });
});

describe("deleteEditingDocument", () => {
  it("deletes without a second confirmation - the modal is the confirmation", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 200));
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);

    await state.deleteEditingDocument();

    expect(globalThis.confirm).not.toHaveBeenCalled();
    expect(state.documents).toEqual([]);
    expect(state.documentDetailsModalOpen).toBe(false);
    expect(state.editingDocument).toBeNull();
  });

  it("leaves the modal open when the server refuses", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: "Still in use" }, false, 409),
    );
    const state = documents([UPLOADED.document]);
    state.openDocumentDetailsModal(UPLOADED.document);

    await state.deleteEditingDocument();

    expect(state.documentDetailsModalOpen).toBe(true);
    expect(state.documents).toEqual([UPLOADED.document]);
  });

  it("does nothing when no document is being edited", async () => {
    const state = documents([UPLOADED.document]);

    await state.deleteEditingDocument();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("copyDocumentSnippet", () => {
  it("copies the anchor snippet the server built", async () => {
    const state = documents([UPLOADED.document]);

    await state.copyDocumentSnippet(UPLOADED.document);

    expect(writeText).toHaveBeenCalledWith(UPLOADED.document.a_snippet);
    expect(state.showToast).toHaveBeenCalledWith(
      "Snippet copied to clipboard",
      "success",
    );
  });

  it("says so when the page has no slug yet, so there is no public URL", async () => {
    const state = documents();
    const unpublished = { ...UPLOADED.document, a_snippet: "" };

    await state.copyDocumentSnippet(unpublished);

    expect(writeText).not.toHaveBeenCalled();
    expect(state.showToast).toHaveBeenCalledWith(
      "No public URL available yet",
      "error",
    );
  });

  it("reports a clipboard the browser refused", async () => {
    writeText.mockRejectedValue(new Error("Denied"));
    const state = documents([UPLOADED.document]);

    await state.copyDocumentSnippet(UPLOADED.document);

    expect(state.showToast).toHaveBeenCalledWith(
      "Failed to copy to clipboard",
      "error",
    );
  });
});
