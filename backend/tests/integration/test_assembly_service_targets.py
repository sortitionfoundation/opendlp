"""ABOUTME: Integration tests for assembly service target category functions
ABOUTME: Tests target category creation, import, and retrieval service functions"""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import assembly_service, respondent_service
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
    """Create a UnitOfWork for testing."""
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow):
    """Create an admin user."""
    user = User(email="admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached_user = user.create_detached_copy()
        uow.commit()
        return detached_user


@pytest.fixture
def regular_user(uow):
    """Create a regular user with no management permissions."""
    user = User(email="viewer@test.com", global_role=GlobalRole.USER, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached_user = user.create_detached_copy()
        uow.commit()
        return detached_user


@pytest.fixture
def other_assembly(uow):
    """Create a second test assembly."""
    assembly = Assembly(title="Other Assembly", question="Other?", number_to_select=20)
    with uow:
        uow.assemblies.add(assembly)
        detached_assembly = assembly.create_detached_copy()
        uow.commit()
        return detached_assembly


@pytest.fixture
def test_assembly(uow):
    """Create a test assembly with number_to_select set."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    with uow:
        uow.assemblies.add(assembly)
        detached_assembly = assembly.create_detached_copy()
        uow.commit()
        return detached_assembly


class TestCreateTargetCategory:
    def test_create_category_success(self, uow, admin_user: User, test_assembly: Assembly):
        """Test creating a target category."""
        category = assembly_service.create_target_category(
            uow,
            admin_user.id,
            test_assembly.id,
            name="Gender",
            description="Gender category",
            sort_order=0,
        )

        assert category.name == "Gender"
        assert category.description == "Gender category"
        assert category.assembly_id == test_assembly.id
        assert category.sort_order == 0

        # Verify it was persisted
        with uow:
            retrieved = uow.target_categories.get(category.id)
            assert retrieved is not None
            assert retrieved.name == "Gender"

    def test_create_category_with_invalid_assembly(self, uow, admin_user: User):
        """Test creating category for non-existent assembly raises error."""
        with pytest.raises(AssemblyNotFoundError):
            assembly_service.create_target_category(
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
        assembly_service.create_target_category(uow1, admin_user.id, test_assembly.id, name="Gender")

        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(ValueError, match="already exists"):
            assembly_service.create_target_category(uow2, admin_user.id, test_assembly.id, name="Gender")

    def test_create_duplicate_category_case_insensitive(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test duplicate check is case-insensitive."""
        uow1 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.create_target_category(uow1, admin_user.id, test_assembly.id, name="Gender")

        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(ValueError, match="already exists"):
            assembly_service.create_target_category(uow2, admin_user.id, test_assembly.id, name="gender")

    def test_create_category_without_permission(self, uow, test_assembly: Assembly):
        """Test creating category without permission raises error."""
        # Create non-admin user
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            detached_user = user.create_detached_copy()
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            assembly_service.create_target_category(
                uow,
                detached_user.id,
                test_assembly.id,
                name="Gender",
            )


class TestGetTargetsForAssembly:
    def test_get_empty_targets(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting targets for assembly with no targets."""
        categories = assembly_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert categories == []

    def test_get_targets_ordered_by_sort_order(self, uow, admin_user: User, test_assembly: Assembly):
        """Test targets are returned ordered by sort_order."""
        # Create categories in reverse order
        assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Age", sort_order=2)
        assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Gender", sort_order=1)
        assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, name="Location", sort_order=0)

        categories = assembly_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)

        assert len(categories) == 3
        assert categories[0].name == "Location"  # sort_order=0
        assert categories[1].name == "Gender"  # sort_order=1
        assert categories[2].name == "Age"  # sort_order=2

    def test_get_targets_without_permission(self, uow, test_assembly: Assembly):
        """Test getting targets without permission raises error."""
        # Create non-admin user with no assembly role
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            assembly_service.get_targets_for_assembly(uow, user_id, test_assembly.id)


class TestImportTargetsFromCSV:
    def test_import_valid_csv(self, uow, admin_user: User, test_assembly: Assembly):
        """Test importing valid CSV data."""
        csv_content = """feature,value,min,max,min_flex,max_flex
Gender,Male,12,17,9,19
Gender,Female,12,17,9,19
Age,16-29,17,22,14,25
Age,30-44,5,9,4,10"""

        categories = assembly_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

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

        categories = assembly_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

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
            assembly_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

    def test_import_with_replace_existing(self, uow, admin_user: User, test_assembly: Assembly):
        """Test replacing existing targets with new import."""
        # First import
        csv1 = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        assembly_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv1)

        # Verify first import
        categories = assembly_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert len(categories) == 1
        assert categories[0].name == "Gender"

        # Second import with replace
        csv2 = """feature,value,min,max
Age,16-29,17,22
Age,30-44,5,9"""

        categories = assembly_service.import_targets_from_csv(
            uow, admin_user.id, test_assembly.id, csv2, replace_existing=True
        )

        assert len(categories) == 1
        assert categories[0].name == "Age"

        # Verify old categories are gone
        all_cats = assembly_service.get_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert len(all_cats) == 1
        assert all_cats[0].name == "Age"

    def test_import_without_permission(self, uow, test_assembly: Assembly):
        """Test importing without permission raises error."""
        # Create non-admin user
        user = User(email="user@test.com", global_role=GlobalRole.USER, password_hash="hash123")
        with uow:
            uow.users.add(user)
            user_id = user.id
            uow.commit()

        csv_content = """feature,value,min,max
Gender,Male,10,15"""

        with pytest.raises(InsufficientPermissions):
            assembly_service.import_targets_from_csv(uow, user_id, test_assembly.id, csv_content)


class TestGetFeatureCollectionForAssembly:
    def test_convert_to_feature_collection(self, uow, admin_user: User, test_assembly: Assembly):
        """Test converting targets to FeatureCollection."""
        csv_content = """feature,value,min,max
Gender,Male,10,15
Gender,Female,10,15"""

        assembly_service.import_targets_from_csv(uow, admin_user.id, test_assembly.id, csv_content)

        fc, report = assembly_service.get_feature_collection_for_assembly(uow, admin_user.id, test_assembly.id)

        assert "Gender" in fc
        assert "Male" in fc["Gender"]
        assert "Female" in fc["Gender"]
        assert fc["Gender"]["Male"].min == 10
        assert fc["Gender"]["Male"].max == 15

        # Check report is not empty - we can't check for specific messages as they're library-internal
        assert report is not None

    def test_empty_feature_collection(self, uow, admin_user: User, test_assembly: Assembly):
        """Test getting feature collection when no targets exist."""
        fc, _ = assembly_service.get_feature_collection_for_assembly(uow, admin_user.id, test_assembly.id)

        assert len(fc) == 0


class TestUpdateTargetCategory:
    def test_update_category_name(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        updated = assembly_service.update_target_category(
            uow2, admin_user.id, test_assembly.id, category.id, name="Sex"
        )
        assert updated.name == "Sex"

    def test_update_nonexistent_category_raises(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(NotFoundError):
            assembly_service.update_target_category(uow, admin_user.id, test_assembly.id, uuid.uuid4(), name="Nope")

    def test_update_category_wrong_assembly_raises(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(NotFoundError):
            assembly_service.update_target_category(uow2, admin_user.id, other_assembly.id, category.id, name="Nope")

    def test_update_category_insufficient_permissions(
        self, admin_user: User, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(InsufficientPermissions):
            assembly_service.update_target_category(uow2, regular_user.id, test_assembly.id, category.id, name="X")


class TestDeleteTargetCategory:
    def test_delete_category(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.delete_target_category(uow2, admin_user.id, test_assembly.id, category.id)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cats = assembly_service.get_targets_for_assembly(uow3, admin_user.id, test_assembly.id)
        assert len(cats) == 0

    def test_delete_nonexistent_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(NotFoundError):
            assembly_service.delete_target_category(uow, admin_user.id, test_assembly.id, uuid.uuid4())


class TestAddTargetValue:
    def test_add_value_to_category(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        updated = assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        assert len(updated.values) == 1
        assert updated.values[0].value == "Male"
        assert updated.values[0].min == 5
        assert updated.values[0].max == 10
        assert updated.values[0].min_flex == 0
        assert updated.values[0].max_flex == MAX_FLEX_UNSET

    def test_add_duplicate_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(ValueError, match="already exists"):
            assembly_service.add_target_value(uow3, admin_user.id, test_assembly.id, category.id, "Male", 3, 7)

    def test_add_value_invalid_min_max_raises(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(ValueError):
            assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 10, 5)


class TestUpdateTargetValue:
    def test_update_value(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        updated = assembly_service.update_target_value(
            uow3, admin_user.id, test_assembly.id, category.id, value_id, "Female", 6, 12
        )
        assert updated.values[0].value == "Female"
        assert updated.values[0].min == 6
        assert updated.values[0].max == 12

    def test_update_to_duplicate_name_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = assembly_service.add_target_value(uow3, admin_user.id, test_assembly.id, category.id, "Female", 5, 10)
        value_id = cat.values[1].value_id
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(ValueError, match="already exists"):
            assembly_service.update_target_value(
                uow4, admin_user.id, test_assembly.id, category.id, value_id, "Male", 5, 10
            )

    def test_update_value_resets_max_flex(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Editing a value via the form should reset max_flex to unset,
        since the form doesn't expose max_flex and the sortition library
        recalculates it at selection time."""
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.import_targets_from_csv(
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
        updated = assembly_service.update_target_value(
            uow3, admin_user.id, test_assembly.id, category_id, value_id, "Male", 4, 8
        )
        updated_male = next(v for v in updated.values if v.value == "Male")
        assert updated_male.min == 4
        assert updated_male.max == 8
        assert updated_male.max_flex == MAX_FLEX_UNSET

    def test_update_nonexistent_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(NotFoundError):
            assembly_service.update_target_value(
                uow2, admin_user.id, test_assembly.id, category.id, uuid.uuid4(), "Male", 5, 10
            )


class TestDeleteTargetValue:
    def test_delete_value(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = assembly_service.add_target_value(uow2, admin_user.id, test_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        updated = assembly_service.delete_target_value(uow3, admin_user.id, test_assembly.id, category.id, value_id)
        assert len(updated.values) == 0

    def test_delete_nonexistent_value_raises(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(NotFoundError):
            assembly_service.delete_target_value(uow2, admin_user.id, test_assembly.id, category.id, uuid.uuid4())


class TestDeleteTargetsForAssembly:
    def test_delete_all_targets(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Test deleting all target categories for an assembly."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender", sort_order=0)
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.create_target_category(uow2, admin_user.id, test_assembly.id, "Age", sort_order=1)

        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        count = assembly_service.delete_targets_for_assembly(uow3, admin_user.id, test_assembly.id)
        assert count == 2

        # Verify they're gone
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cats = assembly_service.get_targets_for_assembly(uow4, admin_user.id, test_assembly.id)
        assert len(cats) == 0

    def test_delete_targets_returns_zero_when_none_exist(
        self, admin_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting targets when none exist returns 0."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        count = assembly_service.delete_targets_for_assembly(uow, admin_user.id, test_assembly.id)
        assert count == 0

    def test_delete_targets_insufficient_permissions(
        self, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that a regular user cannot delete targets."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(InsufficientPermissions):
            assembly_service.delete_targets_for_assembly(uow, regular_user.id, test_assembly.id)

    def test_delete_targets_nonexistent_assembly(self, admin_user: User, postgres_session_factory):
        """Test that deleting targets for a nonexistent assembly raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(AssemblyNotFoundError):
            assembly_service.delete_targets_for_assembly(uow, admin_user.id, uuid.uuid4())

    def test_delete_targets_nonexistent_user(self, test_assembly: Assembly, postgres_session_factory):
        """Test that deleting targets with a nonexistent user raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(UserNotFoundError):
            assembly_service.delete_targets_for_assembly(uow, uuid.uuid4(), test_assembly.id)

    def test_delete_targets_does_not_affect_other_assembly(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting targets for one assembly doesn't affect another."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.create_target_category(uow, admin_user.id, test_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.create_target_category(uow2, admin_user.id, other_assembly.id, "Age")

        # Delete only from test_assembly
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.delete_targets_for_assembly(uow3, admin_user.id, test_assembly.id)

        # other_assembly targets should still exist
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        other_cats = assembly_service.get_targets_for_assembly(uow4, admin_user.id, other_assembly.id)
        assert len(other_cats) == 1
        assert other_cats[0].name == "Age"


class TestDeleteRespondentsForAssembly:
    def test_delete_all_respondents(self, admin_user: User, test_assembly: Assembly, postgres_session_factory):
        """Test deleting all respondents for an assembly."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        respondent_service.create_respondent(
            uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={"Gender": "Male"}
        )
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        respondent_service.create_respondent(
            uow2, admin_user.id, test_assembly.id, external_id="NB002", attributes={"Gender": "Female"}
        )

        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
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
        count = assembly_service.delete_respondents_for_assembly(uow, admin_user.id, test_assembly.id)
        assert count == 0

    def test_delete_respondents_insufficient_permissions(
        self, regular_user: User, test_assembly: Assembly, postgres_session_factory
    ):
        """Test that a regular user cannot delete respondents."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(InsufficientPermissions):
            assembly_service.delete_respondents_for_assembly(uow, regular_user.id, test_assembly.id)

    def test_delete_respondents_nonexistent_assembly(self, admin_user: User, postgres_session_factory):
        """Test that deleting respondents for a nonexistent assembly raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(AssemblyNotFoundError):
            assembly_service.delete_respondents_for_assembly(uow, admin_user.id, uuid.uuid4())

    def test_delete_respondents_nonexistent_user(self, test_assembly: Assembly, postgres_session_factory):
        """Test that deleting respondents with a nonexistent user raises error."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        with pytest.raises(UserNotFoundError):
            assembly_service.delete_respondents_for_assembly(uow, uuid.uuid4(), test_assembly.id)

    def test_delete_respondents_does_not_affect_other_assembly(
        self, admin_user: User, test_assembly: Assembly, other_assembly: Assembly, postgres_session_factory
    ):
        """Test that deleting respondents for one assembly doesn't affect another."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        respondent_service.create_respondent(
            uow, admin_user.id, test_assembly.id, external_id="NB001", attributes={"Gender": "Male"}
        )
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        respondent_service.create_respondent(
            uow2, admin_user.id, other_assembly.id, external_id="NB002", attributes={"Gender": "Female"}
        )

        # Delete only from test_assembly
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        assembly_service.delete_respondents_for_assembly(uow3, admin_user.id, test_assembly.id)

        # other_assembly respondents should still exist
        uow4 = SqlAlchemyUnitOfWork(postgres_session_factory)
        with uow4:
            other_resps = uow4.respondents.get_by_assembly_id(other_assembly.id)
            assert len(other_resps) == 1
            assert other_resps[0].external_id == "NB002"
