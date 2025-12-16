"""ABOUTME: Translation helpers for sortition-algorithms library errors
ABOUTME: Provides functions to translate error messages from sortition_algorithms using error codes and parameters"""

from sortition_algorithms.error_messages import ERROR_MESSAGES
from sortition_algorithms.errors import (
    ParseTableMultiError,
    ParseTableMultiValueErrorMsg,
    SelectionMultilineError,
    SortitionBaseError,
)

from opendlp.translations import gettext as _


def translate_sortition_error(error: Exception) -> str:
    """
    Translate a sortition-algorithms error into the current language.

    This function handles errors from the sortition-algorithms library by checking
    for error_code and error_params attributes. If present, it translates the error
    using the error code. If not, it falls back to the English message.

    Args:
        error: Exception from sortition-algorithms library

    Returns:
        Translated error message as string

    Examples:
        Simple errors (BadDataError, SelectionError, etc.):
        >>> translate_sortition_error(error)

        ParseTableMultiError (validation errors):
        >>> translate_sortition_error(parse_error)
    """
    if isinstance(error, ParseTableMultiError):
        return _translate_parse_table_multi_error(error)
    elif isinstance(error, SelectionMultilineError):
        # SelectionMultilineError messages are pre-formatted with multiple lines
        # They are not structured for per-line translation, so return as-is
        return str(error)
    elif isinstance(error, SortitionBaseError):
        return _translate_simple_error(error)
    else:
        # Not a sortition error, return as-is
        return str(error)


def translate_sortition_error_to_html(error: Exception) -> str:
    """
    Translate a sortition-algorithms error into HTML format.

    Similar to translate_sortition_error but returns HTML-formatted output
    suitable for display in web interfaces.

    Args:
        error: Exception from sortition-algorithms library

    Returns:
        Translated error message as HTML string
    """
    if isinstance(error, ParseTableMultiError):
        return _translate_parse_table_multi_error_to_html(error)
    elif isinstance(error, SelectionMultilineError):
        # SelectionMultilineError has its own to_html() method
        return error.to_html()
    elif isinstance(error, SortitionBaseError):
        return _translate_simple_error(error)
    else:
        # Not a sortition error, return as-is
        return str(error)


def _translate_simple_error(error: SortitionBaseError) -> str:
    """Translate a simple sortition error using its error code."""
    if hasattr(error, "error_code") and error.error_code:
        # Translate using the error code and parameters
        try:
            translated_msg = _(ERROR_MESSAGES[error.error_code]) % error.error_params
            return translated_msg
        except (KeyError, TypeError, ValueError):
            # Fallback if translation fails
            return str(error)
    else:
        # No error code, use English message
        return str(error)


def _translate_parse_table_multi_error_lines(error: ParseTableMultiError) -> list[str]:
    """Translate a ParseTableMultiError with all its sub-errors into list of lines."""
    translated_lines = []

    for sub_error in error.all_errors:
        if sub_error.error_code:
            # Translate core message
            try:
                core_msg = _(ERROR_MESSAGES[sub_error.error_code]) % sub_error.error_params
            except (KeyError, TypeError, ValueError):
                # Fallback to original message if translation fails
                core_msg = sub_error.msg

            # Add context (row/column information)
            try:
                if isinstance(sub_error, ParseTableMultiValueErrorMsg):
                    context = _(ERROR_MESSAGES["parse_error_multi_column"]) % {
                        "msg": core_msg,
                        "row": sub_error.row,
                        "keys": ", ".join(sub_error.keys),
                    }
                else:  # Single-column error
                    context = _(ERROR_MESSAGES["parse_error_single_column"]) % {
                        "msg": core_msg,
                        "row": sub_error.row,
                        "key": sub_error.key,
                    }
                translated_lines.append(context)
            except (KeyError, TypeError, ValueError):
                # Fallback if context formatting fails
                translated_lines.append(str(sub_error))
        else:
            # Fallback to English message
            translated_lines.append(str(sub_error))

    return translated_lines


def _translate_parse_table_multi_error(error: ParseTableMultiError) -> str:
    """Translate a ParseTableMultiError with all its sub-errors."""
    return "\n".join(_translate_parse_table_multi_error_lines(error))


def _translate_parse_table_multi_error_to_html(error: ParseTableMultiError) -> str:
    """Translate a ParseTableMultiError with all its sub-errors to HTML."""
    return "<br />".join(_translate_parse_table_multi_error_lines(error))
