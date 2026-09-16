# Derived fields — notes for the UI branch

Findings from the code review of `793-derived-fields` (2026-09-15) that are
either UI work or need a UI-level decision, so they were not fixed on the
backend branch. Read alongside [plan-simple-ui.md](plan-simple-ui.md); each
note says which section of that plan it touches.

## 1. `update_field` refuses any edit of a source field (plan §5)

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

## 2. Derived fields on the respondent edit form (plan §4, §6)

`update_respondent` now always recomputes derived values from their sources
(`keep_supplied_on_fallback=False`), so a value typed into a derived field on
the edit form is overwritten on save, silently. The edit form should therefore
render derived fields **read-only**, with a hint naming the source field
("Computed from `date_of_birth`"). Do not offer them as editable inputs.

## 3. Eligibility sentence date format (plan §6, age brackets)

`AgeBracketRule.eligibility_sentence()` renders `as_of_date.isoformat()` inside
a public-facing sentence: "I will be at least 16 years old on 2027-03-01." A
British visitor reads an ISO date awkwardly. Before this sentence reaches a
registration form, decide whether to format the date with
`flask_babel.format_date` at the template layer (the domain object should stay
free of Flask), or keep ISO deliberately because the sentence is copied into
organiser-authored HTML.

## 4. DATE fields on the registration form (plan §5, §11)

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

## 5. Header-less mapping CSV loses its first row (plan §7)

`upload_large_mapping` treats `rows[0]` as the header. When the headers do not
match the source and derived field keys it falls back to positional columns,
but still discards that first row. A two-column file with no header line
therefore silently loses its first mapping. `MappingUploadReport.used_positional_headers`
is `True` in that case, so the upload dialog must show a warning when it is set
("The first row was read as column headings"). Parked: whether to detect a
header-less file (say, when neither cell of row 0 looks like a heading) is a
later decision.

## 6. Labels for `DerivationType`

`DerivationType` has no labels dict, unlike `RespondentFieldGroup.DERIVED` and
`FieldType.DATE`. The modal's method radios (plan §6 item 2) and the row
summary (plan §4) will need "Age brackets", "Map choices" and "Lookup table".
Add `DERIVATION_TYPE_LABELS` beside the enum in `domain/respondent_field_schema.py`
with one `_l()` per member, expose it to Jinja in `flask_app.py`, and add the
parametrised test that `tests/unit/domain/test_global_roles.py` uses. Never
render `.value`.

## 7. Rule validation messages are untranslated

The `ValueError`s raised by the rule classes' `__post_init__` in
`domain/respondent_derivation.py` ("min_age must be greater than zero",
"boundaries must be sorted and unique", ...) read like code and are not
wrapped for translation. Once the modal collects these numbers they become the
messages the organiser sees on a 422. Either translate them in the domain with
`_()`, or map them to curated messages at the route, the way
`FixedFieldError` is translated into `FieldDefinitionConflictError` in the
schema service.
