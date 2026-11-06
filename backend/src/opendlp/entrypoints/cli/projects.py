"""ABOUTME: CLI commands for project (assembly) operations
ABOUTME: Lists projects one per line, and clones a project for demos and training"""

import click

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import list_assemblies


@click.group()
@click.pass_context
def projects(ctx: click.Context) -> None:
    """Project management commands."""
    ctx.ensure_object(dict)


@projects.command("list")
@click.option("--member", "member_email", default="", help="Only projects this user holds a role on")
@click.option("--include-archived", is_flag=True, help="Include archived projects")
@click.pass_context
def list_projects(ctx: click.Context, member_email: str, include_archived: bool) -> None:
    """List projects, newest first, one per line: id, status, data source, title - separated by tabs."""
    session_factory = ctx.obj.get("session_factory") if ctx.obj else None
    uow = bootstrap.bootstrap(session_factory=session_factory)
    with uow:
        member_user_id = None
        if member_email:
            member = uow.users.get_by_email(member_email)
            if not member:
                click.echo(click.style(f"✗ User with email '{member_email}' not found.", "red"), err=True)
                raise click.Abort()
            member_user_id = member.id

        listings = list_assemblies(uow, member_user_id=member_user_id, include_archived=include_archived)

    for listing in listings:
        assembly = listing.assembly
        click.echo(f"{assembly.id}\t{assembly.status.value}\t{listing.data_source or '-'}\t{assembly.title}")
