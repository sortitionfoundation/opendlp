"""ABOUTME: CLI commands for database management operations
ABOUTME: Provides commands to initialize, upgrade, and seed the database"""

import os

import click

from opendlp.adapters.orm import metadata
from opendlp.service_layer.db_utils import seed_database
from opendlp.service_layer.exceptions import UserAlreadyExists
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@click.group()
def database() -> None:
    """Database management commands."""
    pass


@database.command("seed")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def seed_db(ctx: click.Context, confirm: bool) -> None:
    """Seed the database with test data."""
    try:
        if not confirm and not click.confirm("This will add test data to the database. Continue?"):
            click.echo("Operation cancelled.")
            return

        user_passwords, invites, assemblies = seed_database()

        click.echo(click.style("✓ Database seeded successfully with test data:", "green"))
        for user, password in user_passwords:
            click.echo(f"  {user.global_role} user: {user.email} / {password}")
        for invite in invites:
            click.echo(f"  {invite.global_role} invite: {invite.code}")
        for assembly in assemblies:
            click.echo(f"  Sample assembly: {assembly.title}")

    except UserAlreadyExists:
        click.echo(click.style("Database already contains users. Skipping seed.", "yellow"))
        return
    except Exception as e:
        click.echo(click.style(f"✗ Error seeding database: {e}", "red"))
        raise click.Abort() from e


@database.command("reset")
@click.pass_context
def reset_db(ctx: click.Context) -> None:
    """Reset the database (drop all tables and recreate)."""
    try:
        if os.environ.get("ALLOW_RESET_DB", "") != "DANGEROUS":
            click.echo("Resetting the database is a dangerous operation. In order to enable it set the")
            click.echo("environment variable ALLOW_RESET_DB to DANGEROUS.")
            return

        click.echo(click.style("⚠️  WARNING: This will destroy ALL data in the database!", "red"))
        delete_confirm = click.prompt("Type 'delete everything' if you want to continue.")
        if delete_confirm != "delete everything":
            click.echo("Operation cancelled.")
            return

        with SqlAlchemyUnitOfWork() as uow:
            # Drop all tables
            if uow.session.bind is not None:
                metadata.drop_all(uow.session.bind)

                # Create all tables
                metadata.create_all(uow.session.bind)

            uow.commit()

        click.echo(click.style("✓ Database reset successfully.", "green"))
        click.echo("Run 'opendlp database seed' to add test data.")

    except Exception as e:
        click.echo(click.style(f"✗ Error resetting database: {e}", "red"))
        raise click.Abort() from e
