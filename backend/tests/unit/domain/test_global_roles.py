"""ABOUTME: Unit tests for the global role labels and descriptions.
ABOUTME: Every role must carry a form option, a short label and an explanation, or the UI shows a gap."""

import pytest

from opendlp.domain.value_objects import (
    GlobalRole,
    get_role_level,
    global_role_descriptions,
    global_role_labels,
    global_role_options,
)


@pytest.mark.parametrize("role", list(GlobalRole))
class TestEveryRoleIsDescribed:
    """A role added later must not silently render as a blank tag."""

    def test_has_a_form_option(self, role):
        assert global_role_options[role.name]

    def test_has_a_short_label(self, role):
        assert global_role_labels[role]

    def test_has_an_explanation(self, role):
        assert global_role_descriptions[role]

    def test_has_a_place_in_the_hierarchy(self, role):
        assert get_role_level(role) > 0


class TestRoleValues:
    def test_the_retired_global_organiser_value_is_gone(self):
        """After issue 913 the string 'global-organiser' names nothing."""
        with pytest.raises(ValueError, match="global-organiser"):
            GlobalRole("global-organiser")

    def test_organiser_is_stored_as_organiser(self):
        assert GlobalRole.ORGANISER.value == "organiser"

    def test_the_hierarchy_orders_user_below_organiser_below_admin(self):
        assert get_role_level(GlobalRole.USER) < get_role_level(GlobalRole.ORGANISER)
        assert get_role_level(GlobalRole.ORGANISER) < get_role_level(GlobalRole.ADMIN)
