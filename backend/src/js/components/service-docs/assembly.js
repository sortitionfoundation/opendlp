// ABOUTME: Assembly tab of the service docs console - create, read and update an assembly
// ABOUTME: One of the per-tab slices composed into serviceDocsController

/**
 * Build the assembly slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsAssembly() {
  return {
    createAssemblyTitle: "",
    createAssemblyQuestion: "",
    createAssemblyNumberToSelect: 10,
    getAssemblyId: "",
    updateAssemblyId: "",
    updateAssemblyTitle: "",
    updateAssemblyQuestion: "",

    executeCreateAssembly: function () {
      return this.executeService("create_assembly", {
        title: this.createAssemblyTitle,
        question: this.createAssemblyQuestion,
        number_to_select: this.createAssemblyNumberToSelect,
      });
    },

    executeGetAssembly: function () {
      return this.executeService("get_assembly_with_permissions", {
        assembly_id: this.getAssemblyId,
      });
    },

    executeUpdateAssembly: function () {
      return this.executeService("update_assembly", {
        assembly_id: this.updateAssemblyId,
        title: this.updateAssemblyTitle,
        question: this.updateAssemblyQuestion,
      });
    },

    copyCreateAssemblyResponse: function () {
      return this.copyResponse("create_assembly");
    },

    copyGetAssemblyResponse: function () {
      return this.copyResponse("get_assembly");
    },

    copyAssemblyServiceRef: function () {
      return this.copyToClipboard("assembly_service.py:46");
    },
  };
}
