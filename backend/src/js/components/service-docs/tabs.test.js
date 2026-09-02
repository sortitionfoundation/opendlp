// ABOUTME: Tests for the per-tab slices of the service docs console
// ABOUTME: Each execute method must post the right service name with the right flat properties

import { describe, expect, it, vi } from "vitest";

import {
  EMAIL_BODY,
  EMAIL_SUBJECT,
  IMPORT_RESPONDENTS_CSV,
  IMPORT_TARGETS_CSV,
} from "./samples.js";
import { serviceDocsAssembly } from "./assembly.js";
import { serviceDocsCsvConfig } from "./csv-config.js";
import { serviceDocsDashboard } from "./dashboard.js";
import { serviceDocsDocuments } from "./documents.js";
import { serviceDocsEmails } from "./emails.js";
import { serviceDocsFields } from "./fields.js";
import { serviceDocsImages } from "./images.js";
import { serviceDocsRegistration } from "./registration.js";
import { serviceDocsRespondents } from "./respondents.js";
import { serviceDocsTargets } from "./targets.js";

/**
 * A slice on its own, with the core's methods replaced by spies.
 *
 * A slice only ever reaches the server through this.executeService, which the core
 * slice supplies once they are merged - so that is the seam to watch.
 */
function slice(factory) {
  const state = factory();
  state.executeService = vi.fn();
  state.copyToClipboard = vi.fn();
  state.showToast = vi.fn();
  state.responses = {};
  return state;
}

/**
 * Every execute method, with the flat properties it reads and the call it should make.
 *
 * A table rather than a test each: the risk being covered is a property name drifting
 * apart from the template's x-model, or a service name drifting from dev.py, and both
 * are best seen as one list you can read down.
 */
