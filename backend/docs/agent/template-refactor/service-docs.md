# Splitting up `service_docs/_registration.html`

Deferred options, written up 2026-08-25. Nothing here has been done yet.

The sibling work on `templates/backoffice/assembly_registration.html` (options A
and B of the same review) *has* been done — see the commits that introduced
`templates/backoffice/registration/` and the controlled-modal macros in
`components/modal.html`. Those options are not repeated here.

## The problem

`templates/backoffice/service_docs/_registration.html` is 1904 lines. Unlike the
assembly registration page, nothing in it is deeply nested — it is the same
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

`publish` / `unpublish` / `close` / `reopen` are ~115 lines each and differ in
roughly eight strings.

The file already reaches for the fix: it defines a local
`{% macro page_id_input(model) %}` at the top, the only macro in any of the ten
`service_docs/` partials.

Scale of the prize: the ten partials in `templates/backoffice/service_docs/`
total 5994 lines and all share this skeleton, so macros written for the
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
| `_registration.html` | **1904** |

## Priority

Low. This is the dev-only service documentation console, and CLAUDE.md
explicitly holds that area to a lower bar than production code. Do it when
touching these files for another reason, or when a second partial crosses
~1000 lines.

## Option D — extract a `service_doc_card` macro set (recommended)

Add `templates/backoffice/service_docs/_macros.html`:

```jinja
{% macro doc_card(name, code_ref, permission="", description="") %}
{% macro param_table(params) %}          {# params: list of (name, type, required, description) #}
{% macro returns_block(text) %}
{% macro error_cases(errors) %}
{% macro assembly_select(model) %}       {# the ~10-line <select> repeated 13x #}
{% macro try_it(response_key, execute_fn) %}
```

`try_it` covers the panel wrapper, the execute button with its
`loading.<key>` / `Loading...` spinner pair, and the `x-show="responses.<key>"`
response `<pre>`; the caller supplies the per-service form fields.

Expected outcome: `_registration.html` drops to roughly 600-700 lines, most of
it actual documentation content rather than markup.

**Caveat that will bite.** The parameter tables currently omit
`border-bottom` on the final `<tr>` by hand-editing each last row. A macro
normalises that. Either always emit the border and add a `tr:last-child`
override in CSS, or pass a loop flag through. Either way the rendered HTML
shifts slightly, so check:

- `tests/component/test_dev_service_docs_page.py`
- `tests/bdd/test_dev_service_docs.py`

Follow-up worth doing once D lands: apply the same macros to the other nine
partials.

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

Reconsider only if the try-it forms get normalised first.

## Option F — split by service group

Three files: `_registration_pages.html` (create / list / duplicate / delete /
get / update / update_html / generate_starter), `_registration_lifecycle.html`
(publish / unpublish / close / reopen) and `_registration_submit.html`
(submit_registration).

Only worth doing *combined* with D. On its own it produces three 600-line files
and removes no duplication.

## Mechanical notes for whoever picks this up

- New partials need their own `{% from ... import %}` lines rather than
  relying on context inheritance from `service_docs.html`. Inheritance does
  work — it is how `_registration.html` gets `card` and `card_body` today —
  but it is invisible coupling.
- Markdown files do not take the `ABOUTME:` header, but new `.html` partials
  do.
- `djhtml` (via prek) reindents templates, so run `just check` after moving
  blocks between files.
