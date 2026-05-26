# Refactoring: add_field() Service Function

**Date:** 2026-05-26
**Branch:** `610-registration-page-html`
**Status:** Implemented

---

## Background

While implementing the registration form feature, we discovered that `generate_starter_form_html()` sources its fields from `RespondentFieldDefinition` (the Fields tab), **not** from `TargetCategory` (the Targets tab). This is by design — see `deltas-to-fix.md` §1 for the rationale.

However, there was no way to manually add fields to an assembly's schema. Field creation was embedded in bulk operations:

- `populate_schema_from_headers()` — creates fields from CSV headers
- `apply_reconciliation()` — creates fields for new CSV columns
- `initialise_empty_schema()` — creates fixed fields only

Users who had target categories configured but no matching field definitions could not generate starter form HTML that included those fields.

---

## Solution

Extracted a granular `add_field()` service function that allows single-field creation.

### New Function

**File:** `src/opendlp/service_layer/respondent_field_schema_service.py`

```python
def add_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_key: str,
    *,
    label: str | None = None,
    group: RespondentFieldGroup = RespondentFieldGroup.GENERAL,
    field_type: FieldType = FieldType.TEXT,
    options: list[ChoiceOption] | None = None,
) -> RespondentFieldDefinition:
    """Add a single field to an assembly's schema."""
```

### Features

- **Permission check:** Requires `can_manage_assembly()` permission
- **Duplicate detection:** Raises `FieldDefinitionConflictError` if `field_key` already exists
- **Auto sort_order:** Computes next sort_order for the specified group
- **Auto label:** Defaults to `humanise_field_key(field_key)` if label not provided
- **Choice field support:** Accepts options list for `CHOICE_RADIO` / `CHOICE_DROPDOWN` types
- **Groups:** `eligibility`, `name_and_contact`, `address`, `about_you`, `consent`, `other`

### Service-Docs Integration

Added to the service-docs under a new **Fields** tab:

- **Route:** `/backoffice/dev/service-docs?tab=fields`
- **Handler:** `_handle_add_field()` in `dev.py`
- **Template:** `templates/backoffice/service_docs/_fields.html`

---

## Usage Example

To add an "age_range" field matching a target category:

1. Go to `/backoffice/dev/service-docs?tab=fields`
2. Select the assembly
3. Enter:
   - Field Key: `age_range`
   - Label: `Age Range` (or leave blank for auto)
   - Group: `about_you`
   - Field Type: `CHOICE_RADIO`
   - Options: `18-30, 31-50, 51-65, 65+`
4. Click Execute

The field will appear on the Fields tab and in `generate_starter_form_html()` output.

---

## Future Considerations

### UI Integration

A future enhancement could add an "Add Field" button directly to the Fields tab (`/backoffice/assembly/<id>/respondent-schema`), using this same service function.

### CSV Workflow Refactoring

The bulk operations (`populate_schema_from_headers`, `apply_reconciliation`) could be refactored to call `add_field()` internally. This was deferred for performance reasons — bulk operations insert many fields at once via `bulk_add()`, while `add_field()` uses single-row `add()`. For typical use cases (single-field creation), `add_field()` is appropriate; for CSV imports (many fields), the bulk path remains optimal.

---

## Files Changed

| File | Change |
|------|--------|
| `src/opendlp/service_layer/respondent_field_schema_service.py` | Added `add_field()` function |
| `src/opendlp/entrypoints/blueprints/dev.py` | Added `_handle_add_field()` handler |
| `templates/backoffice/service_docs.html` | Added Fields tab, Alpine.js bindings |
| `templates/backoffice/service_docs/_fields.html` | New template for Fields tab |
