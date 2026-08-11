// ABOUTME: Targets tab of the service docs console - quota CSV import
// ABOUTME: One of the per-tab slices composed into serviceDocsController

import { IMPORT_TARGETS_CSV } from "./samples.js";

/**
 * Build the targets slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsTargets() {
  return {
    importTargetsAssemblyId: "",
    importTargetsCsvContent: "",

    executeImportTargets: function () {
      return this.executeService("import_targets_from_csv", {
        assembly_id: this.importTargetsAssemblyId,
        csv_content: this.importTargetsCsvContent,
        // Targets are always replaced wholesale - a half-updated quota set is not
        // a state the selection algorithm can do anything sensible with.
        replace_existing: true,
      });
    },

    resetImportTargets: function () {
      this.importTargetsAssemblyId = "";
      this.importTargetsCsvContent = "";
      this.responses.import_targets = null;
    },

    loadTargetsSample: function () {
      this.importTargetsCsvContent = IMPORT_TARGETS_CSV;
    },

    copyImportTargetsResponse: function () {
      return this.copyResponse("import_targets");
    },

    copyAssemblyServiceTargetsRef: function () {
      return this.copyToClipboard("assembly_service.py:501");
    },
  };
}
