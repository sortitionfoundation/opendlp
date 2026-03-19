"""ABOUTME: Integration tests for OpenDLPDataAdapter
ABOUTME: Tests the data adapter that bridges OpenDLP database with sortition-algorithms library"""

import pytest
from sortition_algorithms import BadDataError
from sortition_algorithms.adapters import SelectionData
from sortition_algorithms.settings import Settings

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def test_assembly(postgres_session):
    """Create a test assembly with number_to_select set."""
    assembly = Assembly(title="Test Assembly", question="Test?", number_to_select=30)
    postgres_session.add(assembly)
    postgres_session.commit()
    return assembly


class TestOpenDLPDataAdapter:
    def test_read_feature_data(self, postgres_session_factory, test_assembly: Assembly):
        """Test loading target categories as feature data."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create target categories
        cat = TargetCategory(assembly_id=test_assembly.id, name="Gender", sort_order=0)
        cat.add_value(TargetValue(value="Male", min=10, max=15, min_flex=8, max_flex=18))
        cat.add_value(TargetValue(value="Female", min=10, max=15, min_flex=8, max_flex=18))

        with uow:
            uow.target_categories.add(cat)
            uow.commit()

        # Test adapter reading features
        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            features, _ = select_data.load_features(number_to_select=30)

            assert "Gender" in features
            assert "Male" in features["Gender"]
            assert "Female" in features["Gender"]
            assert features["Gender"]["Male"].min == 10
            assert features["Gender"]["Male"].max == 15
            assert features["Gender"]["Male"].min_flex == 8
            assert features["Gender"]["Male"].max_flex == 18

    def test_read_people_data(self, postgres_session_factory, test_assembly: Assembly):
        """Test loading respondents as people data."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create respondents
        resp1 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Male", "Age": "30-44"},
            eligible=True,
            can_attend=True,
        )
        resp2 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB002",
            attributes={"Gender": "Female", "Age": "16-29"},
            eligible=True,
            can_attend=True,
        )

        with uow:
            uow.respondents.add(resp1)
            uow.respondents.add(resp2)
            uow.commit()

        # Test adapter reading people
        with uow:
            # Need features to load people
            cat = TargetCategory(assembly_id=test_assembly.id, name="Gender")
            cat.add_value(TargetValue(value="Male", min=1, max=1))
            cat.add_value(TargetValue(value="Female", min=1, max=1))
            uow.target_categories.add(cat)
            uow.commit()

        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            settings = Settings(id_column="external_id", columns_to_keep=[])
            features, _ = select_data.load_features(number_to_select=2)
            people, _ = select_data.load_people(settings, features)

            assert people.count == 2
            assert set(people) == {"NB001", "NB002"}

    def test_only_eligible_respondents_loaded(self, subtests, postgres_session_factory, test_assembly: Assembly):
        """Test that only eligible respondents are loaded for selection."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create respondents with different eligibility
        resp1 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Male"},
            eligible=True,
            can_attend=True,
            selection_status=RespondentStatus.POOL,
        )
        resp2 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB002",
            attributes={"Gender": "Female"},
            eligible=False,  # Not eligible
            can_attend=True,
            selection_status=RespondentStatus.POOL,
        )
        resp3 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB003",
            attributes={"Gender": "Male"},
            eligible=True,
            can_attend=False,  # Can't attend
            selection_status=RespondentStatus.POOL,
        )
        resp4 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB004",
            attributes={"Gender": "Female"},
            eligible=True,
            can_attend=True,  # Can't attend
            selection_status=RespondentStatus.SELECTED,  # Already selected
        )

        with uow:
            uow.respondents.add(resp1)
            uow.respondents.add(resp2)
            uow.respondents.add(resp3)
            uow.respondents.add(resp4)
            uow.commit()

        # Add features
        with uow:
            cat = TargetCategory(assembly_id=test_assembly.id, name="Gender")
            cat.add_value(TargetValue(value="Male", min=0, max=1))
            cat.add_value(TargetValue(value="Female", min=0, max=1))
            uow.target_categories.add(cat)
            uow.commit()

        settings = Settings(id_column="external_id", columns_to_keep=[])
        with subtests.test("Default - eligible_only is True"), uow:
            # Test adapter - should only load NB001
            adapter = OpenDLPDataAdapter(uow, test_assembly.id, eligible_only=True)
            select_data = SelectionData(adapter)

            features, _ = select_data.load_features(number_to_select=1)
            people, _ = select_data.load_people(settings, features)

            assert people.count == 1
            assert set(people) == {"NB001"}

        with subtests.test("All people - eligible_only is False"), uow:
            # Test adapter with eligible_only=False - should load all 4
            adapter = OpenDLPDataAdapter(uow, test_assembly.id, eligible_only=False)
            select_data = SelectionData(adapter)

            features, _ = select_data.load_features(number_to_select=1)
            people, _ = select_data.load_people(settings, features)

            assert people.count == 4
            assert set(people) == {"NB001", "NB002", "NB003", "NB004"}

    def test_empty_data_sources(self, postgres_session_factory, test_assembly: Assembly):
        """Test adapter behavior with no features or people."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            # Load empty features
            features, _ = select_data.load_features(number_to_select=30)
            assert len(features) == 0

        # Add features but no people
        with uow:
            cat = TargetCategory(assembly_id=test_assembly.id, name="Gender")
            cat.add_value(TargetValue(value="Male", min=1, max=1))
            uow.target_categories.add(cat)
            uow.commit()

        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            settings = Settings(id_column="external_id", columns_to_keep=[])
            features, _ = select_data.load_features(number_to_select=1)
            with pytest.raises(BadDataError):
                select_data.load_people(settings, features)

    def test_no_eligible_respondents_gives_clear_error(self, postgres_session_factory, test_assembly: Assembly):
        """Test that when respondents exist but none are eligible, the error message is clear."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create respondents that are explicitly NOT eligible
        resp1 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Male"},
            eligible=False,
            can_attend=True,
        )
        resp2 = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB002",
            attributes={"Gender": "Female"},
            eligible=True,
            can_attend=False,
        )

        with uow:
            uow.respondents.add(resp1)
            uow.respondents.add(resp2)
            uow.commit()

        # Add features
        with uow:
            cat = TargetCategory(assembly_id=test_assembly.id, name="Gender")
            cat.add_value(TargetValue(value="Male", min=0, max=1))
            cat.add_value(TargetValue(value="Female", min=0, max=1))
            uow.target_categories.add(cat)
            uow.commit()

        # When we try to load people, we should get a clear error about no eligible respondents
        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            settings = Settings(id_column="external_id", columns_to_keep=[])
            features, _ = select_data.load_features(number_to_select=1)
            with pytest.raises(BadDataError, match="No eligible respondents"):
                select_data.load_people(settings, features)

    def test_respondents_with_none_eligibility_are_included(self, postgres_session_factory, test_assembly: Assembly):
        """Test that respondents with eligible=None and can_attend=None are included in selection.

        These are three-way states: True means yes, False means no, None means not yet set.
        Only respondents explicitly marked as False should be excluded.
        """
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create respondents with various eligibility states
        resp_none = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB001",
            attributes={"Gender": "Male"},
            eligible=None,
            can_attend=None,
        )
        resp_true = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB002",
            attributes={"Gender": "Female"},
            eligible=True,
            can_attend=True,
        )
        resp_false_eligible = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB003",
            attributes={"Gender": "Male"},
            eligible=False,
            can_attend=True,
        )
        resp_false_attend = Respondent(
            assembly_id=test_assembly.id,
            external_id="NB004",
            attributes={"Gender": "Female"},
            eligible=True,
            can_attend=False,
        )

        with uow:
            uow.respondents.add(resp_none)
            uow.respondents.add(resp_true)
            uow.respondents.add(resp_false_eligible)
            uow.respondents.add(resp_false_attend)
            uow.commit()

        # Add features
        with uow:
            cat = TargetCategory(assembly_id=test_assembly.id, name="Gender")
            cat.add_value(TargetValue(value="Male", min=0, max=1))
            cat.add_value(TargetValue(value="Female", min=0, max=1))
            uow.target_categories.add(cat)
            uow.commit()

        # NB001 (None/None) and NB002 (True/True) should be included
        # NB003 (False/True) and NB004 (True/False) should be excluded
        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            settings = Settings(id_column="external_id", columns_to_keep=[])
            features, _ = select_data.load_features(number_to_select=2)
            people, _ = select_data.load_people(settings, features)

            assert people.count == 2
            assert set(people) == {"NB001", "NB002"}

    def test_multiple_features(self, postgres_session_factory, test_assembly: Assembly):
        """Test loading multiple target categories as features."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        # Create multiple target categories
        cat1 = TargetCategory(assembly_id=test_assembly.id, name="Gender", sort_order=0)
        cat1.add_value(TargetValue(value="Male", min=10, max=15))
        cat1.add_value(TargetValue(value="Female", min=10, max=15))

        cat2 = TargetCategory(assembly_id=test_assembly.id, name="Age", sort_order=1)
        cat2.add_value(TargetValue(value="16-29", min=5, max=10))
        cat2.add_value(TargetValue(value="30-44", min=5, max=10))
        cat2.add_value(TargetValue(value="45-64", min=5, max=10))

        with uow:
            uow.target_categories.add(cat1)
            uow.target_categories.add(cat2)
            uow.commit()

        # Test adapter
        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)
            select_data = SelectionData(adapter)

            features, _ = select_data.load_features(number_to_select=30)

            assert len(features) == 2
            assert "Gender" in features
            assert "Age" in features
            assert len(features["Gender"]) == 2
            assert len(features["Age"]) == 3

    def test_adapter_properties(self, postgres_session_factory, test_assembly: Assembly):
        """Test adapter property methods."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)

        with uow:
            adapter = OpenDLPDataAdapter(uow, test_assembly.id)

            assert adapter.people_data_container == "OpenDLP respondents database"
            assert adapter.already_selected_data_container == "OpenDLP already selected respondents"
