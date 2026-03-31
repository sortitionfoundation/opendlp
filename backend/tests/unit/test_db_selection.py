"""ABOUTME: Unit tests for database selection service layer and form
ABOUTME: Tests check_db_selection_data service function, form validation, and parse helper"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from sortition_algorithms import RunReport
from sortition_algorithms.errors import SortitionBaseError

from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.blueprints.db_selection import _parse_comma_list
from opendlp.entrypoints.flask_app import create_app
from opendlp.entrypoints.forms import DbSelectionSettingsForm
from opendlp.service_layer.exceptions import AssemblyNotFoundError
from opendlp.service_layer.sortition import CheckDataResult, check_db_selection_data
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def app() -> Flask:
    return create_app("testing")


class TestCheckDbSelectionData:
    """Tests for the check_db_selection_data service function."""

    def _setup_uow(self) -> tuple[FakeUnitOfWork, User, Assembly]:
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)
        assembly = Assembly(title="Test Assembly", number_to_select=5)
        assembly.csv = AssemblyCSV(assembly_id=assembly.id)
        assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
        uow.assemblies.add(assembly)
        return uow, admin_user, assembly

    @patch("opendlp.service_layer.sortition.OpenDLPDataAdapter")
    @patch("opendlp.service_layer.sortition.adapters.SelectionData")
    def test_success_when_data_valid(self, mock_selection_data_cls, mock_adapter_cls):
        uow, admin_user, assembly = self._setup_uow()

        mock_features = MagicMock()
        mock_features.__len__ = MagicMock(return_value=3)
        mock_people = MagicMock()
        mock_people.count = 100

        mock_select_data = MagicMock()
        mock_select_data.load_features.return_value = (mock_features, RunReport())
        mock_select_data.load_people.return_value = (mock_people, RunReport())
        mock_selection_data_cls.return_value = mock_select_data

        result = check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=assembly.id)

        assert isinstance(result, CheckDataResult)
        assert result.success is True
        assert result.errors == []
        assert result.num_features == 3
        assert result.num_people == 100

    @patch("opendlp.service_layer.sortition.OpenDLPDataAdapter")
    @patch("opendlp.service_layer.sortition.adapters.SelectionData")
    def test_returns_error_when_features_fail(self, mock_selection_data_cls, mock_adapter_cls):
        uow, admin_user, assembly = self._setup_uow()

        mock_select_data = MagicMock()
        mock_select_data.load_features.side_effect = SortitionBaseError("Bad features")
        mock_selection_data_cls.return_value = mock_select_data

        result = check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=assembly.id)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.num_features == 0
        assert result.num_people == 0

    @patch("opendlp.service_layer.sortition.OpenDLPDataAdapter")
    @patch("opendlp.service_layer.sortition.adapters.SelectionData")
    def test_returns_error_when_people_fail(self, mock_selection_data_cls, mock_adapter_cls):
        uow, admin_user, assembly = self._setup_uow()

        mock_features = MagicMock()
        mock_features.__len__ = MagicMock(return_value=3)
        mock_people_error = SortitionBaseError("Respondent mismatch")

        mock_select_data = MagicMock()
        mock_select_data.load_features.return_value = (mock_features, RunReport())
        mock_select_data.load_people.side_effect = mock_people_error
        mock_selection_data_cls.return_value = mock_select_data

        result = check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=assembly.id)

        assert result.success is False
        assert len(result.errors) == 1
        assert result.num_features == 3
        assert result.num_people == 0

    @patch("opendlp.service_layer.sortition.OpenDLPDataAdapter")
    @patch("opendlp.service_layer.sortition.adapters.SelectionData")
    def test_skips_people_when_features_fail(self, mock_selection_data_cls, mock_adapter_cls):
        uow, admin_user, assembly = self._setup_uow()

        mock_select_data = MagicMock()
        mock_select_data.load_features.side_effect = SortitionBaseError("Bad features")
        mock_selection_data_cls.return_value = mock_select_data

        check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=assembly.id)

        mock_select_data.load_people.assert_not_called()

    def test_assembly_not_found_raises(self):
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        with pytest.raises(AssemblyNotFoundError):
            check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=uuid.uuid4())

    def test_returns_error_when_settings_invalid(self):
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)
        assembly = Assembly(title="Test Assembly", number_to_select=5)
        # No selection_settings set, so _get_selection_settings falls back to defaults:
        # check_same_address=True but empty check_same_address_cols, which causes
        # a ConfigurationError from to_settings()
        uow.assemblies.add(assembly)

        result = check_db_selection_data(uow=uow, user_id=admin_user.id, assembly_id=assembly.id)

        assert isinstance(result, CheckDataResult)
        assert result.success is False
        assert len(result.errors) == 1
        assert result.num_features == 0
        assert result.num_people == 0


class TestParseCommaList:
    """Tests for the _parse_comma_list helper."""

    def test_empty_string(self):
        assert _parse_comma_list("") == []

    def test_logically_empty_string(self):
        assert _parse_comma_list(" , ,") == []

    def test_none(self):
        assert _parse_comma_list(None) == []

    def test_single_item(self):
        assert _parse_comma_list("age") == ["age"]

    def test_multiple_items(self):
        assert _parse_comma_list("age, gender, postcode") == ["age", "gender", "postcode"]

    def test_strips_whitespace(self):
        assert _parse_comma_list("  age ,  gender  , postcode ") == ["age", "gender", "postcode"]

    def test_ignores_empty_entries(self):
        assert _parse_comma_list("age,,gender,") == ["age", "gender"]

    def test_trailing_comma(self):
        assert _parse_comma_list("age, gender,") == ["age", "gender"]


class TestDbSelectionSettingsForm:
    """Tests for DbSelectionSettingsForm validation."""

    def test_form_validates_with_valid_data(self, app):
        with app.test_request_context():
            form = DbSelectionSettingsForm(
                data={
                    "check_same_address": True,
                    "check_same_address_cols_string": "address1, postcode",
                    "columns_to_keep_string": "first_name, last_name",
                },
                meta={"csrf": False},
            )
            assert form.validate()

    def test_form_validates_with_empty_optional_fields(self, app):
        with app.test_request_context():
            form = DbSelectionSettingsForm(
                data={
                    "check_same_address": False,
                    "check_same_address_cols_string": "",
                    "columns_to_keep_string": "",
                },
                meta={"csrf": False},
            )
            assert form.validate()
