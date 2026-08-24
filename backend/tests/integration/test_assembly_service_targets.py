"""ABOUTME: Integration tests for assembly service target category functions
ABOUTME: Tests target category creation, import, and retrieval service functions"""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import assembly_service, respondent_service, target_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    """An already-entered UnitOfWork, for tests that need only one."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as entered:
        yield entered


def _seed(postgres_session_factory, repository_name: str, item):
    """Commit one item on its own UnitOfWork and return a detached copy.

    Its own UnitOfWork rather than the `uow` fixture: a seed that shared the
    test's still-open transaction would hold locks that the test's second
    UnitOfWork then waits on.
    """
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        getattr(uow, repository_name).add(item)
        detached = item.create_detached_copy()
        uow.commit()
    return detached


@pytest.fixture
def admin_user(postgres_session_factory):
    """Create an admin user."""
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    return _seed(postgres_session_factory, "users", user)


@pytest.fixture
def regular_user(postgres_session_factory):
    """Create a regular user with no management permissions."""
    user = User(email="viewer@test.com", global_role=GlobalRole.USER, password_hash="hash123")
    return _seed(postgres_session_factory, "users", user)


@pytest.fixture
def other_assembly(postgres_session_factory):
    """Create a second test assembly."""
    assembly = Assembly(title="Other Assembly", question="Other?", number_to_select=20)
    return _seed(postgres_session_factory, "assemblies", assembly)


@pytest.fixture
def test_assembly(postgres_session_factory):
    """Create a test assembly with number_to_select set."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    return _seed(postgres_session_factory, "assemblies", assembly)


