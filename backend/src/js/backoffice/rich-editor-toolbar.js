// ABOUTME: Wires the server-rendered visual editor toolbar to a Tiptap editor.
// ABOUTME: Runs each button's command, keeps aria-pressed in step, moves focus with the arrows, opens the table menu.

export const TOOLTIPS_DISMISSED_CLASS =
  "rich-editor__toolbar--tooltips-dismissed";

/**
 * What each `data-command` button does. `active` marks a toggle, whose
 * aria-pressed follows the selection; `enabled` marks a command that can be
 * unavailable, such as undo with nothing to undo.
 */
export const COMMANDS = {
  paragraph: {
    run: (chain) => chain.setParagraph(),
    active: (editor) => editor.isActive("paragraph"),
  },
  heading1: {
    run: (chain) => chain.toggleHeading({ level: 1 }),
    active: (editor) => editor.isActive("heading", { level: 1 }),
  },
  heading2: {
    run: (chain) => chain.toggleHeading({ level: 2 }),
    active: (editor) => editor.isActive("heading", { level: 2 }),
  },
  heading3: {
    run: (chain) => chain.toggleHeading({ level: 3 }),
    active: (editor) => editor.isActive("heading", { level: 3 }),
  },
  bold: {
    run: (chain) => chain.toggleBold(),
    active: (editor) => editor.isActive("bold"),
  },
  italic: {
    run: (chain) => chain.toggleItalic(),
    active: (editor) => editor.isActive("italic"),
  },
  underline: {
    run: (chain) => chain.toggleUnderline(),
    active: (editor) => editor.isActive("underline"),
  },
  strike: {
    run: (chain) => chain.toggleStrike(),
    active: (editor) => editor.isActive("strike"),
  },
  bulletList: {
    run: (chain) => chain.toggleBulletList(),
    active: (editor) => editor.isActive("bulletList"),
  },
  orderedList: {
    run: (chain) => chain.toggleOrderedList(),
    active: (editor) => editor.isActive("orderedList"),
  },
  blockquote: {
    run: (chain) => chain.toggleBlockquote(),
    active: (editor) => editor.isActive("blockquote"),
  },
  horizontalRule: {
    run: (chain) => chain.setHorizontalRule(),
  },
  // A plain table: no header row and no role, until the team decides whether
  // tables are for layout or data (Q6 in the plan).
  insertTable: {
    run: (chain) =>
      chain.insertTable({ rows: 2, cols: 2, withHeaderRow: false }),
    enabled: (editor) => !editor.isActive("table"),
  },
  addRowAfter: {
    run: (chain) => chain.addRowAfter(),
    enabled: (editor) => editor.can().addRowAfter(),
  },
  addColumnAfter: {
    run: (chain) => chain.addColumnAfter(),
    enabled: (editor) => editor.can().addColumnAfter(),
  },
  deleteRow: {
    run: (chain) => chain.deleteRow(),
    enabled: (editor) => editor.can().deleteRow(),
  },
  deleteColumn: {
    run: (chain) => chain.deleteColumn(),
    enabled: (editor) => editor.can().deleteColumn(),
  },
  deleteTable: {
    run: (chain) => chain.deleteTable(),
    enabled: (editor) => editor.can().deleteTable(),
  },
  undo: {
    run: (chain) => chain.undo(),
    enabled: (editor) => editor.can().undo(),
  },
  redo: {
    run: (chain) => chain.redo(),
    enabled: (editor) => editor.can().redo(),
  },
};

/**
 * Connect `toolbar` to `editor`.
 *
 * `actions` supplies the commands that leave the editor, such as opening the
 * link dialog: `{link: () => ..., image: () => ...}`. Returns `refresh()`,
 * which re-reads the editor state into the buttons.
 */
