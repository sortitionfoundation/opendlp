# Registration errors for fields the form HTML does not render are never shown

Found while debugging the `new-creation` test page on the `1361-disable-auto-reply`
branch, but not related to that branch. Written so it can be pasted into an issue.

## Problem

A registration page's form HTML is written by the organiser (or generated, then
edited). Validation does not use that HTML. It checks the assembly's respondent
field definitions. If a field is `yes_required` on the registration page but the
form HTML has no input for it, every submission fails. The form is re-rendered
with no visible error, and nobody filling it in can get past it.

### How it was found

`POST /register/new-creation` with every visible field filled in validly just
showed the form again. The form HTML includes `{{ form_errors() }}`, but nothing
appeared.

The assembly (`de57525e-96be-49f0-95b1-03d9ecfaf0a1`) has 19 field definitions.
Seven of them, all created together on 2026-11-17 at 15:31:59 (most likely by
one import), are `on_registration_page = yes_required` and do not appear in the
form HTML:

```
first_name, last_name, mobile_number, primary_address1,
primary_address2, primary_city, primary_zip
```

Calling `_validate_form_data` with the form's own fields filled in returns:

```python
{'first_name': ['This field is required'], 'last_name': ['This field is required'],
 'mobile_number': ['This field is required'], 'primary_address1': ['This field is required'],
 'primary_address2': ['This field is required'], 'primary_city': ['This field is required'],
 'primary_zip': ['This field is required']}
```

The form HTML predates those fields. Adding fields to an assembly does not
update form HTML that has already been written.

### Why nothing is shown

- `_validate_form_data` (`src/opendlp/service_layer/registration_submission_service.py`)
  checks every field definition that is not `on_registration_page = no`, whether
  or not the page renders it.
- Failures go into `field_errors`, keyed by `field_key`. `submit_registration`
  always returns `form_errors=[]` on a validation failure.
- `form_errors()` (`_form_errors_html` in `src/opendlp/domain/registration_page.py`)
  only renders `form_level_errors`, so it is empty here.
- A field's error is only rendered where the HTML calls
  `{{ field_errors('<key>') }}`. These seven keys are never called, so their
  errors are worked out and then dropped.

Each piece does what it was written to do. The gap is that an error for a field
the page does not render has nowhere to go.

## Proposal

Do both of these. Each covers a case the other misses.

### 1. Backstop when rendering (the user-facing fix)

When re-rendering after a failed validation, move any `field_errors` entry whose
key the form HTML does not render into the form-level errors, so `form_errors()`
shows it, for example: "Please answer: First name — This field is required"
(using the field's label, not its key).

Deciding whether a key is "rendered" could mean:

- recording which keys `field_errors()` / `has_error()` / `first_error()` were
  called with while the template rendered, then promoting the rest. That needs
  two passes, or rendering `form_errors()` lazily after the fields; or
- checking the form HTML for an input `name` matching the key (or the
  `-day`/`-month`/`-year` trio for a DATE field). This is simpler, but it parses
  the organiser's HTML.

The first matches what the person actually sees, so prefer it if it can be done
cleanly. Also log a warning (with the page id and field keys, no values) so the
problem shows up in logs as well as to the public.

If the form HTML does not call `{{ form_errors() }}` at all, the backstop still
shows nothing. Rule 2 below should also require `form_errors()` to be present.

### 2. Check when saving the form HTML (the organiser-facing fix)

When the organiser saves the form HTML, and when the page's status changes to
test or open, warn if any `yes_required` field has no input in the HTML (or if
`{{ form_errors() }}` is missing). This catches the problem before a member of
the public meets it.

This alone is not enough. Fields can be added or made required *after* the HTML
is saved, as happened here, so the warning would also need to appear on the
registration page overview whenever the check fails, not only on save.

## Tests

- Service/blueprint: a page whose form HTML omits a required field. Submitting
  it re-renders the form with that field's label in the form-level errors.
- A field that *is* rendered keeps its error next to the field and is not also
  added to the form-level list.
- DATE fields rendered as the three-part inputs count as rendered.
- Backoffice: saving form HTML that omits a required field shows the warning.
- BDD: the public form shows the backstop message for a missing required field.

## Workaround for an affected page

Set the missing fields to "not on the registration page" (or optional) in the
backoffice, or add inputs for them to the form HTML.
