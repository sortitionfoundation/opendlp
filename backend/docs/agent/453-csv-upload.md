# 453 CSV Upload Implementation

This document tracks the implementation of the CSV upload feature for assemblies, allowing data import without using Google Spreadsheets.

## Branch: 453-csv-upload

## Overview

The goal is to add CSV file upload capability as an alternative to Google Spreadsheets for managing assembly data. This involves:

1. Adding new tabs (Targets, Respondents) to the assembly navigation
2. Implementing CSV upload UI components
3. Creating service layer functions for CSV parsing and import
4. Building the frontend patterns and documentation

## Implementation Progress

### Phase 1: Tab Navigation (Completed)

Added two new tabs to the assembly view navigation:

- **Targets** - For managing selection target categories (demographic quotas)
- **Respondents** - For managing participant/respondent data

#### Tab Behavior

| Condition | Targets Tab | Respondents Tab |
|-----------|-------------|-----------------|
| No data source configured | Disabled | Disabled |
| GSheet configured | Enabled (shows info box) | Enabled (shows info box) |
| CSV source, no upload yet | Disabled | Disabled |
| CSV source, data uploaded | Enabled | Enabled |

### Files Changed

#### New Files

- `templates/backoffice/components/assembly_tabs.html` - Shared macro for consistent tab rendering
- `templates/backoffice/assembly_targets.html` - Targets page template
- `templates/backoffice/assembly_respondents.html` - Respondents page template

#### Modified Files

- `src/opendlp/entrypoints/blueprints/backoffice.py`:
  - Added `view_assembly_targets()` route
  - Added `view_assembly_respondents()` route
  - Updated existing routes to pass tab context (data_source, gsheet, targets_enabled, respondents_enabled)

- `src/opendlp/entrypoints/blueprints/gsheets.py`:
  - Updated `view_assembly_selection()` to pass tab context

- Template files updated to use `assembly_tabs` macro:
  - `templates/backoffice/assembly_details.html`
  - `templates/backoffice/assembly_data.html`
  - `templates/backoffice/assembly_members.html`
  - `templates/backoffice/assembly_selection.html`

- BDD tests:
  - `features/backoffice-csv-upload.feature` - Updated test scenarios
  - `tests/bdd/test_backoffice.py` - Added new step definitions
  - `tests/bdd/config.py` - Added URL helpers for new routes

### Phase 2: UI Components (Completed)

Created a file input component (`file_input` macro) in `templates/backoffice/components/input.html` with:

- Label and hint text support
- Error state display
- Accept attribute for file type filtering
- Required and disabled states
- Alpine.js binding support via attrs parameter

Added file upload pattern documentation to `/backoffice/dev/patterns` page.

### Phase 3: GSheet Info Display (Completed)

For assemblies using Google Sheets as the data source:

- **Targets page**: Shows an info box explaining that targets are configured in Google Sheets, displaying the configured tab names (Categories Tab for initial/replacement selection)
- **Respondents page**: Shows similar info box with Respondents tab names

### Phase 4: CSV Upload (Pending)

Still to implement:

1. CSV upload form on Targets page (CSV source)
2. CSV upload form on Respondents page (CSV source)
3. Integration with existing service layer functions:
   - `import_targets_from_csv()`
   - `import_respondents_from_csv()`

## Technical Notes

### Assembly Tabs Macro

The `assembly_tabs` macro centralizes tab rendering logic:

```jinja
{{ assembly_tabs(
    assembly=assembly,
    active_tab="data",
    data_source=data_source,
    gsheet=gsheet,
    targets_enabled=targets_enabled,
    respondents_enabled=respondents_enabled
) }}
```

Parameters:
- `assembly` - Assembly object
- `active_tab` - One of: "details", "data", "targets", "respondents", "selection", "members"
- `data_source` - "gsheet", "csv", or ""
- `gsheet` - GSheet configuration object (or None)
- `targets_enabled` - Boolean for tab clickability
- `respondents_enabled` - Boolean for tab clickability

### Tab Enabled Logic

For GSheet source:
- Tabs are enabled when `gsheet` configuration exists

For CSV source (future):
- Targets tab enabled when targets CSV has been uploaded
- Respondents tab enabled when respondents CSV has been uploaded

### CSP Compatibility

All Alpine.js code follows CSP-compatible patterns:
- Flat properties only in `x-model` (no nested paths)
- No string arguments in click handlers
- CSRF token included in fetch requests via `X-CSRFToken` header

## Related Documents

- [Frontend Patterns Documentation](/backoffice/dev/patterns) - Live examples and patterns
- [Service Docs](/backoffice/dev/service-docs) - Service layer testing interface
- [CSV Upload GDS Plan](csv-upload-gds-plan.md) - Original planning document
- [CSV Upload GDS Research](csv-upload-gds-research.md) - Research notes

## Next Steps

1. Implement CSV upload form on Targets page
2. Implement CSV upload form on Respondents page
3. Add success/error feedback after uploads
4. Add data preview functionality
5. Run BDD tests to verify all scenarios pass
