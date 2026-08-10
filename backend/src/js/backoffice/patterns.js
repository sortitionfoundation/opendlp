// ABOUTME: Entry point for the dev-only frontend patterns reference page
// ABOUTME: Loaded only by patterns.html, so its demo components stay out of every other page

import { fileUploadDemo } from "../components/file-upload-demo.js";
import { patternsController } from "../components/patterns-controller.js";

document.addEventListener("alpine:init", function () {
  Alpine.data("patternsController", patternsController);
  Alpine.data("fileUploadDemo", fileUploadDemo);
});
