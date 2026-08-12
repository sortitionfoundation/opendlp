// ABOUTME: Entry point for the backoffice registration page
// ABOUTME: Loaded only by assembly_registration.html, so its component stays off other pages

import { registrationPageController } from "../components/registration-page-controller.js";
import { readJsonScript } from "../lib/json-script.js";

document.addEventListener("alpine:init", function () {
  // Registered as a callback rather than the factory itself so the page's
  // configuration is read here, leaving the component a plain function of its
  // options and so testable without a DOM.
  Alpine.data("registrationPageController", function () {
    return registrationPageController(readJsonScript("registration-page-data"));
  });
});
