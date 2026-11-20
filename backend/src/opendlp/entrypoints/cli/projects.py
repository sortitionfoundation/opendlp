"""ABOUTME: CLI commands for project (assembly) operations
ABOUTME: Lists projects one per line, and clones a project for demos and training"""

import uuid
from typing import NoReturn

import click

from opendlp import bootstrap
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.assembly_clone_service import (
    CloneOptions,
    CloneResult,
    clone_assembly,
    count_respondents_to_clone,
    validate_clone_options,
)
from opendlp.service_layer.assembly_service import list_assemblies
from opendlp.service_layer.exceptions import AssemblyTitleTaken, OpenDLPError
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


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


@projects.command("clone")
@click.argument("source_id", type=click.UUID)
@click.option("--user-email", required=True, help="Email of the admin doing the clone, who will manage the copy")
@click.option("--title", default="", help='Title for the copy (default: "<original title> (copy)")')
@click.option("--targets/--no-targets", default=True, help="Clone the targets, and the derived fields feeding them")
@click.option("--questions/--no-questions", default=True, help="Clone the registration questions")
@click.option("--registration/--no-registration", default=True, help="Clone the registration pages and their assets")
@click.option("--respondents", is_flag=True, help="Clone the respondents (needs --for-training-or-demo)")
@click.option("--for-training-or-demo", is_flag=True, help="State that the respondents hold no real personal data")
@click.option("--preserve-respondent-status", is_flag=True, help="Keep respondent statuses instead of resetting")
@click.option("--team", is_flag=True, help="Clone the team members and their roles")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def clone_project(
    ctx: click.Context,
    source_id: uuid.UUID,
    user_email: str,
    title: str,
    targets: bool,
    questions: bool,
    registration: bool,
    respondents: bool,
    for_training_or_demo: bool,
    preserve_respondent_status: bool,
    team: bool,
    yes: bool,
) -> None:
    """Copy a project held in OpenDLP, for demos and training. Selection history is never copied."""
    if respondents and not for_training_or_demo:
        _fail("Cloning respondents needs --for-training-or-demo, to state they hold no real personal data.")
    options = CloneOptions(
        title=title,
        targets=targets,
        questions=questions,
        registration=registration,
        respondents=respondents,
        preserve_respondent_status=preserve_respondent_status,
        team=team,
        confirm_no_personal_data=for_training_or_demo,
    )
    session_factory = ctx.obj.get("session_factory") if ctx.obj else None
    uow = bootstrap.bootstrap(session_factory=session_factory)
    try:
        validate_clone_options(options)
        # Checked before any prompt, and no transaction is held open while
        # waiting for the operator to answer.
        with uow:
            admin_id = _admin_id(uow, user_email)
            respondent_count = count_respondents_to_clone(uow, admin_id, source_id) if respondents else 0

        if (
            respondents
            and not yes
            and not click.confirm(
                f"This will copy {respondent_count} respondents. Confirm they contain no real personal data"
            )
        ):
            click.echo("Operation cancelled.")
            return

        with uow:
            result = clone_assembly(uow, admin_id, source_id, options)
            uow.commit()
    except AssemblyTitleTaken as e:
        _fail(f"{e.user_msg()}. Choose another title with --title.")
    except OpenDLPError as e:
        _fail(e.user_msg())

    _print_result(result)


def _fail(message: str) -> NoReturn:
    click.echo(click.style(f"✗ {message}", "red"), err=True)
    raise click.Abort()


def _admin_id(uow: AbstractUnitOfWork, email: str) -> uuid.UUID:
    user = uow.users.get_by_email(email)
    if not user:
        _fail(f"User with email '{email}' not found.")
    if not user.is_active or user.global_role != GlobalRole.ADMIN:
        _fail(f"User '{email}' must be an active user with the ADMIN role to clone projects.")
    return user.id


def _print_result(result: CloneResult) -> None:
    assembly = result.assembly
    click.echo(click.style(f"✓ Cloned as '{assembly.title}'", "green"))
    click.echo(f"  ID: {assembly.id}")
    click.echo(f"  Backoffice: /backoffice/project/{assembly.id}")
    for page in result.registration_pages:
        label = page.name or page.language or "Registration page"
        click.echo(f"  {label}: /register/{page.url_slug} (short code {page.short_url_slug})")
    for part, count in result.counts.items():
        click.echo(f"  {part.replace('_', ' ')}: {count}")
