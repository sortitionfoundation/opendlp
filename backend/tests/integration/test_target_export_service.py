"""ABOUTME: Integration tests for exporting targets, against a real database
ABOUTME: An export uploads back as the same targets; manage permission; the saved Google Sheet config"""

import pytest

from opendlp.adapters.tabular_export import CsvExportTarget, ExportTargetError
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole, GSheetExportKind
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_export_service import (
    export_targets,
    export_targets_to_gsheet,
    get_targets_gsheet_config,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import grant_user_assembly_role
from tests.fakes import FakeGSheetExportTarget

SHEET_URL = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"


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


@pytest.fixture
def caller(uow):
    """A user who can see the assembly once given a role on it, but not manage it."""
    user = User(email="targets-export-caller@test.com", global_role=GlobalRole.USER, password_hash="hash123")
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

    def test_an_assembly_with_no_targets_exports_headers_only(self, uow, admin_user, assembly):
        target = CsvExportTarget()

        export_targets(uow, admin_user.id, assembly.id, target=target)

        assert len([line for line in target.getvalue().splitlines() if line]) == 1

    @pytest.mark.usefixtures("targets")
    def test_a_user_who_can_only_view_may_not_export(self, uow, caller, assembly, admin_user):
        """Export is a manage action, matching the respondent and dashboard exports."""
        grant_user_assembly_role(uow, caller.id, assembly.id, AssemblyRole.CONFIRMATION_CALLER, admin_user)

        with pytest.raises(InsufficientPermissions):
            export_targets(uow, caller.id, assembly.id, target=CsvExportTarget())


class TestExportingToGoogleSheets:
    @pytest.mark.usefixtures("targets")
    def test_writes_the_sheet_and_saves_the_config(self, uow, admin_user, assembly):
        target = FakeGSheetExportTarget()

        export_targets_to_gsheet(
            uow, admin_user.id, assembly.id, spreadsheet_url=SHEET_URL, worksheet_name="Quotas", target=target
        )

        ((title, table),) = target.writes
        assert title == "Quotas"
        assert table.headers[0] == "feature"
        saved = get_targets_gsheet_config(uow, admin_user.id, assembly.id)
        assert saved is not None
        assert saved.export_kind == GSheetExportKind.TARGETS
        assert saved.url == SHEET_URL
        assert saved.worksheet_name == "Quotas"

    @pytest.mark.usefixtures("targets")
    def test_a_blank_worksheet_name_writes_to_targets(self, uow, admin_user, assembly):
        target = FakeGSheetExportTarget()

        export_targets_to_gsheet(
            uow, admin_user.id, assembly.id, spreadsheet_url=SHEET_URL, worksheet_name="  ", target=target
        )

        assert [title for title, _table in target.writes] == ["Targets"]

    @pytest.mark.usefixtures("targets")
    def test_keeps_its_own_sheet_apart_from_the_other_exports(self, uow, admin_user, assembly):
        export_targets_to_gsheet(
            uow,
            admin_user.id,
            assembly.id,
            spreadsheet_url=SHEET_URL,
            worksheet_name="",
            target=FakeGSheetExportTarget(),
        )

        for kind in (GSheetExportKind.RESPONDENTS, GSheetExportKind.DASHBOARD):
            assert uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly.id, kind) is None

    @pytest.mark.usefixtures("targets")
    def test_a_rejected_url_writes_nothing(self, uow, admin_user, assembly):
        target = FakeGSheetExportTarget()

        with pytest.raises(ValueError):
            export_targets_to_gsheet(
                uow,
                admin_user.id,
                assembly.id,
                spreadsheet_url="https://example.com/not-a-sheet",
                worksheet_name="",
                target=target,
            )

        assert target.writes == []

    @pytest.mark.usefixtures("targets")
    def test_a_failed_write_saves_no_config(self, uow, admin_user, assembly):
        target = FakeGSheetExportTarget(error=ExportTargetError("no access"))

        with pytest.raises(ExportTargetError):
            export_targets_to_gsheet(
                uow, admin_user.id, assembly.id, spreadsheet_url=SHEET_URL, worksheet_name="", target=target
            )

        assert get_targets_gsheet_config(uow, admin_user.id, assembly.id) is None
