// ABOUTME: Tests for the image assets slice of the registration page controller
// ABOUTME: Upload, alt-text edit, delete and snippet copy, against recorded API fixtures

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadApiFixture } from "../test-support/api-fixtures.js";
import { ID_SENTINEL } from "../lib/url-utils.js";
import { registrationImages } from "./registration-images.js";

const UPLOADED = loadApiFixture(
  "registration-image-upload",
  "registration-image",
);
const RENAMED = loadApiFixture(
  "registration-image-alt-update",
  "registration-image",
);
const UPLOAD_ERROR = loadApiFixture("image-upload-error", "error");

const MESSAGES = {
  altRequired: "Alt text is required for accessibility",
  uploadFailed: "Upload failed",
  imageUploaded: "Image uploaded",
  imageUploadNetworkError: "Network error while uploading the image",
  confirmDeleteImage: "Delete this image?",
  deleteImageFailed: "Failed to delete image",
  imageDeleted: "Image deleted",
  deleteImageNetworkError: "Network error while deleting the image",
  updateImageFailed: "Failed to update image",
  imageUpdated: "Image updated",
  updateImageNetworkError: "Network error while updating the image",
  noPublicUrl: "No public URL available yet",
  snippetCopied: "Snippet copied to clipboard",
  copyFailed: "Failed to copy to clipboard",
};

let fetchMock;
let writeText;

function images(seeded) {
  const state = registrationImages({
    csrfToken: "csrf-123",
    images: seeded || [],
    uploadImageUrl: "/assembly/1/registration/images",
    imageItemUrlTemplate: `/assembly/1/registration/images/${ID_SENTINEL}`,
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
    const state = images();
    state.imageFileName = "old.png";
    state.imageAlt = "old alt";
    state.imageUploadError = "old error";

    state.openImageUploadModal();

    expect(state.imageUploadModalOpen).toBe(true);
    expect(state.imageFile).toBeNull();
    expect(state.imageFileName).toBe("");
    expect(state.imageAlt).toBe("");
    expect(state.imageUploadError).toBe("");
  });

  it("cannot be dismissed mid-upload, which would strand the request", () => {
    const state = images();
    state.openImageUploadModal();
    state.imageUploading = true;

    state.closeImageUploadModalIfAllowed();

    expect(state.imageUploadModalOpen).toBe(true);
  });

  it("shows the chosen file's name and clears any earlier error", () => {
    const state = images();
    state.imageUploadError = "Upload failed";

    state.onImageFileSelected(fileEvent("logo.png"));

    expect(state.imageFileName).toBe("logo.png");
    expect(state.imageFile).not.toBeNull();
    expect(state.imageUploadError).toBe("");
  });

  it("clears the file when the picker is dismissed with nothing chosen", () => {
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));

    state.onImageFileSelected(fileEvent(null));

    expect(state.imageFile).toBeNull();
    expect(state.imageFileName).toBe("");
  });
});

