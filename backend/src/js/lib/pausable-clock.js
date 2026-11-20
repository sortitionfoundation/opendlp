// ABOUTME: A clock whose waits count only the time it runs: a hold freezes every pending wait where it is,
// ABOUTME: and once the last hold is released they run on from there

/**
 * A clock for a timeline that has to stop and later carry on from where it
 * stopped, rather than start again.
 *
 * `sleep(ms)` resolves once the clock has run for `ms`. `hold(reason)` stops
 * the clock, and `release(reason)` starts it again only when no other reason
 * still holds it - so two independent reasons, such as a visitor's pause and
 * the page scrolled away, never undo each other. Holding twice for the same
 * reason is one hold.
 *
 * `onChange(running)` is told each time the clock stops (`false`) or starts
 * again (`true`), for what the clock cannot freeze by itself, such as
 * animations already running.
 *
 * @param {Object} [options]
 * @param {function(boolean): void} [options.onChange] called when the clock stops or starts
 * @param {function(): number} [options.now] the current time in milliseconds
 * @returns {{sleep: function(number): Promise<void>, hold: function(string): void,
 *            release: function(string): void, isHeld: function(string): boolean, running: boolean}}
 */
export function pausableClock({
  onChange = () => {},
  now = () => performance.now(),
} = {}) {
  const holds = new Set();
  const waits = new Set();
  const running = () => holds.size === 0;

  const start = (wait) => {
    wait.startedAt = now();
    wait.timer = setTimeout(() => {
      waits.delete(wait);
      wait.resolve();
    }, wait.remaining);
  };
  const stop = (wait) => {
    clearTimeout(wait.timer);
    wait.remaining = Math.max(0, wait.remaining - (now() - wait.startedAt));
  };

  return {
    get running() {
      return running();
    },
    sleep(ms) {
      return new Promise((resolve) => {
        const wait = { remaining: ms, resolve };
        waits.add(wait);
        if (running()) start(wait);
      });
    },
    hold(reason) {
      if (holds.has(reason)) return;
      const wasRunning = running();
      holds.add(reason);
      if (!wasRunning) return;
      waits.forEach(stop);
      onChange(false);
    },
    release(reason) {
      if (!holds.delete(reason) || !running()) return;
      waits.forEach(start);
      onChange(true);
    },
    isHeld(reason) {
      return holds.has(reason);
    },
  };
}
