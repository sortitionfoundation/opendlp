// ABOUTME: Resolves which element the scroll-preservation helpers should measure
// ABOUTME: The window by default, or the takeover dialog's body when one is on the page

/**
 * A page takeover modal (e.g. the registration editor) locks the window scroll
 * and scrolls its own .dialog-body instead, so the ?scroll= round-trip must
 * read and restore that element's position rather than the window's.
 */
var TAKEOVER_SCROLLER_SELECTOR = ".dialog-panel--takeover .dialog-body";

/**
 * The current scroll offset of the page's main scroll container.
 *
 * @returns {number} scroll offset in pixels
 */
export function getPageScrollTop() {
  var takeoverBody = document.querySelector(TAKEOVER_SCROLLER_SELECTOR);
  return takeoverBody ? takeoverBody.scrollTop : window.scrollY;
}

/**
 * Scroll the page's main scroll container to the given offset.
 *
 * @param {number} position - scroll offset in pixels
 */
export function setPageScrollTop(position) {
  var takeoverBody = document.querySelector(TAKEOVER_SCROLLER_SELECTOR);
  if (takeoverBody) {
    takeoverBody.scrollTop = position;
  } else {
    window.scrollTo(0, position);
  }
}
