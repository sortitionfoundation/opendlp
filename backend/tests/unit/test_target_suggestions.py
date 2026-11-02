"""ABOUTME: Unit tests for the comments written when a target suggestion is accepted
ABOUTME: Covers the per-field sentence and adding it to a comment the value already has"""

import pytest

from opendlp.service_layer.target_suggestions import append_comment, suggestion_comment


class TestSuggestionComment:
    def test_a_minimum(self):
        assert suggestion_comment("min", 6, 5) == "Accepted algorithm suggestion — minimum 6 → 5"

    def test_a_maximum(self):
        assert suggestion_comment("max", 4, 5) == "Accepted algorithm suggestion — maximum 4 → 5"


class TestAppendComment:
    @pytest.mark.parametrize(
        ("existing", "addition", "expected"),
        [
            ("", "Accepted", "Accepted"),
            ("From the census", "Accepted", "From the census; Accepted"),
            ("  From the census  ", " Accepted ", "From the census; Accepted"),
            ("From the census", "", "From the census"),
        ],
        ids=["no comment yet", "adds after", "trims both", "nothing to add"],
    )
    def test_adds_after_what_is_there(self, existing, addition, expected):
        assert append_comment(existing, addition) == expected
