// ABOUTME: Keyboard focus for the fragment dialogs HTMX swaps into a [data-fragment-dialog-host]
// ABOUTME: Focus goes in on open, stays put through re-renders, returns to the opener on close; what is behind goes inert

/**
 * A fragment dialog is server-rendered markup swapped into a host element:
 *
 *   <div id="ts-modal-container" data-fragment-dialog-host>...</div>
 *
 * The dialog is open while the host contains a [role="dialog"], and closed
 * when a later swap leaves the host empty. Nothing else marks the two states,
 * so this module reads them off the host around every swap:
 *
 * - opening moves focus to the dialog's first control, and remembers the element
 *   whose request opened it;
 * - a re-render of an open dialog (the set-up dialog re-renders on every
 *   choice) puts focus back on the control that had it, found by id, or by
 *   name and value for a radio button or checkbox without one;
 * - while a dialog is open the host's siblings - the step dialog it sits over -
 *   are inert, so Tab cannot reach what is underneath;
 * - closing returns focus to the opener. The swap that closes a dialog usually
 *   replaces the list the opener was in, so the opener is found again by its
 *   data-focus-id. One without - a menu item, a form - borrows the
 *   data-focus-id of the marked control in its [data-focus-row]. Failing both,
 *   its id.
 *
 * A dialog also closes through plain links (Cancel, the X, the backdrop), which
 * load the page afresh. Those get `#focus=<data-focus-id>` added, which
 * init/focus-restore.js reads after the load.
 */

var HOST_SELECTOR = "[data-fragment-dialog-host]";
var INERT_MARK = "data-inert-by-fragment-dialog";
var FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]",
]
  .map(function (selector) {
    return selector + ':not([tabindex="-1"])';
  })
  .join(", ");

// Per host: what opened its dialog, what had focus before its latest swap, and
// whether a dialog was open then.
var openers = new WeakMap();
var heldFocus = new WeakMap();
var wasOpenBeforeSwap = new WeakMap();

function hostOf(element) {
  return element && element.closest ? element.closest(HOST_SELECTOR) : null;
}

function dialogIn(host) {
  return host.querySelector('[role="dialog"]');
}

function firstFocusable(root) {
  if (!root) return null;
  return root.querySelector(FOCUSABLE_SELECTOR);
}

/** The first of `elements` whose `attribute` is exactly `value` - no selector to escape. */
function withAttribute(elements, attribute, value) {
  for (var i = 0; i < elements.length; i++) {
    if ((elements[i].getAttribute(attribute) || "") === value) {
      return elements[i];
    }
  }
  return null;
}

function describeOpener(element) {
  if (!element || element === document.body) return null;
  var focusId = element.getAttribute("data-focus-id") || "";
  var row = element.closest("[data-focus-row]");
  if (!focusId && row) {
    // A menu item or a form in the row: come back to the row's marked control.
    var marked = row.querySelector("[data-focus-id]");
    focusId = marked ? marked.getAttribute("data-focus-id") : "";
  }
  return { id: element.id || "", focusId: focusId };
}

function findOpener(opener) {
  if (!opener) return null;
  if (opener.focusId) {
    var marked = withAttribute(
      document.querySelectorAll("[data-focus-id]"),
      "data-focus-id",
      opener.focusId,
    );
    if (marked) return marked;
  }
  return opener.id ? document.getElementById(opener.id) : null;
}

function describeControl(element) {
  return {
    id: element.id || "",
    name: element.getAttribute("name") || "",
    value: element.getAttribute("value") || "",
  };
}

function findControl(host, control) {
  if (control.id) {
    var byId = document.getElementById(control.id);
    if (byId && host.contains(byId)) return byId;
  }
  if (!control.name) return null;
  var named = [];
  var candidates = host.querySelectorAll("[name]");
  for (var i = 0; i < candidates.length; i++) {
    if (candidates[i].getAttribute("name") === control.name) {
      named.push(candidates[i]);
    }
  }
  return withAttribute(named, "value", control.value) || named[0] || null;
}

/**
 * Make everything beside an open dialog's host inert, and undo exactly that
 * when it closes - an element that was inert already is left alone.
 */
function syncInert(host, isOpen) {
  var siblings = host.parentElement ? host.parentElement.children : [];
  for (var i = 0; i < siblings.length; i++) {
    var sibling = siblings[i];
    if (sibling === host) continue;
    if (isOpen && !sibling.hasAttribute("inert")) {
      sibling.setAttribute("inert", "");
      sibling.setAttribute(INERT_MARK, "");
    } else if (!isOpen && sibling.hasAttribute(INERT_MARK)) {
      sibling.removeAttribute("inert");
      sibling.removeAttribute(INERT_MARK);
    }
  }
}

/** Point the dialog's plain close links at the opener, for after the page load. */
function tagCloseLinks(host, opener) {
  if (!opener || !opener.focusId) return;
  var links = host.querySelectorAll("a[href]");
  for (var i = 0; i < links.length; i++) {
    var href = links[i].getAttribute("href");
    if (href.indexOf("#") === -1) {
      links[i].setAttribute("href", href + "#focus=" + opener.focusId);
    }
  }
}

function focusInto(host) {
  var dialog = dialogIn(host);
  var target =
    dialog.querySelector("[data-dialog-initial-focus]") ||
    firstFocusable(dialog.querySelector(".dialog-body")) ||
    firstFocusable(dialog);
  if (target) target.focus();
}

/** A request aimed at a closed host is what opens its dialog: remember what sent it. */
function beforeRequest(host, sender) {
  if (!dialogIn(host)) openers.set(host, describeOpener(sender));
}

function beforeSwap(host) {
  var active = document.activeElement;
  var wasOpen = Boolean(dialogIn(host));
  wasOpenBeforeSwap.set(host, wasOpen);
  heldFocus.set(
    host,
    wasOpen && host.contains(active) ? describeControl(active) : null,
  );
}

function afterSwap(host) {
  var wasOpen = Boolean(wasOpenBeforeSwap.get(host));
  var isOpen = Boolean(dialogIn(host));
  syncInert(host, isOpen);

  if (!isOpen) {
    if (wasOpen) {
      var opener = findOpener(openers.get(host));
      if (opener) opener.focus();
    }
    openers.delete(host);
    return;
  }
  tagCloseLinks(host, openers.get(host));
  var held = wasOpen ? heldFocus.get(host) : null;
  var control = held ? findControl(host, held) : null;
  if (control) {
    control.focus();
  } else {
    focusInto(host);
  }
}

/** A full page load can arrive with a dialog already open in its host. */
export function focusDialogsOpenOnLoad() {
  var hosts = document.querySelectorAll(HOST_SELECTOR);
  for (var i = 0; i < hosts.length; i++) {
    if (dialogIn(hosts[i])) {
      syncInert(hosts[i], true);
      focusInto(hosts[i]);
    }
  }
}

export function initFragmentDialogFocus() {
  document.addEventListener("DOMContentLoaded", function () {
    focusDialogsOpenOnLoad();

    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var host = hostOf(event.detail.target);
      if (host && host === event.detail.target) {
        beforeRequest(host, event.detail.elt);
      }
    });
    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var host = hostOf(event.detail.target);
      if (host && host === event.detail.target) beforeSwap(host);
    });
    document.body.addEventListener("htmx:afterSettle", function (event) {
      var host = hostOf(event.detail.target);
      if (host && host === event.detail.target) afterSwap(host);
    });
  });
}
