// ABOUTME: CSV config tab of the service docs console - read and update a selection config
// ABOUTME: One of the per-tab slices composed into serviceDocsController

/**
 * Build the CSV config slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsCsvConfig() {
  return {
    getCsvConfigAssemblyId: "",
    updateCsvConfigAssemblyId: "",
    updateCsvConfigIdColumn: "",
    updateCsvConfigCheckSameAddress: true,
    updateCsvConfigAlgorithm: "",
    updateCsvConfigSettingsConfirmed: false,

    executeGetCsvConfig: function () {
      return this.executeService("get_or_create_csv_config", {
        assembly_id: this.getCsvConfigAssemblyId,
      });
    },

    executeUpdateCsvConfig: function () {
      return this.executeService("update_csv_config", {
        assembly_id: this.updateCsvConfigAssemblyId,
        id_column: this.updateCsvConfigIdColumn,
        check_same_address: this.updateCsvConfigCheckSameAddress,
        selection_algorithm: this.updateCsvConfigAlgorithm,
        settings_confirmed: this.updateCsvConfigSettingsConfirmed,
      });
    },

    // Restores the form's initial values rather than blanking every field, so the
    // check_same_address default survives a reset.
    resetUpdateCsvConfig: function () {
      this.updateCsvConfigAssemblyId = "";
      this.updateCsvConfigIdColumn = "";
      this.updateCsvConfigCheckSameAddress = true;
      this.updateCsvConfigAlgorithm = "";
      this.updateCsvConfigSettingsConfirmed = false;
      this.responses.update_csv_config = null;
    },

    copyGetCsvConfigResponse: function () {
      return this.copyResponse("get_csv_config");
    },

    copyUpdateCsvConfigResponse: function () {
      return this.copyResponse("update_csv_config");
    },
  };
}
