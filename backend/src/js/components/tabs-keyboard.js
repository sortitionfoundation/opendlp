/**
 * ABOUTME: Alpine component providing WAI-ARIA keyboard navigation for tab lists
 * ABOUTME: Arrow Left/Right wrap around, Home/End jump to the ends
 *
 * Activation modes (per the WAI-ARIA APG):
 * - "automatic" (default): focus movement also activates the tab
 *   (synthesises a click). Suitable when panel switching is cheap.
 * - "manual": arrow keys only move focus. The user presses Enter or
 *   Space to activate the focused tab. Prefer this when tab activation
 *   causes a full page navigation, so arrow-key exploration doesn't
 *   trigger reload after reload.
 *
 * Usage:
 *   <ul role="tablist"
 *       x-data="tabsKeyboard({ activation: 'manual' })"
 *       @keydown="handleKeydown($event)">
 *     <li role="presentation">
 *       <a role="tab" href="?tab=one" tabindex="0">Tab 1</a>
 *     </li>
 *   </ul>
 */

/**
 * Build the tabsKeyboard component state.
 *
 * @param {Object} [config] - configuration
 * @param {string} [config.activation="automatic"] - "automatic" or "manual"
 * @returns {Object} Alpine component state
 */
export function tabsKeyboard(config) {
  var activation =
    config && config.activation === "manual" ? "manual" : "automatic";
  return {
    handleKeydown: function (event) {
      var key = event.key;

      // Only handle arrow keys, Home, and End
      if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(key) === -1) {
        return;
      }

      // Get all focusable tabs (exclude disabled)
      // Use event.currentTarget (the element with @keydown) to find tabs
      var tablist = event.currentTarget;
      var tabs = Array.prototype.slice.call(
        tablist.querySelectorAll('[role="tab"]:not([aria-disabled="true"])'),
      );

      if (tabs.length === 0) {
        return;
      }

      // Find current tab index
      var currentIndex = tabs.indexOf(document.activeElement);
      if (currentIndex === -1) {
        return;
      }

      var newIndex;

      if (key === "ArrowLeft") {
        // Move to previous tab, wrap to end
        newIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
      } else if (key === "ArrowRight") {
        // Move to next tab, wrap to start
        newIndex = currentIndex < tabs.length - 1 ? currentIndex + 1 : 0;
      } else if (key === "Home") {
        newIndex = 0;
      } else if (key === "End") {
        newIndex = tabs.length - 1;
      }

      if (newIndex !== undefined && newIndex !== currentIndex) {
        event.preventDefault();
        var targetTab = tabs[newIndex];
        targetTab.focus();
        if (activation === "automatic") {
          // Follow the link when focus moves
          targetTab.click();
        }
        // Manual mode: focus only, wait for Enter/Space to activate
      }
    },
  };
}
