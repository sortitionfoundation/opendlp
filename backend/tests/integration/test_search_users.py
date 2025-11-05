"""ABOUTME: Integration tests for user search endpoint
ABOUTME: Tests HTMX search functionality for adding users to assemblies"""

import pytest
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import (
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserRepository,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole


@pytest.fixture
def user_repo(postgres_session: Session):
    """Create a UserRepository using PostgreSQL."""
    return SqlAlchemyUserRepository(postgres_session)


@pytest.fixture
def role_repo(postgres_session: Session):
    """Create a UserAssemblyRoleRepository using PostgreSQL."""
    return SqlAlchemyUserAssemblyRoleRepository(postgres_session)


@pytest.fixture
def assembly(postgres_session: Session):
    """Create an assembly for testing and persist it."""
    asm = Assembly(
        title="Test Assembly",
        status=AssemblyStatus.ACTIVE,
    )
    postgres_session.add(asm)
    postgres_session.commit()
    return asm


@pytest.fixture
def users_for_search(postgres_session: Session):
    """Create multiple users with various names/emails for search testing.

    Uses PostgreSQL instead of FakeUnitOfWork because the search query is complex
    and benefits from testing the actual SQL ORM behavior.
    """
    users = [
        User(
            email="john.smith@example.com",
            first_name="John",
            last_name="Smith",
            global_role=GlobalRole.USER,
            password_hash="hash123",  # pragma: allowlist secret
        ),
        User(
            email="jane.doe@example.com",
            first_name="Jane",
            last_name="Doe",
            global_role=GlobalRole.USER,
            password_hash="hash123",  # pragma: allowlist secret
        ),
        User(
            email="bob.johnson@example.com",
            first_name="Bob",
            last_name="Johnson",
            global_role=GlobalRole.USER,
            password_hash="hash123",  # pragma: allowlist secret
        ),
        User(
            email="alice@example.com",
            first_name="Alice",
            last_name="Brown",
            global_role=GlobalRole.USER,
            password_hash="hash123",  # pragma: allowlist secret
        ),
    ]
    # Persist users to database
    for user in users:
        postgres_session.add(user)
    postgres_session.commit()
    return users


def test_search_users_not_in_assembly_by_email(users_for_search, assembly, user_repo):
    """Test searching users by email prioritizes email matches."""
    # Search for "john.smith" - should match john.smith@example.com
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "john.smith"))
    assert len(results) == 1
    assert results[0].email == "john.smith@example.com"


def test_search_users_not_in_assembly_by_first_name(users_for_search, assembly, user_repo):
    """Test searching users by first name."""
    # Search for "alice" - should match Alice Brown by first name
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "alice"))
    assert len(results) == 1
    assert results[0].first_name == "Alice"


def test_search_users_not_in_assembly_by_last_name(users_for_search, assembly, user_repo):
    """Test searching users by last name."""
    # Search for "doe" - should match Jane Doe by last name
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "doe"))
    assert len(results) == 1
    assert results[0].last_name == "Doe"


def test_search_users_excludes_users_already_in_assembly(
    users_for_search, assembly, user_repo, role_repo, postgres_session
):
    """Test that search excludes users already assigned to the assembly."""
    # Add one user to the assembly
    john = users_for_search[0]
    role = UserAssemblyRole(
        user_id=john.id,
        assembly_id=assembly.id,
        role=AssemblyRole.CONFIRMATION_CALLER,
    )
    postgres_session.add(role)
    postgres_session.commit()

    # Search for "smith" - should not find john.smith since he's already in the assembly
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "smith"))
    assert len(results) == 0


def test_search_users_case_insensitive(users_for_search, assembly, user_repo):
    """Test that search is case-insensitive."""
    # Search with uppercase
    results_upper = list(user_repo.search_users_not_in_assembly(assembly.id, "ALICE"))
    assert len(results_upper) == 1
    assert results_upper[0].first_name == "Alice"

    # Search with mixed case
    results_mixed = list(user_repo.search_users_not_in_assembly(assembly.id, "AlIcE"))
    assert len(results_mixed) == 1
    assert results_mixed[0].first_name == "Alice"


