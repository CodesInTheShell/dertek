from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dertek import __version__
from dertek.cli.render import RichEventSink
from dertek.cli.repl import cli_approval, run_repl
from dertek.exceptions import DertekError
from dertek.runtime import SessionStore, build_runtime, load_settings

app = typer.Typer(
    help="Dertek, a two-speed agentic coding CLI.",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True},
)
sessions_app = typer.Typer(help="List and manage persisted Dertek sessions.")
app.add_typer(sessions_app, name="sessions")
console = Console()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    workspace: Annotated[Path, typer.Option("--workspace", "-C", help="Workspace directory.")] = Path("."),
    provider: Annotated[str | None, typer.Option("--provider", help="LLM provider: openai, anthropic, or gemini.")] = None,
    model: Annotated[str | None, typer.Option("--model", help="Provider model name.")] = None,
    session: Annotated[str | None, typer.Option("--session", help="Resume a persisted session by ID.")] = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    prompt = " ".join(ctx.args) or None
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise typer.BadParameter(f"Workspace is not a directory: {workspace}")
    try:
        runtime = build_runtime(
            workspace,
            provider_name=provider,
            model=model,
            session_id=session,
            events=RichEventSink(console),
            approval_handler=lambda tool_name, detail: cli_approval(console, tool_name, detail),
        )
    except (DertekError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc

    if prompt:
        async def one_shot() -> None:
            result = await runtime.run(prompt)
            console.print(result.text)

        try:
            asyncio.run(one_shot())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from exc
    else:
        console.print(f"[dim]Session: {runtime.session.id}[/dim]")
        asyncio.run(run_repl(runtime, console))


@app.command()
def doctor() -> None:
    """Check local configuration without calling external APIs."""
    settings = load_settings()
    table = Table(title="Dertek doctor")
    table.add_column("Item")
    table.add_column("Status")
    table.add_row("Version", __version__)
    table.add_row("Provider", settings.provider)
    table.add_row("Model", settings.model)
    table.add_row("OPENAI_API_KEY", "set" if os.getenv("OPENAI_API_KEY") else "missing")
    table.add_row("TYPESAFE_API_KEY", "set" if os.getenv("TYPESAFE_API_KEY") else "missing (heuristic router fallback)")
    table.add_row("Approval mode", settings.approval_mode)
    console.print(table)


@app.command("version")
def version_command() -> None:
    """Print the Dertek version."""
    console.print(__version__)


@sessions_app.command("list")
def list_sessions() -> None:
    """List saved sessions in ~/.dertek/sessions."""
    saved = SessionStore().list()
    table = Table(title="Dertek sessions")
    table.add_column("ID")
    table.add_column("Workspace")
    table.add_column("Updated")
    table.add_column("Turns", justify="right")
    for session in saved:
        table.add_row(session.id, str(session.workspace), session.updated_at, str(session.turns))
    console.print(table)


@sessions_app.command("delete")
def delete_session(session_id: str = typer.Argument(help="The session ID to delete.")) -> None:
    """Delete one persisted session."""
    try:
        SessionStore().delete(session_id)
    except DertekError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(f"Deleted session {session_id}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
