// ABOUTME: Tests for the link dialog host used on pages outside the registration editor.
// ABOUTME: Checks it reads its translated messages from the page's data block.
import { afterEach, describe, expect, it } from "vitest";
import {
  LINK_HOST_DATA_ID,
  richEditorLinkHost,
} from "./rich-editor-link-host.js";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("richEditorLinkHost", () => {
  it("refuses an empty address with the page's own message", () => {
    document.body.innerHTML = `<script type="application/json" id="${LINK_HOST_DATA_ID}">{"messages": {"linkUrlRequired": "Enter a link address"}}</script>`;
    const host = richEditorLinkHost();
    host.openLinkDialog({ detail: { editorId: "body", href: "" } });

    host.applyLink();

    expect(host.linkDialogOpen).toBe(true);
    expect(host.linkError).toBe("Enter a link address");
  });

  it("still works with no data block, just without messages", () => {
    const host = richEditorLinkHost();
    host.openLinkDialog({ detail: { editorId: "body", href: "" } });

    host.applyLink();

    expect(host.linkError).toBe("");
  });
});
