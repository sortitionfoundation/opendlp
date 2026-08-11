// ABOUTME: Emails tab of the service docs console - template CRUD and auto-reply assignment
// ABOUTME: One of the per-tab slices composed into serviceDocsController

import { EMAIL_BODY, EMAIL_SUBJECT } from "./samples.js";

/**
 * Build the emails slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsEmails() {
  return {
    createTemplateAssemblyId: "",
    createTemplateName: "",
    createTemplateSubject: "",
    createTemplateBodyHtml: "",
    listTemplatesAssemblyId: "",
    getTemplateId: "",
    updateTemplateId: "",
    updateTemplateName: "",
    updateTemplateSubject: "",
    updateTemplateBodyHtml: "",
    deleteTemplateId: "",
    assignAutoReplyAssemblyId: "",
    assignAutoReplyTemplateId: "",
    autoReplyReadinessAssemblyId: "",

    executeCreateEmailTemplate: function () {
      return this.executeService("create_email_template", {
        assembly_id: this.createTemplateAssemblyId,
        name: this.createTemplateName,
        subject: this.createTemplateSubject,
        body_html: this.createTemplateBodyHtml,
      });
    },

    executeListEmailTemplates: function () {
      return this.executeService("list_email_templates", {
        assembly_id: this.listTemplatesAssemblyId,
      });
    },

    executeGetEmailTemplate: function () {
      return this.executeService("get_email_template", {
        template_id: this.getTemplateId,
      });
    },

    executeUpdateEmailTemplate: function () {
      // Only the fields that were filled in are sent, so one can be changed at a time
      // without blanking the others.
      var params = { template_id: this.updateTemplateId };
      if (this.updateTemplateName) params.name = this.updateTemplateName;
      if (this.updateTemplateSubject)
        params.subject = this.updateTemplateSubject;
      if (this.updateTemplateBodyHtml)
        params.body_html = this.updateTemplateBodyHtml;

      return this.executeService("update_email_template", params);
    },

    executeDeleteEmailTemplate: function () {
      return this.executeService("delete_email_template", {
        template_id: this.deleteTemplateId,
      });
    },

    executeAssignAutoReplyTemplate: function () {
      return this.executeService("assign_auto_reply_template", {
        assembly_id: this.assignAutoReplyAssemblyId,
        // No template chosen means "unassign", which the service spells as null.
        template_id: this.assignAutoReplyTemplateId || null,
      });
    },

    executeAutoReplyReadinessProblems: function () {
      return this.executeService("auto_reply_readiness_problems", {
        assembly_id: this.autoReplyReadinessAssemblyId,
      });
    },

    loadEmailSubjectSample: function () {
      this.createTemplateSubject = EMAIL_SUBJECT;
    },

    loadEmailBodySample: function () {
      this.createTemplateBodyHtml = EMAIL_BODY;
    },
  };
}
