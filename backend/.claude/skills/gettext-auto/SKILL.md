---
name: gettext-auto
description: AI-assisted gettext translation. Use when the user types /translate <lang> or asks to translate a gettext-based project.
---

# gettext-auto

Translate a gettext project one language at a time. All mechanical work goes through the `gettext-auto` CLI; only translation itself uses the model. `gettext-auto` is installed in the local `.venv/` using `uv`

## Protocol

1. **Parse the argument.** Accept BCP-47 / ISO codes (`en`, `fr`, `pt_BR`, `zh_Hans`). Reject friendly names ("french", "mandarin") with a suggested code. Confirm the code back to the user.

2. **Run `uv run gettext-auto detect`.** Print a one-line summary of project_type, gettext_status, and the target language state. If `pot_path` or `po_files` point somewhere unexpected (a vendored dependency, a build output, an unrelated subtree), ask the user to confirm the canonical location and re-run every `gettext-auto` invocation with `--po-root <dir>` to scope discovery.

3. **Branch on state:**
   - `gettext_status == "not-integrated"`: hard error. Tell the user no `.pot` or `.po` files were found, that gettext has to be set up in the project first (a `.pot` extracted from source, strings wrapped in `_()`), and that they should re-run `/translate <lang>` once that's done.
   - `detect.source_lang == <lang>`: hard error. "Source and target match. Did you mean a different language?"
   - `<lang>` not in `po_files`: run `uv run gettext-auto init-po <lang>` to create the catalog, then re-run `uv run gettext-auto detect` and proceed with the translation loop. The POT must exist first; if not, fall back to the "not-integrated" branch.
   - Nothing pending: "Everything up to date." Done.
   - Otherwise: enter the translation loop.

4. **Translation loop.** Repeat until `scan` returns zero entries:
   a. `uv run gettext-auto scan <lang> --batch 50`.
   b. Call the model with a system prompt covering: preserve placeholders exactly, match tone, correct plural count. Include `examples` and `entries` from scan output, plus the target `plural_rule`. If `project.context` has a value, pass it through verbatim as extra context about the project. Emit JSON matching `{"translations": [{"id": "...", "msgstr": "..."}, ...]}`.
   c. Pipe the JSON to `uv run gettext-auto apply <lang> --input -`.
   d. No retries. Accumulate counters from the `summary` field.

5. **NVDA add-on extension.** If `detect.nvda` is non-null, after the gettext loop reaches zero pending, run one extra pass for the add-on manifest:
   a. `uv run gettext-auto nvda scan <lang>`. Emits entries for any of `summary` / `description` that have a source string but no translation yet.
   b. If entries are empty, skip.
   c. Otherwise translate with the same prompt shape as step 4b and pipe to `uv run gettext-auto nvda apply <lang> --input -`. No fuzzy flag is used; the write is direct. Accumulate the counters into the same end-of-run summary.

6. **Doc file extension.** Run a single pass for markdown / doc files configured via `[[translate_files]]` in the user config (or the built-in NVDA default when no user config is set).
   a. `uv run gettext-auto files scan <lang>`. Emits entries with full source-file content inline. If entries are empty, skip this step.
   b. Call the model with a prompt tuned for whole-file markdown: preserve every heading, code fence, link, and image. Translate prose only; leave code blocks, URLs, and command examples untouched. If the doc has anchor links pointing at headings in the same file, update them to match the translated heading slugs. Include `project.context` if set. Emit JSON of shape `{"translations": [{"id": "...", "content": "...full translated file..."}, ...]}`.
   c. Pipe to `uv run gettext-auto files apply <lang> --input -`. Apply verifies heading/code-fence/link counts; failures are reported and no file is written. Translate-once semantics mean existing target files are never overwritten by the skill; the user must invoke `uv run gettext-auto files scan <lang> --force` directly if they want to regenerate.
   d. Accumulate the counters into the same end-of-run summary.

7. **Print the end-of-run summary** using the counters. Tell the user to review translations and commit. Do not compile .mo unless they ask.

## What you do NOT do

- Never touch a non-fuzzy entry.
- Never clear `fuzzy` flags.
- Never commit to git. Never modify project README or CI.
- No retries on verification failure. `apply` writes `#. AUTOTRANS-ERROR:` comments so `msgfmt` catches them.
