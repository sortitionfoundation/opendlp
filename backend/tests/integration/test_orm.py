"""ABOUTME: Integration tests for ORM mapping and database operations
ABOUTME: Tests that domain objects can be saved, retrieved, and relationships work correctly"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opendlp.adapters import orm
from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from tests.data import VALID_GSHEET_URL


class TestUserORM:
    def test_save_and_retrieve_user(self, postgres_session: Session):
        """Test that User objects can be saved and retrieved."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",
            first_name="Test",
            last_name="User",
        )

        # Save user
        postgres_session.add(user)
        postgres_session.commit()

        # Retrieve user
        retrieved_user = postgres_session.query(User).filter_by(email="test@example.com").first()

        assert retrieved_user is not None
        assert retrieved_user.email == "test@example.com"
        assert retrieved_user.first_name == "Test"
        assert retrieved_user.last_name == "User"
        assert retrieved_user.global_role == GlobalRole.USER
        assert retrieved_user.password_hash == "hashed_password"
        assert retrieved_user.is_active is True
        assert isinstance(retrieved_user.id, uuid.UUID)
        assert isinstance(retrieved_user.created_at, datetime)
        assert retrieved_user.created_at.tzinfo is not None

    def test_user_oauth_fields(self, postgres_session: Session):
        """Test that OAuth fields are properly stored and retrieved."""
        user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
            first_name="OAuth",
            last_name="User",
        )

        postgres_session.add(user)
        postgres_session.commit()

        retrieved_user = postgres_session.query(User).filter_by(email="oauth@example.com").first()

        assert retrieved_user.oauth_provider == "google"
        assert retrieved_user.oauth_id == "12345"
        assert retrieved_user.password_hash is None

    def test_user_unique_constraints(self, postgres_session: Session):
        """Test that email unique constraints work."""
        user1 = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash1")

        postgres_session.add(user1)
        postgres_session.commit()

        # Try to create user with same email
        user2 = User(
            email="test@example.com",  # Same email
            global_role=GlobalRole.USER,
            password_hash="hash2",
        )

        postgres_session.add(user2)

        with pytest.raises(IntegrityError):  # Should raise integrity error
            postgres_session.commit()


class TestAssemblyORM:
    def test_save_and_retrieve_assembly(self, postgres_session: Session):
        """Test that Assembly objects can be saved and retrieved."""
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        # Save assembly
        postgres_session.add(assembly)
        postgres_session.commit()

        # Retrieve assembly
        retrieved_assembly = postgres_session.query(Assembly).filter_by(title="Test Assembly").first()

        assert retrieved_assembly is not None
        assert retrieved_assembly.title == "Test Assembly"
        assert retrieved_assembly.question == "Test question?"
        assert retrieved_assembly.first_assembly_date == future_date
        assert retrieved_assembly.status == AssemblyStatus.ACTIVE
        assert isinstance(retrieved_assembly.id, uuid.UUID)
        assert isinstance(retrieved_assembly.created_at, datetime)
        assert isinstance(retrieved_assembly.updated_at, datetime)
        assert retrieved_assembly.created_at.tzinfo is not None
        assert retrieved_assembly.updated_at.tzinfo is not None

    def test_assembly_json_config(self, postgres_session: Session):
        """Test that JSON config field works properly."""
        future_date = date.today() + timedelta(days=30)

        # Create assembly with custom ID to set config
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()  # Flush to get ID but don't commit yet

        # Set JSON config directly on the mapped object
        postgres_session.execute(
            orm.assemblies.update()
            .where(orm.assemblies.c.id == assembly.id)
            .values(config={"sheet_tabs": ["main", "backup"], "columns": {"name": "A", "email": "B"}})
        )
        postgres_session.commit()

        # Retrieve and check JSON config
        result = postgres_session.execute(orm.assemblies.select().where(orm.assemblies.c.id == assembly.id)).first()

        assert result.config is not None
        assert result.config["sheet_tabs"] == ["main", "backup"]
        assert result.config["columns"]["name"] == "A"