class TestCreateTargetCategory:
    def test_create_category_success(self, uow, admin_user: User, test_assembly: Assembly):
        """Test creating a target category."""
        category = target_service.create_target_category(
            uow,
            admin_user.id,
            test_assembly.id,
            name="Gender",
            comment="Gender category",
            sort_order=0,
        )

        assert category.name == "Gender"
        assert category.comment == "Gender category"
        assert category.assembly_id == test_assembly.id
        assert category.sort_order == 0

        # Verify it was persisted
        retrieved = uow.target_categories.get(category.id)
        assert retrieved is not None
        assert retrieved.name == "Gender"

    def test_create_category_with_invalid_assembly(self, uow, admin_user: User):
        """Test creating category for non-existent assembly raises error."""
        with pytest.raises(AssemblyNotFoundError):
            target_service.create_target_category(
                uow,
                admin_user.id,
                uuid.uuid4(),  # Non-existent assembly
                name="Gender",
            )

    def test_create_duplicate_category_raises_value_error(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test creating a category with the same name raises ValueError."""
        uow1 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow1:
            target_service.create_target_category(uow1, admin_user.id, test_assembly.id, name="Gender")

        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(ValueError, match="already exists"):
            target_service.create_target_category(uow2, admin_user.id, test_assembly.id, name="Gender")

    def test_create_duplicate_category_case_insensitive(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test duplicate check is case-insensitive."""
        uow1 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow1:
            target_service.create_target_category(uow1, admin_user.id, test_assembly.id, name="Gender")

        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(ValueError, match="already exists"):
            target_service.create_target_category(uow2, admin_user.id, test_assembly.id, name="gender")

    def test_create_category_without_permission(self, uow, test_assembly: Assembly):
        """Test creating category without permission raises error."""
        # Create non-admin user
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        uow.users.add(user)
        detached_user = user.create_detached_copy()
        uow.commit()

        with pytest.raises(InsufficientPermissions):
            target_service.create_target_category(
                uow,
                detached_user.id,
                test_assembly.id,
                name="Gender",
            )


class TestGetTargetsForAssembly:
    def test_get_empty_targets(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting targets for assembly with no targets."""
        categories = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert categories == []

    def test_get_targets_ordered_by_sort_order(self, uow, admin_user: User, test_assembly: Assembly):
        """Test targets are returned ordered by sort_order."""
        # Create categories in reverse order
        target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Age", sort_order=2)
        target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender", sort_order=1)
        target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Location", sort_order=0)

        categories = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)

        assert len(categories) == 3
        assert categories[0].name == "Location"  # sort_order=0
        assert categories[1].name == "Gender"  # sort_order=1
        assert categories[2].name == "Age"  # sort_order=2

    def test_get_targets_without_permission(self, uow, test_assembly: Assembly):
        """Test getting targets without permission raises error."""
        # Create non-admin user with no assembly role
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        uow.users.add(user)
        user_id = user.id
        uow.commit()

        with pytest.raises(InsufficientPermissions):
            target_service.get_targets_for_assembly(uow, user_id, test_assembly.id)


class TestImportTargetsFromCSV:
    def test_import_valid_csv(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing valid CSV data."""
        csv_content = """feature,value,min,max,min_flex,max_flex
Gender,Male,12,17,9,19
Gender,Female,12,17,9,19
Age,16-29,17,22,14,25
Age,30-44,5,9,4,10"""

        categories = target_service.import_targets_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        ).categories

        assert len(categories) == 2
        assert categories[0].name == "Gender"
        assert len(categories[0].values) == 2
        assert categories[1].name == "Age"
        assert len(categories[1].values) == 2

        # Verify min_flex and max_flex were preserved
        male_value = categories[0].get_value("Male")
        assert male_value is not None
        assert male_value.min_flex == 9
        assert male_value.max_flex == 19

    def test_import_csv_with_minimal_columns(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing CSV with just min/max (no flex values)."""
        csv_content = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        categories = target_service.import_targets_from_csv(
            uow, admin_user.id, test_assembly.id, csv_content
        ).categories

        assert len(categories) == 1
        assert categories[0].name == "Gender"
        assert len(categories[0].values) == 2

        # Verify defaults were applied by sortition-algorithms
        male_value = categories[0].get_value("Male")
        assert male_value is not None
        assert male_value.min == 10
        assert male_value.max == 15

    def test_import_invalid_csv_raises_error(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing invalid CSV raises InvalidSelection."""
        csv_content = """feature,value,min,max
Gender,Male,20,10"""  # Invalid: min > max

        with pytest.raises(InvalidSelection):
            target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

    def test_import_with_replace_existing(self, uow, admin_user: User, test_assembly: Assembly):
        """Test replacing existing targets with new import."""
        # First import
        csv1 = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv1)

        # Verify first import
        categories = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert len(categories) == 1
        assert categories[0].name == "Gender"

        # Second import with replace
        csv2 = """feature,value,min,max
Age,16-29,17,22
Age,30-44,5,9"""

        categories = target_service.import_targets_from_csv(
            uow, admin_user.id, test_assembly.id, csv2, replace_existing=True
        ).categories

        assert len(categories) == 1
        assert categories[0].name == "Age"

        # Verify old categories are gone
        all_cats = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert len(all_cats) == 1
        assert all_cats[0].name == "Age"

    def test_import_without_permission(self, uow, test_assembly: Assembly):
        """Test importing without permission raises error."""
        # Create non-admin user
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        uow.users.add(user)
        user_id = user.id
        uow.commit()

        csv_content = """feature,value,min,max
Gender,Male,10,15"""

        with pytest.raises(InsufficientPermissions):
            target_service.import_targets_from_csv(uow, user_id, test_assembly.id, csv_content)


class TestGetFeatureCollectionForAssembly:
    def test_convert_to_feature_collection(self, uow, admin_user: User, test_assembly: Assembly):
        """Test converting targets to FeatureCollection."""
        csv_content = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        fc, report = target_service.get_feature_collection_for_assembly(uow, admin_user.id, test_assembly.id)

        assert "Gender" in fc
        assert "Male" in fc["Gender"]
        assert "Female" in fc["Gender"]
        assert fc["Gender"]["Male"].min == 10
        assert fc["Gender"]["Male"].max == 15

        # Check report is not empty - we can't check for specific messages as they're library-internal
        assert report is not None

    def test_empty_feature_collection(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting feature collection when no targets exist."""
        fc, _ = target_service.get_feature_collection_for_assembly(uow, admin_user.id, test_assembly.id)

        assert len(fc) == 0


class TestUpdateTargetCategory:
    def test_update_category_name(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            updated = target_service.update_target_category(
                uow2, admin_user.id, test_assembly.id, category.id, name="Sex"
            )
        assert updated.name == "Sex"

    def test_update_nonexistent_category_raises(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(NotFoundError):
            target_service.update_target_category(uow, admin_user.id, test_assembly.id, uuid.uuid4(), name="Nope")

    def test_update_category_wrong_assembly_raises(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(NotFoundError):
            target_service.update_target_category(uow2, admin_user.id, other_assembly.id, category.id, name="Nope")

    def test_update_category_insufficient_permissions(
        self, admin_user: User, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(InsufficientPermissions):
            target_service.update_target_category(uow2, regular_user.id, test_assembly.id, category.id, name="X")


class TestDeleteTargetCategory:
    def test_delete_category(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            target_service.delete_target_category(uow2, admin_user.id, test_assembly.id, category.id)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            cats = target_service.get_targets_for_assembly(uow3, admin_user.id, test_assembly.id)
        assert len(cats) == 0

    def test_delete_nonexistent_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(NotFoundError):
            target_service.delete_target_category(uow, admin_user.id, test_assembly.id, uuid.uuid4())


class TestAddTargetValue:
    def test_add_value_to_category(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            updated = target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        assert len(updated.values) == 1
        assert updated.values[0].value == "Male"
        assert updated.values[0].min == 5
        assert updated.values[0].max == 10
        assert updated.values[0].min_flex == 0
        assert updated.values[0].max_flex == MAX_FLEX_UNSET

    def test_add_duplicate_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3, pytest.raises(ValueError, match="already exists"):
            target_service.add_target_value(uow3, admin_user.id, test_assembly.id, category.id, "Male", 3, 7)

    def test_add_value_invalid_min_max_raises(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(ValueError):
            target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 10, 5)


class TestUpdateTargetValue:
    def test_update_value(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            cat = target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            updated = target_service.update_target_value(
                uow3, admin_user.id, test_assembly.id, category.id, value_id, "Female", 6, 12
            )
        assert updated.values[0].value == "Female"
        assert updated.values[0].min == 6
        assert updated.values[0].max == 12

    def test_update_to_duplicate_name_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            cat = target_service.add_target_value(uow3, admin_user.id, test_assembly.id, category.id, "Female", 5, 10)
        value_id = cat.values[1].value_id
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4, pytest.raises(ValueError, match="already exists"):
            target_service.update_target_value(
                uow4, admin_user.id, test_assembly.id, category.id, value_id, "Male", 5, 10
            )

    def test_update_value_resets_max_flex(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Editing a value via the form should reset max_flex to unset,
        since the form doesn't expose max_flex and the sortition library
        recalculates it at selection time."""
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            target_service.import_targets_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
            )

        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            categories = uow2.target_categories.get_by_assembly_id(test_assembly.id)
            category = categories[0]
            male_value = next(v for v in category.values if v.value == "Male")
            assert male_value.max_flex != MAX_FLEX_UNSET, "CSV import should set max_flex"
            category_id = category.id
            value_id = male_value.value_id

        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            updated = target_service.update_target_value(
                uow3, admin_user.id, test_assembly.id, category_id, value_id, "Male", 4, 8
            )
        updated_male = next(v for v in updated.values if v.value == "Male")
        assert updated_male.min == 4
        assert updated_male.max == 8
        assert updated_male.max_flex == MAX_FLEX_UNSET

    def test_update_nonexistent_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(NotFoundError):
            target_service.update_target_value(
                uow2, admin_user.id, test_assembly.id, category.id, uuid.uuid4(), "Male", 5, 10
            )


class TestDeleteTargetValue:
    def test_delete_value(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            cat = target_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            updated = target_service.delete_target_value(uow3, admin_user.id, test_assembly.id, category.id, value_id)
        assert len(updated.values) == 0

    def test_delete_nonexistent_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2, pytest.raises(NotFoundError):
            target_service.delete_target_value(uow2, admin_user.id, test_assembly.id, category.id, uuid.uuid4())


class TestDeleteTargetsForAssembly:
    def test_delete_all_targets(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Test deleting all target categories for an assembly."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender", sort_order=0)
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            target_service.create_target_category(uow2, admin_user.id, test_assembly.id, "Age", sort_order=1)

        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            count = target_service.delete_targets_for_assembly(uow3, admin_user.id, test_assembly.id)
        assert count == 2

        # Verify they're gone
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4:
            cats = target_service.get_targets_for_assembly(uow4, admin_user.id, test_assembly.id)
        assert len(cats) == 0

    def test_delete_targets_returns_zero_when_none_exist(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting targets when none exist returns 0."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            count = target_service.delete_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert count == 0

    def test_delete_targets_insufficient_permissions(
        self, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that a regular user cannot delete targets."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(InsufficientPermissions):
            target_service.delete_targets_for_assembly(uow, regular_user.id, test_assembly.id)

    def test_delete_targets_nonexistent_assembly(self, admin_user: User, postgres_session_factory):
        """Test that deleting targets for a nonexistent assembly raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(AssemblyNotFoundError):
            target_service.delete_targets_for_assembly(uow, admin_user.id, uuid.uuid4())

    def test_delete_targets_nonexistent_user(self, test_assembly: Assembly, postgres_session_factory):
        """Test that deleting targets with a nonexistent user raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(UserNotFoundError):
            target_service.delete_targets_for_assembly(uow, uuid.uuid4(), test_assembly.id)

    def test_delete_targets_does_not_affect_other_assembly(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting targets for one assembly doesn't affect another."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            target_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            target_service.create_target_category(uow2, admin_user.id, other_assembly.id, "Age")

        # Delete only from test_assembly
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            target_service.delete_targets_for_assembly(uow3, admin_user.id, test_assembly.id)

        # other_assembly targets should still exist
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4:
            other_cats = target_service.get_targets_for_assembly(uow4, admin_user.id, other_assembly.id)
        assert len(other_cats) == 1
        assert other_cats[0].name == "Age"


class TestDeleteRespondentsForAssembly:
    def test_delete_all_respondents(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Test deleting all respondents for an assembly."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            respondent_service.create_respondent(
                uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={"Gender": "Male"}
            )
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            respondent_service.create_respondent(
                uow2, admin_user.id, test_assembly.id, external_id="NB002", attributes={"Gender": "Female"}
            )

        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            count = assembly_service.delete_respondents_for_assembly(uow3, admin_user.id, test_assembly.id)
        assert count == 2

        # Verify they're gone
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4:
            respondents = uow4.respondents.get_by_assembly_id(test_assembly.id)
            assert len(respondents) == 0

    def test_delete_respondents_returns_zero_when_none_exist(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting respondents when none exist returns 0."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            count = assembly_service.delete_respondents_for_assembly(uow, admin_user.id, test_assembly.id)
        assert count == 0

    def test_delete_respondents_insufficient_permissions(
        self, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that a regular user cannot delete respondents."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(InsufficientPermissions):
            assembly_service.delete_respondents_for_assembly(uow, regular_user.id, test_assembly.id)

    def test_delete_respondents_nonexistent_assembly(self, admin_user: User, postgres_session_factory):
        """Test that deleting respondents for a nonexistent assembly raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(AssemblyNotFoundError):
            assembly_service.delete_respondents_for_assembly(uow, admin_user.id, uuid.uuid4())

    def test_delete_respondents_nonexistent_user(self, test_assembly: Assembly, postgres_session_factory):
        """Test that deleting respondents with a nonexistent user raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow, pytest.raises(UserNotFoundError):
            assembly_service.delete_respondents_for_assembly(uow, uuid.uuid4(), test_assembly.id)

    def test_delete_respondents_does_not_affect_other_assembly(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting respondents for one assembly doesn't affect another."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow:
            respondent_service.create_respondent(
                uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={"Gender": "Male"}
            )
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow2:
            respondent_service.create_respondent(
                uow2, admin_user.id, other_assembly.id, external_id="NB002", attributes={"Gender": "Female"}
            )

        # Delete only from test_assembly
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow3:
            assembly_service.delete_respondents_for_assembly(uow3, admin_user.id, test_assembly.id)

        # other_assembly respondents should still exist
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4:
            other_resps = uow4.respondents.get_by_assembly_id(other_assembly.id)
            assert len(other_resps) == 1
            assert other_resps[0].external_id == "NB002"


def _category_with_percentages(uow, admin_user, assembly, percentages):
    """A category whose values all carry a percentage and an intact link."""
    category = target_service.create_target_category(uow, admin_user.id, assembly.id, name="Gender")
    for name, percentage in percentages.items():
        target_service.add_target_value(uow, admin_user.id, assembly.id, category.id, value=name, percentage=percentage)
    return target_service.get_targets_for_assembly(uow, admin_user.id, assembly.id)[0]


class TestReorderTargetCategories:
    def test_reissues_sort_order_in_tens(self, uow, admin_user: User, test_assembly: Assembly):
        names = ["Gender", "Age", "Region"]
        created = [target_service.create_target_category(uow, admin_user.id, test_assembly.id, name=n) for n in names]

        target_service.reorder_target_categories(
            uow, admin_user.id, test_assembly.id, [created[2].id, created[0].id, created[1].id]
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert [c.name for c in after] == ["Region", "Gender", "Age"]
        assert [c.sort_order for c in after] == [10, 20, 30]

    def test_partial_id_set_is_rejected(self, uow, admin_user: User, test_assembly: Assembly):
        """A stale page must not be able to silently drop a category."""
        first = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender")
        target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Age")

        with pytest.raises(ValueError, match="complete set"):
            target_service.reorder_target_categories(uow, admin_user.id, test_assembly.id, [first.id])

    def test_id_from_another_assembly_is_rejected(
        self, uow, admin_user: User, test_assembly: Assembly, other_assembly: Assembly
    ):
        mine = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender")
        theirs = target_service.create_target_category(uow, admin_user.id, other_assembly.id, name="Gender")

        with pytest.raises(ValueError, match="complete set"):
            target_service.reorder_target_categories(uow, admin_user.id, test_assembly.id, [mine.id, theirs.id])

    def test_requires_manage_permission(self, uow, regular_user: User, test_assembly: Assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.reorder_target_categories(uow, regular_user.id, test_assembly.id, [])


class TestCreateCategorySortOrder:
    def test_new_category_lands_after_the_existing_ones(self, uow, admin_user: User, test_assembly: Assembly):
        first = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender")
        second = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Age")

        assert second.sort_order > first.sort_order


class TestRecalculateOnNumberToSelectChange:
    def test_linked_values_move_and_manual_ones_do_not(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0, "Woman": 50.0})
        manual = category.values[1]
        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            manual.value_id,
            value="Woman",
            min_count=7,
            max_count=9,
        )

        assembly_service.update_assembly(uow, test_assembly.id, admin_user.id, number_to_select=100)

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        linked = after.get_value("Man")
        untouched = after.get_value("Woman")
        assert (linked.min, linked.max) == (50, 51)
        assert (untouched.min, untouched.max) == (7, 9)

    def test_other_assembly_fields_do_not_touch_targets(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        before = (category.values[0].min, category.values[0].max)

        assembly_service.update_assembly(uow, test_assembly.id, admin_user.id, title="Renamed")

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert (after.values[0].min, after.values[0].max) == before

    def test_returns_the_values_that_moved(self, uow, admin_user: User, test_assembly: Assembly):
        _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0, "Woman": 50.0})
        test_assembly_obj = uow.assemblies.get(test_assembly.id)
        test_assembly_obj.number_to_select = 100

        changes = target_service.recalculate_minmax_for_assembly(uow, test_assembly.id)

        assert len(changes) == 2
        assert {c.value for c in changes} == {"Man", "Woman"}
        assert all(c.new_min == 50 and c.new_max == 51 for c in changes)


class TestUpdateTargetValueLinkRules:
    def test_unchanged_minmax_does_not_break_the_link(self, uow, admin_user: User, test_assembly: Assembly):
        """The rule the whole bulk-save UI rests on."""
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]

        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            value.value_id,
            value="Man",
            min_count=value.min,
            max_count=value.max,
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].minmax_manual is False

    def test_changed_minmax_breaks_the_link(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]

        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            value.value_id,
            value="Man",
            min_count=1,
            max_count=2,
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].minmax_manual is True
        assert (after.values[0].min, after.values[0].max) == (1, 2)

    def test_explicit_minmax_wins_over_a_percentage_in_the_same_call(
        self, uow, admin_user: User, test_assembly: Assembly
    ):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]

        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            value.value_id,
            value="Man",
            percentage=25.0,
            min_count=3,
            max_count=4,
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].percentage_target == 25.0
        assert (after.values[0].min, after.values[0].max) == (3, 4)
        assert after.values[0].minmax_manual is True

    def test_clearing_the_percentage_leaves_minmax_alone(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]
        before = (value.min, value.max)

        target_service.update_target_value(
            uow, admin_user.id, test_assembly.id, category.id, value.value_id, value="Man", percentage=None
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].percentage_target is None
        assert (after.values[0].min, after.values[0].max) == before


class TestRelinkTargetValue:
    def test_restores_auto_calculation(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]
        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            value.value_id,
            value="Man",
            min_count=1,
            max_count=2,
        )

        target_service.relink_target_value_to_percentage(
            uow, admin_user.id, test_assembly.id, category.id, value.value_id
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].minmax_manual is False
        assert (after.values[0].min, after.values[0].max) == (15, 16)

    def test_a_relinked_value_moves_with_number_to_select(self, uow, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})
        value = category.values[0]
        target_service.update_target_value(
            uow,
            admin_user.id,
            test_assembly.id,
            category.id,
            value.value_id,
            value="Man",
            min_count=1,
            max_count=2,
        )
        target_service.relink_target_value_to_percentage(
            uow, admin_user.id, test_assembly.id, category.id, value.value_id
        )

        assembly_service.update_assembly(uow, test_assembly.id, admin_user.id, number_to_select=100)

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert (after.values[0].min, after.values[0].max) == (50, 51)

    def test_refuses_without_a_percentage(self, uow, admin_user: User, test_assembly: Assembly):
        category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender")
        target_service.add_target_value(
            uow, admin_user.id, test_assembly.id, category.id, value="Man", min_count=1, max_count=2
        )
        reloaded = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]

        with pytest.raises(ValueError, match="no percentage"):
            target_service.relink_target_value_to_percentage(
                uow, admin_user.id, test_assembly.id, category.id, reloaded.values[0].value_id
            )

    def test_requires_manage_permission(self, uow, regular_user: User, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})

        with pytest.raises(InsufficientPermissions):
            target_service.relink_target_value_to_percentage(
                uow, regular_user.id, test_assembly.id, category.id, category.values[0].value_id
            )


