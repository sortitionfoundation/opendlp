"""ABOUTME: Unit tests for the short names of the roles someone can hold on a project.
ABOUTME: Every role needs one, because a role's stored value is never shown."""

from opendlp.domain.value_objects import AssemblyRole, assembly_role_labels, assembly_role_options


class TestAssemblyRoleLabels:
    def test_every_role_has_a_short_label(self):
        """A role with no label would put its database token on the page."""
        assert set(assembly_role_labels) == set(AssemblyRole)

    def test_no_label_is_the_stored_value(self):
        for role, label in assembly_role_labels.items():
            assert str(label) != role.value

    def test_every_role_has_a_long_label_for_choosing_it(self):
        assert set(assembly_role_options) == {role.name for role in AssemblyRole}
