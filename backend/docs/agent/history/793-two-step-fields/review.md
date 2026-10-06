# Code review: `793-two-step-fields` vs `main`

Reviewed 2026-09-18 against the checklist in `.claude/skills/sf-code-review`.
Five parallel reviewers (Python/architecture/transactions, tests,
templates/a11y/tokens, i18n/language, JavaScript); findings 1 and 3 were then
re-checked by hand.

**How much to trust this:** apart from three Vitest files and the two unit guard
tests (`test_icons.py`, `test_design_tokens.py`) - all green - no tests were run.
Every runtime claim ("returns a 500", "prompts twice") comes from reading the
code, not from reproducing it. The tests reviewer read the target-sources
blueprint, service and tests in full, but only the diffs and test outlines for
the respondent-field-schema and targets code, so coverage gaps there may have
been missed.

All paths are relative to `backend/`.

**Status (2026-09-18, later):** each `COMMENT:` line below is followed by what
was done about it. Everything marked "fix" is done except one item where two
comments disagree (must-fix 4 / modal focus). After the fixes: `just check`
passes, `just test-nobdd` 5,879 passed, `just test-bdd-headless` 184 passed and
5 skipped (none of them new).

**Status (2026-09-18, on `793-large-mapping-flow`):** this branch was merged into
`793-large-mapping-flow` (`714067fd`) and the items marked "defer" were worked
through there. Each has a dated note below. Done: the i18n / language section,
the fragment dialogs' focus management (which is also must-fix 4), and the
schema blueprint's units of work that this branch had left for that one. **Still
open, on purpose:** finding 5, which you deferred to the age brackets branch.
After that work: `just check` passes, `just test-nobdd` 5,887 passed, `just test-js`
521 passed, `just test-bdd-headless` 187 passed and 5 skipped (the same five).

## Fix before merge

### 1. `data-confirm` regression on legacy pages (confirmed by hand)

> **Done.** Form-level `data-confirm` is handled on the `submit` event (skipping
> forms that HTMX submits); the click handler matches only
> `button[data-confirm], a[data-confirm]`. Tests added for both paths, the
> `_checklist.html` comment corrected, and `docs/frontend_security.md` updated.
> Still worth a manual browser check after a rebuild: the unlink button inside
> the `hx-post` form at `_checklist.html:140`, and the six legacy form-level
> confirms, which now prompt where on main they never did.

`src/js/init/document-actions.js:33` changed from `e.target.dataset.confirm` to
`e.target.closest("[data-confirm]")`. The motive is sound - a click often lands
on a button's label span - but several legacy templates put `data-confirm` on
the `<form>`, not the button:

- `templates/profile/2fa_settings.html:100`
- `templates/admin/user_view.html:122`
- `templates/profile/view.html:54,88,139`
- `templates/gsheets/manage_tabs.html:71`

On main these forms never prompted at all (the click target was the button,
which has no `data-confirm`), so the change does fix something. But now *any*
click inside the form prompts. The clear victim is `2fa_settings.html:100-117`,
where the form also holds the TOTP code input and its label: clicking into the
code field pops "Are you sure you want to disable two-factor authentication?",
and clicking the label prompts twice (the label click dispatches a synthetic
click on the input).

No other handler covers form-level `data-confirm` - `form-confirm.js` is the
Alpine `$confirm` magic, a separate mechanism. `utilities.js` loads from both
`templates/base.html` and `backoffice/base.html`, so this reaches public and
legacy pages.

Options:

- handle form-level `data-confirm` on the `submit` event, which is what
  `docs/frontend_security.md` actually shows; or
- when the matched element is a `<form>`, confirm only if the click was on a
  submit control.

Also:

- `document-actions.test.js` only covers a button carrying `data-confirm`. Add a
  case for a form carrying it with a non-submit child clicked.
- The comment at `templates/backoffice/target_sources/_checklist.html:77-79`
  ("data-confirm, which reads the click target, sees the button itself") is now
  false.

### 2. Uncaught exceptions that become 500s

> **Done**, with local fixes - each bullet below, plus one the new tests found:
> `unlink_view` answered an unknown *assembly* with "Target not found", because
> `AssemblyNotFoundError` is a `NotFoundError`. The legacy delete route answers an
> HTMX request with `HX-Redirect`, since a followed 302 would swap the whole page
> into the category block. Covered by `TestRoutesTurnAwayThoseWithoutAccess`
> (every target-sources route, as a user with no role and with an unknown
> assembly), `TestLegacyPagesRefuseLinkedTargets`, and one test each for the
> `save_all` rename collision and the unparsable resync. Thirteen of those tests
> fail without the fixes, which confirms the 500s were real.
>
> App-level handlers for `InsufficientPermissions` / `NotFoundError` are written
> up as an issue in [future-work.md](future-work.md), not done here. A handler for
> `ServiceLayerError` is argued against there.
>
> Not addressed: these routes still show `str(e)` for the uncurated
> `FieldDefinitionNotFoundError` - that is the first Medium finding below.

`flask_app.py` has handlers for 404, 500, 403, 413 and CSRF only - nothing for
`InsufficientPermissions`, `AssemblyNotFoundError` or `ServiceLayerError`.

- **`target_sources.py:636` (`recompute_view`) and `:694` (`upload_view`)** call
  `_linked_field_id()` *before* their `try`. It runs `target_source_status`,
  which raises `InsufficientPermissions` / `AssemblyNotFoundError`. A read-only
  user or a bad assembly id POSTing to either gets a 500 rather than the
  dashboard redirect. Their `try` blocks (`:640-648`, `:719-722`) also omit
  `NotFoundError`.
- **`configure_view:575`** renders the error modal from inside an `except`
  handler. `_render_setup_modal` -> `_page_context` runs the permission check,
  and `_setup_modal_ctx` raises `NotFoundError` for a foreign category. A
  `ValueError` from `_parse_setup_spec` is raised before any permission check,
  so an unauthorised user posting an invalid form hits `InsufficientPermissions`
  inside the handler. Nothing leaks - the check still runs before anything
  renders - but it is a 500.
- **`resync_view:617`** does not catch the `ValueError` that `rule_from_field`
  can raise for a config that no longer parses (`_stale_for_derived` in the same
  service acknowledges that it can).
- **`targets_legacy.py:277,324`** - `update_target_category` and
  `delete_target_category` now raise `TargetLinkedError` for a linked category.
  `edit_category` catches `(ValueError, NotFoundError, InsufficientPermissions)`
  and `remove_category` catches `(NotFoundError, InsufficientPermissions)`, so
  it escapes both. The legacy UI is still registered and has no way to force
  the change. `FieldDefinitionConflictError` from `rename_derived_field` escapes
  `edit_category` the same way.
- **`targets.py:492-505` (`save_all`)** has no clause for the curated
  `FieldDefinitionConflictError` ("A question named ... already exists") raised
  during a forced rename. It falls into the blanket `except Exception`: the user
  sees the generic "An error occurred" and the event is logged as unexpected
  with a traceback. The rollback is still correct.

### 3. Two paths bypass the linked-target guard (confirmed by hand)

`update_target_category` / `delete_target_category` refuse a linked category,
but two bulk paths call `uow.target_categories.delete_all_for_assembly` with no
guard:

- `target_service.delete_targets_for_assembly` (`target_service.py:682`)
- `target_csv_import.import_targets_from_csv` with `replace_existing`
  (`target_csv_import.py:180`)

