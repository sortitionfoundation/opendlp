"""ABOUTME: Integration tests for detailed target checking with real database
ABOUTME: Tests check_targets_detailed service function against PostgreSQL"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole, RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.target_checking import check_targets_detailed
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    return SqlAlchemyUnitOfWork(postgres_session_factory)


@pytest.fixture
def admin_user(uow):
    user = User(email="admin-check@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    with uow:
        uow.users.add(user)
        detached = user.create_detached_copy()
        uow.commit()
        return detached


@pytest.fixture
def assembly_with_csv(uow):
    assembly = Assembly(title="Check Test Assembly", number_to_select=10)
    with uow:
        uow.assemblies.add(assembly)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        detached = assembly.create_detached_copy()
        uow.commit()
        return detached


class TestCheckTargetsDetailedIntegration:
    def test_success_with_valid_data(self, uow, admin_user, assembly_with_csv):
        assembly_id = assembly_with_csv.id

        with uow:
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=assembly_id,
                    name="gender",
                    values=[
                        TargetValue(value="male", min=3, max=7),
                        TargetValue(value="female", min=3, max=7),
                    ],
                )
            )
            for i in range(20):
                uow.respondents.add(
                    Respondent(
                        assembly_id=assembly_id,
                        external_id=f"p{i}",
                        attributes={"gender": "male" if i % 2 == 0 else "female"},
                        selection_status=RespondentStatus.POOL,
                    )
                )
            uow.commit()

        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2:
            result = check_targets_detailed(uow2, admin_user.id, assembly_id)

        assert result.success is True
        assert result.num_features == 1
        assert result.num_people == 20

    def test_insufficient_respondents_annotated(self, uow, admin_user, assembly_with_csv):
        assembly_id = assembly_with_csv.id

        with uow:
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=assembly_id,
                    name="gender",
                    values=[
                        TargetValue(value="male", min=5, max=7),
                        TargetValue(value="female", min=5, max=7),
                    ],
                )
            )
            # Only 1 female, but min is 5
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly_id,
                    external_id="p0",
                    attributes={"gender": "female"},
                    selection_status=RespondentStatus.POOL,
                )
            )
            for i in range(1, 20):
                uow.respondents.add(
                    Respondent(
                        assembly_id=assembly_id,
                        external_id=f"p{i}",
                        attributes={"gender": "male"},
                        selection_status=RespondentStatus.POOL,
                    )
                )
            uow.commit()

        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2:
            result = check_targets_detailed(uow2, admin_user.id, assembly_id)

        assert result.success is False
        assert "gender" in result.annotations
        assert "female" in result.annotations["gender"]
        assert any(ann.level == "error" and ann.field == "min" for ann in result.annotations["gender"]["female"])

    def test_no_respondents_gives_global_error(self, uow, admin_user, assembly_with_csv):
        assembly_id = assembly_with_csv.id

        with uow:
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=assembly_id,
                    name="gender",
                    values=[TargetValue(value="male", min=3, max=7)],
                )
            )
            uow.commit()

        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2:
            result = check_targets_detailed(uow2, admin_user.id, assembly_id)

        assert result.success is False
        assert len(result.global_errors) > 0

    def test_cross_feature_error_annotated(self, uow, admin_user, assembly_with_csv):
        assembly_id = assembly_with_csv.id

        with uow:
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=assembly_id,
                    name="gender",
                    values=[
                        TargetValue(value="male", min=8, max=10),
                        TargetValue(value="female", min=8, max=10),
                    ],
                )
            )
            # sum of mins = 16 > number_to_select = 10
            for i in range(30):
                uow.respondents.add(
                    Respondent(
                        assembly_id=assembly_id,
                        external_id=f"p{i}",
                        attributes={"gender": "male" if i % 2 == 0 else "female"},
                        selection_status=RespondentStatus.POOL,
                    )
                )
            uow.commit()

        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2:
            result = check_targets_detailed(uow2, admin_user.id, assembly_id)

        assert result.success is False
        assert "gender" in result.category_annotations

    def test_assembly_not_found_raises(self, uow, admin_user):
        uow2 = SqlAlchemyUnitOfWork(uow.session_factory)
        with uow2, pytest.raises(AssemblyNotFoundError):
            check_targets_detailed(uow2, admin_user.id, uuid.uuid4())