class TestSetTargetValuePercentage:
    def test_sets_and_recalculates(self, uow, admin_user: User, test_assembly: Assembly):
        category = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender")
        target_service.add_target_value(uow, admin_user.id, test_assembly.id, category.id, value="Man")
        reloaded = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]

        target_service.set_target_value_percentage(
            uow, admin_user.id, test_assembly.id, category.id, reloaded.values[0].value_id, 50.0
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert after.values[0].percentage_target == 50.0
        assert (after.values[0].min, after.values[0].max) == (15, 16)

    def test_requires_manage_permission(self, uow, regular_user: User, admin_user: User, test_assembly: Assembly):
        category = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0})

        with pytest.raises(InsufficientPermissions):
            target_service.set_target_value_percentage(
                uow, regular_user.id, test_assembly.id, category.id, category.values[0].value_id, 25.0
            )


class TestSaveAllTargets:
    def test_saves_across_two_categories(self, uow, admin_user: User, test_assembly: Assembly):
        gender = _category_with_percentages(uow, admin_user, test_assembly, {"Man": 50.0, "Woman": 50.0})
        age = target_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Age")

        target_service.save_all_targets(
            uow,
            admin_user.id,
            test_assembly.id,
            [
                target_service.TargetCategoryEdit(
                    category_id=gender.id,
                    name="Gender",
                    comment="from the census",
                    source_url="https://www.ons.gov.uk/dataset",
                    values=[
                        target_service.TargetValueEdit(
                            value_id=gender.values[0].value_id, value="Man", percentage=60.0
                        ),
                        target_service.TargetValueEdit(
                            value_id=gender.values[1].value_id, value="Woman", percentage=40.0
                        ),
                    ],
                ),
                target_service.TargetCategoryEdit(
                    category_id=age.id,
                    name="Age",
                    values=[target_service.TargetValueEdit(value="16-29", percentage=100.0)],
                ),
            ],
        )

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        by_name = {c.name: c for c in after}
        assert by_name["Gender"].comment == "from the census"
        assert by_name["Gender"].source_url == "https://www.ons.gov.uk/dataset"
        assert [v.percentage_target for v in by_name["Gender"].values] == [60.0, 40.0]
        assert by_name["Age"].values[0].value == "16-29"

    def test_a_failure_partway_through_commits_nothing(
        self, postgres_session_factory, admin_user: User, test_assembly: Assembly
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as setup:
            category = _category_with_percentages(setup, admin_user, test_assembly, {"Man": 50.0})
            setup.commit()

        # The exception must escape the `with uow:` block, exactly as it would
        # from a route - that is what makes the UnitOfWork roll back rather than
        # commit the half-applied edit.
        with pytest.raises(ValueError), SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            target_service.save_all_targets(
                uow,
                admin_user.id,
                test_assembly.id,
                [
                    target_service.TargetCategoryEdit(
                        category_id=category.id,
                        name="Renamed",
                        source_url="javascript:alert(1)",
                        values=[],
                    )
                ],
            )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as check:
            after = target_service.get_targets_for_assembly(check, admin_user.id, test_assembly.id)
            assert after[0].name == "Gender"

    def test_requires_manage_permission(self, uow, regular_user: User, test_assembly: Assembly):
        with pytest.raises(InsufficientPermissions):
            target_service.save_all_targets(uow, regular_user.id, test_assembly.id, [])


class TestImportTargetsNewColumns:
    def test_reads_the_optional_columns(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,percentage,comment,category_comment,source_url
Gender,Male,10,15,48.5,boosted by 2,from the census,https://www.ons.gov.uk/dataset
Gender,Female,10,15,51.5,,from the census,https://www.ons.gov.uk/dataset"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        category = result.categories[0]
        assert category.comment == "from the census"
        assert category.source_url == "https://www.ons.gov.uk/dataset"
        male = category.get_value("Male")
        assert male.percentage_target == 48.5
        assert male.comment == "boosted by 2"
        assert result.warnings == []

    def test_legacy_headers_work_with_the_new_columns(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """category,name,min,max,percentage
Gender,Male,10,15,48.5
Gender,Female,10,15,51.5"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        assert result.categories[0].get_value("Male").percentage_target == 48.5

    def test_imported_values_are_marked_manual(self, uow, admin_user: User, test_assembly: Assembly):
        """The regression test for silent range-narrowing.

        Imported min/max are always deliberate. If the auto-calculate link were
        left intact, the first change to number_to_select would recalculate them
        from the derived percentage and quietly narrow every imported range.
        """
        csv_content = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""
        target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        assembly_service.update_assembly(uow, test_assembly.id, admin_user.id, number_to_select=100)

        after = target_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)[0]
        assert all(v.minmax_manual for v in after.values)
        assert (after.get_value("Male").min, after.get_value("Male").max) == (10, 15)

    def test_derives_percentage_from_midpoint_when_seats_are_known(
        self, uow, admin_user: User, test_assembly: Assembly
    ):
        csv_content = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        # test_assembly selects 30, so a midpoint of 12.5 is 41.7%.
        assert result.categories[0].get_value("Male").percentage_target == 41.7

    def test_derives_percentage_by_ratio_when_seats_are_unknown(self, uow, admin_user: User, postgres_session_factory):
        assembly = _seed(
            postgres_session_factory,
            "assemblies",
            Assembly(title="No seats yet", question="?", number_to_select=0),
        )
        csv_content = """feature,value,min,max
Gender,Male,10,20
Gender,Female,30,40"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, assembly.id, csv_content)

        category = result.categories[0]
        assert category.get_value("Male").percentage_target == 30.0
        assert category.get_value("Female").percentage_target == 70.0
        assert category.percentage_total() == pytest.approx(100.0)

    def test_all_zero_minmax_with_no_seats_leaves_percentages_unset(
        self, uow, admin_user: User, postgres_session_factory
    ):
        assembly = _seed(
            postgres_session_factory,
            "assemblies",
            Assembly(title="Nothing to infer", question="?", number_to_select=0),
        )
        csv_content = """feature,value,min,max
Gender,Male,0,0
Gender,Female,0,0"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, assembly.id, csv_content)

        assert all(v.percentage_target is None for v in result.categories[0].values)

    def test_an_explicit_percentage_is_not_overwritten(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,percentage
Gender,Male,10,15,48.5
Gender,Female,10,15,"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        category = result.categories[0]
        assert category.get_value("Male").percentage_target == 48.5
        assert category.get_value("Female").percentage_target == 41.7

    def test_disagreeing_source_url_warns_and_takes_the_first(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,source_url
Gender,Male,10,15,https://www.ons.gov.uk/one
Gender,Female,10,15,https://www.ons.gov.uk/two"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        assert result.categories[0].source_url == "https://www.ons.gov.uk/one"
        assert len(result.warnings) == 1
        assert "source_url" in result.warnings[0]
        assert "https://www.ons.gov.uk/one" in result.warnings[0]

    def test_disagreeing_category_comment_warns(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,category_comment
Gender,Male,10,15,census 2021
Gender,Female,10,15,census 2011"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        assert result.categories[0].comment == "census 2021"
        assert len(result.warnings) == 1
        assert "category_comment" in result.warnings[0]

    def test_consistent_rows_produce_no_warnings(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,source_url
Gender,Male,10,15,https://www.ons.gov.uk/one
Gender,Female,10,15,https://www.ons.gov.uk/one"""

        result = target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        assert result.warnings == []

    def test_an_invalid_source_url_fails_the_import(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,source_url
Gender,Male,10,15,javascript:alert(1)"""

        with pytest.raises(ValueError, match="http"):
            target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

    def test_an_invalid_percentage_fails_the_import(self, uow, admin_user: User, test_assembly: Assembly):
        csv_content = """feature,value,min,max,percentage
Gender,Male,10,15,not a number"""

        with pytest.raises(InvalidSelection, match="percentage"):
            target_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)
