"""ABOUTME: CLI commands for Celery task management and monitoring
ABOUTME: Provides commands to check for running tasks and manage background workers"""

import time

import click
from click.exceptions import Exit

from opendlp.entrypoints.celery.app import app as celery_app


def _get_active_tasks() -> dict[str, list] | None:
    """Get active tasks from all Celery workers.

    Returns None if no workers are available, otherwise returns a dict mapping
    worker names to lists of active tasks.
    """
    try:
        inspect = celery_app.control.inspect()
        return inspect.active()
    except Exception as e:
        click.echo(click.style(f"✗ Error connecting to Celery: {e}", "red"))
        click.echo("  Make sure Redis is accessible and Celery is configured correctly")
        raise Exit(2) from e


def _count_total_tasks(active_tasks: dict[str, list]) -> int:
    """Count total active tasks across all workers."""
    return sum(len(tasks) for tasks in active_tasks.values())


def _display_active_tasks(active_tasks: dict[str, list], total_tasks: int) -> None:
    """Display information about active tasks."""
    click.echo(click.style(f"⚙  {total_tasks} task(s) currently running:", "cyan"))
    for worker_name, tasks in active_tasks.items():
        if tasks:
            click.echo(f"  Worker: {worker_name}")
            for task in tasks:
                task_name = task.get("name", "unknown")
                task_id = task.get("id", "unknown")
                click.echo(f"    - {task_name} (ID: {task_id[:8]}...)")


@click.group()
@click.pass_context
def celery(ctx: click.Context) -> None:
    """Celery task management commands."""
    ctx.ensure_object(dict)


@celery.command("list-tasks")
@click.pass_context
def list_tasks(ctx: click.Context) -> None:
    """List currently running Celery tasks.

    Always exits with code 0, regardless of whether tasks are running.
    Useful for monitoring and inspection.
    """
    active_tasks = _get_active_tasks()

    if active_tasks is None:
        click.echo(click.style("⚠️  Warning: No Celery workers are running", "yellow"))
        return

    total_tasks = _count_total_tasks(active_tasks)

    if total_tasks == 0:
        click.echo(click.style("✓ No tasks currently running", "green"))
        return

    _display_active_tasks(active_tasks, total_tasks)


@celery.command("check-tasks")
@click.pass_context
def check_tasks(ctx: click.Context) -> None:
    """Check if any Celery tasks are currently running.

    Exits with code 0 if no tasks are running, code 1 if tasks are active.
    Useful as a gate in deployment scripts.
    """
    active_tasks = _get_active_tasks()

    if active_tasks is None:
        click.echo(click.style("⚠️  Warning: No Celery workers are running", "yellow"))
        raise Exit(2)

    total_tasks = _count_total_tasks(active_tasks)

    if total_tasks == 0:
        click.echo(click.style("✓ No tasks currently running", "green"))
        return

    _display_active_tasks(active_tasks, total_tasks)
    click.echo(click.style("✗ Tasks are running (deployment blocked)", "red"))
    raise click.Abort()


@celery.command("wait-tasks")
@click.option(
    "--timeout",
    type=int,
    default=300,
    help="Maximum seconds to wait for tasks to complete (default: 300)",
)
@click.pass_context
def wait_tasks(ctx: click.Context, timeout: int) -> None:
    """Wait for all Celery tasks to complete.

    Polls every 5 seconds until all tasks are finished or timeout is reached.
    Exits with code 0 if all tasks complete, code 1 if timeout is reached.
    """
    poll_interval = 5
    elapsed = 0

    click.echo(f"Waiting up to {timeout}s for tasks to complete (checking every {poll_interval}s)...")

    while elapsed <= timeout:
        active_tasks = _get_active_tasks()

        if active_tasks is None:
            click.echo(click.style("⚠️  Warning: No Celery workers are running", "yellow"))
            raise Exit(2)

        total_tasks = _count_total_tasks(active_tasks)

        if total_tasks == 0:
            click.echo(click.style("✓ All tasks completed", "green"))
            return

        if elapsed == 0:
            _display_active_tasks(active_tasks, total_tasks)

        time.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    click.echo(click.style(f"✗ Tasks still running after {timeout}s timeout (deployment blocked)", "red"))
    raise click.Abort()
