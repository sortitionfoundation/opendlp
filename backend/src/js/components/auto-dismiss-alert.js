/**
 * ABOUTME: Alpine component for an alert that hides itself after a delay
 * ABOUTME: The countdown pauses while the pointer is over the alert and resumes on leave
 *
 * Registered as a component because the CSP Alpine build forbids inline
 * setTimeout in x-* expressions.
 *
 * Usage:
 *   <div x-data="autoDismissAlert({ duration: 4000 })" x-show="show" x-transition
 *        @mouseenter="pause()" @mouseleave="resume()">
 *     ...
 *     <button @click="show = false">Close</button>
 *   </div>
 */

/**
 * Build the autoDismissAlert component state.
 *
 * @param {Object} [options] - configuration
 * @param {number} [options.duration=0] - milliseconds before auto-dismissal; 0 never dismisses
 * @returns {Object} Alpine component state
 */
export function autoDismissAlert(options) {
  var duration = (options && options.duration) || 0;
  return {
    show: true,
    remaining: duration,
    timer: null,
    startedAt: 0,

    init: function () {
      if (duration > 0) {
        this.startTimer();
      }
    },

    startTimer: function () {
      var self = this;
      self.startedAt = Date.now();
      self.timer = setTimeout(function () {
        self.show = false;
        self.timer = null;
      }, self.remaining);
    },

    pause: function () {
      if (this.timer) {
        clearTimeout(this.timer);
        this.timer = null;
        this.remaining -= Date.now() - this.startedAt;
      }
    },

    resume: function () {
      if (duration > 0 && !this.timer && this.remaining > 0) {
        this.startTimer();
      }
    },
  };
}