On Postgres the FK's `ON DELETE SET NULL` (`adapters/orm.py:638`) nulls the link
and leaves a derived field with no target - the state commit 98ea3e4e ("never
leave a computed question behind with no target") set out to prevent. The fake
repository leaves a dangling ID instead, so the two backends diverge.

No test covers the column at database level: `TestTargetLinkedGuardWrites`
(`tests/integration/test_target_service.py:1472+`) asserts only on in-session
objects after `flush()`, never commits and reloads, and never checks `SET NULL`.
`tests/integration/test_create_assembly_persistence.py:120` is the pattern to
copy.

COMMENT: fix it

> **Done** in `4ce9ff00`. Both paths now break the links first, exactly as
> deleting each category would: questions are unlinked and stay, computed
> questions go with their target.
>
> **One judgement call to check.** A CSV re-import (`replace_existing`) gives
> every category a new id, so breaking all the links would throw away the whole
> data sources set-up each time someone re-uploads the same targets with new
> numbers. So a target that comes back *under the same name* keeps its fields,
> re-linked to the new row; only targets that do not come back lose theirs. If
> the values changed, the existing staleness check flags it. "Delete all targets"
> has no such nuance and takes the computed questions with it - it does so
> without the naming confirmation that deleting one target gets. If you want
> that confirmation there too, it needs a confirm page for that route; say so.
>
> The real-Postgres test earned its keep: the re-link failed there with a
> foreign key violation the fake store could never show (with no
> `relationship()`, the session flushed the field UPDATE before the new category
> INSERT). `AbstractUnitOfWork` gains `flush()` for it. `TestDeletingEveryTargetKeepsLinksHonest`
> also pins the `SET NULL` rule itself.

### 4. Authorisation is not tested

- `tests/component/test_backoffice_target_sources.py` uses `logged_in_admin`
  throughout. All nine routes have `except InsufficientPermissions` /
  `except NotFoundError` redirect branches that nothing exercises - which is how
  finding 2's first bullet went unnoticed.
- At unit level, `TestPermissions`
  (`tests/unit/test_target_source_service.py:675-691`) covers only
  `configure_target_source` and `target_source_status`. `adopt_field`,
  `resync_from_target` and `unlink` have no permission test.
- No test creates a second assembly. The guards exist and look right
  (`field.assembly_id != assembly_id` in `_resolve_source_field`,
  `_configure_exact_copy`, `adopt_field`; `category.assembly_id != assembly_id`
  in `_get_category`, `unlink`), but the only "wrong ID" tests use a random
  `uuid4()`. Deleting the `assembly_id` half of any guard would break no test.

This is the masking problem the TODO in `docs/testing.md` warns about.

> **Partly done** alongside finding 2: every target-sources route is now
> exercised as a user with no role on the assembly and with an unknown assembly,
> and one test sends a target belonging to another assembly to `configure`. Still
> open: a read-only role (can view, cannot manage) against the POST routes; unit
> permission tests for `adopt_field`, `resync_from_target` and `unlink`;
> cross-assembly tests for `adopt`, `resync`, `unlink` and `reuse_field_id`.

COMMENT: add the cross-assembly tests and unit permission tests. I can live without the read-only role tests

> **Done** in `742cdfa7` (with the route-level half in `b1f7ce54`).
> `TestIdsFromAnotherAssemblyAreRefused` hands every guard an id that is real but
> belongs to another assembly the same admin manages: a foreign category to
> `configure`, `adopt`, `resync` and `unlink`; a foreign field to `adopt`, to
> exact-copy reuse and to a derivation's `reuse_field_id`. Mutation-checked:
> stripping the five `assembly_id` guards fails all seven tests. `adopt_field`,
> `resync_from_target` and `unlink` have the permission test too. Read-only-role
> tests not written, as agreed.

### 5. Editing a saved age rule shows the target's prefill, not the stored config (regression, confirmed by probe)

Must-fix 2 of the [`793-derived-fields-ui` review](../793-derived-fields/ui-branch-review.md)
was fixed there in `d8c35a1f` (`prefill_from_target`, true only for a new field).
The set-up modal on this branch reintroduces it. `_setup_modal_ctx`
(`target_sources.py:308`) calls `_apply_age_prefills` whenever the method is age
brackets, new or edit, and that function (`:242-253`) runs
`values.update(prefill)` whenever the boundaries string is blank - which it is
for any stored rule with no boundaries.

Probed with a throwaway component test: a linked field stored as min 18, max 90,
no boundaries, feeding a target `16-24, 25-39, 40+`, opens in the modal as
**min 16, max 40, boundaries 25**. Pressing Save persists those and recomputes
the pool. The organiser changed nothing.

The prefill should run only when the target has no linked field yet. The test
that pinned the old fix
(`test_edit_modal_keeps_a_stored_config_the_target_would_have_prefilled`) covers
the old modal, which the UI no longer reaches - see "Carried over" below.

COMMENT: defer - I want to make some changes to how the age brackets work, so I'll do that in another branch.

> **Deferred** to the age brackets branch. Note the related nit under "Carried
> over" (the prefill overwriting typed min/max for a new field) is the same
> function, so it travels with this.
>
> **Still deferred (2026-09-18, `793-large-mapping-flow`).** Not touched when the
> other deferred items were done: you said the age brackets are changing on their
> own branch, and a fix here would be conflict bait for it. Worth keeping in mind
> that until then the regression is live - opening a saved age rule with no
> boundaries and pressing Save rewrites its min and max. `_apply_age_prefills` is
> now at `target_sources.py:229`. If that branch is more than a few days off, the
> one-line guard (`if not setup.is_linked`) is cheap and I would take it.

## Medium

### Python / architecture

- **`str(e)` reaches the page.** `target_sources.py:575,600,618,645,720` flash or
  render `str(e)` for `FieldDefinitionNotFoundError`, which does not mix in
  `CuratedMessage`. Its messages are untranslated f-strings with internal UUIDs
  ("Field {id} not found in assembly {id}"). `:470`'s
  `uuid.UUID(values["reuse_field_id"])` lets "badly formed hexadecimal UUID
  string" through to the modal via `:575`; `:575` also surfaces bare domain
  `ValueError`s (`domain/respondent_field_schema.py:364,366,396,400`). These are
  HTML responses, so the JSON rule is not broken, but it is the same class of
  leak. `adopt_view:600` shows the right shape - it swaps `ValueError` for a
  wrapped string. The pattern exists on main; the branch widens it.
- **Several `with uow:` blocks per request**, against "exactly one context
  around the work of that request" in `docs/architecture.md`:
  - `setup_modal` opens three (`:551` status, `:289` `_setup_modal_ctx`, `:196`
    `_page_context`);
  - `configure_view` opens two on success and three on the error path;
  - `recompute_view` / `upload_view` resolve `field_id` in one transaction and
    write in another - a time-of-check/time-of-use gap;
  - `_schema_page_context` already opened two and now does more in each;
    `_edit_modal_ctx` adds a third via `_linked_target_name`.
  The reads can disagree: a checklist rendered from a later snapshot than the
  modal.
- **`_setup_modal_ctx` (`target_sources.py:288-297`) reads repositories directly
  with no permission check of its own.** Safe today only because every caller
  then calls `_page_context`; a future caller that skips it is an IDOR. It also
  holds business logic (candidate computation, `_exact_reuse_candidates`,
  staleness, prefills) that belongs in `target_source_service`.
  `_linked_target_name` (`respondent_field_schema.py:477-484`) is the same
  pattern, smaller.

COMMENT: fix all these

> **Done**, in four commits.
>
> - `c126608e` - `str(e)`. Not-found now shows a generic message, a conflict its
>   curated one, a malformed reuse id "Choose the question to use"; a domain guard
>   the form cannot trip is logged rather than displayed. `ValueError` from the
>   form parsers and rule constructors is still shown as-is - those are written
>   for the organiser, in `_()`. One exception I left: `SmallMappingRule` and
>   `LargeMappingRule` raise untranslated `"mapping cannot be empty"` /
>   `"fallback cannot be blank"`; `parse_small_mapping_rule` pre-empts the first,
>   and nothing in the form can produce the second.
> - `26965765` - the parsers leave the blueprint (see should-fix 13 below).
> - `172c0886` - `target_sources.py`: every route opens **one** `with uow:` around
>   everything it reads and writes, including the page context its response is
>   rendered from, and renders after the block closes. `recompute` and `upload`
>   find the linked field in the transaction that writes to it. The one exception
>   is a failed save: its block has rolled back, so the dialog it re-opens is read
>   in a fresh one - that is two units of work, not a lapse.
>   `_setup_modal_ctx`'s repository reads moved into
>   `target_source_service.target_setup_data`, which checks permission itself, and
>   the reuse-candidate rules into `reusable_source_fields`. Checked against real
>   Postgres by the BDD suite, since a page context read after a write in the same
>   session is exactly where a detached-instance error would show.
> - `52040ecf` - `_schema_page_context` opens one block instead of two, and
>   `_linked_target_name` checks permission and the category's assembly.
>
> **Not done, deliberately:** the rest of `respondent_field_schema.py` still opens
> a block per helper (`_matching_choice_target`, `_assembly_has_targets`,
> `_build_derived_ctx`, `_load_field`, then the page context). Converting it means
> re-plumbing every route in a 1,700-line file of which `f3b0f09b` deletes 600
> lines, so it is far cheaper on `793-large-mapping-flow`. Still open, there.
>
> **Done on `793-large-mapping-flow`** in `e23ee18a`. With the derived routes gone
> only five routes built a page or dialog, and each now opens one block: helpers
> take the route's `uow`, `_modal_response` reads the page and then the dialog in
> one block, and the render happens after it closes. A refused save is the one
> exception, as in `target_sources.py`. `_matching_choice_target` turned out to
> read a target's name and values with no permission check of its own - the same
> latent IDOR this finding describes for `_setup_modal_ctx` - and now makes one.
> `TestOneUnitOfWorkPerRequest` counts the blocks each kind of request opens
> (mutation-checked: it fails on the old blueprint, at the edit dialog).
> The option/move/delete/guess routes already opened one block and redirect.
> **Not touched:** `str(e)` for `FieldDefinitionConflictError` at four flashes in
> that file - curated messages, so safe, but `e.user_msg()` is the house form.

### i18n / language

- **Enum `.value` in a user message.** `target_source_service.py:285`:
  `_l("A '%(type)s' field cannot feed this kind of derivation",
  type=spec.field_type.value)` - the user sees "A 'choice_radio' field...". Use
  `FIELD_TYPE_LABELS[spec.field_type]`.
- **`.value` as a template fallback, and a second labels dict.**
  `_checklist.html:34`:
  `method_labels.get(status.field.derivation_type.value, status.field.derivation_type.value)`
  - a future `DerivationType` member falls through to the raw token.
  `method_labels` comes from `_method_options()` (`target_sources.py:79-84`), a
  blueprint-local dict keyed by `.value`; `docs/translations.md` asks for the
  dict to live beside the enum. One enum now has two sets of English:

  | `DerivationType` | domain `DERIVATION_TYPE_LABELS` | blueprint `_method_options()` |
  | --- | --- | --- |
  | `AGE_BRACKET` | Age brackets | Age ranges |
  | `SMALL_MAPPING` | Map choices | Map more options to fewer |
  | `LARGE_MAPPING` | Lookup table | Map postcode to value |

  The fields editor (`_editor.html:136`) shows the domain set and the checklist
  shows the blueprint set, for the same field.
- **`FieldType` has the same split.** `respondent_field_schema.py:186-213`: the
  type dropdown offers "Radio" / "Dropdown"; the table column shows
  "Choice (radios)" / "Choice (dropdown)" from `FIELD_TYPE_LABELS`.
- **"registration form"** in new strings; the glossary says "registration page":
  `_checklist.html:31`, `_setup_modal.html:130,150`, `registration/_hub.html:47`,
  `target_sources/view.html:54`. (`_setup_modal.html:142` "Label on the form
  (optional)" is borderline.)
- **Remove vs delete.** The guide says Delete destroys data.
  `_checklist.html:121,123,142` ("Remove the computed question ...? Its answers
  ... are deleted", button "Remove computed question") and `target_sources.py:740`
  ("Computed question removed") destroy answers and the lookup table, so should
  say Delete. `targets_force_unlink_confirm.html:41` gets it right.
  `respondent_field_schema_service.py:695` ("rename or remove it first") has the
  same issue.
- **"Computed question" is not in `docs/language.md`**, and the branch's own
  addition to the guide says "a derived field computed from a question". The UI
  now mixes "computed question" (checklist, confirm page), the "Derived" tag and
  "Derived from %(source)s" (`_editor.html:135,237`), and "is derived" in service
  errors. Pick one and record it in the glossary.

COMMENT: defer for now

> **Deferred.** Two things done elsewhere touch this list: "Not on form" and
> "Label on the form" were fixed under should-fix 15, and the `.value` in a user
> message (`target_source_service.py:285`) is still open here.
>
> **Done on `793-large-mapping-flow`** in `3c7187db` (catalogue `007d8d1c`, BDD
> wording `27f90679`). No Hungarian translation was lost: none of the reworded
> msgids had one.
>
> - *Enum `.value` in a message* - the refusal names the type with
>   `FIELD_TYPE_LABELS`; a unit test asserts "Long text", not "longtext".
> - *Two label sets for `DerivationType`* - one now. `f3b0f09b` had left the
>   domain's "Age brackets / Map choices / Lookup table" with no reader, so
>   `DERIVATION_TYPE_LABELS` carries the wording the organiser actually sees
>   ("Age ranges", "Map more options to fewer", "Map postcode to value").
>   `_method_options()` is built from it, and the checklist indexes
>   `derivation_type_labels[...]` - no `.value`, no fallback to a raw token.
> - *`FieldType` split* - the type picker reads `FIELD_TYPE_LABELS`, which turns
>   its "Number" into "Whole number". **Judgement call:** "Radio" and "Dropdown"
>   stay as short forms, because they sit under a "Choice" group heading and
>   "Choice > Choice (radios)" reads worse; a comment says so. The flat list a
>   target-locked question gets has no heading, so it uses the full labels.
> - *"registration form"* - "registration page" in all five strings; the hub's
>   question count became an `ngettext` while it was being reworded, and the
>   reworded strings take single quotes round placeholders (two Low items).
> - *Remove vs delete* - "Delete the computed question ...?", "Delete computed
>   question", "Computed question deleted", "rename or delete it first".
> - *"Computed question"* - it is the term, and `docs/language.md` has an entry.
>   The two places an organiser could still read "derived" now say "computed"
>   (the edit-respondent page, the CSV import row message). **Left alone:**
>   "derived" in refusals only a hand-made request can reach
>   (`derivation_service.py:135,146`, `target_source_service.py:306`,
>   `respondent_field_schema_service.py:358,380`) - the glossary entry says so -
>   and the "Derived" section name, which no screen shows any more.

### Templates / accessibility

- **Row-actions menu is not a full APG menu button**
  (`_checklist.html:79-141`, `_editor.html:126-190`,
  `src/js/components/row-actions-menu.js`). Present: `aria-haspopup="menu"`, bound
  `aria-expanded`, `aria-controls`, `role="menu"`/`menuitem`, `role="none"` on
  wrapper forms, click-outside, Escape closes and returns focus and is stopped
  from reaching `dialog-escape.js`. Missing: focus into the menu on open,
  ArrowUp/Down/Home/End, roving tabindex (every item is a Tab stop), closing when
  focus tabs out, focus management after click-outside. This matches
  `dropdown_button.html`, but `component_accessibility.md` requires arrow keys and
  roving tabindex for menus and asks for deviations to be documented with a
  rationale; the template comments only say "same behaviour as dropdown_button".
  `role="menu"` tells screen-reader users arrow keys work. Either add the key
  handling (with tests) or drop the menu roles.

COMMENT: fix it

> **Done** in `b8d8edd1`. `rowActionsMenu` is now a WAI-ARIA menu button: opening
> moves focus to the first item; ArrowUp/Down (wrapping), Home and End move
> between items; ArrowDown / ArrowUp on the kebab open it on the first / last
> item; items are `tabindex="-1"` so the menu is one Tab stop; tabbing out closes
> it. A `focusout` with no `relatedTarget` is ignored - Safari does not focus a
> clicked button, and closing there would let the kebab's own click reopen the
> menu. 15 Vitest cases over real DOM, including the end-to-end one the review
> asked for (first Escape closes the menu, second closes the dialog), and a BDD
> scenario driving it from the keyboard in a real browser.
> `dropdown_button.html` still has the gap - not touched, it is not this branch's.

- **`_editor.html:180`** - the Remove form inside `role="menu"` is missing
  `role="none"`. Siblings at `:143,154,165` have it, and the comment at `:140`
  explains why it is needed.

COMMENT: fix it

> **No change needed - the finding was wrong.** The Remove form at `_editor.html:180`
> already has `role="none"`, as does every form inside either menu. The only form
> without it (`_checklist.html:149`, adopt) is outside the menu.

- **HTMX fragment dialogs do not manage focus** (`_setup_modal.html`,
  `_upload_modal.html`, `_field_modal.html`, `_step_dialog.html`). The ARIA is
  right and Escape works, but:
  - nothing moves focus into the dialog after the `hx-get` swap (the only
    `htmx:afterSwap` listener, in `progress-modals.js`, serves progress modals);
  - the step dialog behind a fragment modal is not inert, so Tab reaches the
    checklist underneath (`page_takeover`'s `inert` covers header/main/footer
    only);
  - focus does not return to the row's button on close - the OOB swap replaces
    the whole list;
  - every `hx-trigger="change"` refresh in `_setup_modal.html:11` re-swaps the
    modal and drops focus from the control just changed. Keyboard users lose
    their place on each choice - the most user-visible of these;
  - the first focusable element is the full-screen backdrop
    `<a aria-label="Close">` (`_step_dialog.html:20-22`), so screen readers
    announce two "Close" links.

COMMENT: defer for now

> **Deferred.** See the note under must-fix 4 below, where the same work is
> marked "fix this".
>
> **Done on `793-large-mapping-flow`** in `acefb291`, with the design decision
> made for you - say if you disagree. **No morphing**: idiomorph would be a new
> library, and restoring focus by identity needs nothing new.
> `src/js/init/fragment-dialog-focus.js` reads the state of a
> `[data-fragment-dialog-host]` around each HTMX swap:
>
> - *focus in* - opening focuses the first control in `.dialog-body` (or a
>   `data-dialog-initial-focus`); a page that loads with a dialog open gets the
>   same;
> - *re-render* - the control that had focus gets it back, by id, or by name and
>   value for a radio or checkbox without one;
> - *inert* - the host's siblings (the step dialog) are `inert` while a dialog is
>   open, and only what the module made inert is released;
> - *focus return* - to the opener, found again by `data-focus-id` after the
>   out-of-band swap has replaced it; a menu item or form borrows the id of the
>   marked control in its `data-focus-row`. The plain close links (Cancel, X,
>   backdrop) reload the page, so they are given `#focus=<id>`, which the existing
>   `focus-restore.js` reads;
> - *two "Close" links* - the backdrop link is `tabindex="-1" aria-hidden="true"`
>   in all five dialogs: a pointer affordance, with the X and Escape for the
>   keyboard. `dialog-escape.js` still clicks it.
>
> 11 Vitest cases, component tests for the markup, and a BDD scenario in a real
> browser (open from the keyboard, focus lands in the dialog, the step dialog is
> inert, focus survives the method change, Save returns focus to the row).
> `component_accessibility.md` documents the pattern. **Not covered:** the export
> dialogs on the dashboard and respondents pages are fragment dialogs too, but
> not this branch's - they need only the host attribute to opt in. Safari, which
> does not focus a clicked button, gives a mouse user no opener to return to;
> that is harmless, since they were not using the keyboard.

- **`dialog-escape.js:13-22`** - the window-level Escape handler never checks
  `event.defaultPrevented` or `event.isComposing`; the only opt-out is
  `stopPropagation`. Components listening with `@keydown.escape.window`
  (`dropdown_button.html:47`, `account_menu.html:35`, the Alpine modals in
  `modal.html`) cannot stop it, so one Escape would close them *and* navigate
  away from the step. None sits inside a step dialog today - latent. A stray
  Escape also discards unsaved input in the setup and field modals; same as a
  backdrop click, so a design choice, but Escape is pressed by accident far more
  often. Native `<dialog>` is not involved; HTMX-swapped content is handled
  correctly (the query runs at keypress time); "last in the DOM is topmost" holds
  today and `_step_dialog.html:11-13` documents the assumption.

COMMENT: fix this

> **Done** in `bad26085`. The handler skips an Escape that is `defaultPrevented`
> or `isComposing`, and its doc comment states the contract: a component that
> uses Escape for itself claims it with `preventDefault()` or
> `stopPropagation()`, from a listener on its own element. **What this does not
> fix:** a component listening on *window* (`dropdown_button`, `account_menu`,
> the Alpine modals) may run after this handler, so it cannot rely on that. None
> sits inside a step dialog today; moving them to element-level listeners is the
> real fix, and not this branch's. Unsaved input lost to a stray Escape is
> unchanged - that is a design question (a leave guard), not a bug fix.

- **Hand-rolled markup where components exist.**
  - `_setup_modal.html:12-23`, `_upload_modal.html:9-20`, `_field_modal.html`
    and `_step_dialog.html` write `.dialog-header/body/footer` by hand;
    `components/modal.html` provides `dialog_header`, `dialog_body`,
    `dialog_footer`.
  - Error banners are raw divs (`_setup_modal.html:33-38`,
    `_upload_modal.html:30-35`) with no `role="alert"`/`aria-live` and nothing
    tying the error to the input; `alert(variant="error")` exists.
  - `registration/_step_form.html:22-29` hand-rolls a warning banner in a file
    that already imports `alert`.
  - Info cards at `target_sources/view.html:37-49` and
    `respondent_field_schema/view.html:38-44` are hand-rolled.
  - The "✕" close link and error div already exist on main in `_field_modal.html`,
    so the branch copies rather than invents them.

COMMENT: fix this

> **Done** in `8421791a`. The five dialogs and `step_dialog` use `dialog_header`,
> `dialog_body` and `dialog_footer`; error banners and the `_step_form.html`
> warning use `alert()`, so they now carry `role="alert"` (asserted in a test).
> `step_dialog` captures `caller()` before its nested call blocks.
> **Left alone:** the two gsheet info cards. They are copies of the same card on
> `assembly_targets.html` and `assembly_respondents.html`; changing two of four
> would be the inconsistency. Worth a `info_card` macro one day, across all four.

- **Text glyphs instead of icon macros.** `✕` at `_setup_modal.html:22`,
  `_upload_modal.html:19`, `_field_modal.html:45` (`_step_dialog.html:32`
  correctly uses `dialog_close_icon()`); `✓`/`✗` at `_checklist.html:31-43`, read
  out as "check mark" / "ballot x". `test_icons.py` cannot catch these - they are
  not `<svg>`.

COMMENT: fix this

> **Done** in `4516ea69`. Close buttons use `dialog_close_icon()`; the checklist's
> tick and cross are `icon_check` / `icon_close`, `aria-hidden`, since each status
> sentence already says the same in words. A test fails if any of the three
> glyphs reappears in the checklist or the set-up dialog.

- **`_field_modal.html:99`** - `govuk-tag govuk-tag--green` has no styling in the
  backoffice (`backoffice/base.html` loads only the Tailwind `main.css` and the
  tokens; `.govuk-tag` lives in `src/scss/application.scss`). The "Feeds target"
  tag renders as plain bold text. Main used `govuk-tag--grey` in the same spot,
  so the habit is inherited, but the line is new.

COMMENT: fix this

> **Done** in `dcd5e6f5`. The tag now uses `.question-tags`, the same style - and
> the same link to the data sources step - as the question's row in the editor.
> Note `respondent_status_form.html` and `confirm_upload_diff.html` use the
> unstyled `govuk-tag` too; they are on main, so not touched.


### Tests

- **Untested error branches in `target_sources.py`:**
  - `adopt_view` with a malformed/missing `field_id`, and with a name-mismatch
    conflict;
  - `resync_view` error flash (age-bracket refusal, no linked field);
  - `recompute_view` / `upload_view` with nothing linked;
  - `_upload_modal_response` when the linked field is not derived;
  - `upload_view` on `UnicodeDecodeError`, on the 422 conflict, and with
    `allow_new_outputs=1` (grep for `UTF-8` / `allow_new_outputs` in the component
    tests finds nothing);
  - `setup_modal` with an unknown category;
  - `unlink_view` deleting a derived field ("Computed question removed") - BDD
    only;
  - `_parse_setup_spec` for a small mapping with no source selected.
- **`test_unknown_category_404s_politely`**
  (`test_backoffice_target_sources.py:676`) asserts only `status_code == 302`. A
  successful unlink and a permission-denied response also return 302, and the
  name says 404. Assert the redirect location and/or the flash.
- **Service-layer unit gaps in `target_source_service.py`:**
  `_configure_exact_copy` refusing a derived field; `_resolve_source_field` with
  an empty key or a non-existent reuse ID; `_stale_for_derived` when the config
  no longer parses; `_relink` via `adopt_field`; `rename_derived_field` keeping a
  custom label.
- **`delete_derived_field` / `rename_derived_field` reassign
  `respondent.attributes`** "so the JSON column change is detected" - SQLAlchemy
  behaviour tested only over the fake store. `docs/testing.md` puts that in an
  integration test.
- **No `tests/e2e/` smoke test for any target-sources route**; `docs/testing.md`
  asks for a Postgres happy path per route. BDD partly compensates.
- **`_setup_summary` (`backoffice_registration.py`)** - the gsheet branch
  returning `None` and the `targets_stale` count are untested.
- **JS:** `row-actions-menu.test.js` stubs `$refs` and the event, so the real
  claim - Escape in an open menu does not reach `dialog-escape` - is never
  exercised end to end; a jsdom test wiring both would pin it.
  `dialog-escape.test.js` has no case showing a `div.dialog-backdrop--clickable`
  (the Alpine modals) is ignored.

## Carried over from the `793-derived-fields-ui` review

[ui-branch-review.md](../793-derived-fields/ui-branch-review.md) marked items
**DEFERRED** to this branch to avoid merge conflicts. Each was re-checked against
the current code on 2026-09-18. The one that came back as a regression is
finding 5 above.

### First, what changed underneath them

Derived fields no longer appear in the fields editor: `_schema_page_context`
drops the `DERIVED` group (`respondent_field_schema.py:825-835`) and "Derived" is
gone from the question-type picker. They are created and edited from the target
data sources step instead. But the old machinery is all still there:

- routes `fields/add-derived`, `fields/<id>/derivation`,
  `fields/<id>/mapping-modal`, `fields/<id>/mapping-upload` and
  `fields/<id>/recompute` in `respondent_field_schema.py`;
- `_derived_panel.html`, `_mapping_upload_modal.html`, and the `field.is_derived`
  branches of `_editor.html:156-175` and `_field_modal.html:90,175`;
- their component and e2e tests, which keep all of it green.

No link in the UI reaches any of it, but every route answers a direct POST. And
`add-derived` still creates a derived field **without** setting
`target_category_id` (`respondent_field_schema.py:1195-1204`) - the state
`delete_derived_field`'s docstring calls "can never be reached again". (It is
probably recoverable: the checklist's name match should offer to adopt it. Not
verified.)

> **Decided, and done on `793-large-mapping-flow`** (`f3b0f09b`, "retire the
> derived-field UI from the registration questions editor"). That commit removes
> the five routes, `_derived_panel.html`, `_mapping_upload_modal.html` and the
> derived branches of `_editor.html` and `_field_modal.html`; redirects an old
> link to a computed question's edit dialog to the data sources step; and moves
> the upload and Postgres round-trip tests over to target sources. Nothing to do
> on this branch. What it changes for the items below (checked against the tree
> at that commit, not run):
>
> - "Only in the unreachable code" - both items go away with the routes.
> - Must-fix 1 shrinks to the two live routes, `fields/add` and
>   `fields/<id>/update`; `_modal_roundtrip_response` is unchanged there.
> - Should-fix 13 is half done: the parsers and `age_prefill_from_target` move
>   into `target_sources.py`, which ends the import from
>   `respondent_field_schema.py` (the import of `registration_hub_context` from
>   `backoffice_registration.py` remains). They are still in a blueprint, not the
>   domain, so the drift risk against `AgeBracketRule.bracket_labels()` stands.
> - Should-fix 11 loses the `_derived_panel.html` site; `_field_modal.html` and
>   `_setup_modal.html` still send the token.
> - **Finding 5 is not fixed there** - `_apply_age_prefills` is unchanged at that
>   commit - and neither are must-fix 3, the report modal nits or "Copy options
>   from target".
>
> One practical note: `f3b0f09b` rewrites about a hundred lines of
> `target_sources.py`, and the finding 2 fixes on this branch (`b1f7ce54`) touch
> the same file, so expect conflicts there when `793-large-mapping-flow` picks
> this branch up. Any further fixes to `target_sources.py` - finding 5 in
> particular - may be cheaper to make on that branch.

### Still open

- **Must-fix 1 - modal POST error paths raise uncaught (confirmed by probe).**
  A user with no role on the assembly POSTing to `fields/add`,
  `fields/add-derived`, `fields/<id>/derivation`, `fields/<id>/mapping-upload` or
  `fields/<id>/update` gets `InsufficientPermissions` out of the route: the
  `_try_*` helper catches it and returns a friendly message, then
  `_modal_roundtrip_response` -> `_schema_page_context` raises it again with no
  handler. `fields/<id>/recompute` is fine. Same shape as finding 2, same fix (a
  guarded re-render helper), and the parametrised "no route answers a refusal
  with a 500" test written for target sources would carry over directly.
  `fields/add` and `fields/<id>/update` are live UI routes, so this one does not
  wait on the dead-code decision.

COMMENT: fix this

> **Done** in `db9a7b2f`. A `_refusals_go_to_the_dashboard` decorator on the five
> dialog POST routes. `TestRoutesTurnAwayThoseWithoutAccess` now runs **every**
> route on the blueprint as a user with no role and with an unknown assembly; ten
> of those cases failed before the fix.

- **Must-fix 3 - renaming an option in the modal drops it from small mappings.**
  Unchanged. `_submitted_options` (`respondent_field_schema.py:538-545`) still
  builds the list wholesale with no option identity, so the service sees a rename
  as remove + add and `_drop_small_mapping_keys` deletes the mapping row.
  Respondents who gave the old answer fall to UNKNOWN on the next recompute, with
  nothing on screen saying so. Live: small-mapping sources are ordinary choice
  questions edited in the live modal. Either carry a hidden original value per
  row, or report the dropped keys.

COMMENT: fix this

> **Done** in `cb8748cd`. Each option row carries a hidden `option_original`, which
> survives the dialog's add/remove round trips, and `update_field` takes
> `option_renames`. It checks each pair against the field's real options - old
> value is an option, is no longer in the list, new value is - so a tampered
> `original` describes no rename. Renaming every mapped option at once is no
> longer mistaken for emptying the mapping. **Not covered:** respondents' stored
> answers still hold the old value; that is equally true of the single-option
> rename route, which this mirrors.

- **Must-fix 4 - HTMX modal accessibility contract.** Partly done: Escape now
  works everywhere via `dialog-escape.js`. Focus into the fragment, focus return,
  the trap, and the focusable backdrop link named "Close" are all still open, for
  the old modals and the new ones alike - already written up under "HTMX fragment
  dialogs do not manage focus" in Medium above.

COMMENT: fix this

> **Not done - your two comments disagree.** This is the same work as "HTMX
> fragment dialogs do not manage focus" under Medium, which you marked "defer for
> now". I followed the defer: it is the larger instruction (focus-in after the
> swap, `inert` on the step dialog, focus return across an OOB swap that replaces
> the button, and keeping focus through every `hx-trigger="change"` re-render),
> and the last of those really wants a design decision - morph the form rather
> than replace it, or restore focus by element id. Tell me which you meant.
>
> **Done on `793-large-mapping-flow`** in `acefb291` - restore by identity, not
> morph. See the note under "HTMX fragment dialogs do not manage focus" above.

- **Should-fix 11 - CSRF token in GET query strings.** Unchanged, and the new
  modal copies it: `hx-include="closest form"` on a refresh `hx-get` at
  `_field_modal.html:10`, `_derived_panel.html:7` and now
  `target_sources/_setup_modal.html:11`. The token and the whole form go into the
  URL, so into access logs and browser history. No `hx-params` anywhere in either
  template directory. Fix: `hx-params="not csrf_token"`.

COMMENT: fix this

> **Done** in `7eaf3d98`: `hx-params="not csrf_token"` on all three refresh
> requests, with a test on each live dialog.

- **Should-fix 12 - several `with uow:` blocks per request.** Unchanged in the
  schema blueprint and repeated in the new one - already under Medium above.

COMMENT: fix this

> **Done for `target_sources.py`, partly for the schema blueprint** - see the
> note under "Python / architecture" in Medium above.
> The schema blueprint was finished on `793-large-mapping-flow` in `e23ee18a`.

- **Should-fix 13 - business logic in the blueprint.** Worse.
  `age_prefill_from_target` (the inverse of `AgeBracketRule.bracket_labels()`),
  `parse_age_rule` and `parse_small_mapping_rule` still live in
  `respondent_field_schema.py`, and `target_sources.py` now imports them from
  there - the blueprint-imports-blueprint item under Low. They want to move to the
  domain or service layer, which fixes both.

COMMENT: fix this

> **Done** in `26965765`. The form parsers live in
> `entrypoints/derivation_form_parser.py`, which both blueprints import, so
> `target_sources.py` no longer imports from `respondent_field_schema.py`. The
> reading of bracket-shaped target values is now
> `domain.respondent_derivation.age_brackets_from_labels`, beside the
> `bracket_labels()` it inverts, with a round-trip test that fails if either
> changes alone.
>
> **Expect a conflict:** `f3b0f09b` moves these same functions into
> `target_sources.py`. The resolution is to keep this branch's module and delete
> that branch's copies - and move its `test_target_source_parsers.py` imports to
> match. The import of `registration_hub_context` from `backoffice_registration.py`
> remains (it was not part of this item).
>
> **Merged as predicted** (`714067fd`): this branch's module kept, that branch's
> copies deleted, `test_target_source_parsers.py` repointed. `parse_derivation_rule`
> went too - its only callers were the routes `f3b0f09b` retired.

- **Should-fix 15 - wording.**
  - "Not on form" is still the label for `FieldOnRegistrationPage.NO`
    (`domain/respondent_field_schema.py:145`), and the new
    "Label on the form (optional)" (`_setup_modal.html:142`) joins it. Glossary:
    "registration page". "Shown on the form as" has gone.
  - Hand-built plurals: "%(count)d lookup rows" (`_editor.html:92`), its new
    near-duplicate "%(count)s lookup rows" (`_checklist.html:36`), and
    "%(count)d completed selection run(s)" - now in two places
    (`_derivation_report_modal.html:26`, `target_sources.py:416`). Use `ngettext`.
  - "Remove" deleting what other copy calls "delete" - now the remove-vs-delete
    item under Medium above.

COMMENT: fix this

> **Done** in `2f9a2ab9` (catalogue in `d2d3a850`), except the remove-vs-delete
> bullet, which belongs to the deferred i18n section.
> That bullet has since been done, in `3c7187db`.
>
> - "Not on form" -> "Not on registration page"; "Label on the form (optional)" ->
>   "Label on the registration page (optional)". The first had a Hungarian
>   translation, now lost.
> - The lookup-row and selection-run counts use `ngettext`, and the two lookup-row
>   msgids are one. `opendlp.translations` had no `ngettext`, so it gains a wrapper
>   mirroring `gettext` (Flask-Babel in a request, the loaded catalogue outside).
>   `translate-check` passes; the new plural entries need Hungarian.

- **Should-fix 16 - hand-rolled components.** Unchanged, and copied into the new
  templates - already under Medium above.
- **Should-fix 17 - JS preview diverges from the server.** Half open. The blank
  min/max case is closed in the new modal, because the server writes 16 and 100
  into the inputs before rendering. But `age-bracket-preview.js:39,58-60` still
  accepts `min_age = 0` (`/^\d+$/`, then only `maxAge <= minAge`) while
  `AgeBracketRule` rejects `min_age <= 0`, so the preview shows brackets for a
  rule the save will refuse.
- **Nit - report modal.** `_derivation_report_modal.html:71` still hardcodes
  `limit=20` rather than `UNMATCHED_SAMPLE_SIZE`, and `:66` still hardcodes
  "UNKNOWN" in the msgid "Fell back to UNKNOWN:" while sibling strings pass
  `%(fallback)s`. The modal is shared by the new target-sources flow, so this is
  live.
- **Nit - double quotes round placeholders** in `_field_modal.html:156,165`
  (moved from 178,186) - joins the double-quote item under Low above.
- **Nit - prefill overwrites typed min/max for a new field.** Still true, in its
  new home: `_apply_age_prefills` (`target_sources.py:248-251`) replaces min, max
  and boundaries together whenever boundaries is blank, and the modal refreshes on
  every `change`. Same function as finding 5; fix them together by only filling
  fields that are blank.
- **Nit - hardcoded English `Day` / `Month` / `Year`** in the generated public
  registration form (`registration_page.py:515,617`). Unchanged; still the known
  gap that the sandboxed environment has no `_`.
- **Nit - `data-target-values` attribute route.** Unchanged and now used by the new
  modal - already under Low above.
- **Deviation - a non-HTMX POST answered with a 200 page, so a refresh re-runs the
  work.** Mostly fixed in the new flow: configure, adopt, resync, recompute and
  unlink redirect when the request is not HTMX, and HTMX successes now raise a
  toast. One left: `_report_response` (`target_sources.py:372-395`), used by the
  lookup-table upload, still renders `view.html` with a 200, so refreshing
  re-posts the upload and recomputes again. The old schema routes are unchanged
  but unreachable.

### Only in the unreachable code - removed by `f3b0f09b`, nothing to do

- **Should-fix 10 - editing a small mapping after a target rename shrinks its
  options.** `_try_update_derivation` (`respondent_field_schema.py:1251-1252`)
  still finds the target by lower-cased `field_key` rather than by the
  `target_category_id` link that now exists. The original trigger is mostly closed
  anyway, since renaming a target now re-keys its derived field.
- **Nit - `create_derived_field`'s duplicate check is exact-match**
  (`derivation_service.py:374`) while target matching is case-insensitive. The new
  flow compares with `casefold()` throughout (`target_source_service.py:465-522`),
  so `Gender` beside `gender` is only reachable through the old `add-derived`
  route.

### Fixed along the way

- **Nit - `<th>` without `scope="col"`.** Fixed: `_editor.html:47-50`.
- **Deviation Q4** (key override as a `<details>` disclosure) - superseded; the new
  modal names the question it will create.
- **Deviation - "Derived option disabled with hint"** - superseded; the option is
  gone from the picker.
- **Deviation - no flash or toast on an HTMX success** - fixed in the new flow
  (`_toast_response`, `_saved_response`).

### Deviations still standing, to confirm as deliberate

- **Q8 - the derived field key is the target name verbatim**, not
  `normalise_field_key`. Still so, and now load-bearing: `rename_derived_field`
  keeps key and target name in step.
- **"Copy options from target"** is still in the field modal (`_field_modal.html:156`)
  and still not in any plan. With exact-copy set-up on the data sources step doing
  the same job properly - linked, and re-syncable - is it still wanted?

### Test gaps carried over

The earlier review left its test-gap list open. Not re-audited line by line; the
ones that visibly still matter:

- No permission-denied test on the schema blueprint's modal routes - which is why
  must-fix 1 is still there two branches on.
- No modal-path 422 test for `FieldDefinitionConflictError` on edit.
- `age-bracket-preview.test.js` still lacks the zero-age case (should-fix 17).
- The rest sat in the derived-field tests, which `f3b0f09b` removes or moves.

## Rewords - your call

The Hungarian catalogue has no fuzzy entries, so each of these is now an
untranslated new msgid.

| Old | New |
| --- | --- |
| "Yes / No", "Yes / No / Not set" | "Checkbox" (both), plus "Checkbox (can be left unanswered)" |
| "Add a field" | "Add a question" |
| "Field added" / "updated" / "removed" | "Question added" / "updated" / "removed" |
| "Field" (table header) | "Question" |
| "Guess field types from data" | "Guess question types from data" |
| "Guessed types for %(count)d fields" | "Guessed types for %(count)d questions" |
| "No fields were guessed - ..." | "No question types were guessed - ..." |
| "Only fields still set to Text will be updated; explicitly-typed fields are left alone." | "Only questions still set to Text ...; explicitly-typed questions are left alone." |
| "Schema initialised with %(count)d fixed fields" | "... %(count)d built-in questions" |
| "Fixed fields keep their built-in type." | "This is a built-in question, so its type can't be changed." |
| "No schema has been set up ... reserved fixed fields only (...)" | "... built-in questions only (...)" |
| "Remove this field from the schema? Respondent data keeps its values..." | "Remove this question? Respondent data keeps its values..." |
| "Help text" | "Help text (optional)" |
| "Optional hint shown beneath the field on the registration page." | "Shown beneath the question on the registration page." |
| "Radio buttons" | "Radio" |
| "Registration" (h2) | "Registration page" |
| "This assembly has no registration pages yet. Create one to start..." | "No registration page created yet" + "Use the button above to create one." |

Dropped with no successor: "Fields" (tab), "Fixed" (tag), "Summary", "Order",
"Move", "Section for %(key)s", "Kind of text", "Shown on the form as", "On the
registration page", "Derived (computed from another field)", "Create targets
first to add a derived field - it feeds one."

Nearly all follow from the deliberate field -> question move, which I would
accept. Two look incidental and could be reverted to save retranslation:
**"Help text" -> "Help text (optional)"** and **"Radio buttons" -> "Radio"**.

## Low

- `assert` used for control flow in `target_source_service.py`
  (`assert created is not None`, `assert linked.derivation_type is not None`,
  `assert linked.derivation_config is not None`) - stripped under `python -O`.
- A blueprint imports another blueprint: `target_sources.py` and
  `respondent_field_schema.py` import `registration_hub_context` from
  `backoffice_registration.py`; `target_sources.py` imports `parse_age_rule`,
  `parse_small_mapping_rule`, `age_prefill_from_target` from
  `respondent_field_schema.py`. Better in a non-blueprint module.
- `delete_derived_field` / `rename_derived_field` load every respondent of the
  assembly to rewrite one JSON key, inside the `save_all` / unlink request
  transaction. Slow on large pools.
- `TargetLinkedError` is correctly uncurated (the route renders `blocks`, never
  the message). `LinkedFieldBlock.action` is a bare `"rename"`/`"delete"` string
  where an Enum would be tidier.
- `tests/fixtures/json_api/respondent-field-spec.json` - every record has
  `"feeds_target": null`, so the JS/contract side never sees the string case.
- Double quotes around placeholders where the guide asks for single:
  `_checklist.html:31,33,39`, `_setup_modal.html:130,150`,
  `targets_force_unlink_confirm.html:30,32,40`. `_checklist.html:121-126` uses
  single, so the file disagrees with itself.
- `target_source_service.py:190` - "before wiring a data source" is code jargon;
  "setting up a data source" matches the screen.
- Field and question mixed within one flow: `_checklist.html:48`,
  `_field_modal.html:103`, `respondent_field_schema_service.py:351`,
  `target_sources.py:674` next to `:638`. ("Field '%(key)s' ..." service errors are
  defensible - they name a field key.)
- "Choose one" (`_field_modal.html:16`), "Select one" (`_setup_modal.html:40`)
  and "Choose a question..." are separate msgids for one idea.
- "%(count)s lookup rows" (`_checklist.html:36`) has no plural handling and sits
  beside the existing "%(count)d lookup rows" - two msgids differing only in
  format. "%(count)s questions on the registration form" also lacks plurals.
- `target_sources.py:102-104` defaults new field keys to "Postcode",
  "year_of_birth", "date_of_birth"; they become labels via `humanise_field_key`,
  so are English in every language. Probably accepted as data.
- Static inline styles, which `frontend_security.md` discourages: widths at
  `_setup_modal.html:177-194`, `min-width: 12rem` on the menus and mapping rows,
  `list-style: none; padding: 0;` at `_checklist.html:20`, `<col style>` at
  `_editor.html:41-45`. (`style="color: var(--...)"` is house style - not flagged.)
- `_editor.html:61-66` - the question name cell is a `<td>`; `<th scope="row">`
  would give row context. The hand-rolled `.question-table` is otherwise
  justified by the Figma design and structurally correct.
- `main.css` `.row-link-host { position: relative }` on a `<tr>` - older Safari
  ignores it, so the `::after` overlay can escape the row. Needs a quick Safari
  check.
- `components/registration_page_list.html:228` - the illustration `<img>` has no
  `v=static_hashes(...)` cache-buster; the SVG is a 66KB unoptimised Figma export
  and contains a layer id `20365528_SEO_Services_6_` that looks like a
  stock-asset identifier. **Worth confirming the licence.**
- `_setup_modal.html:161-164` passes user-written target values to
  `ageBracketPreview` via `data-target-values='{{ ...|tojson }}'` rather than a
  JSON script block. Safe as written (single-quoted, `tojson` escapes `'`,
  commented), and copied from `_derived_panel.html:71-73` on main.
- `_editor.html:185` - `@submit.prevent="$confirm('{{ _("...") }}', $el)"` is the
  established `$confirm` pattern and was on main; known weakness that a
  translation containing an apostrophe breaks the expression. The same file uses
  `data-confirm` elsewhere, which does not have the problem.
- `pie_chart_card.html:11-24` references `--color-data-*` primitives directly. A
  semantic `--color-chart-series-N` layer would be purer; with one consumer, not
  worth blocking on.
- Test brittleness: BDD steps match literal English ("2 fell back to UNKNOWN",
  "Break the links and save"); many component-test `"..." not in body` negatives
  pass silently if wording changes (`test_backoffice_target_sources.py:172,206,225,358-360`);
  `see_warning_toast` asserts the inline style contains `--color-warning-100`.
- `tests/e2e/test_backoffice_respondent_field_schema.py:48-49` - positive
  `b"Fixed" in body` became negative `b">Fixed<" not in body`. Justified product
  change, and other positive assertions keep the test from being vacuous.
- Spotted while fixing: `_setup_modal.html:76,117,221` build their option lists
  with `{% set _ = list.append(...) %}`, which shadows gettext's `_` for the rest
  of that scope. It works today only because nothing after it in the loop body
  calls `_()`. `_editor.html` carries a comment warning against exactly this.
- Not this branch (raise an issue): `docs/frontend_build.md`'s entry-point table
  omits `backoffice/js/pie-chart`, which came in from main.

## Clean

- **Config/build:** no changes to `config.py`, `env.example`,
  `docs/configuration.md`, `esbuild.config.mjs`, `package.json`, the justfile or
  either conftest. No new table, so the conftest delete lists need no change.
- **JS:** nothing hand-written under `static/`; `row-actions-menu.js` is imported
  by `backoffice/alpine-components.js` and `dialog-escape.js` by `utilities.js`,
  both entry points; no CDN references; new Alpine code is CSP-compliant (named
  `Alpine.data()` components, zero-arg handlers, simple ternaries, no `x-model`);
  no user-facing strings added in JS; no hand-typed API literals in tests.
- **Templates:** the one `caller()` (`_step_dialog.html:36`) is directly in the
  macro body; no inline `<svg>`; `icon_arrow_forward` is a proper Lucide glyph
  with `aria-hidden` and a showcase entry; no per-call-site stroke-width; every
  `var(--...)` is defined; `test_icons.py` and `test_design_tokens.py` untouched;
  the `--color-data-*` scale belongs in `primitive.css`. Icon-only buttons all
  have contextual `aria_label`s; unlabelled selects carry `aria-label`; fieldsets
  and legends used; removing the stale static `aria-checked` from the switch in
  `input.html` is correct.
- **JSON API:** no `str(e)` in any JSON body; the field-spec route, schema and
  fixture agree (`feeds_target` added, required, `string|null`; `SPEC_VERSION` 5
  in service, fixture and `docs/respondent_field_spec.md`).
- **Transactions:** no `render_template`, gspread or SMTP inside a `with uow:`;
  no new `except Exception`; no `commit_and_reset()`; no broad suppress inside a
  block (`contextlib.suppress(ServiceLayerError)` in `_page_context` is narrow
  and follows precedent). `_guard_linked_categories` breaks links before
  validation, but `TargetsNotSaved` is raised inside the block, so it all rolls
  back.
- **Layering:** domain stays plain Python; no Flask in the service layer; the new
  ORM column is a plain UUID FK with no relationship.
- **Auth/CSRF:** every new route has `@login_required`; every service entry point
  asks `can_manage_assembly` / `can_view_assembly` (a capability, not a role);
  every URL/form id is checked against `assembly_id`; all seven POST forms and
  the force-unlink page carry `csrf_token`.
- **Personal data:** structlog only, no PII logged; the uploaded CSV (a postcode
  lookup table, not respondent data) is held in memory only; nothing touches
  cookies, sessions or analytics.
- **i18n mechanics:** `_()`/`_l()` used correctly (module-level dicts use `_l()`,
  request-time dicts use `_()`); no literal-beside-lookup, f-string or `.format()`
  inside `_()`; no lone `%`; placeholders well-formed; glossary terms (Google
  Sheets, spreadsheet, target, respondent), British spelling and "no we" all
  hold. The `docs/language.md` additions match the strings used, apart from
  "computed question".
- **Tests:** tiers are right (unit over `FakeUnitOfWork`, component over
  `FakeStore`, BDD via feature files); no `skip`, `xfail`, `sleep` or mocks
  added; `TargetLinkedError` went on the UNCURATED list (the safe side);
  `test_accessibility.py`'s selector change is a legitimate tightening; the
  deleted BDD scenario is replaced by one in `target-data-sources.feature`.

## Suggested order

1. Finding 1 - it affects live pages the branch never meant to touch.
2. Finding 3 - it undermines the invariant the branch's last commit was written
   to protect.
3. Finding 2 - the 500s.
4. Finding 4 - the tests that would have caught part of 2.

Added after re-checking the deferred items: finding 5 belongs with 3, since both
silently change data. Carried-over must-fix 1 is the same fix as finding 2 and is
cheap to do alongside it. Must-fix 3 is the remaining silent data loss.

One thing to push back on in advance: if the APG menu gap is waved through
because `dropdown_button` does it too, that makes two components announcing
arrow-key behaviour they do not have.