const EXECUTE_CALLS = [
  {
    factory: serviceDocsRespondents,
    method: "executeImportRespondents",
    props: {
      importRespondentsAssemblyId: "a-1",
      importRespondentsCsvContent: "id,name",
      importRespondentsReplaceExisting: true,
      importRespondentsIdColumn: "id",
    },
    service: "import_respondents_from_csv",
    params: {
      assembly_id: "a-1",
      csv_content: "id,name",
      replace_existing: true,
      id_column: "id",
    },
  },
  {
    factory: serviceDocsRespondents,
    method: "executeResetStatus",
    props: { resetStatusAssemblyId: "a-1" },
    service: "reset_selection_status",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsRespondents,
    method: "executeGetRespondents",
    props: {
      getRespondentsAssemblyId: "a-1",
      getRespondentsStatus: "SELECTED",
    },
    service: "get_respondents_for_assembly",
    params: { assembly_id: "a-1", status: "SELECTED" },
  },
  {
    factory: serviceDocsTargets,
    method: "executeImportTargets",
    props: {
      importTargetsAssemblyId: "a-1",
      importTargetsCsvContent: "feature,value",
    },
    service: "import_targets_from_csv",
    params: {
      assembly_id: "a-1",
      csv_content: "feature,value",
      replace_existing: true,
    },
  },
  {
    factory: serviceDocsCsvConfig,
    method: "executeGetCsvConfig",
    props: { getCsvConfigAssemblyId: "a-1" },
    service: "get_or_create_csv_config",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsCsvConfig,
    method: "executeUpdateCsvConfig",
    props: {
      updateCsvConfigAssemblyId: "a-1",
      updateCsvConfigIdColumn: "id",
      updateCsvConfigCheckSameAddress: false,
      updateCsvConfigAlgorithm: "maximin",
      updateCsvConfigSettingsConfirmed: true,
    },
    service: "update_csv_config",
    params: {
      assembly_id: "a-1",
      id_column: "id",
      check_same_address: false,
      selection_algorithm: "maximin",
      settings_confirmed: true,
    },
  },
  {
    factory: serviceDocsAssembly,
    method: "executeCreateAssembly",
    props: {
      createAssemblyTitle: "An assembly",
      createAssemblyQuestion: "A question?",
      createAssemblyNumberToSelect: 25,
    },
    service: "create_assembly",
    params: {
      title: "An assembly",
      question: "A question?",
      number_to_select: 25,
    },
  },
  {
    factory: serviceDocsAssembly,
    method: "executeGetAssembly",
    props: { getAssemblyId: "a-1" },
    service: "get_assembly_with_permissions",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsAssembly,
    method: "executeUpdateAssembly",
    props: {
      updateAssemblyId: "a-1",
      updateAssemblyTitle: "New",
      updateAssemblyQuestion: "Why?",
    },
    service: "update_assembly",
    params: { assembly_id: "a-1", title: "New", question: "Why?" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeCreateRegistrationPage",
    props: {
      createRegistrationAssemblyId: "a-1",
      createRegistrationName: "English",
      createRegistrationLanguage: "en",
      createRegistrationWithSlugs: true,
    },
    service: "create_registration_page",
    params: {
      assembly_id: "a-1",
      name: "English",
      language: "en",
      with_slugs: true,
    },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeListRegistrationPages",
    props: { listPagesAssemblyId: "a-1" },
    service: "list_registration_pages",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeDuplicateRegistrationPage",
    props: {
      duplicateSourcePageId: "p-1",
      duplicateName: "Spanish",
      duplicateLanguage: "es",
    },
    service: "duplicate_registration_page",
    params: { source_page_id: "p-1", name: "Spanish", language: "es" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeDeleteRegistrationPage",
    props: { deletePagePageId: "p-1" },
    service: "delete_registration_page",
    params: { page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeGetRegistrationPage",
    props: { getRegistrationAssemblyId: "a-1", getRegistrationPageId: "p-1" },
    service: "get_registration_page_with_source",
    params: { assembly_id: "a-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeUpdateRegistrationPage",
    props: {
      updateRegistrationAssemblyId: "a-1",
      updateRegistrationPageId: "p-1",
      updateRegistrationUrlSlug: "slug",
      updateRegistrationShortUrlSlug: "s",
    },
    service: "update_registration_page",
    params: {
      assembly_id: "a-1",
      page_id: "p-1",
      url_slug: "slug",
      short_url_slug: "s",
    },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeUpdateRegistrationHtml",
    props: {
      updateHtmlAssemblyId: "a-1",
      updateHtmlPageId: "p-1",
      updateHtmlContent: "<form></form>",
    },
    service: "update_registration_page_html",
    params: { assembly_id: "a-1", page_id: "p-1", form_html: "<form></form>" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executePublishRegistrationPage",
    props: { publishAssemblyId: "a-1", publishPageId: "p-1" },
    service: "publish_registration_page",
    params: { assembly_id: "a-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeUnpublishRegistrationPage",
    props: { unpublishAssemblyId: "a-1", unpublishPageId: "p-1" },
    service: "unpublish_registration_page",
    params: { assembly_id: "a-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeCloseRegistrationPage",
    props: { closeAssemblyId: "a-1", closePageId: "p-1" },
    service: "close_registration_page",
    params: { assembly_id: "a-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeReopenRegistrationPage",
    props: { reopenAssemblyId: "a-1", reopenPageId: "p-1" },
    service: "reopen_registration_page",
    params: { assembly_id: "a-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsRegistration,
    method: "executeGenerateStarterHtml",
    props: { generateStarterAssemblyId: "a-1" },
    service: "generate_starter_form_html",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsFields,
    method: "executeAddField",
    props: {
      addFieldAssemblyId: "a-1",
      addFieldKey: "age",
      addFieldLabel: "Age",
      addFieldGroup: "demographic",
      addFieldType: "select",
      addFieldOptions: "18-30, 31-50 , 51+",
    },
    service: "add_field",
    params: {
      assembly_id: "a-1",
      field_key: "age",
      label: "Age",
      group: "demographic",
      field_type: "select",
      options: ["18-30", "31-50", "51+"],
    },
  },
  {
    factory: serviceDocsImages,
    method: "executeListRegistrationImages",
    props: { listImagesAssemblyId: "a-1" },
    service: "list_registration_images",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsImages,
    method: "executeDeleteRegistrationImage",
    props: { deleteImageAssemblyId: "a-1", deleteImageImageId: "i-1" },
    service: "delete_registration_image",
    params: { assembly_id: "a-1", image_id: "i-1" },
  },
  {
    factory: serviceDocsImages,
    method: "executeSetRegistrationImageAlt",
    props: {
      setAltAssemblyId: "a-1",
      setAltImageId: "i-1",
      setAltText: "A logo",
    },
    service: "set_registration_image_alt",
    params: { assembly_id: "a-1", image_id: "i-1", alt: "A logo" },
  },
  {
    factory: serviceDocsImages,
    method: "executeListImageSnippets",
    props: { listSnippetsAssemblyId: "a-1" },
    service: "list_image_snippets",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsImages,
    method: "executeGetRegistrationImageForServing",
    props: { serveImageUrlSlug: "slug", serveImageImageName: "abc.png" },
    service: "get_registration_image_for_serving",
    params: { url_slug: "slug", image_name: "abc.png" },
  },
  {
    factory: serviceDocsDocuments,
    method: "executeListRegistrationDocuments",
    props: { listDocumentsAssemblyId: "a-1" },
    service: "list_registration_documents",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsDocuments,
    method: "executeDeleteRegistrationDocument",
    props: { deleteDocumentAssemblyId: "a-1", deleteDocumentDocumentId: "d-1" },
    service: "delete_registration_document",
    params: { assembly_id: "a-1", document_id: "d-1" },
  },
  {
    factory: serviceDocsDocuments,
    method: "executeSetRegistrationDocumentLabel",
    props: {
      setLabelAssemblyId: "a-1",
      setLabelDocumentId: "d-1",
      setLabelText: "Pack",
    },
    service: "set_registration_document_label",
    params: { assembly_id: "a-1", document_id: "d-1", label: "Pack" },
  },
  {
    factory: serviceDocsDocuments,
    method: "executeListDocumentSnippets",
    props: { listDocSnippetsAssemblyId: "a-1" },
    service: "list_document_snippets",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsDocuments,
    method: "executeGetRegistrationDocumentForServing",
    props: {
      serveDocumentUrlSlug: "slug",
      serveDocumentDocumentName: "abc.pdf",
    },
    service: "get_registration_document_for_serving",
    params: { url_slug: "slug", document_name: "abc.pdf" },
  },
  {
    factory: serviceDocsEmails,
    method: "executeCreateEmailTemplate",
    props: {
      createTemplateAssemblyId: "a-1",
      createTemplateName: "Auto reply",
      createTemplateSubject: "Thanks",
      createTemplateBodyHtml: "<p>Hi</p>",
    },
    service: "create_email_template",
    params: {
      assembly_id: "a-1",
      name: "Auto reply",
      subject: "Thanks",
      body_html: "<p>Hi</p>",
    },
  },
  {
    factory: serviceDocsEmails,
    method: "executeListEmailTemplates",
    props: { listTemplatesAssemblyId: "a-1" },
    service: "list_email_templates",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsEmails,
    method: "executeGetEmailTemplate",
    props: { getTemplateId: "t-1" },
    service: "get_email_template",
    params: { template_id: "t-1" },
  },
  {
    factory: serviceDocsEmails,
    method: "executeDeleteEmailTemplate",
    props: { deleteTemplateId: "t-1" },
    service: "delete_email_template",
    params: { template_id: "t-1" },
  },
  {
    factory: serviceDocsEmails,
    method: "executeAssignAutoReplyTemplate",
    props: {
      assignAutoReplyAssemblyId: "a-1",
      assignAutoReplyTemplateId: "t-1",
      assignAutoReplyPageId: "p-1",
    },
    service: "assign_auto_reply_template",
    params: { assembly_id: "a-1", template_id: "t-1", page_id: "p-1" },
  },
  {
    factory: serviceDocsEmails,
    method: "executeAutoReplyReadinessProblems",
    props: { autoReplyReadinessAssemblyId: "a-1" },
    service: "auto_reply_readiness_problems",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsDashboard,
    method: "executeGetDashboardSummary",
    props: { dashboardSummaryAssemblyId: "a-1" },
    service: "get_assembly_dashboard_summary",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsDashboard,
    method: "executeGetDashboardReport",
    props: { dashboardReportAssemblyId: "a-1" },
    service: "get_assembly_dashboard_report",
    params: { assembly_id: "a-1" },
  },
  {
    factory: serviceDocsDashboard,
    method: "executeExportDashboard",
    props: { dashboardExportAssemblyId: "a-1", dashboardExportFormat: "xlsx" },
    service: "export_assembly_dashboard",
    params: { assembly_id: "a-1", export_format: "xlsx" },
  },
];

describe.each(EXECUTE_CALLS)(
  "$method",
  ({ factory, method, props, service, params }) => {
    it(`posts ${service} with the values from its form`, () => {
      const state = slice(factory);
      Object.assign(state, props);

      state[method]();

      expect(state.executeService).toHaveBeenCalledWith(service, params);
    });
  },
);

describe("the properties the templates bind with x-model", () => {
  it("all exist on a freshly built slice, so nothing is bound to undefined", () => {
    const missing = EXECUTE_CALLS.flatMap(({ factory, props }) => {
      const state = factory();
      return Object.keys(props).filter((name) => !(name in state));
    });

    expect(missing).toEqual([]);
  });
});

describe("optional and parsed parameters", () => {
  it("sends a null respondent status rather than an empty string, which would filter on nothing", () => {
    const state = slice(serviceDocsRespondents);
    state.getRespondentsAssemblyId = "a-1";

    state.executeGetRespondents();

    expect(state.executeService).toHaveBeenCalledWith(
      "get_respondents_for_assembly",
      {
        assembly_id: "a-1",
        status: null,
      },
    );
  });

  it("sends a null field label rather than an empty one", () => {
    const state = slice(serviceDocsFields);
    state.addFieldKey = "age";

    state.executeAddField();

    expect(state.executeService.mock.calls[0][1].label).toBeNull();
  });

  it("sends null field options when none were typed", () => {
    const state = slice(serviceDocsFields);
    state.addFieldOptions = "   ";

    state.executeAddField();

    expect(state.executeService.mock.calls[0][1].options).toBeNull();
  });

  it("drops empty entries from a trailing comma in the field options", () => {
    const state = slice(serviceDocsFields);
    state.addFieldOptions = "a, b, ";

    state.executeAddField();

    expect(state.executeService.mock.calls[0][1].options).toEqual(["a", "b"]);
  });

  it("sends a null auto-reply template id, which is how the template is unassigned", () => {
    const state = slice(serviceDocsEmails);
    state.assignAutoReplyAssemblyId = "a-1";

    state.executeAssignAutoReplyTemplate();

    expect(state.executeService.mock.calls[0][1].template_id).toBeNull();
  });

  it("sends only the email template fields that were filled in, so one can be updated alone", () => {
    const state = slice(serviceDocsEmails);
    state.updateTemplateId = "t-1";
    state.updateTemplateSubject = "New subject";

    state.executeUpdateEmailTemplate();

    expect(state.executeService).toHaveBeenCalledWith("update_email_template", {
      template_id: "t-1",
      subject: "New subject",
    });
  });
});

describe("executeSubmitRegistration", () => {
  it("parses the form data JSON and sends it as an object", () => {
    const state = slice(serviceDocsRegistration);
    state.submitRegistrationAssemblyId = "a-1";
    state.submitRegistrationFormData = '{"first_name": "Ada"}';
    state.submitRegistrationIsTest = true;

    state.executeSubmitRegistration();

    expect(state.executeService).toHaveBeenCalledWith("submit_registration", {
      assembly_id: "a-1",
      form_data: { first_name: "Ada" },
      is_test: true,
    });
  });

  it("reports bad JSON in the response panel without troubling the server", () => {
    const state = slice(serviceDocsRegistration);
    state.submitRegistrationFormData = "{not json";

    state.executeSubmitRegistration();

    expect(state.executeService).not.toHaveBeenCalled();
    expect(state.responses.submit_registration).toEqual({
      status: "error",
      error: "Invalid JSON in form data",
    });
  });

  it("starts with an empty JSON object, so the field is valid before it is touched", () => {
    expect(serviceDocsRegistration().submitRegistrationFormData).toBe("{}");
  });
});

describe("choosing an image file", () => {
  it("holds the file name and its base64 payload", async () => {
    const state = slice(serviceDocsImages);
    const file = new File(["png-bytes"], "logo.png", { type: "image/png" });

    await state.handleImageFileChange({ target: { files: [file] } });

    expect(state.addImageFileName).toBe("logo.png");
    expect(state.addImageBase64).toBe(btoa("png-bytes"));
  });

  it("clears both when the picker is dismissed with nothing chosen", async () => {
    const state = slice(serviceDocsImages);
    state.addImageFileName = "old.png";
    state.addImageBase64 = "old";

    await state.handleImageFileChange({ target: { files: [] } });

    expect(state.addImageFileName).toBe("");
    expect(state.addImageBase64).toBe("");
  });

  it("says so when the file cannot be read", async () => {
    const state = slice(serviceDocsImages);

    await state.handleImageFileChange({
      target: { files: [{ name: "broken" }] },
    });

    expect(state.addImageBase64).toBe("");
    expect(state.showToast).toHaveBeenCalledWith(
      "Failed to read file",
      "error",
    );
  });

  it("refuses to upload before a file has been chosen", () => {
    const state = slice(serviceDocsImages);
    state.addImageAssemblyId = "a-1";

    state.executeAddRegistrationImage();

    expect(state.executeService).not.toHaveBeenCalled();
    expect(state.responses.add_image.error).toContain("choose an image file");
  });

  it("uploads the payload once there is one", () => {
    const state = slice(serviceDocsImages);
    state.addImageAssemblyId = "a-1";
    state.addImageBase64 = "AAAA";
    state.addImageAlt = "A logo";

    state.executeAddRegistrationImage();

    expect(state.executeService).toHaveBeenCalledWith(
      "add_registration_image",
      {
        assembly_id: "a-1",
        image_base64: "AAAA",
        alt: "A logo",
      },
    );
  });
});

describe("choosing a document file", () => {
  it("holds the file name and its base64 payload", async () => {
    const state = slice(serviceDocsDocuments);
    const file = new File(["pdf-bytes"], "info.pdf", {
      type: "application/pdf",
    });

    await state.handleDocumentFileChange({ target: { files: [file] } });

    expect(state.addDocumentFileName).toBe("info.pdf");
    expect(state.addDocumentBase64).toBe(btoa("pdf-bytes"));
  });

  it("refuses to upload before a file has been chosen", () => {
    const state = slice(serviceDocsDocuments);

    state.executeAddRegistrationDocument();

    expect(state.executeService).not.toHaveBeenCalled();
    expect(state.responses.add_document.error).toContain("choose a PDF file");
  });

  it("sends the original filename along with the payload", () => {
    const state = slice(serviceDocsDocuments);
    state.addDocumentAssemblyId = "a-1";
    state.addDocumentBase64 = "AAAA";
    state.addDocumentFileName = "info.pdf";
    state.addDocumentLabel = "Information pack";

    state.executeAddRegistrationDocument();

    expect(state.executeService).toHaveBeenCalledWith(
      "add_registration_document",
      {
        assembly_id: "a-1",
        pdf_base64: "AAAA",
        original_filename: "info.pdf",
        label: "Information pack",
      },
    );
  });
});

describe("loading a sample into a form", () => {
  it("fills the respondents CSV", () => {
    const state = slice(serviceDocsRespondents);

    state.loadRespondentsSample();

    expect(state.importRespondentsCsvContent).toBe(IMPORT_RESPONDENTS_CSV);
  });

  it("fills the targets CSV", () => {
    const state = slice(serviceDocsTargets);

    state.loadTargetsSample();

    expect(state.importTargetsCsvContent).toBe(IMPORT_TARGETS_CSV);
  });

  it("fills the email subject and body", () => {
    const state = slice(serviceDocsEmails);

    state.loadEmailSubjectSample();
    state.loadEmailBodySample();

    expect(state.createTemplateSubject).toBe(EMAIL_SUBJECT);
    expect(state.createTemplateBodyHtml).toBe(EMAIL_BODY);
  });

  it("keeps the Jinja placeholders the samples are there to demonstrate", () => {
    expect(EMAIL_SUBJECT).toContain("{{ respondent.first_name_or_friend }}");
    expect(EMAIL_BODY).toContain("{{ assembly.title }}");
  });
});

describe("resetting a form", () => {
  it("clears the respondents import and its response", () => {
    const state = slice(serviceDocsRespondents);
    state.importRespondentsAssemblyId = "a-1";
    state.importRespondentsCsvContent = "id";
    state.importRespondentsReplaceExisting = true;
    state.importRespondentsIdColumn = "id";
    state.responses.import_respondents = { status: "success" };

    state.resetImportRespondents();

    expect(state.importRespondentsAssemblyId).toBe("");
    expect(state.importRespondentsCsvContent).toBe("");
    expect(state.importRespondentsReplaceExisting).toBe(false);
    expect(state.importRespondentsIdColumn).toBe("");
    expect(state.responses.import_respondents).toBeNull();
  });

  it("clears the targets import and its response", () => {
    const state = slice(serviceDocsTargets);
    state.importTargetsAssemblyId = "a-1";
    state.importTargetsCsvContent = "feature";
    state.responses.import_targets = { status: "success" };

    state.resetImportTargets();

    expect(state.importTargetsAssemblyId).toBe("");
    expect(state.importTargetsCsvContent).toBe("");
    expect(state.responses.import_targets).toBeNull();
  });

  it("clears the CSV config update, restoring the checkbox default rather than blanking it", () => {
    const state = slice(serviceDocsCsvConfig);
    state.updateCsvConfigAssemblyId = "a-1";
    state.updateCsvConfigIdColumn = "id";
    state.updateCsvConfigCheckSameAddress = false;
    state.updateCsvConfigAlgorithm = "maximin";
    state.updateCsvConfigSettingsConfirmed = true;
    state.responses.update_csv_config = { status: "success" };

    state.resetUpdateCsvConfig();

    expect(state.updateCsvConfigAssemblyId).toBe("");
    expect(state.updateCsvConfigIdColumn).toBe("");
    expect(state.updateCsvConfigCheckSameAddress).toBe(true);
    expect(state.updateCsvConfigAlgorithm).toBe("");
    expect(state.updateCsvConfigSettingsConfirmed).toBe(false);
    expect(state.responses.update_csv_config).toBeNull();
  });
});

describe("copying a response panel", () => {
  const COPY_METHODS = [
    [
      serviceDocsRespondents,
      "copyImportRespondentsResponse",
      "import_respondents",
    ],
    [serviceDocsRespondents, "copyResetStatusResponse", "reset_status"],
    [serviceDocsRespondents, "copyGetRespondentsResponse", "get_respondents"],
    [serviceDocsTargets, "copyImportTargetsResponse", "import_targets"],
    [serviceDocsCsvConfig, "copyGetCsvConfigResponse", "get_csv_config"],
    [serviceDocsCsvConfig, "copyUpdateCsvConfigResponse", "update_csv_config"],
    [serviceDocsAssembly, "copyCreateAssemblyResponse", "create_assembly"],
    [serviceDocsAssembly, "copyGetAssemblyResponse", "get_assembly"],
    [
      serviceDocsRegistration,
      "copyCreateRegistrationResponse",
      "create_registration_page",
    ],
    [
      serviceDocsRegistration,
      "copyGetRegistrationResponse",
      "get_registration_page",
    ],
    [
      serviceDocsRegistration,
      "copyGenerateStarterResponse",
      "generate_starter_html",
    ],
  ];

  it.each(COPY_METHODS)("%# copies the right panel", (factory, method, key) => {
    const state = slice(factory);
    state.copyResponse = vi.fn();

    state[method]();

    expect(state.copyResponse).toHaveBeenCalledWith(key);
  });
});

describe("copying a code reference", () => {
  const CODE_REFS = [
    [
      serviceDocsRespondents,
      "copyRespondentServiceRef",
      "respondent_service.py:63",
    ],
    [
      serviceDocsTargets,
      "copyAssemblyServiceTargetsRef",
      "assembly_service.py:501",
    ],
    [serviceDocsAssembly, "copyAssemblyServiceRef", "assembly_service.py:46"],
    [
      serviceDocsRegistration,
      "copyRegistrationServiceRef",
      "registration_page_service.py:54",
    ],
  ];

  it.each(CODE_REFS)(
    "%# copies the file and line",
    (factory, method, reference) => {
      const state = slice(factory);

      state[method]();

      expect(state.copyToClipboard).toHaveBeenCalledWith(reference);
    },
  );
});
