"""ABOUTME: Tests the data migration that retires the global-organiser role.
ABOUTME: Inserts rows holding the retired value with raw SQL, since the enum no longer has it."""

import uuid

from migrations.versions.a31214157d0b_retire_the_global_organiser_role import (
    RETIRE_ROLE_ON_INVITES,
    RETIRE_ROLE_ON_USERS,
    downgrade,
)
from sqlalchemy import text

from opendlp.adapters.sql_repository import SqlAlchemyUserRepository
from opendlp.domain.value_objects import GlobalRole


def _insert_user(session, email, global_role):
    user_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO users (id, email, first_name, last_name, password_hash,
                               global_role, created_at, is_active, totp_enabled)
            VALUES (:id, :email, '', '', 'hash', :global_role, now(), true, false)
            """
        ),
        {"id": user_id, "email": email, "global_role": global_role},
    )
    return user_id


def _insert_invite(session, code, global_role, created_by):
    invite_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO user_invites (id, code, global_role, created_by, created_at, expires_at)
            VALUES (:id, :code, :global_role, :created_by, now(), now() + interval '1 day')
            """
        ),
        {"id": invite_id, "code": code, "global_role": global_role, "created_by": created_by},
    )
    return invite_id


def _read_user_role(session, user_id):
    return session.execute(text("SELECT global_role FROM users WHERE id = :id"), {"id": user_id}).scalar_one()


def _read_invite_role(session, invite_id):
    return session.execute(text("SELECT global_role FROM user_invites WHERE id = :id"), {"id": invite_id}).scalar_one()


class TestRetireGlobalOrganiser:
    def test_converts_a_global_organiser_to_a_plain_user(self, postgres_session):
        user_id = _insert_user(postgres_session, f"old-{uuid.uuid4()}@example.com", "global-organiser")

        postgres_session.execute(text(RETIRE_ROLE_ON_USERS))

        assert _read_user_role(postgres_session, user_id) == "user"

    def test_leaves_admins_and_users_alone(self, postgres_session):
        """Only the retired value is touched - the other roles keep their meaning."""
        admin_id = _insert_user(postgres_session, f"admin-{uuid.uuid4()}@example.com", "admin")
        user_id = _insert_user(postgres_session, f"user-{uuid.uuid4()}@example.com", "user")

        postgres_session.execute(text(RETIRE_ROLE_ON_USERS))

        assert _read_user_role(postgres_session, admin_id) == "admin"
        assert _read_user_role(postgres_session, user_id) == "user"

    def test_converts_an_unredeemed_global_organiser_invite(self, postgres_session):
        """Whoever holds the link signs up as a plain user, not with the retired role."""
        creator_id = _insert_user(postgres_session, f"creator-{uuid.uuid4()}@example.com", "admin")
        invite_id = _insert_invite(postgres_session, f"OLD{uuid.uuid4().hex[:8]}", "global-organiser", creator_id)

        postgres_session.execute(text(RETIRE_ROLE_ON_INVITES))

        assert _read_invite_role(postgres_session, invite_id) == "user"

    def test_leaves_other_invites_alone(self, postgres_session):
        creator_id = _insert_user(postgres_session, f"creator-{uuid.uuid4()}@example.com", "admin")
        invite_id = _insert_invite(postgres_session, f"ADM{uuid.uuid4().hex[:8]}", "admin", creator_id)

        postgres_session.execute(text(RETIRE_ROLE_ON_INVITES))

        assert _read_invite_role(postgres_session, invite_id) == "admin"

    def test_converted_users_load_through_the_orm(self, postgres_session):
        """The point of the migration: a row holding the retired value cannot be loaded."""
        email = f"loads-{uuid.uuid4()}@example.com"
        _insert_user(postgres_session, email, "global-organiser")
        postgres_session.execute(text(RETIRE_ROLE_ON_USERS))
        postgres_session.commit()
        postgres_session.expunge_all()

        user = SqlAlchemyUserRepository(postgres_session).get_by_email(email)

        assert user.global_role == GlobalRole.USER

    def test_is_idempotent(self, postgres_session):
        user_id = _insert_user(postgres_session, f"twice-{uuid.uuid4()}@example.com", "global-organiser")

        postgres_session.execute(text(RETIRE_ROLE_ON_USERS))
        postgres_session.execute(text(RETIRE_ROLE_ON_USERS))

        assert _read_user_role(postgres_session, user_id) == "user"


class TestDowngradeIsANoOp:
    def test_downgrade_does_nothing(self, postgres_session):
        """Asserted explicitly so nobody "fixes" the empty downgrade later.

        Converting global-organiser to user destroys the information needed to
        reverse it. A downgrade that promoted every user back would be a
        privilege escalation, so the migration deliberately does nothing.
        """
        user_id = _insert_user(postgres_session, f"down-{uuid.uuid4()}@example.com", "user")

        downgrade()

        assert _read_user_role(postgres_session, user_id) == "user"
