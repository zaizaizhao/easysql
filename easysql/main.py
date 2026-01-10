"""
EasySql CLI Entry Point

Command-line interface for running the schema extraction pipeline.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from easysql.config import get_settings, load_settings
from easysql.pipeline.schema_pipeline import SchemaPipeline
from easysql.utils.logger import setup_logging

app = typer.Typer(
    name="easysql",
    help="EasySql - Database schema to Neo4j/Milvus pipeline",
    add_completion=False,
    invoke_without_command=True,  # Allow running without subcommand
)
console = Console()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    env_file: Optional[Path] = typer.Option(None, "--env", "-e", help="Path to .env file"),
    extract: bool = typer.Option(True, "--extract/--no-extract", help="Extract database schemas"),
    neo4j: bool = typer.Option(True, "--neo4j/--no-neo4j", help="Write to Neo4j"),
    milvus: bool = typer.Option(True, "--milvus/--no-milvus", help="Write to Milvus"),
    drop_existing: bool = typer.Option(
        False, "--drop-existing", "-d", help="Drop existing data before writing"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """
    EasySql - Database schema to Neo4j/Milvus pipeline.

    Run directly without subcommand to execute the pipeline.
    Use subcommands (config, version) for other operations.

    Examples:
        easysql                         # Run pipeline directly
        easysql --verbose               # Run with debug logging
        easysql --no-milvus             # Skip Milvus write
        easysql config                  # Show configuration
        easysql version                 # Show version
    """
    if ctx.invoked_subcommand is not None:
        return

    _run_pipeline(env_file, extract, neo4j, milvus, drop_existing, verbose)


def _run_pipeline(
    env_file: Optional[Path],
    extract: bool,
    neo4j: bool,
    milvus: bool,
    drop_existing: bool,
    verbose: bool,
) -> None:
    """
    Internal function to run the pipeline.

    Shared by the default callback when no subcommand is provided.
    """
    if env_file:
        settings = load_settings(env_file)
    else:
        settings = get_settings()

    if verbose:
        settings.log_level = "DEBUG"

    setup_logging(level=settings.log_level, log_file=settings.log_file)

    console.print("\n[bold blue]EasySql Pipeline[/bold blue]")
    console.print("-" * 40)

    if not settings.databases:
        console.print("[red]Error: No databases configured![/red]")
        console.print("Please configure databases in your .env file.")
        console.print("Example: DB_HIS_TYPE=mysql, DB_HIS_HOST=localhost, ...")
        raise typer.Exit(1)

    table = Table(title="Configured Databases")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Host", style="yellow")
    table.add_column("Database", style="magenta")

    for db in settings.databases.values():
        table.add_row(db.name, db.db_type, f"{db.host}:{db.port}", db.database)

    console.print(table)
    console.print()

    try:
        pipeline = SchemaPipeline(settings)
        stats = pipeline.run(
            extract=extract,
            write_neo4j=neo4j,
            write_milvus=milvus,
            drop_existing=drop_existing,
        )

        if stats.errors:
            console.print(f"\n[yellow]Completed with {len(stats.errors)} error(s)[/yellow]")
            for error in stats.errors:
                console.print(f"  [red]- {error}[/red]")
        else:
            console.print("\n[green]Pipeline completed successfully![/green]")

        results_table = Table(title="Results")
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Count", justify="right", style="green")

        results_table.add_row("Databases processed", str(stats.databases_processed))
        results_table.add_row("Tables extracted", str(stats.tables_extracted))
        results_table.add_row("Columns extracted", str(stats.columns_extracted))
        results_table.add_row("Foreign keys extracted", str(stats.foreign_keys_extracted))
        results_table.add_row("Neo4j tables written", str(stats.neo4j_tables_written))
        results_table.add_row("Milvus tables written", str(stats.milvus_tables_written))

        console.print(results_table)

    except Exception as e:
        console.print(f"\n[red]Pipeline failed: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def config(
    env_file: Optional[Path] = typer.Option(None, "--env", "-e", help="Path to .env file"),
):
    """
    Show current configuration.
    """
    if env_file:
        settings = load_settings(env_file)
    else:
        settings = get_settings()

    console.print("\n[bold blue]EasySql Configuration[/bold blue]")
    console.print("-" * 40)

    console.print("\n[cyan]Neo4j:[/cyan]")
    console.print(f"  URI: {settings.neo4j_uri}")
    console.print(f"  User: {settings.neo4j_user}")

    console.print("\n[cyan]Milvus:[/cyan]")
    console.print(f"  URI: {settings.milvus_uri}")

    console.print("\n[cyan]Embedding:[/cyan]")
    console.print(f"  Model: {settings.embedding_model}")
    console.print(f"  Dimension: {settings.embedding_dimension}")

    console.print("\n[cyan]Databases:[/cyan]")
    if settings.databases:
        for db in settings.databases.values():
            console.print(f"  - {db.name}: {db.db_type} @ {db.host}:{db.port}/{db.database}")
    else:
        console.print("  [yellow]No databases configured[/yellow]")


@app.command()
def version():
    """
    Show version information.
    """
    from easysql import __version__

    console.print(f"EasySql version: [green]{__version__}[/green]")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
