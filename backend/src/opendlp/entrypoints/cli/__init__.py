"""ABOUTME: Main CLI entry point using Click for OpenDLP system administration
ABOUTME: Provides subcommands for user management, invites, and database operations"""

import click

from opendlp.adapters.database import start_mappers
from opendlp.config import get_config


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """OpenDLP system administration CLI."""
    # Ensure context object exists
    ctx.ensure_object(dict)

    # Initialize configuration and database mappers
    config = get_config()
    ctx.obj["config"] = config
    start_mappers()


@cli.command()
def version() -> None:
    """Show OpenDLP version."""
    click.echo("OpenDLP 0.1.0")


# Import subcommands to register them
from .database import database  # noqa: E402
from .invites import invites  # noqa: E402
from .users import users  # noqa: E402

cli.add_command(database)
cli.add_command(invites)
cli.add_command(users)


if __name__ == "__main__":
    cli()

