/**
 * ABOUTME: Alpine component demonstrating client-side file selection on the patterns page
 * ABOUTME: Validates the extension, formats the size, and previews the first 200 characters
 *
 * Demo only - it never uploads anything. The real pattern it documents is a plain
 * multipart form POST; see the File Upload tab for the template and route code.
 *
 * Usage:
 *   <div x-data="fileUploadDemo()">
 *     <input type="file" accept=".csv" @change="onFileSelect($event)">
 *     <p x-text="error"></p>
 *     <p x-text="fileName"></p>
 *     <p x-text="fileSize"></p>
 *     <pre x-text="preview"></pre>
 *   </div>
 */

const PREVIEW_CHARS = 200;

/**
 * Format a byte count for display.
 *
 * @param {number} bytes - size in bytes
 * @returns {string} a human-readable size
 */
export function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " bytes";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

/**
 * Build the fileUploadDemo component state.
 *
 * @returns {Object} Alpine component state
 */
export function fileUploadDemo() {
  return {
    fileName: "",
    fileSize: "",
    preview: "",
    error: "",

    formatFileSize: formatFileSize,

    onFileSelect: function (event) {
      var file = event.target.files[0];
      this.error = "";
      this.preview = "";

      if (!file) {
        this.fileName = "";
        this.fileSize = "";
        return;
      }

      if (!file.name.endsWith(".csv")) {
        this.error = "Please select a CSV file";
        this.fileName = "";
        this.fileSize = "";
        event.target.value = "";
        return;
      }

      this.fileName = file.name;
      this.fileSize = formatFileSize(file.size);

      var self = this;
      var reader = new FileReader();
      reader.onload = function (e) {
        var content = e.target.result;
        self.preview =
          content.substring(0, PREVIEW_CHARS) +
          (content.length > PREVIEW_CHARS ? "..." : "");
      };
      reader.readAsText(file);
    },

    handleSubmit: function () {
      alert(
        'Demo: Would submit file "' +
          this.fileName +
          '" to server.\n\nIn real implementation, form would POST to server with enctype="multipart/form-data".',
      );
    },
  };
}
