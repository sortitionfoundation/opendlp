// ABOUTME: Fields tab of the service docs console - add a respondent field to an assembly
// ABOUTME: One of the per-tab slices composed into serviceDocsController

/**
 * Build the fields slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsFields() {
  return {
    addFieldAssemblyId: "",
    addFieldKey: "",
    addFieldLabel: "",
    addFieldGroup: "other",
    addFieldType: "text",
    addFieldOptions: "",

    executeAddField: function () {
      // The options are typed as a comma-separated list. Nothing typed means the field
      // has no options at all, which is a different thing from an empty list.
      var options = null;
      if (this.addFieldOptions && this.addFieldOptions.trim()) {
        options = this.addFieldOptions
          .split(",")
          .map(function (option) {
            return option.trim();
          })
          .filter(function (option) {
            return option;
          });
      }

      return this.executeService("add_field", {
        assembly_id: this.addFieldAssemblyId,
        field_key: this.addFieldKey,
        // An empty label means "derive one from the key", which the service spells as null.
        label: this.addFieldLabel || null,
        group: this.addFieldGroup,
        field_type: this.addFieldType,
        options: options,
      });
    },
  };
}
