"""ABOUTME: Integration tests for exporting targets, against a real database
ABOUTME: An export uploads back through the CSV import as the same targets"""

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_export_service import export_targets
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def uow(postgres_session_factory):
    """An already-entered UnitOfWork; the whole test is one transaction."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as entered:
        yield entered


@pytest.fixture
def admin_user(uow):
    user = User(email="targets-export-admin@test.com", global_role=GlobalRole.ADMIN, password_hash="hash123")
    uow.users.add(user)
    detached = user.create_detached_copy()
    uow.commit()
    return detached


def _assembly(uow, title):
    assembly = Assembly(title=title, question="Should we?", number_to_select=20)
    uow.assemblies.add(assembly)
    detached = assembly.create_detached_copy()
    uow.commit()
    return detached


@pytest.fixture
def assembly(uow):
    return _assembly(uow, "Targets Export Assembly")


@pytest.fixture
def targets(uow, assembly):
    uow.target_categories.add(
        TargetCategory(
            assembly_id=assembly.id,
            name="Gender",
            sort_order=10,
            comment="from the 2021 census\nrounded to whole seats",
            source_url="https://example.com/census",
            values=[
                TargetValue(value="Woman", min=9, max=11, percentage_target=51.5, comment="boosted, see notes"),
                TargetValue(value="Man", min=8, max=10, percentage_target=48.5),
            ],
        )
    )
    uow.target_categories.add(
        TargetCategory(
            assembly_id=assembly.id,
            name="Age",
            sort_order=20,
            # With percentages: the import works out one for a value that has none.
            values=[
                TargetValue(value="16-29", min=2, max=6, percentage_target=20.0),
                TargetValue(value="30+", min=14, max=18, percentage_target=80.0),
            ],
        )
    )
    uow.commit()


def _summary(categories):
    """What an export has to carry across, category by category in order."""
    return [
        (
            category.name,
            category.comment,
            category.source_url,
            [(v.value, v.min, v.max, v.percentage_target, v.comment) for v in category.values],
        )
        for category in categories
    ]


class TestExportingToCsv:
    @pytest.mark.usefixtures("targets")
    def test_an_export_uploads_back_as_the_same_targets(self, uow, admin_user, assembly):
        target = CsvExportTarget()
        export_targets(uow, admin_user.id, assembly.id, target=target)
        copy = _assembly(uow, "Targets Copy")

        # Read back as the upload route reads a file, which drops the byte-order mark.
        uploaded_file = target.getvalue().encode("utf-8").decode("utf-8-sig")
        import_targets_from_csv(uow, admin_user.id, copy.id, uploaded_file)

        original = uow.target_categories.get_by_assembly_id(assembly.id)
        uploaded = uow.target_categories.get_by_assembly_id(copy.id)
        assert _summary(uploaded) == _summary(original)
