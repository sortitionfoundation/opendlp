# Plan: Add & remove fields on the respondent field schema page

**Date:** 2026-06-11
**Branch:** `613-require-reg-fields`
**Status:** Approved — in progress
**Page in scope:** `view_schema()` in `entrypoints/blueprints/respondent_field_schema.py`,
served at `GET /backoffice/assembly/<id>/respondent-schema`.

---

## TL;DR / key finding

The task asks to "add and remove fields". **Remove is already fully implemented**, end to end:

- Service: `delete_field()` in `respondent_field_schema_service.py` (protects fixed fields,
  leaves respondent attribute data untouched).
- Route: `delete_field_view()` in the blueprint.
- UI: a red **Remove** button per non-fixed row in `templates/backoffice/respondent_field_schema/view.html`
  (lines ~223–231), with a JS confirm.
- Tests: `test_delete_non_fixed_field`, `test_cannot_delete_fixed_field` (e2e) and
  `TestDeleteField` (integration).

So the real gap is **add**. `add_field()` already exists in the service layer and is
covered by integration tests (`TestAddField`), but it is only reachable through the dev
service-docs tool (`/backoffice/dev/service-docs?tab=fields`) — there is **no blueprint
route and no UI** on the schema page itself. See `refactoring-add-field.md` in this folder,
which explicitly lists "Add Field button on the Fields tab" as a deferred future enhancement.

This plan therefore covers wiring `add_field()` into the schema page (route + UI + tests),
and double-checks that remove is complete. **Open question 1** asks whether that scope read
is correct.

---

## How the feature fits together (DDD layers)

Per `docs/architecture.md`, this feature spans three layers, all of which already exist for
the sibling operations (update / delete / move / options):

| Layer      | File                                                                                                                                              | Status for "add"                                            |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Domain     | `domain/respondent_field_schema.py` — `RespondentFieldDefinition`, `FieldType`, `RespondentFieldGroup`, `FieldOnRegistrationPage`, `ChoiceOption` | ✅ complete, no change needed                               |
| Service    | `service_layer/respondent_field_schema_service.py` — `add_field()`                                                                                | ✅ exists & tested; no change needed (maybe minor, see OQ2) |
| Entrypoint | `entrypoints/blueprints/respondent_field_schema.py` — `view_schema()` + sibling POST routes                                                       | ❌ **needs new `add_field_view` route**                     |
| Template   | `templates/backoffice/respondent_field_schema/view.html`                                                                                          | ❌ **needs an "Add field" form**                            |
| Tests      | `tests/e2e/test_backoffice_respondent_field_schema.py`                                                                                            | ❌ **needs e2e coverage for add**                           |

