// ABOUTME: Alpine component pinning an element just under the page's sticky header as the page scrolls
// ABOUTME: Follows the header's height, which changes with the page title and the window width

/**
 * Keep the element's `top` at the height of the sticky header, so it sticks
 * right under it rather than behind it. The header's height is not a constant
 * worth writing into the CSS: a long project title wraps, and so do the tabs
 * on a narrow screen. The position and look are `.sticky-below-header`'s.
 *
 * The header is the element marked `data-sticky-header`. Without one the
 * element sticks to the top of the window.
 *
 * The page's scroll padding is kept at the header and the element together,
 * so a field the browser scrolls to on focus lands below both of them rather
 * than hidden underneath.
 *
 * @returns {Object} Alpine component state
 */
export function stickyBelowHeader() {
  return {
    observer: null,

    init: function () {
      var header = document.querySelector("[data-sticky-header]");
      if (!header) return;
      var element = this.$el;
      var place = function () {
        element.style.top = header.offsetHeight + "px";
        document.documentElement.style.scrollPaddingTop =
          header.offsetHeight + element.offsetHeight + "px";
      };
      place();
      if (typeof ResizeObserver === "undefined") return;
      this.observer = new ResizeObserver(place);
      this.observer.observe(header);
      this.observer.observe(element);
    },

    destroy: function () {
      if (this.observer) this.observer.disconnect();
      document.documentElement.style.scrollPaddingTop = "";
    },
  };
}
