"""ABOUTME: CLI commands for user management operations
ABOUTME: Provides commands to add, list, deactivate users and reset passwords"""

import click

from opendlp import bootstrap
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.exceptions import PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.security import hash_password
from opendlp.service_layer.user_service import create_user


@click.group()
@click.pass_context
def users(ctx: click.Context) -> None:
    """User management commands."""
    ctx.ensure_object(dict)


@users.command("add")
@click.option("--email", required=True, help="User email address")
@click.option("--password", help="Password (will prompt if not provided)")
@click.option(
    "--role",
    type=click.Choice([r.value for r in GlobalRole], case_sensitive=False),
    default=GlobalRole.ADMIN.value,
    help="Global role for the user (default: user)",
)
@click.pass_context
def add_user(
    ctx: click.Context,
    email: str,
    password: str | None,
    role: str,
) -> None:
    """Add a new user to the system."""
    try:
        # Prompt for password if not provided
        if not password:
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

        # Convert role string to GlobalRole enum
        global_role = GlobalRole(role)

        session_factory = ctx.obj.get("session_factory") if ctx.obj else None
        uow = bootstrap.bootstrap(session_factory=session_factory)
        with uow:
            # create_user now returns (user, token) tuple
            user, _token = create_user(
                uow=uow,
                email=email,
                password=password,
                global_role=global_role,
            )

            click.echo(click.style("✓ User created successfully:", "green"))
            click.echo(f"  ID: {user.id}")
            click.echo(f"  Email: {user.email}")
            click.echo(f"  Role: {user.global_role.value}")

    except UserAlreadyExists as e:
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
@click.pass_context
def list_users(ctx: click.Context, role: str | None, active: bool | None) -> None:
    """List users in the system."""
    try:
        session_factory = ctx.obj.get("session_factory") if ctx.obj else None
        uow = bootstrap.bootstrap(session_factory=session_factory)
        with uow:
            users_list = uow.users.filter(role, active)

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
@click.pass_context
def deactivate_user(ctx: click.Context, email: str, confirm: bool) -> None:
    """Deactivate a user account."""
    try:
        session_factory = ctx.obj.get("session_factory") if ctx.obj else None
        uow = bootstrap.bootstrap(session_factory=session_factory)
        with uow:
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
@click.pass_context
def reset_password(ctx: click.Context, email: str, password: str | None) -> None:
    """Reset a user's password."""
    try:
        session_factory = ctx.obj.get("session_factory") if ctx.obj else None
        uow = bootstrap.bootstrap(session_factory=session_factory)
        with uow:
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