export function wireToolbar(toolbar, editor, actions = {}) {
  const commandButtons = Array.from(
    toolbar.querySelectorAll("button[data-command]"),
  );
  // The toolbar's own buttons; menu items are reached through their menu button.
  const buttons = commandButtons.filter(
    (button) => !button.closest('[role="menu"]'),
  );

  function refresh() {
    for (const button of commandButtons) {
      const command = COMMANDS[button.dataset.command];
      if (!command) {
        continue;
      }
      if (command.active) {
        button.setAttribute("aria-pressed", String(command.active(editor)));
      }
      if (command.enabled) {
        button.setAttribute("aria-disabled", String(!command.enabled(editor)));
      }
    }
  }

  function run(button) {
    if (button.getAttribute("aria-disabled") === "true") {
      return;
    }
    const name = button.dataset.command;
    if (actions[name]) {
      actions[name]();
      return;
    }
    const command = COMMANDS[name];
    if (command) {
      command.run(editor.chain().focus()).run();
      refresh();
    }
  }

  function showTooltips() {
    toolbar.classList.remove(TOOLTIPS_DISMISSED_CLASS);
  }

  function moveFocus(from, to) {
    from.setAttribute("tabindex", "-1");
    to.setAttribute("tabindex", "0");
    showTooltips();
    to.focus();
  }

  buttons.forEach((button, index) => {
    button.setAttribute("tabindex", index === 0 ? "0" : "-1");
    // Keep the editor's selection: a click must not move focus off the text first.
    button.addEventListener("mousedown", (event) => event.preventDefault());
    if (button.getAttribute("aria-haspopup") === "menu") {
      wireMenu(button, run);
    } else {
      button.addEventListener("click", () => run(button));
    }
    button.addEventListener("mouseenter", showTooltips);
    button.addEventListener("keydown", (event) => {
      // The first Escape only hides the tooltip; the next one is the dialog's.
      if (
        event.key === "Escape" &&
        !toolbar.classList.contains(TOOLTIPS_DISMISSED_CLASS)
      ) {
        event.preventDefault();
        event.stopPropagation();
        toolbar.classList.add(TOOLTIPS_DISMISSED_CLASS);
        return;
      }
      const last = buttons.length - 1;
      const targets = {
        ArrowRight: buttons[index === last ? 0 : index + 1],
        ArrowLeft: buttons[index === 0 ? last : index - 1],
        Home: buttons[0],
        End: buttons[last],
      };
      if (targets[event.key]) {
        event.preventDefault();
        moveFocus(button, targets[event.key]);
      }
    });
  });

  function wireMenu(menuButton, runItem) {
    const menu = document.getElementById(
      menuButton.getAttribute("aria-controls"),
    );
    const items = Array.from(menu.querySelectorAll('[role="menuitem"]'));

    function open(index) {
      refresh();
      menu.hidden = false;
      menuButton.setAttribute("aria-expanded", "true");
      items.at(index).focus();
    }

    function close() {
      menu.hidden = true;
      menuButton.setAttribute("aria-expanded", "false");
    }

    menuButton.addEventListener("click", () => {
      if (menu.hidden) {
        open(0);
      } else {
        close();
      }
    });
    menuButton.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        open(event.key === "ArrowDown" ? 0 : -1);
      }
    });
    menu.addEventListener("focusout", (event) => {
      if (!menu.contains(event.relatedTarget)) {
        close();
      }
    });

    items.forEach((item, index) => {
      item.setAttribute("tabindex", "-1");
      item.addEventListener("mousedown", (event) => event.preventDefault());
      item.addEventListener("click", () => {
        if (item.getAttribute("aria-disabled") === "true") {
          return;
        }
        close();
        runItem(item);
      });
      item.addEventListener("keydown", (event) => {
        const last = items.length - 1;
        const targets = {
          ArrowDown: items[index === last ? 0 : index + 1],
          ArrowUp: items[index === 0 ? last : index - 1],
          Home: items[0],
          End: items[last],
        };
        if (targets[event.key]) {
          event.preventDefault();
          targets[event.key].focus();
        } else if (event.key === "Escape") {
          // Close only the menu, not a dialog the editor sits in.
          event.preventDefault();
          event.stopPropagation();
          close();
          menuButton.focus();
        } else if (event.key === "Tab") {
          close();
        }
      });
    });
  }

  // Alt+F10 reaches the toolbar from the text without moving the cursor, which
  // Shift+Tab cannot do from inside a table, where it moves between cells.
  editor.view.dom.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "F10") {
      event.preventDefault();
      buttons.find((button) => button.getAttribute("tabindex") === "0").focus();
    }
  });

  editor.on("transaction", refresh);
  refresh();
  return { refresh };
}
