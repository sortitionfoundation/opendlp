# Splitting up `service_docs/_registration.html`

Deferred options, written up 2026-08-25. **Option D was done on 2026-08-25**;
E and F are still open, and are re-assessed below now that D has landed.

The sibling work on `templates/backoffice/assembly_registration.html` (options A
and B of the same review) has also been done — see the commits that introduced
`templates/backoffice/registration/` and the controlled-modal macros in
`components/modal.html`. Those options are not repeated here.

## The problem

`templates/backoffice/service_docs/_registration.html` was 1904 lines. Unlike
the assembly registration page, nothing in it is deeply nested — it is the same
card repeated 13 times, once per documented service:

```txt
card(title="publish_registration_page()")
  code reference + permission badge      ~15 lines
  description                             ~4 lines
  parameters table                     ~20-60 lines
  returns block                           ~7 lines
  error cases list                     ~10-15 lines
  "Try it" panel + execute button       ~25-45 lines
  response <pre>                         ~11 lines
```

`publish` / `unpublish` / `close` / `reopen` were ~115 lines each and differed
in roughly eight strings.

Scale of the prize: the ten partials in `templates/backoffice/service_docs/`
totalled 5994 lines and all share this skeleton, so macros written for the
registration partial pay for themselves several times over.

| Partial | Lines |
| --- | --- |
| `_targets.html` | 195 |
| `_config.html` | 337 |
| `_assembly.html` | 392 |
| `_documents.html` | 456 |
| `_images.html` | 456 |
| `_selection.html` | 505 |
| `_respondents.html` | 542 |
| `_fields.html` | 556 |
| `_emails.html` | 651 |
| `_registration.html` | 1904 → **573** |

## Priority

Low. This is the dev-only service documentation console, and CLAUDE.md
explicitly holds that area to a lower bar than production code. Do it when
touching these files for another reason, or when a second partial crosses
~1000 lines.

## Option D — extract a `service_doc_card` macro set — **DONE**

`templates/backoffice/service_docs/_macros.html` now holds:

```jinja
{% macro doc_card(name, code_ref, permission, description, permission_variant="warning", copy_click="") %}
{% macro param_table(params) %}          {# params: list of (name, type, required, description) #}
{% macro returns_block(text) %}
{% macro error_cases(errors) %}          {# errors: list of (exception_name, when) #}
{% macro assembly_select(model, assemblies) %}
{% macro text_field(label, model, placeholder="", hint="", code=false) %}
{% macro textarea_field(label, model, placeholder="", rows=6, help="") %}
{% macro checkbox_field(id, model, label) %}
{% macro try_it(key, execute_click, copy_click="", danger=false) %}
```

`_registration.html` went 1904 → 573 lines against 255 lines of shared macros.

Notes for whoever applies these elsewhere:

- **Keep every `{% call %}` tag on one line, however long it gets.** djhtml
  cannot track nesting through a block tag whose arguments wrap, so multi-line
  `{% call %}` tags make it indent the whole rest of the file wrongly — and
  because it reindents on commit, the damage lands whether you asked for it or
  not. A one-line `{% call doc_card(...) %}` runs to ~380 characters here and
  that is the price. Multi-line arguments are fine in `{{ ... }}` expressions
  such as `param_table([...])`, which are not block tags.

- **`doc_card` captures its caller block first** (`{% set body_content =
  caller() %}`) because it nests `{% call card %}{% call card_body %}` inside
  itself, and `caller()` in there would resolve to `card_body()`'s caller. Same
  trap, same fix, as `components/modal.html`.
- **`try_it` emits the response block too.** The panel and the `<pre>` share the
  service key — the button disables on `loading.<key>` and the response shows on
  `responses.<key>` — so keeping them in one macro is what stops the pair
  drifting.
- **The last-row `border-bottom` caveat resolved itself.** The old tables
  hand-omitted the border on the final `<tr>`; `param_table` reproduces that from
  `loop.last`, so no CSS override was needed and the rendered HTML is unchanged.
- **`assemblies` is passed explicitly** rather than imported `with context`, so
  the dependency is visible at each call site.
- **Watch autoescaping when text moves into a macro argument.** Prose that lived
  as a literal in the template is now a Jinja string, so `"` and `'` come out as
  `&#34;` / `&#39;` and `<slug>` must be written raw (autoescaping produces the
  `&lt;slug&gt;` the template used to spell out). Decoded output is identical
  either way, but a byte-for-byte render diff will show it.

**Follow-up worth doing: apply the same macros to the other nine partials**
(4090 lines between them). Nothing about the macros is registration-specific.

## Option E — move the content into Python data

The card content *is* structured data: name, code ref, permission, description,
params, returns, errors, try-it fields, response key. Put it in `dev.py` (or a
data module next to it) as a list of dicts and render every card from one loop.
`_registration.html` becomes ~80 lines of template plus a data structure.

Attractive because it would make the existing "does the docs page cover every
service in `_SERVICE_HANDLERS`?" unit test trivially strong — the coverage
assertion becomes a comparison of two Python structures.

Rejected for now, for two reasons:

1. It puts English documentation prose into Python source.
2. The "Try it" forms genuinely differ per service — file uploads, textareas,
   checkboxes, multi-field forms — so a per-card escape hatch is needed anyway,
   and once that exists most of the saving evaporates.

D weakens this further: the params/returns/errors arguments are already
structured data at the call sites, so the remaining prize is mostly the coverage
test. Reconsider only if the try-it forms get normalised first.

## Option F — split by service group

Three files: `_registration_pages.html` (create / list / duplicate / delete /
get / update / update_html / generate_starter), `_registration_lifecycle.html`
(publish / unpublish / close / reopen) and `_registration_submit.html`
(submit_registration).

Was only worth doing *combined* with D. Now that D has landed and the file is
626 lines, the case is weak: three ~200-line files buy little, and the partial
is already skimmable as one list of cards. Leave it.

## Mechanical notes for whoever picks this up

- New partials need their own `{% from ... import %}` lines rather than
  relying on context inheritance from `service_docs.html`. Inheritance does
  work — it is how `_registration.html` used to get `card` and `card_body` —
  but it is invisible coupling.
- Markdown files do not take the `ABOUTME:` header, but new `.html` partials
  do.
- `djhtml` (via prek) reindents templates, so run `just check` after moving
  blocks between files.
- Verify by rendering. Every tab is a GET away
  (`/backoffice/dev/service-docs?tab=<name>`); dumping all ten before and after
  and diffing whitespace-normalised output is what proved D changed nothing —
  and is what caught the three cosmetic regressions it did introduce.
