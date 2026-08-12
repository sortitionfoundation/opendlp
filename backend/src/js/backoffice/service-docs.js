// ABOUTME: Entry point for the dev-only service layer documentation console
// ABOUTME: Loaded only by service_docs.html, so its component stays off every other page

import { serviceDocsController } from "../components/service-docs/controller.js";
import { readJsonScript } from "../lib/json-script.js";

document.addEventListener("alpine:init", function () {
  // Registered as a callback rather than the factory itself so the page's configuration
  // is read here, leaving the component a plain function of its options.
  Alpine.data("serviceDocsController", function () {
    return serviceDocsController(readJsonScript("service-docs-data"));
  });
});