class TestUserAssemblyRoleORM:
    def test_save_and_retrieve_user_assembly_role(self, postgres_session: Session):
        """Test that UserAssemblyRole objects can be saved and retrieved."""
        # Create user and assembly first
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(user)
        postgres_session.add(assembly)
        postgres_session.flush()  # Get IDs

        # Create role assignment
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)

        postgres_session.add(role)
        postgres_session.commit()

        # Retrieve role
        retrieved_role = (
            postgres_session.query(UserAssemblyRole).filter_by(user_id=user.id, assembly_id=assembly.id).first()
        )

        assert retrieved_role is not None
        assert retrieved_role.user_id == user.id
        assert retrieved_role.assembly_id == assembly.id
        assert retrieved_role.role == AssemblyRole.ASSEMBLY_MANAGER
        assert isinstance(retrieved_role.id, uuid.UUID)
        assert isinstance(retrieved_role.created_at, datetime)
        assert retrieved_role.created_at.tzinfo is not None

    def test_foreign_key_constraints(self, postgres_session: Session):
        """Test that foreign key constraints work properly."""
        # Try to create role without valid user/assembly
        invalid_role = UserAssemblyRole(
            user_id=uuid.uuid4(),  # Non-existent user
            assembly_id=uuid.uuid4(),  # Non-existent assembly
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )

        postgres_session.add(invalid_role)

        with pytest.raises(IntegrityError):  # Should raise foreign key constraint error
            postgres_session.commit()


class TestUserInviteORM:
    def test_save_and_retrieve_user_invite(self, postgres_session: Session):
        """Test that UserInvite objects can be saved and retrieved."""
        # Create user first
        user = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        postgres_session.add(user)
        postgres_session.flush()  # Get user ID

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, expires_in_hours=168)

        postgres_session.add(invite)
        postgres_session.commit()

        # Retrieve invite
        retrieved_invite = postgres_session.query(UserInvite).filter_by(created_by=user.id).first()

        assert retrieved_invite is not None
        assert retrieved_invite.global_role == GlobalRole.USER
        assert retrieved_invite.created_by == user.id
        assert isinstance(retrieved_invite.id, uuid.UUID)
        assert isinstance(retrieved_invite.code, str)
        assert len(retrieved_invite.code) == 12
        assert isinstance(retrieved_invite.created_at, datetime)
        assert isinstance(retrieved_invite.expires_at, datetime)
        assert retrieved_invite.created_at.tzinfo is not None
        assert retrieved_invite.expires_at.tzinfo is not None
        assert retrieved_invite.used_by is None
        assert retrieved_invite.used_at is None

    def test_invite_code_unique_constraint(self, postgres_session: Session):
        """Test that invite codes are unique."""
        user = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        postgres_session.add(user)
        postgres_session.flush()

        # Create first invite
        invite1 = UserInvite(global_role=GlobalRole.USER, created_by=user.id, code="TESTCODE123")

        postgres_session.add(invite1)
        postgres_session.commit()

        # Try to create second invite with same code
        invite2 = UserInvite(
            global_role=GlobalRole.USER,
            created_by=user.id,
            code="TESTCODE123",  # Same code
        )

        postgres_session.add(invite2)

        with pytest.raises(IntegrityError):  # Should raise unique constraint error
            postgres_session.commit()

    def test_invite_usage(self, postgres_session: Session):
        """Test that invite usage is properly tracked."""
        # Create creator and user
        creator = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        invitee = User(email="invitee@example.com", global_role=GlobalRole.USER, password_hash="hash")

        postgres_session.add(creator)
        postgres_session.add(invitee)
        postgres_session.flush()

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=creator.id)

        postgres_session.add(invite)
        postgres_session.flush()

        # Use invite (simulate using domain method)
        invite.use(invitee.id)
        postgres_session.commit()

        # Retrieve and verify
        retrieved_invite = postgres_session.query(UserInvite).filter_by(id=invite.id).first()

        assert retrieved_invite.used_by == invitee.id
        assert isinstance(retrieved_invite.used_at, datetime)


