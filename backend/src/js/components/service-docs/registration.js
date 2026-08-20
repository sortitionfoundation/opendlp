// ABOUTME: Registration tab of the service docs console - page lifecycle and test submissions
// ABOUTME: One of the per-tab slices composed into serviceDocsController

/**
 * Build the registration slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsRegistration() {
  return {
    createRegistrationAssemblyId: "",
    createRegistrationName: "",
    createRegistrationLanguage: "",
    // Checked by default: a page with generated slugs can be published straight away.
    createRegistrationWithSlugs: true,
    listPagesAssemblyId: "",
    duplicateSourcePageId: "",
    duplicateName: "",
    duplicateLanguage: "",
    deletePagePageId: "",
    getRegistrationAssemblyId: "",
    getRegistrationPageId: "",
    updateRegistrationAssemblyId: "",
    updateRegistrationPageId: "",
    updateRegistrationUrlSlug: "",
    updateRegistrationShortUrlSlug: "",
    updateHtmlAssemblyId: "",
    updateHtmlPageId: "",
    updateHtmlContent: "",
    publishAssemblyId: "",
    publishPageId: "",
    unpublishAssemblyId: "",
    unpublishPageId: "",
    closeAssemblyId: "",
    closePageId: "",
    reopenAssemblyId: "",
    reopenPageId: "",
    generateStarterAssemblyId: "",
    submitRegistrationAssemblyId: "",
    // An empty object rather than an empty string, so the field parses before it is edited.
    submitRegistrationFormData: "{}",
    submitRegistrationIsTest: false,

    executeCreateRegistrationPage: function () {
      return this.executeService("create_registration_page", {
        assembly_id: this.createRegistrationAssemblyId,
        name: this.createRegistrationName,
        language: this.createRegistrationLanguage,
        with_slugs: this.createRegistrationWithSlugs,
      });
    },

    executeListRegistrationPages: function () {
      return this.executeService("list_registration_pages", {
        assembly_id: this.listPagesAssemblyId,
      });
    },

    executeDuplicateRegistrationPage: function () {
      return this.executeService("duplicate_registration_page", {
        source_page_id: this.duplicateSourcePageId,
        name: this.duplicateName,
        language: this.duplicateLanguage,
      });
    },

    executeDeleteRegistrationPage: function () {
      return this.executeService("delete_registration_page", {
        page_id: this.deletePagePageId,
      });
    },

    executeGetRegistrationPage: function () {
      return this.executeService("get_registration_page_with_source", {
        assembly_id: this.getRegistrationAssemblyId,
        page_id: this.getRegistrationPageId,
      });
    },

    executeUpdateRegistrationPage: function () {
      return this.executeService("update_registration_page", {
        assembly_id: this.updateRegistrationAssemblyId,
        page_id: this.updateRegistrationPageId,
        url_slug: this.updateRegistrationUrlSlug,
        short_url_slug: this.updateRegistrationShortUrlSlug,
      });
    },

    executeUpdateRegistrationHtml: function () {
      return this.executeService("update_registration_page_html", {
        assembly_id: this.updateHtmlAssemblyId,
        page_id: this.updateHtmlPageId,
        form_html: this.updateHtmlContent,
      });
    },

    executePublishRegistrationPage: function () {
      return this.executeService("publish_registration_page", {
        assembly_id: this.publishAssemblyId,
        page_id: this.publishPageId,
      });
    },

    executeUnpublishRegistrationPage: function () {
      return this.executeService("unpublish_registration_page", {
        assembly_id: this.unpublishAssemblyId,
        page_id: this.unpublishPageId,
      });
    },

    executeCloseRegistrationPage: function () {
      return this.executeService("close_registration_page", {
        assembly_id: this.closeAssemblyId,
        page_id: this.closePageId,
      });
    },

    executeReopenRegistrationPage: function () {
      return this.executeService("reopen_registration_page", {
        assembly_id: this.reopenAssemblyId,
        page_id: this.reopenPageId,
      });
    },

    executeGenerateStarterHtml: function () {
      return this.executeService("generate_starter_form_html", {
        assembly_id: this.generateStarterAssemblyId,
      });
    },

    executeSubmitRegistration: function () {
      var formData;
      try {
        formData = JSON.parse(this.submitRegistrationFormData);
      } catch (err) {
        // Reported in the panel rather than as a toast, so it sits next to the field
        // that caused it and does not vanish after three seconds.
        this.responses.submit_registration = {
          status: "error",
          error: "Invalid JSON in form data",
        };
        return Promise.resolve();
      }

      return this.executeService("submit_registration", {
        assembly_id: this.submitRegistrationAssemblyId,
        form_data: formData,
        is_test: this.submitRegistrationIsTest,
      });
    },

    copyCreateRegistrationResponse: function () {
      return this.copyResponse("create_registration_page");
    },

    copyGetRegistrationResponse: function () {
      return this.copyResponse("get_registration_page");
    },

    copyListPagesResponse: function () {
      return this.copyResponse("list_registration_pages");
    },

    copyDuplicateRegistrationResponse: function () {
      return this.copyResponse("duplicate_registration_page");
    },

    copyGenerateStarterResponse: function () {
      return this.copyResponse("generate_starter_html");
    },

    copyRegistrationServiceRef: function () {
      return this.copyToClipboard("registration_page_service.py:54");
    },
  };
}
