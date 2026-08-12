// ABOUTME: Formats a byte count as a short human-readable size
// ABOUTME: Used by the asset panels to label uploaded images and documents

const KB = 1024;
const MB = 1024 * 1024;

/**
 * Render a byte count as B, KB or MB.
 *
 * @param {number} bytes - the size in bytes
 * @returns {string} the formatted size, or an empty string if bytes is not a finite number
 */
export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < KB) return bytes + " B";
  if (bytes < MB) return (bytes / KB).toFixed(1) + " KB";
  return (bytes / MB).toFixed(2) + " MB";
}
