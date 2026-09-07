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

5. **Print the end-of-run summary** using the counters. Tell the user to review translations and commit. Do not compile .mo unless they ask.

## What you do NOT do

- Never touch a non-fuzzy entry.
- Never clear `fuzzy` flags.
- Never commit to git. Never modify project README or CI.
- No retries on verification failure. `apply` writes `#. AUTOTRANS-ERROR:` comments so `msgfmt` catches them.
