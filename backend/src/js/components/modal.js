/**
 * ABOUTME: Alpine component holding open/closed state for dialogs and overlays
 * ABOUTME: Closing can navigate to a URL, reload the page, or simply hide the modal
 *
 * Usage:
 *   <div x-data="modal({initialOpen: true, canClose: false, refreshOnClose: true})"
 *        @task-finished.window="setCanClose(true)">
 *     {% call modal(id="my-modal", title="Modal Title") %}
 *       Modal content here
 *     {% endcall %}
 *   </div>
 */

/**
 * Build the modal component state.
 *
 * @param {Object} options - configuration
 * @param {boolean} [options.initialOpen=false] - whether the modal starts open
 * @param {boolean} [options.canClose=true] - whether the modal can be closed
 * @param {boolean} [options.refreshOnClose=false] - reload the page when closing
 * @param {string} [options.closeUrl=""] - URL to navigate to when closing. Takes
 *   precedence over refreshOnClose. Use for server-driven modals whose open
 *   state lives in the URL, so closing clears it.
 * @returns {Object} Alpine component state
 */
export function modal(options) {
  var initialOpen = options.initialOpen || false;
  var initialCanClose =
    options.canClose !== undefined ? options.canClose : true;
  var refreshOnClose = options.refreshOnClose || false;
  var closeUrl = options.closeUrl || "";

  return {
    isOpen: initialOpen,
    canClose: initialCanClose,

    open: function () {
      this.isOpen = true;
    },

    close: function () {
      if (this.canClose) {
        this.isOpen = false;
        if (closeUrl) {
          window.location.href = closeUrl;
        } else if (refreshOnClose) {
          window.location.reload();
        }
      }
    },

    closeIfAllowed: function () {
      this.close();
    },

    setCanClose: function (value) {
      this.canClose = value;
    },
  };
}
