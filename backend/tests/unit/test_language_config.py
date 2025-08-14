"""ABOUTME: Unit tests for language configuration
ABOUTME: Tests that language configuration can be set via environment variables"""

from opendlp.config import FlaskConfig
from opendlp.translations import get_supported_languages


class TestLanguageConfiguration:
    """Test language configuration functionality."""

    def test_default_languages(self) -> None:
        """Test default language configuration."""
        config = FlaskConfig()
        assert config.LANGUAGES == ["en", "es", "fr", "de"]

        supported = config.get_supported_languages()
        assert ("en", "English") in supported
        assert ("es", "Español") in supported
        assert ("fr", "Français") in supported
        assert ("de", "Deutsch") in supported

    def test_custom_languages_from_env(self, temp_env_vars) -> None:
        """Test custom languages from environment variable."""
        temp_env_vars(SUPPORTED_LANGUAGES="en,it,pt")
        config = FlaskConfig()
        assert config.LANGUAGES == ["en", "it", "pt"]

        supported = config.get_supported_languages()
        assert ("en", "English") in supported
        assert ("it", "Italiano") in supported
        assert ("pt", "Português") in supported
        assert ("es", "Español") not in supported

    def test_single_language_from_env(self, temp_env_vars) -> None:
        """Test single language from environment variable."""
        temp_env_vars(SUPPORTED_LANGUAGES="en")
        config = FlaskConfig()
        assert config.LANGUAGES == ["en"]

        supported = config.get_supported_languages()
        assert len(supported) == 1
        assert supported[0] == ("en", "English")

    def test_unknown_language_fallback(self, temp_env_vars) -> None:
        """Test that unknown language codes get uppercase fallback names."""
        temp_env_vars(SUPPORTED_LANGUAGES="en,xy,zz")
        config = FlaskConfig()
        supported = config.get_supported_languages()

        # Should have proper names for known languages
        assert ("en", "English") in supported
        # Should have uppercase fallback for unknown languages
        assert ("xy", "XY") in supported
        assert ("zz", "ZZ") in supported

    def test_whitespace_handling(self, temp_env_vars) -> None:
        """Test that whitespace in language list is handled properly."""
        temp_env_vars(SUPPORTED_LANGUAGES=" en , es , fr ")
        config = FlaskConfig()
        assert config.LANGUAGES == ["en", "es", "fr"]

    def test_empty_languages_fallback(self, temp_env_vars) -> None:
        """Test that empty language list falls back to default."""
        temp_env_vars(SUPPORTED_LANGUAGES="")
        config = FlaskConfig()
        # Should fall back to some default
        assert len(config.LANGUAGES) >= 1

    def test_babel_locale_from_env(self, temp_env_vars) -> None:
        """Test that Babel default locale can be set from environment."""
        temp_env_vars(BABEL_DEFAULT_LOCALE="es")
        config = FlaskConfig()
        assert config.BABEL_DEFAULT_LOCALE == "es"

    def test_babel_timezone_from_env(self, temp_env_vars) -> None:
        """Test that Babel default timezone can be set from environment."""
        temp_env_vars(BABEL_DEFAULT_TIMEZONE="Europe/Madrid")
        config = FlaskConfig()
        assert config.BABEL_DEFAULT_TIMEZONE == "Europe/Madrid"

    def test_translations_get_supported_languages(self, temp_env_vars) -> None:
        """Test that translations module uses config for supported languages."""
        temp_env_vars(SUPPORTED_LANGUAGES="en,es")
        supported = get_supported_languages()
        codes = [code for code, name in supported]
        assert codes == ["en", "es"]
