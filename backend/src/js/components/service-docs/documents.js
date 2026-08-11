// ABOUTME: Documents tab of the service docs console - upload, list, delete, label, serve
// ABOUTME: One of the per-tab slices composed into serviceDocsController

import { readFileAsBase64 } from "../../lib/file-reader.js";

/**
 * Build the documents slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsDocuments() {
  return {
    addDocumentAssemblyId: "",
    addDocumentBase64: "",
    addDocumentFileName: "",
    addDocumentLabel: "",
    listDocumentsAssemblyId: "",
    deleteDocumentAssemblyId: "",
    deleteDocumentDocumentId: "",
    setLabelAssemblyId: "",
    setLabelDocumentId: "",
    setLabelText: "",
    listDocSnippetsAssemblyId: "",
    serveDocumentUrlSlug: "",
    serveDocumentDocumentName: "",

    handleDocumentFileChange: function (event) {
      var self = this;
      var file = event.target.files && event.target.files[0];
      self.addDocumentFileName = file ? file.name : "";

      return readFileAsBase64(file).then(
        function (base64) {
          self.addDocumentBase64 = base64;
        },
        function () {
          self.addDocumentBase64 = "";
          self.showToast("Failed to read file", "error");
        },
      );
    },

    executeAddRegistrationDocument: function () {
      if (!this.addDocumentBase64) {
        this.responses.add_document = {
          status: "error",
          error: "Please choose a PDF file first",
          error_type: "ValidationError",
        };
        return Promise.resolve();
      }

      return this.executeService("add_registration_document", {
        assembly_id: this.addDocumentAssemblyId,
        pdf_base64: this.addDocumentBase64,
        original_filename: this.addDocumentFileName,
        label: this.addDocumentLabel,
      });
    },

    executeListRegistrationDocuments: function () {
      return this.executeService("list_registration_documents", {
        assembly_id: this.listDocumentsAssemblyId,
      });
    },

    executeDeleteRegistrationDocument: function () {
      return this.executeService("delete_registration_document", {
        assembly_id: this.deleteDocumentAssemblyId,
        document_id: this.deleteDocumentDocumentId,
      });
    },

    executeSetRegistrationDocumentLabel: function () {
      return this.executeService("set_registration_document_label", {
        assembly_id: this.setLabelAssemblyId,
        document_id: this.setLabelDocumentId,
        label: this.setLabelText,
      });
    },

    executeListDocumentSnippets: function () {
      return this.executeService("list_document_snippets", {
        assembly_id: this.listDocSnippetsAssemblyId,
      });
    },

    executeGetRegistrationDocumentForServing: function () {
      return this.executeService("get_registration_document_for_serving", {
        url_slug: this.serveDocumentUrlSlug,
        document_name: this.serveDocumentDocumentName,
      });
    },
  };
}
