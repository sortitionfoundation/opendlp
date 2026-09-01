// ABOUTME: The Alpine component driving the dev-only service layer documentation console
// ABOUTME: Composes the shared core with one slice per tab into a single flat state

import { serviceDocsAssembly } from "./assembly.js";
import { serviceDocsCore } from "./core.js";
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
 * Build the serviceDocsController component state.
 *
 * One slice per tab, merged flat because the CSP Alpine build needs real property names
 * for `x-model`. Each slice holds only its own form fields and execute methods, and
 * reaches the server through `this.executeService`, which the core slice supplies.
 *
 * The Selection tab has no slice: it is documentation with nothing to execute.
 *
 * The configuration comes from a server-rendered JSON data block - see
 * lib/json-script.js and the entry point in backoffice/service-docs.js - because it
 * holds the execute route, the CSRF token, and the service-name to response-key map
 * that dev.py owns.
 *
 * @param {Object} config - the page configuration
 * @param {string} [config.executeUrl=""] - the dev route that runs a service
 * @param {string} [config.csrfToken=""] - the CSRF token for the session
 * @param {Object} [config.responseKeys={}] - service name -> response key
 * @returns {Object} Alpine component state
 */
export function serviceDocsController(config) {
  return Object.assign(
    {},
    serviceDocsCore({
      executeUrl: config.executeUrl || "",
      csrfToken: config.csrfToken || "",
      responseKeys: config.responseKeys || {},
    }),
    serviceDocsRespondents(),
    serviceDocsTargets(),
    serviceDocsCsvConfig(),
    serviceDocsAssembly(),
    serviceDocsRegistration(),
    serviceDocsFields(),
    serviceDocsImages(),
    serviceDocsDocuments(),
    serviceDocsEmails(),
    serviceDocsDashboard(),
  );
}
