# Derived fields — notes for the UI branch

Findings from the code review of `793-derived-fields` (2026-09-15) that are
either UI work or need a UI-level decision, so they were not fixed on the
backend branch. Read alongside [plan-simple-ui.md](plan-simple-ui.md); each
note says which section of that plan it touches.

**Status (2026-09-16, `793-derived-fields-ui`):** everything is done except §3,
which waits until the eligibility sentence reaches a registration form.
[Left alone](#left-alone) lists smaller things spotted along the way.

## 1. `update_field` refuses any edit of a source field (plan §5) ✅ DONE

Resolved in the service: the guard compares against `field.field_type` and
only refuses a real change. Covered by
`test_relabeling_a_source_field_while_passing_its_unchanged_type_is_allowed`
and the component test `test_relabel_a_source_field_via_the_modal`.

`respondent_field_schema_service.update_field` blocks a `field_type` change on
a field that a derivation depends on. The guard fires whenever `field_type` is
not `None`, without comparing it to the stored type. The current edit route in
`entrypoints/blueprints/respondent_field_schema.py` always passes the form's
`field_type`, so once a derivation exists, **every** edit of its source field
fails with "You can't change the type of ... it is used to derive ...", even a
relabel.

Two ways to resolve it; pick one when the modal's edit form is built:

- Service: compare against `field.field_type` and only refuse a real change.
  Small, and makes the service honest whatever the caller sends.
- Route: only send `field_type` when it differs from the stored value.

The service change is the better one and can be done on the UI branch in the
same commit as the modal's edit submit. The unit test
`test_relabeling_a_source_field_is_still_allowed` passes `field_type=None`, so
it does not catch this; add a case that passes the unchanged type.

## 2. Derived fields on the respondent edit form (plan §4, §6) ✅ DONE

The edit form shows no input for a derived field, just its label and
"Derived from `<source keys>`. Will be recalculated when saved." It reuses the
Fields tab's `Derived from %(source)s` msgid, so it names the source key rather
than its label.

`update_respondent` now always recomputes derived values from their sources
(`keep_supplied_on_fallback=False`), so a value typed into a derived field on
the edit form is overwritten on save, silently. The edit form should therefore
render derived fields **read-only**, with a hint naming the source field
("Computed from `date_of_birth`"). Do not offer them as editable inputs.

## 3. Eligibility sentence date format (plan §6, age brackets) ⏸ OPEN

Not yet reachable: nothing calls `eligibility_sentence()` from a template or
renderer. Decide the format when the sentence is first put on a registration
form.

`AgeBracketRule.eligibility_sentence()` renders `as_of_date.isoformat()` inside
a public-facing sentence: "I will be at least 16 years old on 2027-03-01." A
British visitor reads an ISO date awkwardly. Before this sentence reaches a
registration form, decide whether to format the date with
`flask_babel.format_date` at the template layer (the domain object should stay
free of Flask), or keep ISO deliberately because the sentence is copied into
organiser-authored HTML.

## 4. DATE fields on the registration form (plan §5, §11) ✅ DONE

- Both starter-HTML renderers emit the three-part date input.
- The respondent edit form uses `_DatePartsField` in `edit_respondent_form.py`:
  day/month/year inputs posting `attr_<key>-day` etc., validated with
  `validate_date_field` and stored as ISO. All three blank clears the value.
  A stored value that doesn't parse raises a drift-style warning saying it
  will be cleared on save unless a date is entered — keeping it instead would
  leave no way to clear it.
- The view page formats the date for the locale with the `date_text` filter
  (`template_filters.py`), showing an unparsable value as it is.
- `service_docs/_fields.html` lists `date`.

A `FieldType.DATE` field has no `DATE` branch in either starter-HTML renderer in
`domain/registration_page.py`, so it falls through to a bare
`<input type="text">` with no format hint. Meanwhile `_date_form_value` in
`registration_submission_service.py` only assembles the GOV.UK three-part
`-day`/`-month`/`-year` inputs when the organiser hand-writes them, and
`validate_date_field` accepts only ISO or `dd/mm/yyyy`. The UI chunk needs:

- A `DATE` branch in both renderers emitting the three-part GOV.UK date input
  (which also makes the parsing order unambiguous).
- The edit-form date control and the view macro branch listed in plan.md §3.
- Note that `parse_date_text` reads `03/07/1985` as 3 July, day first. The
  three-part input sidesteps the ambiguity; a bare text input does not.

## 5. Header-less mapping CSV loses its first row (plan §7) ✅ DONE

The upload report says the first row was used as column headings and not
stored, and to add a heading row if the file has none. Detecting a header-less
file is still parked, as below.

`upload_large_mapping` treats `rows[0]` as the header. When the headers do not
match the source and derived field keys it falls back to positional columns,
but still discards that first row. A two-column file with no header line
therefore silently loses its first mapping. `MappingUploadReport.used_positional_headers`
is `True` in that case, so the upload dialog must show a warning when it is set
("The first row was read as column headings"). Parked: whether to detect a
header-less file (say, when neither cell of row 0 looks like a heading) is a
later decision.

## 6. Labels for `DerivationType` ✅ DONE (differently)

The labels exist, but as `_derivation_type_labels()` in the
`respondent_field_schema` blueprint using `_()`, not a `DERIVATION_TYPE_LABELS`
dict beside the enum. Nothing renders `.value`, so there is no bug; see
[Left alone](#left-alone).

`DerivationType` has no labels dict, unlike `RespondentFieldGroup.DERIVED` and
`FieldType.DATE`. The modal's method radios (plan §6 item 2) and the row
summary (plan §4) will need "Age brackets", "Map choices" and "Lookup table".
Add `DERIVATION_TYPE_LABELS` beside the enum in `domain/respondent_field_schema.py`
with one `_l()` per member, expose it to Jinja in `flask_app.py`, and add the
parametrised test that `tests/unit/domain/test_global_roles.py` uses. Never
render `.value`.

## 7. Rule validation messages are untranslated ✅ DONE

The four `AgeBracketRule.__post_init__` checks now raise organiser-facing
sentences wrapped in `_()` in the domain, following `domain/validators.py`.
The other rule errors ("fallback cannot be blank", "mapping cannot be empty",
"as_of_date is required ...", "declared_outputs is required ...") stay
developer messages, because the modal can't reach them: it never collects a
fallback, and the route checks for an empty mapping first.

The `ValueError`s raised by the rule classes' `__post_init__` in
`domain/respondent_derivation.py` ("min_age must be greater than zero",
"boundaries must be sorted and unique", ...) read like code and are not
wrapped for translation. Once the modal collects these numbers they become the
messages the organiser sees on a 422. Either translate them in the domain with
`_()`, or map them to curated messages at the route, the way
`FixedFieldError` is translated into `FieldDefinitionConflictError` in the
schema service.

## Left alone

Spotted while doing the above; not fixed because they were out of scope.

- **`DerivationType` labels live in the blueprint** (§6). Moving them to a
  `DERIVATION_TYPE_LABELS` dict beside the enum, exposed to Jinja in
  `flask_app.py` with the parametrised test from
  `tests/unit/domain/test_global_roles.py`, would match `global_role_labels`.
  Tidying only.
- **Service docs miss the `derived` group.** The `RespondentFieldGroup` list in
  `templates/backoffice/service_docs/_fields.html` doesn't include `derived`.
- **Untranslated rule errors behind the modal** (§7). If a future UI collects a
  fallback value, or stops checking for an empty mapping before building the
  rule, those `ValueError` messages will reach organisers and need the same
  treatment.
- **Detecting a header-less lookup table** (§5) is still a later decision.
