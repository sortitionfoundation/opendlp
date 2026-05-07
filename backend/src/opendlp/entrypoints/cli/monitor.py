"""ABOUTME: CLI commands for the end-to-end selection-monitoring feature
ABOUTME: Provides `opendlp monitor run-selection` for deploy-time gating and ad-hoc checks"""

from __future__ import annotations

import click
from click.exceptions import Exit

from opendlp.bootstrap import bootstrap
from opendlp.service_layer.monitoring import run_monitoring_selection


@click.group()
@click.pass_context
def monitor(ctx: click.Context) -> None:
    """End-to-end monitoring of the selection pipeline."""
    ctx.ensure_object(dict)


@monitor.command("run-selection")
@click.option(
    "--strict/--no-strict",
    default=True,
    help="When --no-strict, exit 0 even on failure (still prints).",
)
@click.pass_context
def run_selection(ctx: click.Context, strict: bool) -> None:
    """Run one full monitor selection. Intended at the end of deploy."""
    session_factory = ctx.obj.get("session_factory") if ctx.obj else None
    uow = bootstrap(session_factory=session_factory)
    with uow:
        result = run_monitoring_selection(uow)

    if result.not_configured:
        click.echo(
            click.style(
                "⚠  Monitoring not configured (MONITOR_ASSEMBLY_ID/MONITOR_USER_ID unset)",
                "yellow",
            )
        )
        return

    if result.success:
        click.echo(
            click.style(
                f"✓ Monitor selection succeeded in {result.duration_seconds:.1f}s",
                "green",
            )
        )
        if result.run_url:
            click.echo(f"  View: {result.run_url}")
        return

    click.echo(click.style(f"✗ Monitor selection failed: {result.message}", "red"))
    if result.error:
        click.echo(f"  {result.error}")
    if result.run_url:
        click.echo(f"  View: {result.run_url}")
    if strict:
        raise Exit(1)
