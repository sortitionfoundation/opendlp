// ABOUTME: Entry point that configures HTMX to swap content on 422 responses
// ABOUTME: Loaded on every page so inline validation error markup is displayed

import { initHtmx422Swap } from "./init/htmx-422-swap.js";

initHtmx422Swap();
