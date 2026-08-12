// ABOUTME: Images tab of the service docs console - upload, list, delete, set alt, serve
// ABOUTME: One of the per-tab slices composed into serviceDocsController

import { readFileAsBase64 } from "../../lib/file-reader.js";

/**
 * Build the images slice of the service docs controller.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsImages() {
  return {
    addImageAssemblyId: "",
    addImageBase64: "",
    addImageFileName: "",
    addImageAlt: "",
    listImagesAssemblyId: "",
    deleteImageAssemblyId: "",
    deleteImageImageId: "",
    setAltAssemblyId: "",
    setAltImageId: "",
    setAltText: "",
    listSnippetsAssemblyId: "",
    serveImageUrlSlug: "",
    serveImageImageName: "",

    handleImageFileChange: function (event) {
      var self = this;
      var file = event.target.files && event.target.files[0];
      self.addImageFileName = file ? file.name : "";

      return readFileAsBase64(file).then(
        function (base64) {
          self.addImageBase64 = base64;
        },
        function () {
          self.addImageBase64 = "";
          self.showToast("Failed to read file", "error");
        },
      );
    },

    executeAddRegistrationImage: function () {
      if (!this.addImageBase64) {
        this.responses.add_image = {
          status: "error",
          error: "Please choose an image file first",
          error_type: "ValidationError",
        };
        return Promise.resolve();
      }

      return this.executeService("add_registration_image", {
        assembly_id: this.addImageAssemblyId,
        image_base64: this.addImageBase64,
        alt: this.addImageAlt,
      });
    },

    executeListRegistrationImages: function () {
      return this.executeService("list_registration_images", {
        assembly_id: this.listImagesAssemblyId,
      });
    },

    executeDeleteRegistrationImage: function () {
      return this.executeService("delete_registration_image", {
        assembly_id: this.deleteImageAssemblyId,
        image_id: this.deleteImageImageId,
      });
    },

    executeSetRegistrationImageAlt: function () {
      return this.executeService("set_registration_image_alt", {
        assembly_id: this.setAltAssemblyId,
        image_id: this.setAltImageId,
        alt: this.setAltText,
      });
    },

    executeListImageSnippets: function () {
      return this.executeService("list_image_snippets", {
        assembly_id: this.listSnippetsAssemblyId,
      });
    },

    executeGetRegistrationImageForServing: function () {
      return this.executeService("get_registration_image_for_serving", {
        url_slug: this.serveImageUrlSlug,
        image_name: this.serveImageImageName,
      });
    },
  };
}
