// ABOUTME: Image assets slice of the registration page controller
// ABOUTME: Upload, alt-text edit, delete and snippet copy, mutating the list in place

import {
  deleteResource,
  patchJson,
  postFormData,
} from "../lib/json-request.js";
import { urlWithId } from "../lib/url-utils.js";

/**
 * Build the image-assets slice of the registration page controller.
 *
 * The list is seeded from the server-side render and mutated in place, so the
 * page never reloads and uncommitted edits in the HTML editor survive.
 *
 * Kept parallel to registrationDocuments rather than shared with it: the CSP
 * Alpine build needs flat properties for x-model, so `imageAlt` and
 * `documentLabel` have to be real names on the component, which a factory
 * generating them from a prefix would hide from anyone grepping the template.
 *
 * @param {Object} options - configuration
 * @param {string} options.csrfToken - the CSRF token for the session
 * @param {Array} options.images - the images already on the page
 * @param {string} options.uploadImageUrl - the upload route
 * @param {string} options.imageItemUrlTemplate - the per-image route, holding ID_SENTINEL
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationImages(options) {
  var messages = options.messages;

  return {
    images: options.images,
    imageUploadModalOpen: false,
    imageUploading: false,
    imageFile: null,
    imageFileName: "",
    imageAlt: "",
    imageUploadError: "",
    imageBeingDeletedId: "",
    imageDetailsModalOpen: false,
    editingImage: null,
    editingImageAlt: "",
    imageEditing: false,
    imageEditError: "",

    imageItemUrl: function (id) {
      return urlWithId(options.imageItemUrlTemplate, id);
    },

    openImageUploadModal: function () {
      this.imageFile = null;
      this.imageFileName = "";
      this.imageAlt = "";
      this.imageUploadError = "";
      this.imageUploadModalOpen = true;
    },

    closeImageUploadModalIfAllowed: function () {
      if (this.imageUploading) return;
      this.imageUploadModalOpen = false;
    },

    onImageFileSelected: function (event) {
      var file = event.target.files && event.target.files[0];
      this.imageFile = file || null;
      this.imageFileName = file ? file.name : "";
      this.imageUploadError = "";
    },

    submitImageUpload: function () {
      var self = this;
      if (!self.imageFile || self.imageUploading) return Promise.resolve();

      var alt = self.imageAlt.trim();
      if (!alt) {
        self.imageUploadError = messages.altRequired;
        return Promise.resolve();
      }

      self.imageUploading = true;
      self.imageUploadError = "";
      var formData = new FormData();
      formData.append("image", self.imageFile);
      formData.append("alt", alt);

      return postFormData(options.uploadImageUrl, formData, options.csrfToken)
        .then(function (result) {
          if (!result.ok) {
            self.imageUploadError = result.data.error || messages.uploadFailed;
            return;
          }
          // The server returns the existing row when the bytes match, so an
          // upload of the same file twice updates rather than duplicates.
          var existing = self.images.findIndex(function (image) {
            return image.id === result.data.image.id;
          });
          if (existing >= 0) {
            self.images.splice(existing, 1, result.data.image);
          } else {
            self.images.push(result.data.image);
          }
          self.imageUploadModalOpen = false;
          self.showToast(messages.imageUploaded, "success");
        })
        .catch(function () {
          self.imageUploadError = messages.imageUploadNetworkError;
        })
        .finally(function () {
          self.imageUploading = false;
        });
    },

    deleteImage: function (image) {
      var self = this;
      if (!image || self.imageBeingDeletedId) return Promise.resolve();
      if (
        !confirm(messages.confirmDeleteImage + " " + (image.display_name || ""))
      ) {
        return Promise.resolve();
      }

      self.imageBeingDeletedId = image.id;

      return deleteResource(self.imageItemUrl(image.id), options.csrfToken)
        .then(function (result) {
          if (!result.ok) {
            self.showToast(
              result.data.error || messages.deleteImageFailed,
              "error",
            );
            return;
          }
          self.images = self.images.filter(function (candidate) {
            return candidate.id !== image.id;
          });
          self.showToast(messages.imageDeleted, "success");
        })
        .catch(function () {
          self.showToast(messages.deleteImageNetworkError, "error");
        })
        .finally(function () {
          self.imageBeingDeletedId = "";
        });
    },

    copyImageSnippet: function (image) {
      var self = this;
      if (!image || !image.img_snippet) {
        self.showToast(messages.noPublicUrl, "error");
        return Promise.resolve();
      }

      return navigator.clipboard.writeText(image.img_snippet).then(
        function () {
          self.showToast(messages.snippetCopied, "success");
        },
        function () {
          self.showToast(messages.copyFailed, "error");
        },
      );
    },

    openImageDetailsModal: function (image) {
      if (!image) return;
      this.editingImage = image;
      this.editingImageAlt = image.alt || "";
      this.imageEditError = "";
      this.imageDetailsModalOpen = true;
    },

    closeImageDetailsModalIfAllowed: function () {
      if (this.imageEditing) return;
      this.imageDetailsModalOpen = false;
      this.editingImage = null;
      this.editingImageAlt = "";
      this.imageEditError = "";
    },

    deleteEditingImage: function () {
      var self = this;
      if (!self.editingImage || self.imageEditing || self.imageBeingDeletedId) {
        return Promise.resolve();
      }

      var image = self.editingImage;
      self.imageBeingDeletedId = image.id;

      return deleteResource(self.imageItemUrl(image.id), options.csrfToken)
        .then(function (result) {
          if (!result.ok) {
            self.showToast(
              result.data.error || messages.deleteImageFailed,
              "error",
            );
            return;
          }
          self.images = self.images.filter(function (candidate) {
            return candidate.id !== image.id;
          });
          self.imageDetailsModalOpen = false;
          self.editingImage = null;
          self.editingImageAlt = "";
          self.showToast(messages.imageDeleted, "success");
        })
        .catch(function () {
          self.showToast(messages.deleteImageNetworkError, "error");
        })
        .finally(function () {
          self.imageBeingDeletedId = "";
        });
    },

    submitImageEdit: function () {
      var self = this;
      if (!self.editingImage || self.imageEditing) return Promise.resolve();

      var alt = self.editingImageAlt.trim();
      if (!alt) {
        self.imageEditError = messages.altRequired;
        return Promise.resolve();
      }

      self.imageEditing = true;
      self.imageEditError = "";

      return patchJson(
        self.imageItemUrl(self.editingImage.id),
        { alt: alt },
        options.csrfToken,
      )
        .then(function (result) {
          if (!result.ok) {
            self.imageEditError =
              result.data.error || messages.updateImageFailed;
            return;
          }
          var index = self.images.findIndex(function (image) {
            return image.id === result.data.image.id;
          });
          if (index >= 0) self.images.splice(index, 1, result.data.image);
          self.imageDetailsModalOpen = false;
          self.editingImage = null;
          self.editingImageAlt = "";
          self.showToast(messages.imageUpdated, "success");
        })
        .catch(function () {
          self.imageEditError = messages.updateImageNetworkError;
        })
        .finally(function () {
          self.imageEditing = false;
        });
    },
  };
}
