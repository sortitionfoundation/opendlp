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

4. **Read the style guide.** If a `styleguide-<lang>.md` sits beside the
   catalogues (here `translations/styleguide-<lang>.md`), read it before
   translating anything and follow it throughout. It carries the tone decision
   and the agreed glossary for that language, and it is what keeps a later run
   consistent with an earlier one. Never silently pick a different tone, or a
   different term for a glossary word, than the guide gives; if the guide is
   silent on something that matters, decide once, use that decision throughout,
   and say so in the end-of-run summary. If there is no guide, offer at the end
   of the run to write one from the decisions you made, so the next run does not
   start from scratch.

5. **Translation loop.** Take **one snapshot** of the pending set up front and
   work through it; do not re-scan to decide when to stop:

   a. `uv run gettext-auto scan <lang> --batch 100000 > scan.json` once, then work
      through `scan.json` in slices of ~50.
   b. Call the model with a system prompt covering: preserve placeholders exactly, match tone, correct plural count. Include `examples` and `entries` from the snapshot slice, plus the target `plural_rule`. Include the style guide from step 3a if there is one. If `project.context` has a value, pass it through verbatim as extra context about the project. Emit JSON matching `{"translations": [{"id": "...", "msgstr": "..."}, ...]}`.
   c. Pipe the JSON to `uv run gettext-auto apply <lang> --input -`.
   d. No retries. Accumulate counters from the `summary` field.
   e. Done when the snapshot is exhausted.

   **Why a snapshot rather than "repeat until `scan` returns zero".** `apply`
   leaves every entry it writes flagged `fuzzy`, and `scan` returns fuzzy
   entries as pending. So the entries you just translated come straight back on
   the next scan, and the loop never terminates - it retranslates the same
   catalogue until someone stops it. Expect `apply` to refuse some entries with
   "Refusing to overwrite clean"; those are already-translated entries and the
   refusal is correct, so filter them out before reporting failures.

6. **Verify the catalogue still compiles.** Run `just translate-check` (or
   `msgfmt --check` over the catalogue if the project has no such recipe).
   `apply` writes `#. AUTOTRANS-ERROR:` comments for entries it could not
   verify, and this is what surfaces them. `pybabel compile` is not a
   substitute - it accepts a catalogue msgfmt rejects.

7. **Print the end-of-run summary** using the counters. Tell the user to review translations and commit. Do not compile .mo unless they ask.

## What you do NOT do

- Never touch a non-fuzzy entry.
- Never clear `fuzzy` flags.
- Never commit to git. Never modify project README or CI.
- No retries on verification failure. `apply` writes `#. AUTOTRANS-ERROR:` comments so `msgfmt` catches them.
