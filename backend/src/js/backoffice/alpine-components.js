// ABOUTME: Entry point registering the Alpine components, magics and directives for the backoffice
// ABOUTME: Registration and wiring only - the behaviour lives under components/ and init/

import { autocomplete } from "../components/autocomplete.js";
import { autoDismissAlert } from "../components/auto-dismiss-alert.js";
import { bulkTargetsCategory } from "../components/bulk-targets-category.js";
import { bulkTargetsValueRow } from "../components/bulk-targets-value-row.js";
import { modal } from "../components/modal.js";
import { registrationPageRow } from "../components/registration-page-row.js";
import {
  buttonLoadingDemo,
  progressModalDemo,
} from "../components/showcase-demos.js";
import { showcaseNav } from "../components/showcase-nav.js";
import { tabsKeyboard } from "../components/tabs-keyboard.js";
import { urlSelect } from "../components/url-select.js";
import { registerFocusMagic } from "../init/focus-magic.js";
import { initFocusRestore } from "../init/focus-restore.js";
import { registerFormConfirm } from "../init/form-confirm.js";

initFocusRestore();

document.addEventListener("alpine:init", function () {
  registerFocusMagic();
  registerFormConfirm();

  Alpine.data("autocomplete", autocomplete);
  Alpine.data("autoDismissAlert", autoDismissAlert);
  Alpine.data("bulkTargetsCategory", bulkTargetsCategory);
  Alpine.data("bulkTargetsValueRow", bulkTargetsValueRow);
  Alpine.data("buttonLoadingDemo", buttonLoadingDemo);
  Alpine.data("modal", modal);
  Alpine.data("progressModalDemo", progressModalDemo);
  Alpine.data("registrationPageRow", registrationPageRow);
  Alpine.data("showcaseNav", showcaseNav);
  Alpine.data("tabsKeyboard", tabsKeyboard);
  Alpine.data("urlSelect", urlSelect);
});
