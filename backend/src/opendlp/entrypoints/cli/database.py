"""ABOUTME: CLI commands for database management operations
ABOUTME: Provides commands to initialize, upgrade, and seed the database"""

import click
from alembic import command
from alembic.config import Config

from opendlp.adapters.orm import metadata
from opendlp.service_layer.db_utils import seed_database
from opendlp.service_layer.exceptions import UserAlreadyExists
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@click.group()
def database() -> None:
    """Database management commands."""
    pass


@database.command("init")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def init_db(ctx: click.Context, confirm: bool) -> None:
    """Initialize the database with tables."""
    try:
        if not confirm and not click.confirm("This will create all database tables. Continue?"):
            click.echo("Operation cancelled.")
            return

        # Create alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run migration to head
        command.upgrade(alembic_cfg, "head")

        click.echo(click.style("✓ Database initialized successfully.", "green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error initializing database: {e}", "red"))
        raise click.Abort() from e


@database.command("upgrade")
@click.option("--revision", default="head", help="Target revision (default: head)")
@click.pass_context
def upgrade_db(ctx: click.Context, revision: str) -> None:
    """Run database migrations."""
    try:
        # Create alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run migration
        command.upgrade(alembic_cfg, revision)

        click.echo(click.style(f"✓ Database upgraded to {revision}.", "green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error upgrading database: {e}", "red"))
        raise click.Abort() from e


@database.command("downgrade")
@click.argument("revision")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def downgrade_db(ctx: click.Context, revision: str, confirm: bool) -> None:
    """Downgrade database to a specific revision."""
    try:
        if not confirm and not click.confirm(f"This will downgrade the database to {revision}. Continue?"):
            click.echo("Operation cancelled.")
            return

        # Create alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Run downgrade
        command.downgrade(alembic_cfg, revision)

        click.echo(click.style(f"✓ Database downgraded to {revision}.", "green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error downgrading database: {e}", "red"))
        raise click.Abort() from e


@database.command("current")
@click.pass_context
def current_revision(ctx: click.Context) -> None:
    """Show current database revision."""
    try:
        # Create alembic configuration
        alembic_cfg = Config("alembic.ini")

        # Show current revision
        command.current(alembic_cfg)

    except Exception as e:
        click.echo(click.style(f"✗ Error getting current revision: {e}", "red"))
        raise click.Abort() from e


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

    except UserAlreadyExists as e:
        click.echo(click.style("Database already contains users. Skipping seed.", "yellow"))
        raise click.Abort() from e
    except Exception as e:
        click.echo(click.style(f"✗ Error seeding database: {e}", "red"))
        raise click.Abort() from e


@database.command("reset")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset_db(ctx: click.Context, confirm: bool) -> None:
    """Reset the database (drop all tables and recreate)."""
    try:
        if not confirm:
            click.echo(click.style("⚠️  WARNING: This will destroy ALL data in the database!", "red"))
            # TODO: make the confirm more work - say "type: 'delete everything' if you want to continue"
            # TODO: get rid of `--confirm` option
            # TODO: check for production in dotenv file as well, or maybe ALLOW_RESET_DB=true or something
            if not click.confirm("Are you absolutely sure you want to continue?"):
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
