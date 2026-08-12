// ABOUTME: PDF document assets slice of the registration page controller
// ABOUTME: Upload, label edit, delete and snippet copy, mutating the list in place

import {
  deleteResource,
  patchJson,
  postFormData,
} from "../lib/json-request.js";
import { urlWithId } from "../lib/url-utils.js";

/**
 * Build the document-assets slice of the registration page controller.
 *
 * Same contract as registrationImages: the list is seeded from the server-side
 * render and mutated in place, and the per-item URL comes from a template
 * rendered once with ID_SENTINEL. The two are kept parallel rather than shared -
 * see registrationImages for why.
 *
 * The one asymmetry is deliberate and predates this file: a label is optional at
 * upload time but required once the details form is open, where alt text is
 * required in both places because an image without it is inaccessible.
 *
 * @param {Object} options - configuration
 * @param {string} options.csrfToken - the CSRF token for the session
 * @param {Array} options.documents - the documents already on the page
 * @param {string} options.uploadDocumentUrl - the upload route
 * @param {string} options.documentItemUrlTemplate - the per-document route, holding ID_SENTINEL
 * @param {Object} options.messages - translated strings, rendered server-side
 * @returns {Object} a flat slice of Alpine component state
 */
export function registrationDocuments(options) {
  var messages = options.messages;

  return {
    documents: options.documents,
    documentUploadModalOpen: false,
    documentUploading: false,
    documentFile: null,
    documentFileName: "",
    documentLabel: "",
    documentUploadError: "",
    documentBeingDeletedId: "",
    documentDetailsModalOpen: false,
    editingDocument: null,
    editingDocumentLabel: "",
    documentEditing: false,
    documentEditError: "",

    documentItemUrl: function (id) {
      return urlWithId(options.documentItemUrlTemplate, id);
    },

    openDocumentUploadModal: function () {
      this.documentFile = null;
      this.documentFileName = "";
      this.documentLabel = "";
      this.documentUploadError = "";
      this.documentUploadModalOpen = true;
    },

    closeDocumentUploadModalIfAllowed: function () {
      if (this.documentUploading) return;
      this.documentUploadModalOpen = false;
    },

    onDocumentFileSelected: function (event) {
      var file = event.target.files && event.target.files[0];
      this.documentFile = file || null;
      this.documentFileName = file ? file.name : "";
      this.documentUploadError = "";
    },

    submitDocumentUpload: function () {
      var self = this;
      if (!self.documentFile || self.documentUploading)
        return Promise.resolve();

      self.documentUploading = true;
      self.documentUploadError = "";
      var formData = new FormData();
      formData.append("document", self.documentFile);
      formData.append("label", self.documentLabel.trim());

      return postFormData(
        options.uploadDocumentUrl,
        formData,
        options.csrfToken,
      )
        .then(function (result) {
          if (!result.ok) {
            self.documentUploadError =
              result.data.error || messages.uploadFailed;
            return;
          }
          // The server returns the existing row when the bytes match, so an
          // upload of the same file twice updates rather than duplicates.
          var existing = self.documents.findIndex(function (candidate) {
            return candidate.id === result.data.document.id;
          });
          if (existing >= 0) {
            self.documents.splice(existing, 1, result.data.document);
          } else {
            self.documents.push(result.data.document);
          }
          self.documentUploadModalOpen = false;
          self.showToast(messages.documentUploaded, "success");
        })
        .catch(function () {
          self.documentUploadError = messages.documentUploadNetworkError;
        })
        .finally(function () {
          self.documentUploading = false;
        });
    },

    deleteDocument: function (doc) {
      var self = this;
      if (!doc || self.documentBeingDeletedId) return Promise.resolve();
      if (
        !confirm(
          messages.confirmDeleteDocument + " " + (doc.display_name || ""),
        )
      ) {
        return Promise.resolve();
      }

      self.documentBeingDeletedId = doc.id;

      return deleteResource(self.documentItemUrl(doc.id), options.csrfToken)
        .then(function (result) {
          if (!result.ok) {
            self.showToast(
              result.data.error || messages.deleteDocumentFailed,
              "error",
            );
            return;
          }
          self.documents = self.documents.filter(function (candidate) {
            return candidate.id !== doc.id;
          });
          self.showToast(messages.documentDeleted, "success");
        })
        .catch(function () {
          self.showToast(messages.deleteDocumentNetworkError, "error");
        })
        .finally(function () {
          self.documentBeingDeletedId = "";
        });
    },

    copyDocumentSnippet: function (doc) {
      var self = this;
      if (!doc || !doc.a_snippet) {
        self.showToast(messages.noPublicUrl, "error");
        return Promise.resolve();
      }

      return navigator.clipboard.writeText(doc.a_snippet).then(
        function () {
          self.showToast(messages.snippetCopied, "success");
        },
        function () {
          self.showToast(messages.copyFailed, "error");
        },
      );
    },

    openDocumentDetailsModal: function (doc) {
      if (!doc) return;
      this.editingDocument = doc;
      this.editingDocumentLabel = doc.label || "";
      this.documentEditError = "";
      this.documentDetailsModalOpen = true;
    },

    closeDocumentDetailsModalIfAllowed: function () {
      if (this.documentEditing) return;
      this.documentDetailsModalOpen = false;
      this.editingDocument = null;
      this.editingDocumentLabel = "";
      this.documentEditError = "";
    },

    deleteEditingDocument: function () {
      var self = this;
      if (
        !self.editingDocument ||
        self.documentEditing ||
        self.documentBeingDeletedId
      ) {
        return Promise.resolve();
      }

      var doc = self.editingDocument;
      self.documentBeingDeletedId = doc.id;

      return deleteResource(self.documentItemUrl(doc.id), options.csrfToken)
        .then(function (result) {
          if (!result.ok) {
            self.showToast(
              result.data.error || messages.deleteDocumentFailed,
              "error",
            );
            return;
          }
          self.documents = self.documents.filter(function (candidate) {
            return candidate.id !== doc.id;
          });
          self.documentDetailsModalOpen = false;
          self.editingDocument = null;
          self.editingDocumentLabel = "";
          self.showToast(messages.documentDeleted, "success");
        })
        .catch(function () {
          self.showToast(messages.deleteDocumentNetworkError, "error");
        })
        .finally(function () {
          self.documentBeingDeletedId = "";
        });
    },

    submitDocumentEdit: function () {
      var self = this;
      if (!self.editingDocument || self.documentEditing) {
        return Promise.resolve();
      }

      var label = self.editingDocumentLabel.trim();
      if (!label) {
        self.documentEditError = messages.labelRequired;
        return Promise.resolve();
      }

      self.documentEditing = true;
      self.documentEditError = "";

      return patchJson(
        self.documentItemUrl(self.editingDocument.id),
        { label: label },
        options.csrfToken,
      )
        .then(function (result) {
          if (!result.ok) {
            self.documentEditError =
              result.data.error || messages.updateDocumentFailed;
            return;
          }
          var index = self.documents.findIndex(function (candidate) {
            return candidate.id === result.data.document.id;
          });
          if (index >= 0) self.documents.splice(index, 1, result.data.document);
          self.documentDetailsModalOpen = false;
          self.editingDocument = null;
          self.editingDocumentLabel = "";
          self.showToast(messages.documentUpdated, "success");
        })
        .catch(function () {
          self.documentEditError = messages.updateDocumentNetworkError;
        })
        .finally(function () {
          self.documentEditing = false;
        });
    },
  };
}