describe("submitImageUpload", () => {
  it("refuses blank alt text without troubling the server", async () => {
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "   ";

    await state.submitImageUpload();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.imageUploadError).toBe(
      "Alt text is required for accessibility",
    );
  });

  it("posts the file and the trimmed alt text", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "  Assembly logo  ";

    await state.submitImageUpload();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/assembly/1/registration/images");
    expect(init.body.get("alt")).toBe("Assembly logo");
    expect(init.body.get("image").name).toBe("logo.png");
  });

  it("adds the new image to the list and closes the modal", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo";

    await state.submitImageUpload();

    expect(state.images).toEqual([UPLOADED.image]);
    expect(state.imageUploadModalOpen).toBe(false);
    expect(state.showToast).toHaveBeenCalledWith("Image uploaded", "success");
    expect(state.imageUploading).toBe(false);
  });

  it("replaces the existing row when the server recognises the bytes", async () => {
    fetchMock.mockResolvedValue(jsonResponse(RENAMED, true, 200));
    const state = images([UPLOADED.image]);
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo, renamed";

    await state.submitImageUpload();

    expect(state.images).toEqual([RENAMED.image]);
  });

  it("shows the server's rejection in the modal, which stays open", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOAD_ERROR, false, 400));
    const state = images();
    state.openImageUploadModal();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo";

    await state.submitImageUpload();

    expect(state.imageUploadError).toBe(UPLOAD_ERROR.error);
    expect(state.imageUploadModalOpen).toBe(true);
    expect(state.images).toEqual([]);
  });

  it("falls back to its own wording when the server sends none", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, false, 500));
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo";

    await state.submitImageUpload();

    expect(state.imageUploadError).toBe("Upload failed");
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo";

    await state.submitImageUpload();

    expect(state.imageUploadError).toBe(
      "Network error while uploading the image",
    );
    expect(state.imageUploading).toBe(false);
  });

  it("ignores a second click while the first upload is in flight", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOADED, true, 201));
    const state = images();
    state.onImageFileSelected(fileEvent("logo.png"));
    state.imageAlt = "Assembly logo";
    state.imageUploading = true;

    await state.submitImageUpload();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("deleteImage", () => {
  it("asks first, and does nothing when the organiser says no", async () => {
    globalThis.confirm.mockReturnValue(false);
    const state = images([UPLOADED.image]);

    await state.deleteImage(UPLOADED.image);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.images).toEqual([UPLOADED.image]);
  });

  it("names the image it is about to delete in the confirmation", async () => {
    globalThis.confirm.mockReturnValue(false);
    const state = images([UPLOADED.image]);

    await state.deleteImage(UPLOADED.image);

    expect(globalThis.confirm.mock.calls[0][0]).toContain(
      UPLOADED.image.display_name,
    );
  });

  it("deletes the image by its own URL and drops it from the list", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 200));
    const state = images([UPLOADED.image]);

    await state.deleteImage(UPLOADED.image);

    expect(fetchMock.mock.calls[0][0]).toBe(
      `/assembly/1/registration/images/${UPLOADED.image.id}`,
    );
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(state.images).toEqual([]);
    expect(state.showToast).toHaveBeenCalledWith("Image deleted", "success");
    expect(state.imageBeingDeletedId).toBe("");
  });

  it("keeps the image when the server refuses, and says why", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: "Still in use" }, false, 409),
    );
    const state = images([UPLOADED.image]);

    await state.deleteImage(UPLOADED.image);

    expect(state.images).toEqual([UPLOADED.image]);
    expect(state.showToast).toHaveBeenCalledWith("Still in use", "error");
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = images([UPLOADED.image]);

    await state.deleteImage(UPLOADED.image);

    expect(state.showToast).toHaveBeenCalledWith(
      "Network error while deleting the image",
      "error",
    );
    expect(state.imageBeingDeletedId).toBe("");
  });

  it("ignores a second click while a delete is in flight", async () => {
    const state = images([UPLOADED.image]);
    state.imageBeingDeletedId = UPLOADED.image.id;

    await state.deleteImage(UPLOADED.image);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("the details modal", () => {
  it("opens on the image, seeded with its current alt text", () => {
    const state = images([UPLOADED.image]);

    state.openImageDetailsModal(UPLOADED.image);

    expect(state.imageDetailsModalOpen).toBe(true);
    expect(state.editingImage).toBe(UPLOADED.image);
    expect(state.editingImageAlt).toBe(UPLOADED.image.alt);
  });

  it("forgets the image when dismissed", () => {
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);

    state.closeImageDetailsModalIfAllowed();

    expect(state.imageDetailsModalOpen).toBe(false);
    expect(state.editingImage).toBeNull();
    expect(state.editingImageAlt).toBe("");
  });

  it("cannot be dismissed while the edit is saving", () => {
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.imageEditing = true;

    state.closeImageDetailsModalIfAllowed();

    expect(state.imageDetailsModalOpen).toBe(true);
  });
});

describe("submitImageEdit", () => {
  it("refuses blank alt text without troubling the server", async () => {
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.editingImageAlt = "   ";

    await state.submitImageEdit();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(state.imageEditError).toBe("Alt text is required for accessibility");
  });

  it("patches the trimmed alt text to the image's own URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse(RENAMED, true, 200));
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.editingImageAlt = "  Assembly logo, renamed  ";

    await state.submitImageEdit();

    expect(fetchMock).toHaveBeenCalledWith(
      `/assembly/1/registration/images/${UPLOADED.image.id}`,
      expect.objectContaining({
        method: "PATCH",
        body: '{"alt":"Assembly logo, renamed"}',
      }),
    );
  });

  it("replaces the row in place and closes the modal", async () => {
    fetchMock.mockResolvedValue(jsonResponse(RENAMED, true, 200));
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.editingImageAlt = "Assembly logo, renamed";

    await state.submitImageEdit();

    expect(state.images).toEqual([RENAMED.image]);
    expect(state.imageDetailsModalOpen).toBe(false);
    expect(state.editingImage).toBeNull();
    expect(state.showToast).toHaveBeenCalledWith("Image updated", "success");
  });

  it("shows the server's rejection in the modal, which stays open", async () => {
    fetchMock.mockResolvedValue(jsonResponse(UPLOAD_ERROR, false, 400));
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.editingImageAlt = "Something";

    await state.submitImageEdit();

    expect(state.imageEditError).toBe(UPLOAD_ERROR.error);
    expect(state.imageDetailsModalOpen).toBe(true);
    expect(state.images).toEqual([UPLOADED.image]);
  });

  it("reports a request that never got through", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);
    state.editingImageAlt = "Something";

    await state.submitImageEdit();

    expect(state.imageEditError).toBe("Network error while updating the image");
    expect(state.imageEditing).toBe(false);
  });
});

