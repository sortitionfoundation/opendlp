// ABOUTME: Reads a file chosen in an <input type="file"> as base64
// ABOUTME: Strips the data-URL prefix, so the payload is what a JSON body wants

/**
 * Read a file as base64, without the `data:<mime>;base64,` prefix.
 *
 * `FileReader.readAsDataURL` is the only way to get base64 out of a File, and it
 * always prefixes the payload with the data URL header. A caller sending the bytes
 * in a JSON body wants the payload alone, every time, so the strip belongs here
 * rather than at each call site.
 *
 * @param {File|null} file - the chosen file, or null if the picker was dismissed
 * @returns {Promise<string>} the base64 payload, or "" when there is no file
 */
export function readFileAsBase64(file) {
  if (!file) return Promise.resolve("");

  return new Promise(function (resolve, reject) {
    var reader = new FileReader();

    reader.onload = function () {
      var result = String(reader.result || "");
      var separator = result.indexOf(",");
      resolve(separator >= 0 ? result.slice(separator + 1) : result);
    };
    reader.onerror = function () {
      reject(reader.error || new Error("Could not read the file"));
    };

    try {
      reader.readAsDataURL(file);
    } catch (err) {
      // readAsDataURL raises synchronously on a value that is not a Blob, which
      // onerror never sees - without this the promise would hang for ever.
      reject(err);
    }
  });
}
