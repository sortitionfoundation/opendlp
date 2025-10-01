"""ABOUTME: Unit tests for user data agreement content functionality
ABOUTME: Tests content retrieval and language support for user data agreements"""

import pytest

from opendlp.domain.user_data_agreement import (
    USER_DATA_AGREEMENT_CONTENT,
    get_available_languages,
    get_user_data_agreement_content,
)


class TestUserDataAgreement:
    def test_get_english_content(self):
        """Test retrieving English user data agreement content."""
        content = get_user_data_agreement_content("en")

        assert isinstance(content, str)
        assert len(content) > 0
        assert "Principles of Data Processing" in content
        assert "# User Data Agreement" in content

    def test_get_hungarian_content(self):
        """Test retrieving Hungarian user data agreement content."""
        content = get_user_data_agreement_content("hu")

        assert isinstance(content, str)
        assert len(content) > 0
        assert "Adatkezelési megállapodás" in content
        assert "Sortírozási Alapítvány" in content

    def test_get_content_defaults_to_english(self):
        """Test that no language code defaults to English."""
        content = get_user_data_agreement_content()
        english_content = get_user_data_agreement_content("en")

        assert content == english_content

    def test_get_content_with_invalid_language_raises_error(self):
        """Test that invalid language code raises KeyError."""
        with pytest.raises(KeyError, match="Language code 'fr' not supported"):
            get_user_data_agreement_content("fr")

    def test_get_available_languages(self):
        """Test getting list of available languages."""
        languages = get_available_languages()

        assert isinstance(languages, list)
        assert "en" in languages
        assert "hu" in languages
        assert len(languages) == 2

    def test_content_dict_structure(self):
        """Test that content dictionary has expected structure."""
        assert isinstance(USER_DATA_AGREEMENT_CONTENT, dict)
        assert "en" in USER_DATA_AGREEMENT_CONTENT
        assert "hu" in USER_DATA_AGREEMENT_CONTENT

        for lang_code, content in USER_DATA_AGREEMENT_CONTENT.items():
            assert isinstance(lang_code, str)
            assert isinstance(content, str)
            assert len(content) > 100  # Reasonable minimum length
