"""ABOUTME: Translation utilities for i18n/l10n support
ABOUTME: Provides gettext functions that work both in Flask context and standalone"""

import gettext
import os
from typing import Any

from flask import current_app, has_app_context
from flask_babel import gettext as flask_gettext
from flask_babel import lazy_gettext as flask_lazy_gettext

# Global translation objects for fallback
_translations: dict[str, gettext.GNUTranslations] = {}
_default_locale = "en"


def _get_text_fallback(message: str, **kwargs: Any) -> str:
    """Fallback gettext that works without Flask context."""
    # Try to get current locale from environment or use default
    locale = os.environ.get("OPENDLP_LOCALE", _default_locale)

    # If we have translations for this locale, use them
    translated = _translations[locale].gettext(message) if locale in _translations else message

    # Handle parameter substitution
    if kwargs:
        try:
            return translated % kwargs
        except (KeyError, ValueError, TypeError):
            # If substitution fails, return the original message
            return message % kwargs if kwargs else message

    return translated


def _lazy_gettext_fallback(message: str, **kwargs: Any) -> str:
    """Fallback lazy_gettext that works without Flask context."""
    # For now, just return the message - in a more sophisticated setup
    # this would return a lazy string object that evaluates later
    return _get_text_fallback(message, **kwargs)


def _(message: str, **kwargs: Any) -> str:
    """Get translated string - works both in Flask context and standalone."""
    if has_app_context():
        try:
            # Check if babel extension is initialized
            if hasattr(current_app, "extensions") and "babel" in current_app.extensions:
                if kwargs:
                    return str(flask_gettext(message, **kwargs))
                return str(flask_gettext(message))
        except (ImportError, KeyError):  # pragma: no cover
            # Flask-Babel not available or not initialized
            pass

    return _get_text_fallback(message, **kwargs)


def _l(message: str, **kwargs: Any) -> str:
    """Get lazy translated string - works both in Flask context and standalone."""
    if has_app_context():
        try:
            # Check if babel extension is initialized
            if hasattr(current_app, "extensions") and "babel" in current_app.extensions:
                if kwargs:
                    return str(flask_lazy_gettext(message, **kwargs))
                return str(flask_lazy_gettext(message))
        except (ImportError, KeyError):  # pragma: no cover
            # Flask-Babel not available or not initialized
            pass

    return _lazy_gettext_fallback(message, **kwargs)


def load_translations(locale_dir: str) -> None:
    """Load translations from locale directory for fallback usage."""
    global _translations

    # Get supported languages from config
    from opendlp.config import get_config

    config = get_config()

    # Try to load translations for all supported locales
    for locale in config.LANGUAGES:
        locale_path = os.path.join(locale_dir, locale, "LC_MESSAGES", "messages.mo")
        if os.path.exists(locale_path):
            with open(locale_path, "rb") as fp:
                _translations[locale] = gettext.GNUTranslations(fp)


def get_supported_languages() -> list[tuple[str, str]]:
    """Get list of supported languages as (code, name) tuples."""
    from opendlp.config import get_config

    config = get_config()
    return config.get_supported_languages()
