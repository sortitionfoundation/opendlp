/**
 * ABOUTME: Alpine component powering the design-system showcase tab and jump-to-section nav
 * ABOUTME: Keeps the active tab and section in the URL so a position is shareable
 *
 * On init, restores the section from window.location.hash and switches to the
 * matching tab (read from the target's data-tab attribute).
 *
 * Usage:
 *   <div x-data="showcaseNav">
 *     <select x-model="selected" @change="goTo()">
 *       <option value="components:button">Button</option>
 *     </select>
 *     <div x-show="tab === 'components'">
 *       <div id="button" data-tab="components">...</div>
 *     </div>
 *   </div>
 */

/**
 * Build the showcaseNav component state.
 *
 * @returns {Object} Alpine component state
 */
export function showcaseNav() {
  return {
    tab: "components",
    selected: "",

    init: function () {
      var self = this;
      // Priority 1: hash points at a known section — its data-tab wins
      var hash = window.location.hash;
      if (hash && hash.length > 1) {
        var id = hash.substring(1);
        var el = document.getElementById(id);
        if (el && el.dataset && el.dataset.tab) {
          self.tab = el.dataset.tab;
          setTimeout(function () {
            self.scrollToSection(id);
          }, 50);
          self.writeUrl(id);
          return;
        }
      }
      // Priority 2: ?tab= query param
      var params = new URLSearchParams(window.location.search);
      var urlTab = params.get("tab");
      if (urlTab === "foundations" || urlTab === "components") {
        self.tab = urlTab;
      }
      self.writeUrl("");
    },

    setTab: function (newTab) {
      this.tab = newTab;
      this.selected = "";
      this.writeUrl("");
    },

    goTo: function () {
      var value = this.selected;
      if (!value) {
        return;
      }
      var sepIndex = value.indexOf(":");
      if (sepIndex === -1) {
        return;
      }
      this.tab = value.substring(0, sepIndex);
      var id = value.substring(sepIndex + 1);
      var self = this;
      setTimeout(function () {
        self.scrollToSection(id);
        self.writeUrl(id);
      }, 0);
    },

    scrollToSection: function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    },

    writeUrl: function (hashId) {
      if (!window.history.replaceState) {
        return;
      }
      var url = window.location.pathname + "?tab=" + this.tab;
      if (hashId) {
        url += "#" + hashId;
      }
      window.history.replaceState(null, "", url);
    },
  };
}
