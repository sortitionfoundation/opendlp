"""ABOUTME: Integration tests for assembly service target category functions
ABOUTME: Tests target category creation, import, and retrieval service functions"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import assembly_service
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions, InvalidSelection
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
        fc, report = assembly_service.get_feature_collection_for_assembly(uow, admin_user.id, test_assembly.id)

        assert len(fc) == 0
