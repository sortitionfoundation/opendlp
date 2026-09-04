"""ABOUTME: Unit tests for permission checking utilities
ABOUTME: Tests role-based access control functions and decorators with various user roles"""

import uuid
from datetime import date, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions, UserNotFoundError
from opendlp.service_layer.permissions import (
    NO_CAPABILITIES,
    UserCapabilities,
    can_administer_site,
    can_call_confirmations,
    can_create_assembly,
    can_edit_respondent,
    can_manage_assembly,
    can_manage_assembly_members,
    can_see_all_assemblies,
    can_view_assembly,
    capabilities_for,
    has_global_admin,
    require_assembly_permission,
    require_global_role,
)


def _user(global_role: GlobalRole) -> User:
    """Build a user with the given global role and no assembly roles."""
    return User(
        email=f"{global_role.name.lower()}@example.com",
        global_role=global_role,
        password_hash="hash",  # pragma: allowlist secret
    )


class TestCanManageAssembly:
    """Test assembly management permission checks."""

    def test_admin_can_manage_any_assembly(self):
        """Test admin can manage any assembly."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(admin_user, assembly) is True

    def test_organiser_cannot_manage_an_assembly_they_have_no_role_on(self):
        """An organiser holds no privilege over assemblies they were not added to."""
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(_user(GlobalRole.ORGANISER), assembly) is False

    def test_assembly_manager_can_manage_specific_assembly(self):
        """Test assembly manager can manage their assigned assembly."""
        manager_user = User(email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Add assembly role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        assert can_manage_assembly(manager_user, assembly) is True

    def test_confirmation_caller_cannot_manage_assembly(self):
        """Test confirmation caller cannot manage assembly."""
        caller_user = User(email="caller@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Add confirmation caller role
        assembly_role = UserAssemblyRole(
            user_id=caller_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        caller_user.assembly_roles.append(assembly_role)

        assert can_manage_assembly(caller_user, assembly) is False

    def test_regular_user_cannot_manage_assembly(self):
        """Test regular user cannot manage assembly."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(regular_user, assembly) is False


class TestCanViewAssembly:
    """Test assembly viewing permission checks."""

    def test_admin_can_view_any_assembly(self):
        """Test admin can view any assembly."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(admin_user, assembly) is True

    def test_organiser_cannot_view_an_assembly_they_have_no_role_on(self):
        """The point of the organiser role: creating assemblies does not mean reading everyone's."""
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(_user(GlobalRole.ORGANISER), assembly) is False

    def test_assembly_role_can_view_assembly(self):
        """Test user with assembly role can view assembly."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Add any assembly role
        assembly_role = UserAssemblyRole(
            user_id=user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        user.assembly_roles.append(assembly_role)

        assert can_view_assembly(user, assembly) is True

    def test_regular_user_cannot_view_assembly(self):
        """Test regular user cannot view assembly without role."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(regular_user, assembly) is False


class TestCanCallConfirmations:
    """Test confirmation calling permission checks."""

    def test_admin_can_call_confirmations(self):
        """Test admin can call confirmations for any assembly."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_call_confirmations(admin_user, assembly) is True

    def test_assembly_manager_can_call_confirmations(self):
        """Test assembly manager can call confirmations."""
        manager_user = User(email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Add assembly manager role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        assert can_call_confirmations(manager_user, assembly) is True

    def test_confirmation_caller_can_call_confirmations(self):
        """Test confirmation caller can call confirmations."""
        caller_user = User(email="caller@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Add confirmation caller role
        assembly_role = UserAssemblyRole(
            user_id=caller_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        caller_user.assembly_roles.append(assembly_role)

        assert can_call_confirmations(caller_user, assembly) is True

    def test_regular_user_cannot_call_confirmations(self):
        """Test regular user cannot call confirmations."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert can_call_confirmations(regular_user, assembly) is False


