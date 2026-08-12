// ABOUTME: Fetch helpers for our JSON routes, carrying the CSRF token every request needs
// ABOUTME: Resolve to {ok, status, data}; a network failure rejects so callers can say so

/**
 * Send a request and resolve with its parsed body.
 *
 * An unparsable body becomes `{}` rather than an error: an error response can
 * be a proxy's HTML page, and a successful DELETE has no body at all, and in
 * neither case does the caller learn anything useful from the parse failure.
 * A network failure does reject, because "the request never happened" is a
 * different message to the user than "the server said no".
 *
 * @param {string} url - the URL to request
 * @param {Object} options - fetch options
 * @returns {Promise<{ok: boolean, status: number, data: Object}>}
 */
function send(url, options) {
  return fetch(url, options).then(function (response) {
    return response
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
  });
}

/**
 * POST a FormData body - a file upload.
 *
 * Deliberately sets no Content-Type: the browser has to supply it, because only
 * the browser knows the multipart boundary it generated.
 *
 * @param {string} url - the URL to post to
 * @param {FormData} formData - the body
 * @param {string} csrfToken - the CSRF token for the session
 * @returns {Promise<{ok: boolean, status: number, data: Object}>}
 */
export function postFormData(url, formData, csrfToken) {
  return send(url, {
    method: "POST",
    headers: { "X-CSRFToken": csrfToken },
    body: formData,
  });
}

/**
 * PATCH a resource with a JSON payload.
 *
 * @param {string} url - the resource URL
 * @param {Object} payload - the fields to change
 * @param {string} csrfToken - the CSRF token for the session
 * @returns {Promise<{ok: boolean, status: number, data: Object}>}
 */
export function patchJson(url, payload, csrfToken) {
  return send(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify(payload),
  });
}

/**
 * DELETE a resource.
 *
 * @param {string} url - the resource URL
 * @param {string} csrfToken - the CSRF token for the session
 * @returns {Promise<{ok: boolean, status: number, data: Object}>}
 */
export function deleteResource(url, csrfToken) {
  return send(url, {
    method: "DELETE",
    headers: { "X-CSRFToken": csrfToken },
  });
}
