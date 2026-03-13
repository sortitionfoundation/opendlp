// ABOUTME: Configures HTMX to swap content on 422 responses for inline validation errors
// ABOUTME: Without this, HTMX ignores 4xx responses and validation error markup is not displayed

document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("htmx:beforeSwap", function (evt) {
        if (evt.detail.xhr.status === 422) {
            evt.detail.shouldSwap = true;
            evt.detail.isError = false;
        }
    });
});