class TestCanEditRespondent:
    def _assembly(self) -> Assembly:
        return Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=date.today() + timedelta(days=30),
        )

    def test_admin_can_edit(self) -> None:
        user = User(email="a@example.com", global_role=GlobalRole.ADMIN, password_hash="h")
        assert can_edit_respondent(user, self._assembly()) is True

    def test_organiser_without_a_role_cannot_edit(self) -> None:
        assert can_edit_respondent(_user(GlobalRole.ORGANISER), self._assembly()) is False

    def test_assembly_manager_can_edit(self) -> None:
        user = User(email="m@example.com", global_role=GlobalRole.USER, password_hash="h")
        assembly = self._assembly()
        user.assembly_roles.append(
            UserAssemblyRole(
                user_id=user.id,
                assembly_id=assembly.id,
                role=AssemblyRole.ASSEMBLY_MANAGER,
            )
        )
        assert can_edit_respondent(user, assembly) is True

    def test_confirmation_caller_can_edit(self) -> None:
        user = User(email="c@example.com", global_role=GlobalRole.USER, password_hash="h")
        assembly = self._assembly()
        user.assembly_roles.append(
            UserAssemblyRole(
                user_id=user.id,
                assembly_id=assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
            )
        )
        assert can_edit_respondent(user, assembly) is True

    def test_user_without_role_cannot_edit(self) -> None:
        user = User(email="u@example.com", global_role=GlobalRole.USER, password_hash="h")
        assert can_edit_respondent(user, self._assembly()) is False

    def test_read_only_cannot_edit(self) -> None:
        user = User(email="r@example.com", global_role=GlobalRole.USER, password_hash="h")
        assembly = self._assembly()
        user.assembly_roles.append(
            UserAssemblyRole(
                user_id=user.id,
                assembly_id=assembly.id,
                role=AssemblyRole.READ_ONLY,
            )
        )
        assert can_edit_respondent(user, assembly) is False


class TestReadOnlyPermissions:
    def _assembly(self) -> Assembly:
        return Assembly(
            title="A",
            question="?",
            first_assembly_date=date.today() + timedelta(days=30),
        )

    def _read_only_user(self, assembly_id):
        user = User(email="ro@example.com", global_role=GlobalRole.USER, password_hash="h")
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly_id, role=AssemblyRole.READ_ONLY)
        )
        return user

    def test_read_only_can_view(self) -> None:
        assembly = self._assembly()
        user = self._read_only_user(assembly.id)
        assert can_view_assembly(user, assembly) is True

    def test_read_only_cannot_manage(self) -> None:
        assembly = self._assembly()
        user = self._read_only_user(assembly.id)
        assert can_manage_assembly(user, assembly) is False

    def test_read_only_cannot_call_confirmations(self) -> None:
        assembly = self._assembly()
        user = self._read_only_user(assembly.id)
        assert can_call_confirmations(user, assembly) is False


