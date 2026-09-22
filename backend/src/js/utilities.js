// ABOUTME: Entry point for the site-wide utility behaviours loaded on every page
// ABOUTME: Wires up navigation, confirm/print/copy/download actions and progress modals

import { initNavigation } from "./init/navigation.js";
import { initDocumentActions } from "./init/document-actions.js";
import { initProgressModals } from "./init/progress-modals.js";
import { initDialogEscape } from "./init/dialog-escape.js";
import { initFragmentDialogFocus } from "./init/fragment-dialog-focus.js";

initNavigation();
initDocumentActions();
initProgressModals();
initDialogEscape();
initFragmentDialogFocus();
