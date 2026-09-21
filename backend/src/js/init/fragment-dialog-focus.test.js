// ABOUTME: Unit tests for keyboard focus in the fragment dialogs HTMX swaps into a host
// ABOUTME: Covers focus on open, through a re-render, back to the opener on close, inert siblings, tagged close links and self-closing modals

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  focusDialogsOpenOnLoad,
  initFragmentDialogFocus,
} from "./fragment-dialog-focus.js";

const DIALOG = `
  <a class="dialog-backdrop dialog-backdrop--clickable" href="/sources" tabindex="-1" aria-hidden="true"></a>
  <div role="dialog" aria-modal="true">
    <a class="dialog-close-btn" href="/sources">Close</a>
    <div class="dialog-body">
      <input type="radio" name="method" value="exact">
      <input type="radio" name="method" value="age_bracket">
      <select id="reuse-field"><option>One</option></select>
    </div>
    <a id="cancel" href="/sources">Cancel</a>
  </div>`;

function fire(name, target, elt) {
  target.dispatchEvent(
    new CustomEvent(name, {
      bubbles: true,
      detail: { target: target, elt: elt || target },
    }),
  );
}

/** What HTMX does around a swap into `host`, with `html` as the response. */
function swap(host, html, sender) {
  fire("htmx:beforeRequest", host, sender);
  fire("htmx:beforeSwap", host, sender);
  host.innerHTML = html;
  fire("htmx:afterSettle", host, sender);
}

function page() {
  document.body.innerHTML = `
    <div id="overlay">
      <div id="step-dialog">
        <ul>
          <li data-focus-row="row-1">
            <a id="edit-1" data-focus-id="ts-row-1" href="/setup/1">Edit</a>
            <a id="menu-upload-1" role="menuitem" tabindex="-1" href="/upload/1">Re-upload table</a>
          </li>
        </ul>
        <button type="button" id="add">Add a question</button>
      </div>
      <div id="already-inert" inert></div>
      <div id="host" data-fragment-dialog-host></div>
    </div>`;
  return document.getElementById("host");
}

describe("initFragmentDialogFocus", () => {
  // One shared document per test file, so register the listeners exactly once.
  beforeAll(() => {
    initFragmentDialogFocus();
    document.dispatchEvent(new Event("DOMContentLoaded"));
  });

  let host;
  beforeEach(() => {
    host = page();
  });

  it("moves focus to the first control in the dialog's body when it opens", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));

    expect(document.activeElement).toBe(
      host.querySelector('[name="method"][value="exact"]'),
    );
  });

  it("prefers a control marked for initial focus", () => {
    swap(
      host,
      DIALOG.replace(
        'id="reuse-field"',
        'id="reuse-field" data-dialog-initial-focus',
      ),
      document.getElementById("edit-1"),
    );

    expect(document.activeElement.id).toBe("reuse-field");
  });

  it("keeps focus on a control with an id through a re-render", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));
    const select = document.getElementById("reuse-field");
    select.focus();

    swap(host, DIALOG, select);

    expect(document.activeElement).not.toBe(select);
    expect(document.activeElement.id).toBe("reuse-field");
  });

  it("keeps focus on the same radio button, found by name and value, through a re-render", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));
    const radio = host.querySelector('[name="method"][value="age_bracket"]');
    radio.focus();

    swap(host, DIALOG, radio);

    expect(document.activeElement.getAttribute("value")).toBe("age_bracket");
  });

  it("makes what is beside the host inert while a dialog is open, and only undoes its own work", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));

    expect(document.getElementById("step-dialog").hasAttribute("inert")).toBe(
      true,
    );
    expect(host.hasAttribute("inert")).toBe(false);

    swap(host, "", host.querySelector("#cancel"));

    expect(document.getElementById("step-dialog").hasAttribute("inert")).toBe(
      false,
    );
    expect(document.getElementById("already-inert").hasAttribute("inert")).toBe(
      true,
    );
  });

  it("returns focus to the opener when the dialog closes, though the list was replaced", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));
    // The closing response replaces the checklist out of band.
    const list = document.querySelector("ul");
    list.innerHTML = list.innerHTML.replace('id="edit-1"', 'id="edit-1-again"');

    swap(host, "", host.querySelector("#cancel"));

    expect(document.activeElement.id).toBe("edit-1-again");
  });

  it("returns focus to the row's marked control when a menu item opened the dialog", () => {
    swap(host, DIALOG, document.getElementById("menu-upload-1"));

    swap(host, "", host.querySelector("#cancel"));

    expect(document.activeElement.id).toBe("edit-1");
  });

  it("returns focus by id to an opener outside any row", () => {
    swap(host, DIALOG, document.getElementById("add"));

    swap(host, "", host.querySelector("#cancel"));

    expect(document.activeElement.id).toBe("add");
  });

  it("points the dialog's plain close links at the opener, for the page load they cause", () => {
    swap(host, DIALOG, document.getElementById("edit-1"));

    expect(host.querySelector("#cancel").getAttribute("href")).toBe(
      "/sources#focus=ts-row-1",
    );
    expect(host.querySelector(".dialog-close-btn").getAttribute("href")).toBe(
      "/sources#focus=ts-row-1",
    );
  });

  it("leaves swaps into anything but a host alone", () => {
    const step = document.getElementById("step-dialog");
    document.getElementById("add").focus();

    swap(step, step.innerHTML + "<p>refreshed</p>", step);

    expect(step.hasAttribute("inert")).toBe(false);
  });

  it("tries focus again after paint when the dialog is still hidden", () => {
    // A hidden control refuses focus: the first attempt takes, the rest do not.
    const realFocus = HTMLElement.prototype.focus;
    let attempts = 0;
    const focus = vi
      .spyOn(HTMLElement.prototype, "focus")
      .mockImplementation(function () {
        attempts += 1;
        if (attempts > 1) realFocus.call(this);
      });
    const frame = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((callback) => callback());

    swap(host, DIALOG, document.getElementById("add"));

    expect(frame).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(
      host.querySelector('[name="method"][value="exact"]'),
    );
    focus.mockRestore();
    frame.mockRestore();
  });

  it("clears away an Alpine modal that closed itself, and undoes what opening did", () => {
    swap(host, DIALOG, document.getElementById("add"));

    host
      .querySelector('[role="dialog"]')
      .dispatchEvent(new CustomEvent("modal-closed", { bubbles: true }));

    expect(host.innerHTML).toBe("");
    expect(document.getElementById("step-dialog").hasAttribute("inert")).toBe(
      false,
    );
    expect(document.activeElement.id).toBe("add");
  });

  it("ignores a modal closing outside any host", () => {
    document.getElementById("add").focus();

    document
      .getElementById("step-dialog")
      .dispatchEvent(new CustomEvent("modal-closed", { bubbles: true }));

    expect(document.getElementById("step-dialog").innerHTML).toContain("Edit");
  });

  it("moves focus into a dialog that was already open when the page loaded", () => {
    host.innerHTML = DIALOG;

    focusDialogsOpenOnLoad();

    expect(document.activeElement).toBe(
      host.querySelector('[name="method"][value="exact"]'),
    );
    expect(document.getElementById("step-dialog").hasAttribute("inert")).toBe(
      true,
    );
  });
});
