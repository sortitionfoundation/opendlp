// ABOUTME: Alpine components that drive the design-system showcase demonstrations
// ABOUTME: Simulated states only - no server calls, so the showcase page needs no backend

/**
 * Button loading-state demo for the design-system showcase.
 *
 * Toggles `saving` for a fixed duration so the button's loading state can be
 * triggered from a click without inlining setTimeout in an Alpine expression
 * (which the CSP build forbids).
 *
 * @returns {Object} Alpine component state
 */
export function buttonLoadingDemo() {
  return {
    saving: false,

    simulate: function () {
      var self = this;
      self.saving = true;
      setTimeout(function () {
        self.saving = false;
      }, 2000);
    },
  };
}

/**
 * Progress modal demo for the design-system showcase.
 *
 * Simulates the running / completed / failed task states without any server
 * polling.
 *
 * @returns {Object} Alpine component state
 */
export function progressModalDemo() {
  return {
    modalOpen: false,
    taskState: "running",
    messages: [
      "Loading configuration...",
      "Processing data...",
      "Running selection algorithm...",
    ],

    showRunning: function () {
      this.taskState = "running";
      this.modalOpen = true;
    },

    showCompleted: function () {
      this.taskState = "completed";
      this.modalOpen = true;
    },

    showFailed: function () {
      this.taskState = "failed";
      this.modalOpen = true;
    },

    closeModal: function () {
      this.modalOpen = false;
    },

    cancelTask: function () {
      this.taskState = "cancelled";
      this.modalOpen = false;
    },

    canClose: function () {
      return this.taskState !== "running";
    },

    isRunning: function () {
      return this.taskState === "running";
    },
  };
}
