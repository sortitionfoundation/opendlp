"""ABOUTME: Translation helpers for sortition-algorithms library run reports
ABOUTME: Provides functions to translate RunReport messages from sortition_algorithms using message codes and parameters"""

import html as html_module

from sortition_algorithms.utils import ReportLevel, RunError, RunLineLevel, RunReport, RunTable
from tabulate import tabulate  # type: ignore[import-untyped]

from opendlp.service_layer.error_translation import translate_sortition_error_to_html
from opendlp.translations import gettext as _


def translate_run_report_to_html(report: RunReport, include_logged: bool = True) -> str:
    """
    Translate a sortition-algorithms RunReport into HTML format in the current language.

    This function iterates through the RunReport elements and translates them:
    - RunLineLevel elements with message_code are translated using the code
    - RunError elements are translated using the error translation module
    - RunTable elements are passed through as-is (already HTML formatted)

    Args:
        report: RunReport from sortition-algorithms library
        include_logged: Whether to include messages that were already logged (default: True)

    Returns:
        Translated HTML string suitable for display in web interfaces

    Examples:
        >>> translated_html = translate_run_report_to_html(report)
    """
    parts = []

    for element in report._data:
        html_part = _translate_element_to_html(element, include_logged)
        if html_part is not None:
            parts.append(html_part)

    return "<br />\n".join(parts)


def _translate_element_to_html(element: RunLineLevel | RunTable | RunError, include_logged: bool) -> str | None:
    """Translate a single RunReport element to HTML."""
    if isinstance(element, RunLineLevel):
        return _translate_line_to_html(element, include_logged)
    elif isinstance(element, RunTable):
        return _translate_table_to_html(element)
    else:
        return _translate_error_to_html(element)


def _translate_line_to_html(line_level: RunLineLevel, include_logged: bool) -> str | None:
    """
    Translate a RunLineLevel element to HTML.

    If the element has a message_code, translate using that code.
    Otherwise, fall back to the English line text.
    """
    # Skip logged messages if requested
    if not include_logged and line_level.log_level != 0:  # logging.NOTSET == 0
        return None

    # Determine the message text (translated if possible)
    if line_level.message_code:
        try:
            msg_key = f"report.{line_level.message_code}"
            message_text = _(msg_key) % line_level.message_params
        except (KeyError, TypeError, ValueError):
            # Fallback to English if translation fails
            message_text = line_level.line
    else:
        # No message code, use English
        message_text = line_level.line

    # Apply HTML formatting based on level
    tags = {
        ReportLevel.NORMAL: ("", ""),
        ReportLevel.IMPORTANT: ("<b>", "</b>"),
        ReportLevel.CRITICAL: ('<b style="color: red">', "</b>"),
    }
    start_tag, end_tag = tags[line_level.level]
    escaped_text = html_module.escape(message_text)
    return f"{start_tag}{escaped_text}{end_tag}"


def _translate_table_to_html(table: RunTable) -> str:
    """
    Convert a RunTable to HTML.

    Tables don't have translation codes, so we just format them as HTML.
    """
    return tabulate(table.data, headers=table.headers, tablefmt="html")  # type: ignore[no-any-return]


def _translate_error_to_html(run_error: RunError) -> str:
    """
    Translate a RunError to HTML.

    Uses the existing error translation module to translate sortition errors.
    """
    start_tag, end_tag = ("<b>", "</b>") if run_error.is_fatal else ("", "")
    translated_error = translate_sortition_error_to_html(run_error.error)
    return f"{start_tag}{translated_error}{end_tag}"
