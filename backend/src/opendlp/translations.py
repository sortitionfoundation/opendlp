"""ABOUTME: Translation utilities for i18n/l10n support
ABOUTME: Provides gettext functions that work both in Flask context and standalone"""

import os
from gettext import GNUTranslations
from typing import Any

from flask import current_app, has_app_context
from flask_babel import LazyString
from flask_babel import gettext as flask_gettext

# Global translation objects for fallback
_translations: dict[str, GNUTranslations] = {}
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


def gettext(message: str, **kwargs: Any) -> str:
    """Get translated string - works both in Flask context and standalone."""
    if has_app_context():
        try:
            # Check if babel extension is initialized
            if hasattr(current_app, "extensions") and "babel" in current_app.extensions:
                return str(flask_gettext(message, **kwargs))
        except (ImportError, KeyError):  # pragma: no cover
            # Flask-Babel not available or not initialized
            pass

    return _get_text_fallback(message, **kwargs)


def lazy_gettext(message: str, **kwargs: Any) -> LazyString:  # type: ignore[no-any-unimported]
    """Get lazy translated string - works both in Flask context and standalone."""
    return LazyString(gettext, message, **kwargs)


_ = gettext
_l = lazy_gettext


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
                _translations[locale] = GNUTranslations(fp)


def get_supported_languages() -> list[tuple[str, str]]:
    """Get list of supported languages as (code, name) tuples."""
    from opendlp.config import get_config

    config = get_config()
    return config.get_supported_languages()
