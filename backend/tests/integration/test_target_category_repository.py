"""ABOUTME: Integration tests for TargetCategoryRepository
ABOUTME: Tests target category repository methods with actual database operations"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import SqlAlchemyTargetCategoryRepository
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import TargetCategory, TargetValue


@pytest.fixture
def target_category_repo(postgres_session):
    """Create a TargetCategoryRepository."""
    return SqlAlchemyTargetCategoryRepository(postgres_session)


@pytest.fixture
def test_assembly(postgres_session):
    """Create a test assembly."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    postgres_session.add(assembly)
    postgres_session.commit()
    return assembly


class TestTargetCategoryRepository:
    def test_add_and_get_category(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test adding and retrieving a target category."""
        category = TargetCategory(assembly_id=test_assembly.id, name="Gender", description="Gender category")
        category.add_value(TargetValue(value="Male", min=10, max=15))
        category.add_value(TargetValue(value="Female", min=10, max=15))

        target_category_repo.add(category)
        postgres_session.commit()

        # Test get by ID
        retrieved = target_category_repo.get(category.id)
        assert retrieved is not None
        assert retrieved.name == "Gender"
        assert retrieved.description == "Gender category"
        assert len(retrieved.values) == 2
        assert retrieved.values[0].value == "Male"
        assert retrieved.values[0].min == 10
        assert retrieved.values[0].max == 15

    def test_get_by_assembly_id(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test retrieving categories by assembly ID."""
        cat1 = TargetCategory(assembly_id=test_assembly.id, name="Gender", sort_order=0)
        cat1.add_value(TargetValue(value="Male", min=10, max=15))

        cat2 = TargetCategory(assembly_id=test_assembly.id, name="Age", sort_order=1)
        cat2.add_value(TargetValue(value="16-29", min=5, max=8))

        target_category_repo.add(cat1)
        target_category_repo.add(cat2)
        postgres_session.commit()

        # Get all categories for assembly
        categories = target_category_repo.get_by_assembly_id(test_assembly.id)
        assert len(categories) == 2
        # Should be ordered by sort_order
        assert categories[0].name == "Gender"
        assert categories[1].name == "Age"

    def test_delete_category(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test deleting a target category."""
        category = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        category.add_value(TargetValue(value="Male", min=10, max=15))

        target_category_repo.add(category)
        postgres_session.commit()
        category_id = category.id

        # Delete the category
        cat = target_category_repo.get(category_id)
        target_category_repo.delete(cat)
        postgres_session.commit()

        # Verify it's gone
        retrieved = target_category_repo.get(category_id)
        assert retrieved is None

    def test_delete_all_for_assembly(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test deleting all categories for an assembly."""
        cat1 = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        cat2 = TargetCategory(assembly_id=test_assembly.id, name="Age")

        target_category_repo.add(cat1)
        target_category_repo.add(cat2)
        postgres_session.commit()

        # Delete all categories for assembly
        count = target_category_repo.delete_all_for_assembly(test_assembly.id)
        postgres_session.commit()

        assert count == 2

        # Verify they're gone
        categories = target_category_repo.get_by_assembly_id(test_assembly.id)
        assert len(categories) == 0

    def test_cascade_delete_with_assembly(
        self, target_category_repo: SqlAlchemyTargetCategoryRepository, postgres_session: Session
    ):
        """Test that categories are deleted when assembly is deleted (cascade)."""
        # Create assembly
        assembly = Assembly(title="Test", question="Q?")
        postgres_session.add(assembly)
        postgres_session.commit()
        assembly_id = assembly.id

        # Create category
        cat = TargetCategory(assembly_id=assembly_id, name="Gender")
        cat.add_value(TargetValue(value="Male", min=10, max=15))
        target_category_repo.add(cat)
        postgres_session.commit()
        category_id = cat.id

        # Delete assembly
        postgres_session.delete(assembly)
        postgres_session.commit()

        # Category should be gone (cascade delete)
        category = target_category_repo.get(category_id)
        assert category is None

    def test_target_value_json_serialization(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test that TargetValue list is properly serialized/deserialized from JSON."""
        category = TargetCategory(assembly_id=test_assembly.id, name="Gender")

        value1 = TargetValue(value="Male", min=10, max=15, min_flex=8, max_flex=18, percentage_target=50.0)
        value2 = TargetValue(value="Female", min=10, max=15, min_flex=8, max_flex=18, percentage_target=50.0)

        category.add_value(value1)
        category.add_value(value2)

        target_category_repo.add(category)
        postgres_session.commit()

        # Retrieve and verify all fields survived serialization
        retrieved = target_category_repo.get(category.id)
        assert retrieved is not None
        assert len(retrieved.values) == 2

        male_value = retrieved.get_value("Male")
        assert male_value is not None
        assert male_value.min == 10
        assert male_value.max == 15
        assert male_value.min_flex == 8
        assert male_value.max_flex == 18
        assert male_value.percentage_target == 50.0
        assert male_value.value_id == value1.value_id

    def test_unique_constraint_assembly_name(
        self,
        target_category_repo: SqlAlchemyTargetCategoryRepository,
        test_assembly: Assembly,
        postgres_session: Session,
    ):
        """Test that category names must be unique per assembly."""
        cat1 = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        target_category_repo.add(cat1)
        postgres_session.commit()

        # Try to add another category with same name
        cat2 = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        target_category_repo.add(cat2)

        # This should raise an integrity error
        with pytest.raises(IntegrityError):
            postgres_session.commit()
