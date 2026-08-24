"""ABOUTME: Integration tests for SQL-specific TargetCategoryRepository behaviour.
ABOUTME: Tests cascade deletes, JSON serialization, and database constraints."""

import pytest
from sqlalchemy import text
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


class TestLegacyStoredValues:
    """Rows written before `description` was removed must still load."""

    def test_row_whose_json_still_contains_description(
        self, target_category_repo: SqlAlchemyTargetCategoryRepository, postgres_session: Session, test_assembly
    ):
        category = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        category.add_value(TargetValue(value="Man", min=10, max=15))
        target_category_repo.add(category)
        postgres_session.commit()
        category_id = category.id

        # Put the row back into the shape an older version of the code wrote:
        # a `description` key the dataclass no longer has.
        postgres_session.execute(
            text(
                """
                UPDATE target_categories
                SET "values" = (
                    SELECT jsonb_agg(elem || '{"description": "legacy"}'::jsonb ORDER BY ord)::json
                    FROM jsonb_array_elements("values"::jsonb) WITH ORDINALITY AS t(elem, ord)
                )
                WHERE id = :id
                """
            ),
            {"id": category_id},
        )
        postgres_session.commit()
        postgres_session.expunge_all()

        reloaded = target_category_repo.get(category_id)

        assert len(reloaded.values) == 1
        assert reloaded.values[0].value == "Man"
        assert not hasattr(reloaded.values[0], "description")

    def test_row_missing_the_new_keys_takes_the_defaults(
        self, target_category_repo: SqlAlchemyTargetCategoryRepository, postgres_session: Session, test_assembly
    ):
        category = TargetCategory(assembly_id=test_assembly.id, name="Gender")
        category.add_value(TargetValue(value="Man", min=10, max=15))
        target_category_repo.add(category)
        postgres_session.commit()
        category_id = category.id

        postgres_session.execute(
            text(
                """
                UPDATE target_categories
                SET "values" = (
                    SELECT jsonb_agg((elem - 'comment') - 'minmax_manual' ORDER BY ord)::json
                    FROM jsonb_array_elements("values"::jsonb) WITH ORDINALITY AS t(elem, ord)
                )
                WHERE id = :id
                """
            ),
            {"id": category_id},
        )
        postgres_session.commit()
        postgres_session.expunge_all()

        value = target_category_repo.get(category_id).values[0]

        assert value.comment == ""
        assert value.minmax_manual is False