class TestRelationships:
    def test_cascade_delete_user_roles(self, postgres_session: Session):
        """Test that deleting a user cascades to their roles."""
        # Create user and assembly
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(user)
        postgres_session.add(assembly)
        postgres_session.flush()

        # Create role
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)

        postgres_session.add(role)
        postgres_session.commit()

        # Verify role exists
        assert postgres_session.query(UserAssemblyRole).filter_by(user_id=user.id).count() == 1

        # Delete user
        postgres_session.delete(user)
        postgres_session.commit()

        # Verify role was cascade deleted
        assert postgres_session.query(UserAssemblyRole).filter_by(user_id=user.id).count() == 0

    def test_cascade_delete_invites(self, postgres_session: Session):
        """Test that deleting a user cascades to invites they created."""
        # Create admin user
        admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        postgres_session.add(admin)
        postgres_session.flush()

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=admin.id)

        postgres_session.add(invite)
        postgres_session.commit()

        # Verify invite exists
        assert postgres_session.query(UserInvite).filter_by(created_by=admin.id).count() == 1

        # Delete admin
        postgres_session.delete(admin)
        postgres_session.commit()

        # Verify invite was cascade deleted
        assert postgres_session.query(UserInvite).filter_by(created_by=admin.id).count() == 0


class TestAssemblyGSheetORM:
    def test_save_and_retrieve_assembly_gsheet(self, postgres_session: Session):
        """Test that AssemblyGSheet objects can be saved and retrieved."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()  # Get assembly ID

        # Create AssemblyGSheet
        assembly_gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            select_registrants_tab="Registrants",
            select_targets_tab="Targets",
            replace_registrants_tab="Remaining",
            replace_targets_tab="Replacement Targets",
            generate_remaining_tab=True,
            id_column="custom_id",
            check_same_address=False,
            check_same_address_cols=["address1", "postcode"],
            columns_to_keep=["name", "email", "phone"],
            selection_algorithm="stratified",
        )

        postgres_session.add(assembly_gsheet)
        postgres_session.commit()

        # Retrieve AssemblyGSheet
        retrieved_gsheet = postgres_session.query(AssemblyGSheet).filter_by(assembly_id=assembly.id).first()

        assert retrieved_gsheet is not None
        assert retrieved_gsheet.assembly_id == assembly.id
        assert retrieved_gsheet.url == VALID_GSHEET_URL
        assert retrieved_gsheet.select_registrants_tab == "Registrants"
        assert retrieved_gsheet.select_targets_tab == "Targets"
        assert retrieved_gsheet.replace_registrants_tab == "Remaining"
        assert retrieved_gsheet.replace_targets_tab == "Replacement Targets"
        assert retrieved_gsheet.generate_remaining_tab is True
        assert retrieved_gsheet.id_column == "custom_id"
        assert retrieved_gsheet.check_same_address is False
        assert retrieved_gsheet.check_same_address_cols == ["address1", "postcode"]
        assert retrieved_gsheet.columns_to_keep == ["name", "email", "phone"]
        assert retrieved_gsheet.selection_algorithm == "stratified"
        assert isinstance(retrieved_gsheet.assembly_gsheet_id, uuid.UUID)

    def test_assembly_gsheet_defaults(self, postgres_session: Session):
        """Test that AssemblyGSheet default values work correctly."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create AssemblyGSheet with minimal data (defaults should apply)
        assembly_gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )

        postgres_session.add(assembly_gsheet)
        postgres_session.commit()

        # Retrieve and check defaults
        retrieved_gsheet = postgres_session.query(AssemblyGSheet).filter_by(assembly_id=assembly.id).first()

        assert retrieved_gsheet.select_registrants_tab == "Respondents"
        assert retrieved_gsheet.select_targets_tab == "Categories"
        assert retrieved_gsheet.replace_registrants_tab == "Remaining"
        assert retrieved_gsheet.replace_targets_tab == "Replacement Categories"
        assert retrieved_gsheet.generate_remaining_tab is True
        assert retrieved_gsheet.id_column == "nationbuilder_id"
        assert retrieved_gsheet.check_same_address is True
        assert retrieved_gsheet.check_same_address_cols == []
        assert retrieved_gsheet.columns_to_keep == []
        assert retrieved_gsheet.selection_algorithm == "maximin"

    def test_assembly_gsheet_for_team(self, postgres_session: Session):
        """Test that AssemblyGSheet.for_team() class method works correctly."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create AssemblyGSheet using for_team class method
        assembly_gsheet = AssemblyGSheet.for_team("uk", assembly.id, VALID_GSHEET_URL)

        postgres_session.add(assembly_gsheet)
        postgres_session.commit()

        # Retrieve and check UK-specific defaults
        retrieved_gsheet = postgres_session.query(AssemblyGSheet).filter_by(assembly_id=assembly.id).first()

        assert retrieved_gsheet.id_column == "nationbuilder_id"  # UK default
        assert retrieved_gsheet.check_same_address_cols == ["primary_address1", "zip_royal_mail"]  # UK default
        expected_uk_columns = [
            "first_name",
            "last_name",
            "mobile_number",
            "email",
            "primary_address1",
            "primary_address2",
            "primary_city",
            "zip_royal_mail",
            "tag_list",
            "age",
            "gender",
        ]
        assert retrieved_gsheet.columns_to_keep == expected_uk_columns

    def test_assembly_gsheet_foreign_key_constraint(self, postgres_session: Session):
        """Test that foreign key constraint works for assembly_id."""
        # Try to create AssemblyGSheet without valid assembly
        assembly_gsheet = AssemblyGSheet(
            assembly_id=uuid.uuid4(),  # Non-existent assembly
            url=VALID_GSHEET_URL,
        )

        postgres_session.add(assembly_gsheet)

        with pytest.raises(IntegrityError):  # Should raise foreign key constraint error
            postgres_session.commit()

    def test_cascade_delete_assembly_gsheet(self, postgres_session: Session):
        """Test that deleting an assembly cascades to its AssemblyGSheet."""
        # Create assembly
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create AssemblyGSheet
        assembly_gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
        )

        postgres_session.add(assembly_gsheet)
        postgres_session.commit()

        # Verify AssemblyGSheet exists
        assert postgres_session.query(AssemblyGSheet).filter_by(assembly_id=assembly.id).count() == 1

        # Delete assembly
        postgres_session.delete(assembly)
        postgres_session.commit()

        # Verify AssemblyGSheet was cascade deleted
        assert postgres_session.query(AssemblyGSheet).filter_by(assembly_id=assembly.id).count() == 0

    def test_assembly_gsheet_one_to_one_relationship(self, postgres_session: Session):
        """Test that SQLAlchemy one-to-one relationship works correctly between Assembly and AssemblyGSheet."""
        # Create assembly
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create single AssemblyGSheet for the assembly
        gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            select_registrants_tab="Registrants",
        )

        postgres_session.add(gsheet)
        postgres_session.commit()

        # Test Assembly -> AssemblyGSheet relationship (one-to-one)
        retrieved_assembly = postgres_session.query(Assembly).filter_by(id=assembly.id).first()
        assert retrieved_assembly is not None
        assert hasattr(retrieved_assembly, "gsheet")
        assert retrieved_assembly.gsheet is not None
        assert retrieved_assembly.gsheet.select_registrants_tab == "Registrants"

        # Test AssemblyGSheet -> Assembly relationship (one-to-one back reference)
        retrieved_gsheet = (
            postgres_session.query(AssemblyGSheet).filter_by(select_registrants_tab="Registrants").first()
        )
        assert retrieved_gsheet is not None
        assert hasattr(retrieved_gsheet, "assembly")
        assert retrieved_gsheet.assembly.id == assembly.id
        assert retrieved_gsheet.assembly.title == "Test Assembly"

    def test_assembly_gsheet_unique_constraint(self, postgres_session: Session):
        """Test that the unique constraint on assembly_id prevents multiple AssemblyGSheets for one Assembly."""
        # Create assembly
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create first AssemblyGSheet
        gsheet1 = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            select_registrants_tab="Registrants1",
        )

        postgres_session.add(gsheet1)
        postgres_session.commit()

        # Try to create second AssemblyGSheet for the same assembly
        gsheet2 = AssemblyGSheet(
            assembly_id=assembly.id,  # Same assembly_id
            url=VALID_GSHEET_URL,
            select_registrants_tab="Registrants2",
        )

        postgres_session.add(gsheet2)

        with pytest.raises(IntegrityError):  # Should raise unique constraint error
            postgres_session.commit()

    def test_assembly_without_gsheet(self, postgres_session: Session):
        """Test that an Assembly can exist without an AssemblyGSheet (optional one-to-one)."""
        # Create assembly without any AssemblyGSheet
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Assembly Without GSheet",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.commit()

        # Retrieve assembly and verify no gsheet is associated
        retrieved_assembly = postgres_session.query(Assembly).filter_by(id=assembly.id).first()
        assert retrieved_assembly is not None
        assert hasattr(retrieved_assembly, "gsheet")
        assert retrieved_assembly.gsheet is None  # Should be None for optional one-to-one


class TestSelectionRunRecordORM:
    def test_save_and_retrieve_selection_run_record(self, postgres_session: Session):
        """Test that SelectionRunRecord objects can be saved and retrieved."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()  # Get assembly ID

        # Create SelectionRunRecord
        task_id = uuid.uuid4()
        selection_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="running",
            task_type="load_gsheet",
            log_messages=["Started task", "Processing data", "Selection in progress"],
            settings_used={"algorithm": "maximin", "target_count": 100, "seed": 42},
            error_message="",
        )

        postgres_session.add(selection_record)
        postgres_session.commit()

        # Retrieve SelectionRunRecord
        retrieved_record = postgres_session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

        assert retrieved_record is not None
        assert retrieved_record.assembly_id == assembly.id
        assert retrieved_record.task_id == task_id
        assert retrieved_record.status == "running"
        assert retrieved_record.task_type == "load_gsheet"
        assert retrieved_record.log_messages == ["Started task", "Processing data", "Selection in progress"]
        assert retrieved_record.settings_used == {"algorithm": "maximin", "target_count": 100, "seed": 42}
        assert retrieved_record.error_message == ""
        assert isinstance(retrieved_record.created_at, datetime)
        assert retrieved_record.created_at.tzinfo is not None
        assert retrieved_record.completed_at is None

    def test_selection_run_record_defaults(self, postgres_session: Session):
        """Test that SelectionRunRecord default values work correctly."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create SelectionRunRecord with minimal data (defaults should apply)
        task_id = uuid.uuid4()
        selection_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="pending",
            task_type="load_gsheet",
        )

        postgres_session.add(selection_record)
        postgres_session.commit()

        # Retrieve and check defaults
        retrieved_record = postgres_session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

        assert retrieved_record.log_messages == []
        assert retrieved_record.settings_used == {}
        assert retrieved_record.error_message == ""
        assert retrieved_record.completed_at is None

    def test_selection_run_record_with_completion(self, postgres_session: Session):
        """Test SelectionRunRecord with completion timestamp."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create SelectionRunRecord
        task_id = uuid.uuid4()
        completed_time = datetime.now()
        selection_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="completed",
            task_type="load_gsheet",
            log_messages=["Task started", "Selection completed successfully"],
            settings_used={"algorithm": "stratified", "target_count": 50},
            completed_at=completed_time,
        )

        postgres_session.add(selection_record)
        postgres_session.commit()

        # Retrieve and verify
        retrieved_record = postgres_session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

        assert retrieved_record.status == "completed"
        assert retrieved_record.completed_at is not None
        assert isinstance(retrieved_record.completed_at, datetime)

    def test_selection_run_record_with_error(self, postgres_session: Session):
        """Test SelectionRunRecord with error information."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create SelectionRunRecord with error
        task_id = uuid.uuid4()
        selection_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="failed",
            task_type="load_gsheet",
            log_messages=["Task started", "Error occurred during processing"],
            settings_used={"algorithm": "maximin", "target_count": 200},
            error_message="Google Sheets API connection failed",
        )

        postgres_session.add(selection_record)
        postgres_session.commit()

        # Retrieve and verify
        retrieved_record = postgres_session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

        assert retrieved_record.status == "failed"
        assert retrieved_record.error_message == "Google Sheets API connection failed"
        assert "Error occurred during processing" in retrieved_record.log_messages

    def test_selection_run_record_foreign_key_constraint(self, postgres_session: Session):
        """Test that foreign key constraint works for assembly_id."""
        # Try to create SelectionRunRecord without valid assembly
        task_id = uuid.uuid4()
        selection_record = SelectionRunRecord(
            assembly_id=uuid.uuid4(),  # Non-existent assembly
            task_id=task_id,
            status="pending",
            task_type="load_gsheet",
        )

        postgres_session.add(selection_record)

        with pytest.raises(IntegrityError):  # Should raise foreign key constraint error
            postgres_session.commit()

    def test_cascade_delete_selection_run_records(self, postgres_session: Session):
        """Test that deleting an assembly cascades to its SelectionRunRecords."""
        # Create assembly
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create multiple SelectionRunRecords
        record1 = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status="completed",
            task_type="load_gsheet",
        )
        record2 = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=uuid.uuid4(),
            status="running",
            task_type="load_gsheet",
        )

        postgres_session.add(record1)
        postgres_session.add(record2)
        postgres_session.commit()

        # Verify records exist
        assert postgres_session.query(SelectionRunRecord).filter_by(assembly_id=assembly.id).count() == 2

        # Delete assembly
        postgres_session.delete(assembly)
        postgres_session.commit()

        # Verify SelectionRunRecords were cascade deleted
        assert postgres_session.query(SelectionRunRecord).filter_by(assembly_id=assembly.id).count() == 0

    def test_selection_run_record_task_id_primary_key(self, postgres_session: Session):
        """Test that task_id serves as primary key and must be unique."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create first SelectionRunRecord
        task_id = uuid.uuid4()
        record1 = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="running",
            task_type="load_gsheet",
        )

        postgres_session.add(record1)
        postgres_session.commit()

        # Try to create second SelectionRunRecord with same task_id
        record2 = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,  # Same task_id
            status="pending",
            task_type="load_gsheet",
        )

        postgres_session.add(record2)

        with pytest.raises(IntegrityError):  # Should raise primary key constraint error
            postgres_session.commit()

    def test_selection_run_record_json_fields_empty(self, postgres_session: Session):
        """Test that JSON fields handle empty collections properly."""
        # Create assembly first
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        postgres_session.add(assembly)
        postgres_session.flush()

        # Create SelectionRunRecord with explicitly empty JSON fields
        task_id = uuid.uuid4()
        selection_record = SelectionRunRecord(
            assembly_id=assembly.id,
            task_id=task_id,
            status="pending",
            task_type="load_gsheet",
            log_messages=[],
            settings_used={},
        )

        postgres_session.add(selection_record)
        postgres_session.commit()

        # Retrieve and verify empty collections are preserved
        retrieved_record = postgres_session.query(SelectionRunRecord).filter_by(task_id=task_id).first()

        assert retrieved_record.log_messages == []
        assert retrieved_record.settings_used == {}
        assert isinstance(retrieved_record.log_messages, list)
        assert isinstance(retrieved_record.settings_used, dict)