The pattern to mirror is the existing **add option** flow (`add_option_view` route +
the inline add-option `<form>` at the bottom of each choice field's options block), and the
**update** flow's choice-seeding logic.

---

## Decisions (from review)

1. **Scope:** add-only. Remove is already complete; no change to remove behaviour.
2. **`field_key` normalisation:** these keys drive the registration form HTML `name`
   attributes, so we **normalise** user input — lowercase, spaces/hyphens → `_`, drop any
   remaining non-`[a-z0-9_]` characters, trim leading/trailing `_`. Implemented as a new
   `normalise_field_key()` domain helper (unit-tested), called by the route. A blank result
   after normalisation is rejected.
3. **Form placement:** a single bottom-of-page "Add a field" form, shown only when a schema
   already exists and the source is not a Google Sheet.
4. **Choice fields at creation:** seed one placeholder option (`option_1`) the organiser
   renames afterward, mirroring `update_field_view`.
5. **Error-message i18n:** leave the pre-existing untranslated `flash(str(e))` pattern as-is
   for this round; revisit separately.
6. **Permission:** `can_manage_assembly` (same as update/delete).

---

## `add_field()` — the service function we're wiring in

```python
def add_field(
    uow, user_id, assembly_id, field_key, *,
    label: str | None = None,
    group: RespondentFieldGroup = RespondentFieldGroup.OTHER,
    field_type: FieldType = FieldType.TEXT,
    options: list[ChoiceOption] | None = None,
    on_registration_page: FieldOnRegistrationPage = FieldOnRegistrationPage.YES_REQUIRED,
) -> RespondentFieldDefinition
```

Already handles, and we get for free:

- `_ensure_manage_permission` (raises `InsufficientPermissions` / `AssemblyNotFoundError`).
- Empty key → `FieldDefinitionConflictError("Field key cannot be empty")`.
- Duplicate key (including collision with a **fixed** key like `email`) → `FieldDefinitionConflictError`.
- Auto sort_order at the end of the chosen group; auto label via `humanise_field_key`.
- Commits the transaction and returns a detached copy.

Caveat: for choice types the domain invariant requires a non-empty `options` list, so the
route must seed a starter option when the user picks a choice type (see OQ4). The
`update_field_view` route already does exactly this with `[ChoiceOption(value="option_1")]`.

---

## Proposed implementation

### 1. New blueprint route — `add_field_view`

In `entrypoints/blueprints/respondent_field_schema.py`:

```
@respondent_field_schema_bp.route(
    "/assembly/<uuid:assembly_id>/respondent-schema/fields/add",
    methods=["POST"],
)
@login_required
def add_field_view(assembly_id):
    field_key = normalise_field_key(request.form.get("field_key", ""))
    label = request.form.get("label", "").strip() or None
    group = _parse_group(request.form.get("group")) or RespondentFieldGroup.OTHER
    field_type = _parse_field_type(request.form.get("field_type")) or FieldType.TEXT
    on_registration_page = (
        _parse_on_registration_page(request.form.get("on_registration_page"))
        or FieldOnRegistrationPage.YES_REQUIRED
    )

    if not field_key:
        flash(_("Field key is required (letters, numbers and underscores)."), "error")
        return _schema_page_redirect(assembly_id)

    # Choice types need at least one option to satisfy the domain invariant;
    # seed a placeholder the organiser can rename, mirroring update_field_view.
    options = [ChoiceOption(value="option_1")] if field_type in CHOICE_TYPES else None

    try:
        uow = bootstrap.bootstrap()
        add_field(
            uow, current_user.id, assembly_id, field_key,
            label=label, group=group, field_type=field_type,
            options=options, on_registration_page=on_registration_page,
        )
        flash(_("Field added."), "success")
    except FieldDefinitionConflictError as e:
        flash(str(e), "error")
    except InsufficientPermissions:
        flash(_("You don't have permission to edit the schema"), "error")
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    return _schema_page_redirect(assembly_id)
```

- Add `add_field` to the existing import from `respondent_field_schema_service`, and
  `normalise_field_key` to the domain import.
- `_parse_group` / `_parse_field_type` / `_parse_on_registration_page` helpers already exist
  and return `None` on bad/empty input, so the `or DEFAULT` fallbacks give sane defaults.
- Note: `FieldDefinitionConflictError` messages from the service are English literals, not
  `_l()`-wrapped (same as today's other routes that `flash(str(e))`). That is an existing
  inconsistency — out of scope here, but flagged in OQ5.

### 2. Template — an "Add field" form

In `view.html`, inside the `{% else %}` branch (schema exists and source is **not** gsheet),
after the `{% for section in sections %}` loop, add a single "Add a field" form. A single
form with a group dropdown is simpler than per-section add buttons and matches the flat,
form-driven style of the page. Reuse the already-passed context vars
(`group_choices`, `field_type_choices`, `on_registration_page_choices`).

Sketch:

```html
<section class="mb-8">
  <h2 class="text-display-sm mb-4">{{ _("Add a field") }}</h2>
  <form
    method="post"
    action="{{ url_for('respondent_field_schema.add_field_view', assembly_id=assembly.id) }}"
    class="flex flex-wrap gap-3 items-end"
  >
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}" />
    <input
      type="text"
      name="field_key"
      required
      class="govuk-input"
      placeholder="{{ _('field_key (e.g. age_range)') }}"
      aria-label="{{ _('Field key') }}"
    />
    <input
      type="text"
      name="label"
      class="govuk-input"
      placeholder="{{ _('Label (optional)') }}"
      aria-label="{{ _('Label') }}"
    />
    <select name="group" class="govuk-select" aria-label="{{ _('Section') }}">
      ...
    </select>
    <select
      name="field_type"
      class="govuk-select"
      aria-label="{{ _('Field Type') }}"
    >
      ...
    </select>
    <select
      name="on_registration_page"
      class="govuk-select"
      aria-label="{{ _('On registration form') }}"
    >
      ...
    </select>
    {{ button(_("Add field"), type="submit", variant="primary") }}
  </form>
  <p class="text-body-sm mt-2" style="color: var(--color-secondary-text);">
    {{ _("Choice fields start with one placeholder option you can rename
    below.") }}
  </p>
</section>
```

- Placement: keep it inside the `else` (existing-schema) branch so it is hidden for
  gsheet-sourced assemblies (whose fields come from the spreadsheet) and when no schema
  exists yet (the Initialise button covers that). See OQ3.
- Accessibility: every control gets an `aria-label` (matches existing rows; see
  `docs/agent/component_accessibility.md`).

### 3. i18n

All new strings wrapped in `_()` (template) / `_l()` not needed here since these are at
request time. After implementation run `just translate-regen`.

### 4. Tests

**e2e** (`tests/e2e/test_backoffice_respondent_field_schema.py`), new `TestAddField` class
mirroring `TestUpdateField` / `TestDeleteField` patterns (seed via `_seed_schema`, post with
`get_csrf_token`, assert 302 then re-query via `respondent_field_schema_service.get_schema`):

- `test_add_field_creates_row` — post field_key + label + group; assert the row exists with
  the right group/label/type and `on_registration_page == YES_REQUIRED`.
- `test_add_choice_field_seeds_placeholder_option` — post `field_type=choice_radio`; assert
  the new field has exactly one option (`option_1`).
- `test_add_duplicate_key_flashes_error` — add a key that already exists (e.g. `custom_notes`
  or fixed `email`); assert no second row created (follow_redirects + check flash / count).
- `test_add_empty_key_is_rejected` — post blank field_key; assert no row added.
- `test_add_field_creates_row` also asserts the submitted `Age Range` is stored normalised
  as `age_range`.
- `test_add_form_renders_when_schema_exists` / `test_add_form_absent_without_schema` — assert
  the form + `add_field_view` action URL appear only once a schema exists (the gsheet branch
  hides the whole edit UI via the same template guard, so it is covered structurally rather
  than with a separate gsheet fixture).

**Unit** (`tests/unit/test_respondent_field_schema.py`): cover `normalise_field_key()` —
lowercasing, space/hyphen → `_`, dropping punctuation, collapsing/trimming `_`, and the
empty-after-normalisation case.

**Integration:** `add_field()` is already covered by `TestAddField` in
`tests/integration/test_respondent_field_schema_service.py`; no new service tests needed
(normalisation lives in the route + domain helper, not in `add_field`).

Per the global testing policy, run `CI=true just test` and `just check` before committing.

### 5. Out of scope (explicitly)

- No domain or ORM changes (the column already exists and round-trips).
- No `conftest.py` `_delete_all_test_data` changes (no new table).
- No change to the CSV-import / reconciliation bulk path (`add_field` deliberately stays
  single-row; see `refactoring-add-field.md` §"CSV Workflow Refactoring").
- The dev service-docs Fields tab stays as-is.

---

## Commit plan

Per repo convention (docs separate from code):

1. Commit this plan doc on its own.
2. Code commit: route + template + e2e tests + regenerated translations, e.g.
   `feat: add fields to the respondent schema page UI`.

---

## Phase checklist

- [x] **Phase 1 — Plan doc.** Integrate review decisions, commit doc on its own.
- [x] **Phase 2 — Domain.** `normalise_field_key()` helper + unit tests.
- [x] **Phase 3 — Route.** `add_field_view` in the schema blueprint.
- [x] **Phase 4 — Template.** Bottom-of-page "Add a field" form.
- [x] **Phase 5 — e2e tests.** `TestAddField`.
- [x] **Phase 6 — Wrap-up.** `just translate-regen`, tests, lint/type/dep checks, commit code.
- [x] **Phase 7 — Error i18n.** Translate the Fields-page `FieldDefinitionConflictError`
      messages; introduce `FixedFieldError` so the fixed-field case is recognised by type
      rather than the brittle `"fixed" in str(exc)` check (Option C, service-owned message).

> Note: `just check`'s prek step can't run in this sandbox (read-only uv tools dir), so
> the equivalent tools were run directly — `mypy`, `deptry src`, `ruff check`, `ruff format`
> all clean. The full test suite passes except the Playwright BDD tests, which fail only
> because the browser executable isn't installed in this environment.

---

## Follow-up (after this round)

- **Done (Phase 7):** the Fields-page `FieldDefinitionConflictError` messages are now
  `_l()`-wrapped, and the fixed-field guard is a typed `FixedFieldError` (domain) caught in
  the service, which raises a translated conflict. The `NotFoundError`/`AssemblyNotFoundError`
  messages were intentionally left English — the blueprint flashes its own translated strings
  and only logs `str(e)` — as was the `reorder_group` programming guard (never user-facing).

- **`InvalidSelection` half-translated flash (separate, CSV-upload feature).**
  `_parse_csv_headers` raises `InvalidSelection("CSV file is empty or has no header row")`
  (in this service), and `respondents.py` surfaces it as
  `flash(_("Invalid CSV format: %(error)s", error=str(e)))` — the wrapper is translated but
  the interpolated message is not, so users see a half-translated flash. Fixing it belongs
  with the CSV-upload / reconciliation work, not the Fields page.

- **Broader flash-message i18n audit (its own ticket).** The `InvalidSelection` case above is
  an instance of a general pattern: `flash(_("… %(error)s", error=str(e)))` where the inner
  exception message is plain English. The same shape appears across `respondents.py`,
  `gsheets*.py`, `targets*.py`, and `db_selection*.py` (many `except InvalidSelection as e`
  sites). A focused pass should audit every such site, decide which inner messages are
  genuinely user-facing, and `_l()`-wrap them at the raise site in the relevant services
  (`respondent_service`, `assembly_service`, `sortition`, …). Scope it separately — it spans
  several features and is larger than this branch.
