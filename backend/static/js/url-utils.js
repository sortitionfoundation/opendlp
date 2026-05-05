// ABOUTME: Reusable utilities for URL query parameter manipulation
// ABOUTME: Provides functions to add, set, remove, and build URL parameters safely

/**
 * URL Parameter Utilities
 *
 * These functions provide safe manipulation of URL query parameters,
 * correctly handling URLs that already have existing parameters.
 *
 * All functions work with both absolute and relative URLs.
 */

/**
 * Add or update a single query parameter in a URL.
 * If the parameter already exists, it will be updated.
 *
 * @param {string} url - The URL to modify
 * @param {string} name - The parameter name
 * @param {string} value - The parameter value
 * @returns {string} The URL with the parameter added/updated
 *
 * @example
 * urlSetParam('/page?tab=1', 'filter', 'active')
 * // Returns: '/page?tab=1&filter=active'
 *
 * urlSetParam('/page', 'filter', 'active')
 * // Returns: '/page?filter=active'
 */
function urlSetParam(url, name, value) {
  if (!url) return url;

  // Handle relative URLs by using a dummy base
  var isRelative = !url.startsWith("http://") && !url.startsWith("https://");
  var fullUrl = isRelative
    ? "http://dummy" + (url.startsWith("/") ? "" : "/") + url
    : url;

  try {
    var urlObj = new URL(fullUrl);
    urlObj.searchParams.set(name, value);

    if (isRelative) {
      // Return just the path + search + hash
      return urlObj.pathname + urlObj.search + urlObj.hash;
    }
    return urlObj.toString();
  } catch (e) {
    // Fallback for malformed URLs: use simple string concatenation
    var separator = url.includes("?") ? "&" : "?";
    return (
      url +
      separator +
      encodeURIComponent(name) +
      "=" +
      encodeURIComponent(value)
    );
  }
}

/**
 * Remove a query parameter from a URL.
 *
 * @param {string} url - The URL to modify
 * @param {string} name - The parameter name to remove
 * @returns {string} The URL with the parameter removed
 *
 * @example
 * urlRemoveParam('/page?tab=1&filter=active', 'filter')
 * // Returns: '/page?tab=1'
 */
function urlRemoveParam(url, name) {
  if (!url) return url;

  var isRelative = !url.startsWith("http://") && !url.startsWith("https://");
  var fullUrl = isRelative
    ? "http://dummy" + (url.startsWith("/") ? "" : "/") + url
    : url;

  try {
    var urlObj = new URL(fullUrl);
    urlObj.searchParams.delete(name);

    if (isRelative) {
      return urlObj.pathname + urlObj.search + urlObj.hash;
    }
    return urlObj.toString();
  } catch (e) {
    // Fallback: return original URL unchanged
    return url;
  }
}

/**
 * Get a query parameter value from a URL.
 *
 * @param {string} url - The URL to parse
 * @param {string} name - The parameter name to get
 * @returns {string|null} The parameter value, or null if not found
 *
 * @example
 * urlGetParam('/page?tab=1&filter=active', 'filter')
 * // Returns: 'active'
 */
function urlGetParam(url, name) {
  if (!url) return null;

  var isRelative = !url.startsWith("http://") && !url.startsWith("https://");
  var fullUrl = isRelative
    ? "http://dummy" + (url.startsWith("/") ? "" : "/") + url
    : url;

  try {
    var urlObj = new URL(fullUrl);
    return urlObj.searchParams.get(name);
  } catch (e) {
    return null;
  }
}

/**
 * Check if a URL has a specific query parameter.
 *
 * @param {string} url - The URL to check
 * @param {string} name - The parameter name to check for
 * @returns {boolean} True if the parameter exists
 */
function urlHasParam(url, name) {
  if (!url) return false;

  var isRelative = !url.startsWith("http://") && !url.startsWith("https://");
  var fullUrl = isRelative
    ? "http://dummy" + (url.startsWith("/") ? "" : "/") + url
    : url;

  try {
    var urlObj = new URL(fullUrl);
    return urlObj.searchParams.has(name);
  } catch (e) {
    return false;
  }
}

/**
 * Add multiple query parameters to a URL.
 * Existing parameters with the same names will be updated.
 *
 * @param {string} url - The URL to modify
 * @param {Object} params - Object with parameter name/value pairs
 * @returns {string} The URL with all parameters added/updated
 *
 * @example
 * urlSetParams('/page?tab=1', {filter: 'active', page: '2'})
 * // Returns: '/page?tab=1&filter=active&page=2'
 */
function urlSetParams(url, params) {
  if (!url) return url;
  if (!params || typeof params !== "object") return url;

  var result = url;
  for (var name in params) {
    if (Object.prototype.hasOwnProperty.call(params, name)) {
      result = urlSetParam(result, name, params[name]);
    }
  }
  return result;
}

/**
 * Build a URL by appending a path and optional parameters to a base URL.
 * This is useful for constructing URLs dynamically.
 *
 * @param {string} baseUrl - The base URL
 * @param {Object} [params] - Optional object with parameter name/value pairs
 * @returns {string} The constructed URL
 *
 * @example
 * urlBuild('/api/users', {page: '1', sort: 'name'})
 * // Returns: '/api/users?page=1&sort=name'
 */
function urlBuild(baseUrl, params) {
  if (!params || typeof params !== "object") return baseUrl;
  return urlSetParams(baseUrl, params);
}