class TestGlobalRoleChecks:
    """Test global role checking functions."""

    def test_has_global_admin(self):
        """Test global admin detection."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assert has_global_admin(admin_user) is True
        assert has_global_admin(organiser_user) is False
        assert has_global_admin(regular_user) is False

    def test_can_create_assembly(self):
        """Admins and organisers can create assemblies; plain users cannot."""
        assert can_create_assembly(_user(GlobalRole.ADMIN)) is True
        assert can_create_assembly(_user(GlobalRole.ORGANISER)) is True
        assert can_create_assembly(_user(GlobalRole.USER)) is False

    def test_can_see_all_assemblies(self):
        """Only admins see every assembly."""
        assert can_see_all_assemblies(_user(GlobalRole.ADMIN)) is True
        assert can_see_all_assemblies(_user(GlobalRole.ORGANISER)) is False
        assert can_see_all_assemblies(_user(GlobalRole.USER)) is False

    def test_can_administer_site(self):
        """Only admins manage users, invites and the admin UI."""
        assert can_administer_site(_user(GlobalRole.ADMIN)) is True
        assert can_administer_site(_user(GlobalRole.ORGANISER)) is False
        assert can_administer_site(_user(GlobalRole.USER)) is False


class TestUserCapabilities:
    """Test the capability bundle handed to templates."""

    def test_capabilities_for_admin(self):
        """An admin may do everything the bundle covers."""
        perms = capabilities_for(_user(GlobalRole.ADMIN))
        assert perms == UserCapabilities(create_assembly=True, see_all_assemblies=True, administer_site=True)

    def test_capabilities_for_organiser(self):
        """An organiser may create assemblies and nothing else global."""
        perms = capabilities_for(_user(GlobalRole.ORGANISER))
        assert perms == UserCapabilities(create_assembly=True, see_all_assemblies=False, administer_site=False)

    def test_capabilities_for_user(self):
        """A plain user has no global capabilities."""
        assert capabilities_for(_user(GlobalRole.USER)) == NO_CAPABILITIES

    def test_no_capabilities_permits_nothing(self):
        """The anonymous bundle permits nothing, so templates can ask it safely."""
        assert NO_CAPABILITIES.create_assembly is False
        assert NO_CAPABILITIES.see_all_assemblies is False
        assert NO_CAPABILITIES.administer_site is False


class TestRequireGlobalRoleDecorator:
    """Test global role requirement decorator."""

    def test_require_global_role_success(self):
        """Test decorator allows access with sufficient role."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        @require_global_role(GlobalRole.ORGANISER)
        def test_function(uow, user):
            return "success"

        # Should succeed because admin >= global organiser
        result = test_function(None, admin_user)
        assert result == "success"

    def test_require_global_role_failure(self):
        """Test decorator blocks access with insufficient role."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        @require_global_role(GlobalRole.ORGANISER)
        def test_function(uow, user):
            return "success"  # pragma: no cover

        # Should fail because user < global organiser
        with pytest.raises(InsufficientPermissions):
            test_function(None, regular_user)

    def test_require_global_role_exact_match(self):
        """Test decorator allows access with exact role match."""
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )

        @require_global_role(GlobalRole.ORGANISER)
        def test_function(uow, user):
            return "success"

        # Should succeed with exact match
        result = test_function(None, organiser_user)
        assert result == "success"


class TestRequireAssemblyPermissionDecorator:
    """Test assembly permission requirement decorator."""

    def test_require_assembly_permission_success(self, uow):
        """Test decorator allows access with sufficient permission."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"

        # Should succeed because admin can manage any assembly
        result = test_function(uow, admin_user.id, assembly.id, "test_data")
        assert result == "success with test_data"

    def test_require_assembly_permission_failure(self, uow):
        """Test decorator blocks access with insufficient permission."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"  # pragma: no cover

        # Should fail because regular user cannot manage assembly
        with pytest.raises(InsufficientPermissions):
            test_function(uow, regular_user.id, assembly.id, "test_data")

    def test_require_assembly_permission_user_not_found(self, uow):
        """Test decorator handles user not found."""
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"  # pragma: no cover

        # Should fail with user not found
        with pytest.raises(UserNotFoundError) as exc_info:
            test_function(uow, uuid.uuid4(), assembly.id, "test_data")
        assert "User" in str(exc_info.value) and "not found" in str(exc_info.value)

    def test_require_assembly_permission_assembly_not_found(self, uow):
        """Test decorator handles assembly not found."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"  # pragma: no cover

        # Should fail with assembly not found
        with pytest.raises(AssemblyNotFoundError) as exc_info:
            test_function(uow, admin_user.id, uuid.uuid4(), "test_data")
        assert "Assembly" in str(exc_info.value) and "not found" in str(exc_info.value)

    def test_require_assembly_permission_different_permission_functions(self, uow):
        """Test decorator works with different permission functions."""
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add assembly role so user can view but not manage
        assembly_role = UserAssemblyRole(
            user_id=regular_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        regular_user.assembly_roles.append(assembly_role)

        @require_assembly_permission(can_view_assembly)
        def view_function(uow, user_id, assembly_id):
            return "can view"

        @require_assembly_permission(can_manage_assembly)
        def manage_function(uow, user_id, assembly_id):
            return "can manage"  # pragma: no cover

        # Should succeed for view (user has assembly role)
        result = view_function(uow, regular_user.id, assembly.id)
        assert result == "can view"

        # Should fail for manage (user cannot manage)
        with pytest.raises(InsufficientPermissions):
            manage_function(uow, regular_user.id, assembly.id)


# The permission matrix, written as a table because the table *is* the
# specification. Every global role crossed with every assembly role (and with
# holding no role at all), for every capability. The coming permissions refactor
# should be able to re-run this unchanged against its new implementation.
#
# Each row is (global role, assembly role or None, the capabilities that are True).
# Anything not listed for a row must be False.
ALL_CAPABILITIES = (
    "view",
    "manage",
    "edit_respondent",
    "call_confirmations",
    "manage_members",
    "create_assembly",
    "see_all_assemblies",
    "administer_site",
)

GLOBAL_CAPABILITIES = ("create_assembly", "see_all_assemblies", "administer_site")

PERMISSION_MATRIX = [
    # An admin may do everything, whatever assembly role they also hold.
    (GlobalRole.ADMIN, None, ALL_CAPABILITIES),
    (GlobalRole.ADMIN, AssemblyRole.ASSEMBLY_MANAGER, ALL_CAPABILITIES),
    (GlobalRole.ADMIN, AssemblyRole.CONFIRMATION_CALLER, ALL_CAPABILITIES),
    (GlobalRole.ADMIN, AssemblyRole.READ_ONLY, ALL_CAPABILITIES),
    # An organiser may create assemblies, and holds nothing over an assembly
    # until they are given a role on it.
    (GlobalRole.ORGANISER, None, ("create_assembly",)),
    (
        GlobalRole.ORGANISER,
        AssemblyRole.ASSEMBLY_MANAGER,
        ("view", "manage", "edit_respondent", "call_confirmations", "manage_members", "create_assembly"),
    ),
    (
        GlobalRole.ORGANISER,
        AssemblyRole.CONFIRMATION_CALLER,
        ("view", "edit_respondent", "call_confirmations", "create_assembly"),
    ),
    (GlobalRole.ORGANISER, AssemblyRole.READ_ONLY, ("view", "create_assembly")),
    # A plain user has exactly the rights their assembly role gives them.
    (GlobalRole.USER, None, ()),
    (
        GlobalRole.USER,
        AssemblyRole.ASSEMBLY_MANAGER,
        ("view", "manage", "edit_respondent", "call_confirmations", "manage_members"),
    ),
    (GlobalRole.USER, AssemblyRole.CONFIRMATION_CALLER, ("view", "edit_respondent", "call_confirmations")),
    (GlobalRole.USER, AssemblyRole.READ_ONLY, ("view",)),
]


def _check(capability: str, user: User, assembly: Assembly) -> bool:
    """Ask one named capability, hiding the difference between the two shapes."""
    if capability in GLOBAL_CAPABILITIES:
        return {
            "create_assembly": can_create_assembly,
            "see_all_assemblies": can_see_all_assemblies,
            "administer_site": can_administer_site,
        }[capability](user)
    return {
        "view": can_view_assembly,
        "manage": can_manage_assembly,
        "edit_respondent": can_edit_respondent,
        "call_confirmations": can_call_confirmations,
        "manage_members": can_manage_assembly_members,
    }[capability](user, assembly)


@pytest.mark.parametrize(("global_role", "assembly_role", "permitted"), PERMISSION_MATRIX)
@pytest.mark.parametrize("capability", list(ALL_CAPABILITIES))
def test_permission_matrix(capability, global_role, assembly_role, permitted):
    """Every capability, for every combination of global role and assembly role."""
    assembly = Assembly(
        title="Matrix",
        question="?",
        first_assembly_date=date.today() + timedelta(days=30),
    )
    user = _user(global_role)
    if assembly_role:
        user.assembly_roles.append(UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=assembly_role))

    assert _check(capability, user, assembly) is (capability in permitted)


@pytest.mark.parametrize(("global_role", "assembly_role", "permitted"), PERMISSION_MATRIX)
@pytest.mark.parametrize("capability", ["view", "manage", "edit_respondent", "call_confirmations", "manage_members"])
def test_assembly_role_does_not_reach_another_assembly(capability, global_role, assembly_role, permitted):
    """A role on one assembly grants nothing on a different one - only admins see across."""
    other_assembly = Assembly(
        title="Someone else's",
        question="?",
        first_assembly_date=date.today() + timedelta(days=30),
    )
    user = _user(global_role)
    if assembly_role:
        user.assembly_roles.append(UserAssemblyRole(user_id=user.id, assembly_id=uuid.uuid4(), role=assembly_role))

    assert _check(capability, user, other_assembly) is (global_role == GlobalRole.ADMIN)
