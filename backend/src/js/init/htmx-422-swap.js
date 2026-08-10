// ABOUTME: Configures HTMX to swap content on 422 responses for inline validation errors
// ABOUTME: Without this, HTMX ignores 4xx responses and validation error markup is not displayed

/**
 * Tell HTMX to swap the response body on a 422, and not to treat it as an error.
 */
export function initHtmx422Swap() {
  document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("htmx:beforeSwap", function (evt) {
      if (evt.detail.xhr.status === 422) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
      }
    });
  });
}
