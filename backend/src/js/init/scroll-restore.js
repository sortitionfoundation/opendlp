// ABOUTME: Restores scroll position from the ephemeral ?scroll= parameter, then cleans the URL
// ABOUTME: The parameter exists only during a transition, so it is removed as soon as it is used

/**
 * Restore the scroll position named by ?scroll= and strip the parameter.
 *
 * Runs as early as possible: immediately if the DOM is already parsed,
 * otherwise on DOMContentLoaded.
 */
export function restoreScrollFromUrl() {
  const urlParams = new URLSearchParams(window.location.search);
  const scrollPos = urlParams.get("scroll");

  if (!scrollPos) return;

  const restoreScroll = () => {
    // Restore scroll position
    window.scrollTo(0, parseInt(scrollPos, 10));

    // Immediately clean URL (remove scroll parameter)
    const url = new URL(window.location.href);
    url.searchParams.delete("scroll");
    window.history.replaceState({}, "", url.toString());
  };

  // Execute as early as possible
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restoreScroll);
  } else {
    // DOM already loaded, restore immediately
    requestAnimationFrame(restoreScroll);
  }
}

/**
 * Safety net: drop a lingering ?scroll= parameter once the user scrolls.
 *
 * The first scroll event after restoration is ignored, since that is the
 * restoration itself rather than the user.
 */
export function initScrollParamCleanup() {
  let scrollTimeout;
  let justRestored = true;

  const cleanupScrollParam = () => {
    const url = new URL(window.location.href);
    if (url.searchParams.has("scroll")) {
      url.searchParams.delete("scroll");
      window.history.replaceState({}, "", url.toString());
    }
  };

  window.addEventListener(
    "scroll",
    () => {
      // Skip cleanup immediately after restoration
      if (justRestored) {
        justRestored = false;
        return;
      }

      // Debounce: wait for scroll to settle
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(cleanupScrollParam, 150);
    },
    { passive: true },
  ); // Passive listener for better performance
}