def test_search_users_returns_empty_when_no_matches(users_for_search, assembly, user_repo):
    """Test that search returns empty list when no users match."""
    # Search for non-existent user
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "nonexistent"))
    assert len(results) == 0


def test_search_users_prioritizes_email_over_name(assembly, postgres_session, user_repo):
    """Test that email matches are prioritized over name matches."""
    # Create users where one has "john" in both email and name
    # and another has it only in name
    user1 = User(
        email="john.smith@example.com",  # "john" in email
        first_name="Alice",
        last_name="Wonder",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )
    user2 = User(
        email="alice@example.com",
        first_name="John",  # "john" in first name
        last_name="Brown",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )

    postgres_session.add(user1)
    postgres_session.add(user2)
    postgres_session.commit()

    # Search for "john" - should get email match first, then name match
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "john"))
    assert len(results) == 2
    assert results[0].email == "john.smith@example.com"  # Email match comes first
    assert results[1].first_name == "John"  # Name match comes second


def test_search_users_empty_search_returns_empty(users_for_search, assembly, user_repo):
    """Test that empty search term returns empty list."""
    # Empty search should return empty results
    results = list(user_repo.search_users_not_in_assembly(assembly.id, ""))
    assert len(results) == 0


def test_search_users_partial_matches(users_for_search, assembly, user_repo):
    """Test that partial matches work correctly."""
    # Search for "sm" - should match "smith" in john.smith@example.com
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "sm"))
    assert len(results) == 1
    assert results[0].email == "john.smith@example.com"

    # Search for ".com" - should match all users with .com domain
    results = list(user_repo.search_users_not_in_assembly(assembly.id, ".com"))
    assert len(results) == 4


def test_search_users_multi_fragment_all_must_match(users_for_search, assembly, user_repo):
    """Test that multi-fragment search requires all fragments to match (AND logic)."""
    # Search for "john smith" - should match john.smith@example.com (both fragments match)
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "john smith"))
    assert len(results) == 1
    assert results[0].email == "john.smith@example.com"

    # Search for "john jane" - should match nothing (no user has both)
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "john jane"))
    assert len(results) == 0


def test_search_users_multi_fragment_or_within_fragment(users_for_search, assembly, user_repo):
    """Test that within a fragment, matches work as OR across fields."""
    # Search for "gm to" - should find "tom.jones@gmail.com"
    # "gm" matches email (gmail), "to" matches first_name (Tom -> to)
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "gm to"))
    assert len(results) == 0  # tom.jones@gmail.com doesn't exist in our test data

    # Let's test with "doe alice" - should find alice@example.com
    # "doe" doesn't match alice (neither email nor name), "alice" matches first_name
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "doe alice"))
    assert len(results) == 0

    # Test with "ex alice" - should find alice@example.com
    # "ex" matches email (example), "alice" matches first_name
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "ex alice"))
    assert len(results) == 1
    assert results[0].first_name == "Alice"


def test_search_users_fragment_order_prioritizes_email_matches(assembly, postgres_session, user_repo):
    """Test that results are prioritized by email matches on first fragment."""
    # Create users where different fields match different fragments
    user1 = User(
        email="john@example.com",
        first_name="Tom",
        last_name="Smith",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )
    user2 = User(
        email="alice@gmail.com",
        first_name="John",
        last_name="Brown",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )

    postgres_session.add(user1)
    postgres_session.add(user2)
    postgres_session.commit()

    # Search for "john sm"
    # user1: "john" matches email, "sm" matches last_name (smith)
    # user2: "john" matches first_name, "sm" doesn't match
    results = list(user_repo.search_users_not_in_assembly(assembly.id, "john sm"))
    assert len(results) == 1
    assert results[0].email == "john@example.com"


def test_search_users_whitespace_handling(users_for_search, assembly, user_repo):
    """Test that extra whitespace is handled correctly."""
    # Multiple spaces should be treated as separate fragments
    results1 = list(user_repo.search_users_not_in_assembly(assembly.id, "jane  doe"))
    results2 = list(user_repo.search_users_not_in_assembly(assembly.id, "jane doe"))
    assert len(results1) == len(results2)

    # Leading/trailing whitespace should be trimmed
    results3 = list(user_repo.search_users_not_in_assembly(assembly.id, "  jane doe  "))
    assert len(results3) == len(results2)
