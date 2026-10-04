---
name: translate-catalogues
description: Regenerate and check the gettext catalogues after adding or changing any translatable string. Use before committing a change that touches a `_()` or `_l()` string, a template string, or a `.po` file.
---

# translate-catalogues

After adding or changing translatable strings, regenerate and check:

```bash
just translate-regen         # extract + update every catalogue
just translate-check         # msgfmt --check and pybabel compile; also run by `just check`
just translate-accept-fuzzy  # clear every fuzzy flag once a reviewer has been through them
```

Never rewrite a catalogue with `msgattrib` or `msgcat` by hand: they wrap lines
differently from pybabel, and the whole file rewraps. A pre-commit hook
normalises staged catalogues to pybabel's wrapping - see
[docs/translations.md](../../../docs/translations.md#one-wrapping-for-the-catalogues).

`translate-check` is not optional politeness. `pybabel compile` accepts a
catalogue with duplicate msgids without a murmur and emits a `.mo` missing
translations, which is how the Hungarian catalogue spent months unable to build
correctly with nothing reporting a problem. `msgfmt --check` catches duplicates,
broken placeholders and bad plural forms. It skips fuzzy entries, though, whose
placeholders `pybabel compile` does check - so the recipe runs both.

Note also that rewording an existing msgid silently discards its translation -
the string simply reverts to English in every language. Nothing catches this, so
prefer leaving wording alone unless the change is worth the retranslation.

See [docs/translations.md](../../../docs/translations.md) for translation management workflow.
