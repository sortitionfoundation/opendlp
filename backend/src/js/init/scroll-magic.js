// ABOUTME: Alpine magic $preserveScroll and directive x-scroll-preserve-links
// ABOUTME: Adds the current scroll position to a URL so it survives a page reload

import { urlSetParam } from "../lib/url-utils.js";

/**
 * Register the scroll-preservation magic and directive on Alpine.
 *
 * Call from an alpine:init listener.
 */
export function registerScrollMagic() {
  /**
   * Magic: $preserveScroll
   *
   * Adds current scroll position to a URL for preservation across page reload.
   *
   * @example
   * <a :href="$preserveScroll('/page?foo=bar')">Link</a>
   * Result: /page?foo=bar&scroll=1250
   */
  Alpine.magic("preserveScroll", () => {
    return (url) => {
      if (!url) return url;

      const currentScroll = Math.round(window.scrollY);
      return urlSetParam(url, "scroll", currentScroll.toString());
    };
  });

  /**
   * Directive: x-scroll-preserve-links
   *
   * Auto-applies scroll preservation to all links within an element.
   * Links can opt-out with data-no-scroll-preserve attribute.
   *
   * @example
   * <nav x-scroll-preserve-links>
   *   <a href="/page1">Auto-preserved</a>
   *   <a href="/page2" data-no-scroll-preserve>Not preserved</a>
   * </nav>
   */
  Alpine.directive("scroll-preserve-links", (el) => {
    el.addEventListener(
      "click",
      (e) => {
        const link = e.target.closest("a[href]");

        // Skip if no link, or link opts out
        if (!link || link.hasAttribute("data-no-scroll-preserve")) {
          return;
        }

        // Skip external links and hash links
        const href = link.getAttribute("href");
        if (href.startsWith("http") || href.startsWith("#")) {
          return;
        }

        // Add scroll parameter using URL utilities
        const currentScroll = Math.round(window.scrollY);
        link.setAttribute(
          "href",
          urlSetParam(href, "scroll", currentScroll.toString()),
        );
      },
      true,
    ); // Use capture phase to run before navigation
  });
}
