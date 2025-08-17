"""ABOUTME: CLI commands for user management operations
ABOUTME: Provides commands to add, list, deactivate users and reset passwords"""

import click

from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import InvalidInvite, PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.security import hash_password
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user


@click.group()
def users() -> None:
    """User management commands."""
    pass


@users.command("add")
@click.option("--email", required=True, help="User email address")
@click.option("--first-name", help="User first name")
@click.option("--last-name", help="User last name")
@click.option(
    "--role",
    type=click.Choice([r.value for r in GlobalRole], case_sensitive=False),
    default=GlobalRole.USER.value,
    help="Global role for the user",
)
@click.option("--password", help="Password (will prompt if not provided)")
@click.option("--invite-code", help="Invite code (required for non-admin users)")
@click.pass_context
def add_user(
    ctx: click.Context,
    email: str,
    first_name: str | None,
    last_name: str | None,
    role: str,
    password: str | None,
    invite_code: str | None,
) -> None:
    """Add a new user to the system."""
    try:
        # Convert role string to enum
        global_role = GlobalRole(role.lower())

        # Prompt for password if not provided
        if not password:
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

        # Admin users don't need invite codes
        if global_role != GlobalRole.ADMIN and not invite_code:
            invite_code = click.prompt("Invite code")

        with SqlAlchemyUnitOfWork() as uow:
            user = create_user(
                uow=uow,
                email=email,
                password=password,
                invite_code=invite_code,
                first_name=first_name or "",
                last_name=last_name or "",
            )

            # For admin users, override role after creation (CLI-only)
            if global_role == GlobalRole.ADMIN:
                user.global_role = GlobalRole.ADMIN
                uow.users.add(user)
                uow.commit()

            click.echo(click.style("✓ User created successfully:", "green"))
            click.echo(f"  ID: {user.id}")
            click.echo(f"  Email: {user.email}")
            click.echo(f"  Name: {user.display_name}")
            click.echo(f"  Role: {user.global_role.value}")

    except UserAlreadyExists as e:
        click.echo(click.style(f"✗ Error: {e}", "red"))
        raise click.Abort() from e
    except InvalidInvite as e:
        click.echo(click.style(f"✗ Error: {e}", "red"))
        raise click.Abort() from e
    except PasswordTooWeak as e:
        click.echo(click.style(f"✗ Error: {e}", "red"))
        raise click.Abort() from e
    except Exception as e:
        click.echo(click.style(f"✗ Unexpected error: {e}", "red"))
        raise click.Abort() from e


@users.command("list")
@click.option(
    "--role", type=click.Choice([r.value for r in GlobalRole], case_sensitive=False), help="Filter by global role"
)
@click.option("--active/--inactive", default=None, help="Filter by active status")
def list_users(role: str | None, active: bool | None) -> None:
    """List users in the system."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            users_list = uow.users.list()

            # Apply filters
            if role:
                role_enum = GlobalRole(role.lower())
                users_list = [u for u in users_list if u.global_role == role_enum]

            if active is not None:
                users_list = [u for u in users_list if u.is_active == active]

            if not users_list:
                click.echo("No users found matching criteria.")
                return

            # Display header
            click.echo(f"{'ID':<36} {'Email':<30} {'Name':<25} {'Role':<15} {'Active':<6} {'Created':<10}")
            click.echo("-" * 125)

            # Display users
            for user in users_list:
                created_str = user.created_at.strftime("%Y-%m-%d")
                active_str = "Yes" if user.is_active else "No"

                click.echo(
                    f"{user.id!s:<36} {user.email:<30} {user.display_name:<25} "
                    f"{user.global_role.value:<15} {active_str:<6} {created_str:<10}"
                )

    except Exception as e:
        click.echo(click.style(f"✗ Error listing users: {e}", "red"))
        raise click.Abort() from e


@users.command("deactivate")
@click.argument("email")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def deactivate_user(email: str, confirm: bool) -> None:
    """Deactivate a user account."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            user = uow.users.get_by_email(email)
            if not user:
                click.echo(click.style(f"✗ User with email '{email}' not found.", "red"))
                raise click.Abort()

            if not user.is_active:
                click.echo(click.style(f"User '{email}' is already deactivated.", "yellow"))
                return

            # Confirmation prompt
            if not confirm and not click.confirm(f"Are you sure you want to deactivate user '{email}'?"):
                click.echo("Operation cancelled.")
                return

            user.is_active = False
            uow.users.add(user)
            uow.commit()

            click.echo(click.style(f"✓ User '{email}' has been deactivated.", "green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error deactivating user: {e}", "red"))
        raise click.Abort() from e


@users.command("reset-password")
@click.argument("email")
@click.option("--password", help="New password (will prompt if not provided)")
def reset_password(email: str, password: str | None) -> None:
    """Reset a user's password."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            user = uow.users.get_by_email(email)
            if not user:
                click.echo(click.style(f"✗ User with email '{email}' not found.", "red"))
                raise click.Abort()

            # Prompt for password if not provided
            if not password:
                password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
            assert isinstance(password, str)

            # Update password
            user.password_hash = hash_password(password)
            uow.users.add(user)
            uow.commit()

            click.echo(click.style(f"✓ Password reset for user '{email}'.", "green"))

    except PasswordTooWeak as e:
        click.echo(click.style(f"✗ Error: {e}", "red"))
        raise click.Abort() from e
    except Exception as e:
        click.echo(click.style(f"✗ Error resetting password: {e}", "red"))
        raise click.Abort() from e
