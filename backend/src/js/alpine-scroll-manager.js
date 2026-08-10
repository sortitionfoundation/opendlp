/**
 * ABOUTME: Global scroll position preservation for page reloads
 * ABOUTME: Preserves scroll on navigation, restores on load, then cleans URL
 *
 * Usage:
 *   <a :href="$preserveScroll('/some/url')">Link</a>
 *   <form :action="$preserveScroll('/submit')" method="post">
 *   <div x-scroll-preserve-links><!-- auto-apply to all links --></div>
 *
 * Philosophy:
 *   - Scroll parameter is EPHEMERAL (exists only during transition)
 *   - URL-based state (testable, shareable, bookmarkable)
 *   - Zero configuration required
 *   - CSP-safe (no inline scripts)
 */

import {
  initScrollParamCleanup,
  restoreScrollFromUrl,
} from "./init/scroll-restore.js";
import { registerScrollMagic } from "./init/scroll-magic.js";

restoreScrollFromUrl();

document.addEventListener("alpine:init", registerScrollMagic);

initScrollParamCleanup();
