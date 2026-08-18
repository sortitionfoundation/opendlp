// ABOUTME: The Alpine component driving the backoffice registration page
// ABOUTME: Composes the toast, edit-guard, skeleton-preview and asset slices into one state

import { formatBytes } from "../lib/format-bytes.js";
import { registrationDocuments } from "./registration-documents.js";
import { registrationEditGuard } from "./registration-edit-guard.js";
import { registrationImages } from "./registration-images.js";
import { registrationSkeleton } from "./registration-skeleton.js";
import { registrationToast } from "./registration-toast.js";

/**
 * Build the registrationPageController component state.
 *
 * The slices are merged rather than nested because the CSP Alpine build needs
 * flat property names: `x-model="imageAlt"` works, `x-model="images.alt"` does
 * not. Each slice returns a flat object and calls `this.showToast(...)`, which
 * the toast slice supplies once they are merged.
 *
 * The configuration comes from a server-rendered JSON data block - see
 * lib/json-script.js and the entry point in backoffice/registration-page.js -
 * because it holds `url_for` URLs, the CSRF token and translated strings that
 * only the template can produce.
 *
 * @param {Object} config - the page configuration
 * @param {boolean} [config.editMode=false] - whether the HTML editor is unlocked
 * @param {string} [config.csrfToken=""] - the CSRF token for the session
 * @param {Array} [config.images=[]] - the images already on the page
 * @param {Array} [config.documents=[]] - the documents already on the page
 * @param {Object} [config.urls={}] - the routes the page calls
 * @param {Object} [config.messages={}] - translated strings
 * @returns {Object} Alpine component state
 */
export function registrationPageController(config) {
  var urls = config.urls || {};
  var messages = config.messages || {};
  var csrfToken = config.csrfToken || "";

  return Object.assign(
    {
      formatBytes: formatBytes,
    },
    registrationToast(messages),
    registrationEditGuard({ editMode: config.editMode, listUrl: urls.list }),
    registrationSkeleton({
      csrfToken: csrfToken,
      skeletonUrl: urls.skeleton,
      messages: messages,
    }),
    registrationImages({
      csrfToken: csrfToken,
      images: config.images || [],
      uploadImageUrl: urls.uploadImage,
      imageItemUrlTemplate: urls.imageItem || "",
      messages: messages,
    }),
    registrationDocuments({
      csrfToken: csrfToken,
      documents: config.documents || [],
      uploadDocumentUrl: urls.uploadDocument,
      documentItemUrlTemplate: urls.documentItem || "",
      messages: messages,
    }),
  );
}
