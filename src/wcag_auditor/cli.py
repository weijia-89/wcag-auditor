from __future__ import annotations

import os

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from wcag_auditor import database
from wcag_auditor.auditor import Auditor
from wcag_auditor.models import AuditReport, ImpactLevel

app = typer.Typer(
    name="wcag-auditor",
    help="WCAG 2.2 accessibility auditor backed by axe-core and a local LLM.",
    add_completion=False,
)

console = Console()

_IMPACT_COLORS: dict[str, str] = {
    ImpactLevel.CRITICAL.value: "bold red",
    ImpactLevel.SERIOUS.value: "bold orange3",
    ImpactLevel.MODERATE.value: "yellow",
    ImpactLevel.MINOR.value: "dim",
}


def _render_table(report: AuditReport) -> None:
    table = Table(
        title=f"Audit: {report.scanned_path}",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("Rule ID", style="cyan", no_wrap=True)
    table.add_column("WCAG", style="magenta")
    table.add_column("Impact", no_wrap=True)
    table.add_column("Fixes #", justify="right")
    table.add_column("Confidence", justify="right")

    for result in report.results:
        impact_color = _IMPACT_COLORS.get(result.impact.value, "white")
        table.add_row(
            result.rule_id,
            result.wcag_criterion,
            f"[{impact_color}]{result.impact.value}[/{impact_color}]",
            str(len(result.fixes)),
            f"{result.confidence_score:.2f}",
        )

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] "
        f"{report.total_violations} violation(s) — "
        f"[bold red]{report.critical_count} critical[/bold red], "
        f"[bold orange3]{report.serious_count} serious[/bold orange3], "
        f"[yellow]{report.moderate_count} moderate[/yellow], "
        f"[dim]{report.minor_count} minor[/dim]"
    )


@app.command()
def audit(
    target: str = typer.Argument(..., help="File path or URL to audit."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json."),
    no_save: bool = typer.Option(False, "--no-save", help="Do not save report to database."),
    timeout: int = typer.Option(
        15_000,
        "--timeout",
        help="Per-page navigation timeout in milliseconds (default: 15000).",
    ),
    unsafe_no_sandbox: bool = typer.Option(
        False,
        "--unsafe-no-sandbox",
        help=(
            "Launch Chromium with --no-sandbox. Required in Docker/CI. "
            "Dangerous on a developer laptop scanning untrusted URLs."
        ),
    ),
) -> None:
    """Run a WCAG 2.2 audit on a file or URL."""
    if unsafe_no_sandbox:
        # The auditor reads this env var directly; setting it here keeps the
        # CLI flag and the env override on the same code path.
        os.environ["WCAG_NO_SANDBOX"] = "1"
    auditor = Auditor(timeout_ms=timeout)
    report = auditor.audit(target, save=not no_save)

    if output == "json":
        typer.echo(report.model_dump_json(indent=2))
    else:
        _render_table(report)


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent reports to show."),
) -> None:
    """List recent audits from the local database."""
    reports = database.list_reports(limit=limit)

    if not reports:
        rprint("[yellow]No audit reports found.[/yellow]")
        return

    table = Table(
        title="Audit History",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Path / URL")
    table.add_column("Timestamp")
    table.add_column("Violations", justify="right")

    for row in reports:
        table.add_row(
            str(row["id"]),
            row["scanned_path"],
            row["timestamp"],
            str(row["total_violations"]),
        )

    console.print(table)


@app.command()
def report(
    report_id: int = typer.Argument(..., help="Report ID to display."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table or json."),
) -> None:
    """Display a stored report by id."""
    audit_report = database.get_report(report_id)

    if audit_report is None:
        rprint(f"[red]Report #{report_id} not found.[/red]")
        raise typer.Exit(code=1)

    if output == "json":
        typer.echo(audit_report.model_dump_json(indent=2))
    else:
        _render_table(audit_report)


if __name__ == "__main__":
    app()
