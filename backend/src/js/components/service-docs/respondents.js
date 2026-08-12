// ABOUTME: Respondents tab of the service docs console - CSV import, status reset, listing
// ABOUTME: One of the per-tab slices composed into serviceDocsController

import { IMPORT_RESPONDENTS_CSV } from "./samples.js";

/**
 * Build the respondents slice of the service docs controller.
 *
 * Flat properties, because the CSP Alpine build's x-model cannot use a nested path.
 * executeService, copyResponse and copyToClipboard come from the core slice once merged.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsRespondents() {
  return {
    importRespondentsAssemblyId: "",
    importRespondentsCsvContent: "",
    importRespondentsReplaceExisting: false,
    importRespondentsIdColumn: "",
    resetStatusAssemblyId: "",
    getRespondentsAssemblyId: "",
    getRespondentsStatus: "",

    executeImportRespondents: function () {
      return this.executeService("import_respondents_from_csv", {
        assembly_id: this.importRespondentsAssemblyId,
        csv_content: this.importRespondentsCsvContent,
        replace_existing: this.importRespondentsReplaceExisting,
        id_column: this.importRespondentsIdColumn,
      });
    },

    executeResetStatus: function () {
      return this.executeService("reset_selection_status", {
        assembly_id: this.resetStatusAssemblyId,
      });
    },

    executeGetRespondents: function () {
      return this.executeService("get_respondents_for_assembly", {
        // An empty select means "every status", which the service spells as null.
        assembly_id: this.getRespondentsAssemblyId,
        status: this.getRespondentsStatus || null,
      });
    },

    resetImportRespondents: function () {
      this.importRespondentsAssemblyId = "";
      this.importRespondentsCsvContent = "";
      this.importRespondentsReplaceExisting = false;
      this.importRespondentsIdColumn = "";
      this.responses.import_respondents = null;
    },

    loadRespondentsSample: function () {
      this.importRespondentsCsvContent = IMPORT_RESPONDENTS_CSV;
    },

    copyImportRespondentsResponse: function () {
      return this.copyResponse("import_respondents");
    },

    copyResetStatusResponse: function () {
      return this.copyResponse("reset_status");
    },

    copyGetRespondentsResponse: function () {
      return this.copyResponse("get_respondents");
    },

    copyRespondentServiceRef: function () {
      return this.copyToClipboard("respondent_service.py:63");
    },
  };
}
