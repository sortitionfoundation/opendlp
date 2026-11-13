"""ABOUTME: Unit tests for working out and recording a project's data source.
ABOUTME: Covers determine_data_source with a stored choice, and the set_data_sources service."""

import pytest

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, DataSource, GlobalRole, RespondentsSource, TargetsSource
from opendlp.service_layer import assembly_service
from opendlp.service_layer.assembly_service import CSVUploadStatus, determine_data_source, get_tab_enabled_states
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InsufficientPermissions, UserNotFoundError
from tests.data import VALID_GSHEET_URL


def _status(targets: int = 0, respondents: int = 0) -> CSVUploadStatus:
    return CSVUploadStatus(targets_count=targets, respondents_count=respondents, csv_config=None)


def _gsheet(assembly: Assembly) -> AssemblyGSheet:
    return AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)


class TestDetermineDataSource:
    def test_a_sheet_decides_and_locks(self):
        """The data wins over anything that was said."""
        assembly = Assembly(title="Sheet")

        result = determine_data_source(_gsheet(assembly), _status(), stored=DataSource.OPENDLP)

        assert result == ("gsheet", True)

    @pytest.mark.parametrize("status", [_status(targets=1), _status(respondents=1)])
    def test_a_target_or_a_respondent_decides_and_locks(self, status):
        """The first target locks the location, long before anyone registers."""
        assert determine_data_source(None, status, stored=DataSource.GSHEET) == ("csv", True)

    def test_no_data_and_no_choice_is_held_in_opendlp_unlocked(self):
        """In OpenDLP is the default a new project gets."""
        assert determine_data_source(None, _status()) == ("csv", False)

    def test_no_data_follows_the_stored_choice_unlocked(self):
        """Saving a choice locks nothing: the organiser can still change their mind."""
        assert determine_data_source(None, _status(), stored=DataSource.GSHEET) == ("gsheet", False)
        assert determine_data_source(None, _status(), stored=DataSource.OPENDLP) == ("csv", False)

    def test_an_undecided_project_has_its_targets_tab_open(self):
        source, _locked = determine_data_source(None, _status())

        assert get_tab_enabled_states(source, None, _status()) == (True, False, False)


class TestSetDataSources:
    @pytest.fixture
    def manager(self, uow):
        user = User(email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)
        return user

    @pytest.fixture
    def assembly(self, uow, manager):
        assembly = Assembly(title="Sources")
        uow.assemblies.add(assembly)
        manager.assembly_roles.append(
            UserAssemblyRole(user_id=manager.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        )
        return assembly

    def test_a_manager_records_the_choices(self, uow, manager, assembly):
        updated = assembly_service.set_data_sources(
            uow,
            manager.id,
            assembly.id,
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.CSV,
            respondents_source=RespondentsSource.REGISTRATION,
        )

        assert updated.data_source == DataSource.OPENDLP
        assert updated.targets_source == TargetsSource.CSV
        assert updated.respondents_source == RespondentsSource.REGISTRATION

    def test_one_choice_can_be_recorded_alone(self, uow, manager, assembly):
        """An upload records "Import from CSV" for its own kind and nothing else."""
        assembly_service.set_data_sources(uow, manager.id, assembly.id, targets_source=TargetsSource.MANUAL)

        updated = assembly_service.set_data_sources(
            uow, manager.id, assembly.id, respondents_source=RespondentsSource.CSV
        )

        assert updated.targets_source == TargetsSource.MANUAL
        assert updated.respondents_source == RespondentsSource.CSV

    def test_someone_without_a_role_is_refused(self, uow, assembly):
        outsider = User(email="outsider@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(outsider)

        with pytest.raises(InsufficientPermissions):
            assembly_service.set_data_sources(uow, outsider.id, assembly.id, data_source=DataSource.GSHEET)

    def test_a_read_only_member_is_refused(self, uow, assembly):
        reader = User(email="reader@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(reader)
        reader.assembly_roles.append(
            UserAssemblyRole(user_id=reader.id, assembly_id=assembly.id, role=AssemblyRole.READ_ONLY)
        )

        with pytest.raises(InsufficientPermissions):
            assembly_service.set_data_sources(uow, reader.id, assembly.id, data_source=DataSource.GSHEET)

    def test_unknown_user_and_assembly_are_reported(self, uow, manager, assembly):
        with pytest.raises(UserNotFoundError):
            assembly_service.set_data_sources(uow, assembly.id, assembly.id)
        with pytest.raises(AssemblyNotFoundError):
            assembly_service.set_data_sources(uow, manager.id, manager.id)


class TestCreateAssemblyWithSources:
    def test_the_choices_are_stored_at_creation(self, uow):
        organiser = User(email="organiser@example.com", global_role=GlobalRole.ORGANISER, password_hash="hash")
        uow.users.add(organiser)

        assembly = assembly_service.create_assembly(
            uow,
            title="Made with choices",
            created_by_user_id=organiser.id,
            data_source=DataSource.OPENDLP,
            targets_source=TargetsSource.MANUAL,
            respondents_source=RespondentsSource.CSV,
        )

        assert assembly.data_source == DataSource.OPENDLP
        assert assembly.targets_source == TargetsSource.MANUAL
        assert assembly.respondents_source == RespondentsSource.CSV