describe("deleteEditingImage", () => {
  it("deletes without a second confirmation - the modal is the confirmation", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, true, 200));
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);

    await state.deleteEditingImage();

    expect(globalThis.confirm).not.toHaveBeenCalled();
    expect(state.images).toEqual([]);
    expect(state.imageDetailsModalOpen).toBe(false);
    expect(state.editingImage).toBeNull();
  });

  it("leaves the modal open when the server refuses", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: "Still in use" }, false, 409),
    );
    const state = images([UPLOADED.image]);
    state.openImageDetailsModal(UPLOADED.image);

    await state.deleteEditingImage();

    expect(state.imageDetailsModalOpen).toBe(true);
    expect(state.images).toEqual([UPLOADED.image]);
    expect(state.showToast).toHaveBeenCalledWith("Still in use", "error");
  });

  it("does nothing when no image is being edited", async () => {
    const state = images([UPLOADED.image]);

    await state.deleteEditingImage();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("copyImageSnippet", () => {
  it("copies the img snippet the server built", async () => {
    const state = images([UPLOADED.image]);

    await state.copyImageSnippet(UPLOADED.image);

    expect(writeText).toHaveBeenCalledWith(UPLOADED.image.img_snippet);
    expect(state.showToast).toHaveBeenCalledWith(
      "Snippet copied to clipboard",
      "success",
    );
  });

  it("says so when the page has no slug yet, so there is no public URL", async () => {
    const state = images();
    const unpublished = { ...UPLOADED.image, img_snippet: "" };

    await state.copyImageSnippet(unpublished);

    expect(writeText).not.toHaveBeenCalled();
    expect(state.showToast).toHaveBeenCalledWith(
      "No public URL available yet",
      "error",
    );
  });

  it("reports a clipboard the browser refused", async () => {
    writeText.mockRejectedValue(new Error("Denied"));
    const state = images([UPLOADED.image]);

    await state.copyImageSnippet(UPLOADED.image);

    expect(state.showToast).toHaveBeenCalledWith(
      "Failed to copy to clipboard",
      "error",
    );
  });
});
