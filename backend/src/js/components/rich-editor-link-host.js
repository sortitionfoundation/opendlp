// ABOUTME: Alpine component hosting the visual editor's link dialog on a page of its own
// ABOUTME: For pages outside the registration editor, whose controller carries the same slice

import { readJsonScript } from "../lib/json-script.js";
import { richEditorLinkDialog } from "./rich-editor-link-dialog.js";

// The id of the <script type="application/json"> block holding the dialog's
// translated messages, rendered beside the dialog.
export const LINK_HOST_DATA_ID = "rich-editor-link-data";

/**
 * The link dialog slice on its own, with its messages read from the page.
 *
 * Put it on an element that listens for the editor's request -
 * `x-data="richEditorLinkHost" @rich-editor-link-request.document="openLinkDialog($event)"` -
 * and include components/rich_editor_link_modal.html inside it.
 */
export function richEditorLinkHost() {
  const data = readJsonScript(LINK_HOST_DATA_ID);
  return richEditorLinkDialog({ messages: data.messages || {} });
}
