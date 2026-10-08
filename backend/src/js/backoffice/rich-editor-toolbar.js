// ABOUTME: Wires the server-rendered visual editor toolbar to a Tiptap editor.
// ABOUTME: Runs each button's command, keeps aria-pressed in step, and moves focus with the arrow keys.

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
  bulletList: {
    run: (chain) => chain.toggleBulletList(),
    active: (editor) => editor.isActive("bulletList"),
  },
  orderedList: {
    run: (chain) => chain.toggleOrderedList(),
    active: (editor) => editor.isActive("orderedList"),
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
  const buttons = Array.from(toolbar.querySelectorAll("button[data-command]"));

  function refresh() {
    for (const button of buttons) {
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

  function moveFocus(from, to) {
    from.setAttribute("tabindex", "-1");
    to.setAttribute("tabindex", "0");
    to.focus();
  }

  buttons.forEach((button, index) => {
    button.setAttribute("tabindex", index === 0 ? "0" : "-1");
    // Keep the editor's selection: a click must not move focus off the text first.
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => run(button));
    button.addEventListener("keydown", (event) => {
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

  editor.on("transaction", refresh);
  refresh();
  return { refresh };
}
