"""ABOUTME: CLI commands for invite management operations
ABOUTME: Provides commands to generate, list, and revoke user invites"""

import uuid

import click

from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@click.group()
def invites() -> None:
    """Invite management commands."""
    pass


@invites.command("generate")
@click.option(
    "--role",
    type=click.Choice([r.value for r in GlobalRole], case_sensitive=False),
    default=GlobalRole.USER.value,
    help="Global role for the invite",
)
@click.option("--expires-in", type=int, default=168, help="Expiry time in hours (default: 168 = 1 week)")
@click.option("--count", type=int, default=1, help="Number of invites to generate")
@click.pass_context
def generate_invites(ctx: click.Context, role: str, expires_in: int, count: int) -> None:
    """Generate new invite codes."""
    try:
        global_role = GlobalRole(role.lower())

        with SqlAlchemyUnitOfWork() as uow:
            # For CLI usage, we need a system user ID - use a special UUID for system generation
            # Using the nil UUID to indicate system-generated
            created_by_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

            # For CLI usage, bypass service layer and create invites directly

            from opendlp.domain.user_invites import UserInvite, generate_invite_code

            invites_list = []
            for _ in range(count):
                # Generate unique invite code
                code = generate_invite_code()
                while uow.user_invites.get_by_code(code):
                    code = generate_invite_code()

                invite = UserInvite(
                    global_role=global_role,
                    created_by=created_by_user_id,
                    expires_in_hours=expires_in,
                    code=code,
                )
                uow.user_invites.add(invite)
                invites_list.append(invite)

            uow.commit()

            click.echo(click.style(f"✓ Generated {count} invite(s) successfully:", "green"))

            # Display header
            click.echo(f"{'Code':<20} {'Role':<15} {'Expires':<19}")
            click.echo("-" * 55)

            # Display invites
            for invite in invites_list:
                expires_str = invite.expires_at.strftime("%Y-%m-%d %H:%M:%S")
                click.echo(f"{invite.code:<20} {invite.global_role.value:<15} {expires_str:<19}")

    except Exception as e:
        click.echo(click.style(f"✗ Error generating invites: {e}", "red"))
        raise click.Abort() from e


@invites.command("list")
@click.option("--include-expired", is_flag=True, help="Include expired invites in the list")
@click.option("--include-used", is_flag=True, help="Include used invites in the list")
@click.option(
    "--role", type=click.Choice([r.value for r in GlobalRole], case_sensitive=False), help="Filter by global role"
)
def list_invites_cmd(include_expired: bool, include_used: bool, role: str | None) -> None:
    """List invite codes."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            # For CLI usage, bypass service layer and list invites directly
            all_invites = uow.user_invites.list()

            # Apply filters manually
            invites_list = []
            for invite in all_invites:
                # Filter by expiry
                if not include_expired and invite.is_expired():
                    continue

                # Filter by usage
                if not include_used and invite.is_used():
                    continue

                invites_list.append(invite)

            # Apply role filter
            if role:
                role_enum = GlobalRole(role.lower())
                invites_list = [i for i in invites_list if i.global_role == role_enum]

            if not invites_list:
                click.echo("No invites found matching criteria.")
                return

            # Display header
            click.echo(f"{'Code':<20} {'Role':<15} {'Status':<8} {'Expires':<19} {'Used By':<30}")
            click.echo("-" * 95)

            # Display invites
            for invite in invites_list:
                expires_str = invite.expires_at.strftime("%Y-%m-%d %H:%M:%S")

                if invite.used_by:
                    status = "Used"
                    used_by = str(invite.used_by)[:29]  # Truncate if too long
                elif not invite.is_valid():
                    status = "Expired"
                    used_by = "-"
                else:
                    status = "Valid"
                    used_by = "-"

                click.echo(
                    f"{invite.code:<20} {invite.global_role.value:<15} {status:<8} {expires_str:<19} {used_by:<30}"
                )

    except Exception as e:
        click.echo(click.style(f"✗ Error listing invites: {e}", "red"))
        raise click.Abort() from e


@invites.command("revoke")
@click.argument("code")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def revoke_invite_cmd(code: str, confirm: bool) -> None:
    """Revoke an invite code."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            invite = uow.user_invites.get_by_code(code)
            if not invite:
                click.echo(click.style(f"✗ Invite with code '{code}' not found.", "red"))
                raise click.Abort()

            if invite.used_by:
                click.echo(click.style(f"Cannot revoke invite '{code}' - it has already been used.", "yellow"))
                return

            if not invite.is_valid():
                click.echo(click.style(f"Invite '{code}' is already expired.", "yellow"))
                return

            # Confirmation prompt
            if not confirm and not click.confirm(f"Are you sure you want to revoke invite '{code}'?"):
                click.echo("Operation cancelled.")
                return

            # For CLI usage, revoke invite directly by marking as used
            # Use the nil UUID to indicate system revocation
            system_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            invite.use(system_user_id)
            uow.user_invites.add(invite)
            uow.commit()

            click.echo(click.style(f"✓ Invite '{code}' has been revoked.", "green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error revoking invite: {e}", "red"))
        raise click.Abort() from e


@invites.command("cleanup")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def cleanup_expired(confirm: bool) -> None:
    """Remove expired invite codes from the database."""
    try:
        with SqlAlchemyUnitOfWork() as uow:
            # Get all expired invites
            all_invites = uow.user_invites.list()
            expired_invites = [i for i in all_invites if not i.is_valid() and not i.used_by]

            if not expired_invites:
                click.echo("No expired invites to clean up.")
                return

            # Confirmation prompt
            if not confirm:
                click.echo(f"Found {len(expired_invites)} expired invite(s) to remove.")
                if not click.confirm("Are you sure you want to delete these expired invites?"):
                    click.echo("Operation cancelled.")
                    return

            # For now, just show expired invites (delete functionality needs repository method)
            click.echo(f"Found {len(expired_invites)} expired invite(s):")
            for invite in expired_invites:
                click.echo(f"  - {invite.code} (expired: {invite.expires_at})")

            click.echo(
                click.style("Note: Automatic cleanup not implemented yet. Expired invites shown above.", "yellow")
            )

    except Exception as e:
        click.echo(click.style(f"✗ Error cleaning up invites: {e}", "red"))
        raise click.Abort() from e
