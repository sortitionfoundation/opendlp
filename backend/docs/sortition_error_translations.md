# Sortition Error and Report Translations

This document describes how sortition-algorithms library errors and run reports are translated in OpenDLP.

## Overview

The sortition-algorithms library provides structured codes and parameters for all error messages and run report messages, enabling web applications to translate them into multiple languages. OpenDLP automatically translates these messages using the application's configured language.

## How It Works

### Error Translation Flow

1. When a sortition task fails, it raises a `SortitionBaseError` or `ParseTableMultiError`
2. The error handler in `celery/tasks.py` catches the error
3. The `translate_sortition_error()` helper checks for `error_code` and `error_params`
4. If present, it translates using `_("errors.{error_code}") % error_params`
5. If not present (or translation fails), it falls back to the English message

### Error Translation Helper

The error translation logic is in `src/opendlp/service_layer/error_translation.py`:

- `translate_sortition_error(error)` - Returns plain text translation
- `translate_sortition_error_to_html(error)` - Returns HTML-formatted translation

Both functions handle:
- Simple errors (BadDataError, SelectionError, etc.)
- ParseTableMultiError (validation errors with multiple sub-errors)
- Fallback to English if error_code is missing

### Report Translation Flow

1. When a sortition task completes, it returns a `RunReport` with informational messages
2. The route handler calls `translate_run_report_to_html()` before rendering the template
3. The function iterates through `report._data` elements checking for `message_code` and `message_params`
4. If present, it translates using `_("report.{message_code}") % message_params`
5. If not present (or translation fails), it falls back to the English message
6. Errors within reports are translated using the error translation module
7. Tables are passed through as-is (no translation needed for data)

### Report Translation Helper

The report translation logic is in `src/opendlp/service_layer/report_translation.py`:

- `translate_run_report_to_html(report)` - Returns HTML-formatted translation of the entire report

The function handles:
- RunLineLevel elements with message codes (translates them)
- RunLineLevel elements without message codes (uses English text)
- RunTable elements (passes through as HTML without translation)
- RunError elements (delegates to error translation module)
- Fallback to English if message_code is missing or translation fails

## Translation Workflow

### Extracting Messages

To extract all translatable strings including sortition errors:

```bash
just translate-regen
```

This command:
1. Extracts strings from the OpenDLP codebase using the `_l()` marker
2. Extracts strings from the installed sortition-algorithms package using the `N_()` marker
3. Updates the translations/messages.pot template file
4. Updates all language-specific .po files

### Compiling Translations

After editing translations in the .po files:

```bash
just translate-compile
```

This compiles the .po files into .mo files that Flask can use at runtime.

## Available Message Types

### Error Types

The sortition-algorithms library provides error codes for:

### Data Validation Errors
- `missing_column` - Required column not found
- `duplicate_column` - Multiple columns with same name
- `empty_feature_value` - Blank value in feature data
- `value_not_in_feature` - Invalid feature value for person
- `empty_value_in_feature` - Missing feature value for person

### Numeric Validation Errors
- `no_value_set` - No value provided for required numeric field
- `not_a_number` - Value cannot be parsed as a number
- `min_greater_than_max` - Minimum exceeds maximum
- `min_flex_greater_than_min` - Flexible minimum exceeds minimum
- `max_flex_less_than_max` - Flexible maximum less than maximum

### System Errors
- `spreadsheet_not_found` - Google Spreadsheet not accessible
- `tab_not_found` - Worksheet tab not found
- `unknown_selection_algorithm` - Invalid algorithm specified
- `gurobi_not_available` - Gurobi solver not installed

See `thirdparty/sortition-algorithms/src/sortition_algorithms/error_messages.py` for the complete list.

### Report Message Types

The sortition-algorithms library provides message codes for run report messages:

#### Data Loading Messages
- `loading_features_from_string` - Loading features from string data
- `loading_people_from_string` - Loading people from string data
- `loading_features_from_file` - Loading features from file (params: `file_path`)
- `loading_people_from_file` - Loading people from file (params: `file_path`)
- `features_found` - Number of features loaded (params: `count`)
- `opened_gsheet` - Google Sheet opened (params: `title`)
- `reading_gsheet_tab` - Reading tab from Google Sheet (params: `tab_name`)

#### Algorithm Messages
- `using_legacy_algorithm` - Using legacy selection algorithm
- `using_maximin_algorithm` - Using maximin algorithm
- `using_leximin_algorithm` - Using leximin algorithm
- `using_nash_algorithm` - Using Nash algorithm
- `gurobi_unavailable_switching` - Switching from leximin to maximin (Gurobi not available)
- `distribution_stats` - Distribution statistics (params: `total_committees`, `non_zero_committees`)

#### Selection Process Messages
- `test_selection_warning` - Warning about non-random test selection
- `initial_state` - Initial state message
- `trial_number` - Current trial number (params: `trial`)
- `selection_success` - Selection succeeded
- `selection_failed` - Selection failed (params: `attempts`)
- `retry_after_error` - Retrying after error (params: `error`)

#### Output Messages
- `writing_selected_csv` - Writing selected people to CSV (params: `file_path`)
- `writing_remaining_csv` - Writing remaining people to CSV (params: `file_path`)
- `writing_selected_tab` - Writing selected people to tab (params: `tab_name`)
- `writing_remaining_tab` - Writing remaining people to tab (params: `tab_name`)
- `finished_writing_selected_only` - Finished writing selected people
- `finished_writing_selected_and_remaining` - Finished writing both selected and remaining

#### Validation Messages
- `blank_id_skipped` - Blank ID cell found and skipped (params: `row`)

See `thirdparty/sortition-algorithms/src/sortition_algorithms/report_messages.py` for the complete list.

## Adding New Languages

1. Initialize a new language (e.g., French):
   ```bash
   uv run pybabel init -i translations/messages.pot -d translations -l fr
   ```

2. Edit `translations/fr/LC_MESSAGES/messages.po` to add translations

3. Compile the translations:
   ```bash
   just translate-compile
   ```

## Technical Details

### Babel Configuration

The `babel.cfg` file is configured to extract:
- `_l` keyword from Python files (lazy translation for OpenDLP)
- `N_` keyword from Python files (no-op marker for sortition-algorithms)
- Standard gettext markers from Jinja2 templates

### Translation Extraction Path

The `translate-regen` command dynamically finds the installed sortition-algorithms package:

```bash
uv run python -c "import sortition_algorithms, os; print(os.path.dirname(sortition_algorithms.__file__))"
```

This ensures extraction works regardless of where the package is installed.

## References

- sortition-algorithms i18n documentation: `thirdparty/sortition-algorithms/docs/i18n.md`
- Flask-Babel documentation: https://python-babel.github.io/flask-babel/
- OpenDLP translations module: `src/opendlp/translations.py`
- Error translation module: `src/opendlp/service_layer/error_translation.py`
- Report translation module: `src/opendlp/service_layer/report_translation.py`
