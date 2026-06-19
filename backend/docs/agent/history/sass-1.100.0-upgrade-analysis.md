# sass 1.99.0 → 1.100.0 — safety analysis

This document records why the Dependabot bump of `sass` to 1.100.0 (PR #157) is safe to merge for our codebase.

## What changed upstream

Dart Sass 1.100.0 ships exactly one user-visible change: it **deprecates writing two compound selectors adjacent to one another without whitespace** between them. The release notes give `[class]a` as the canonical example. This pattern was never valid CSS — Sass only accepted it by accident — so 1.100.0 now emits a deprecation warning. See <https://sass-lang.com/d/adjacent-compounds>.

The bump is otherwise non-breaking; it does not raise the minimum Node version (>=14 from earlier releases) and introduces no API changes that affect our `sass src/scss:static/css --load-path=node_modules --style=compressed` build invocation in `backend/package.json`.

## What the deprecation actually catches

The deprecation fires when a compound selector that starts with something other than a type selector (an attribute selector `[…]`, a pseudo `:…`, etc.) is immediately followed — with no whitespace — by another compound selector. In practice, the patterns that trigger the warning look like:

- `]<letter>` — attribute selector touching a type selector, e.g. `[type="text"]input`
- `)<letter>` — `:not(...)` or similar pseudo-class touching a type selector, e.g. `:not(.foo)bar`
- `:<pseudo><letter>` — pseudo-class touching a type selector, e.g. `:hovera`

Adjacent compounds that are valid CSS (`a[class]`, `.foo:hover`, `input[type="text"]`) are unaffected — the type selector comes first or only one compound is present.

## Audit of our SCSS

Our SCSS sources are:

- `backend/src/scss/application.scss` (756 lines)
- `backend/src/scss/_utilities.scss` (53 lines)
- `backend/src/scss/_sortition.scss` (18 lines)

Grepping for the patterns above:

```bash
grep -nE '\][a-zA-Z]' backend/src/scss/*.scss
grep -nE '\)[a-zA-Z]' backend/src/scss/*.scss
grep -nE ':(hover|focus|active|first-child|last-child|nth-child|not)[a-zA-Z]' backend/src/scss/*.scss
```

All three return no matches. None of the 827 SCSS lines we own contain the deprecated adjacent-compound pattern.

The `--load-path=node_modules` flag means Sass also compiles `govuk-frontend` SCSS. Any deprecation warnings originating from that vendor code are upstream's problem, not ours — they don't fail the build and would be fixed by a future `govuk-frontend` release.

## Conclusion

Safe to merge as-is. No source changes required, no build-tooling changes required, no warnings expected from our own SCSS.

If a future SCSS edit reintroduces the pattern, the build will surface a deprecation warning pointing at the line — at which point the fix is to add a space (`[type="text"] input`) or reorder so the type selector comes first (`input[type="text"]`).
