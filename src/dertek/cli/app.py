from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from dertek import __version__
from dertek.cli.render import RichEventSink
from dertek.cli.repl import cli_approval, run_repl
from dertek.config import ApprovalMode, OpenAIAuthMode
from dertek.exceptions import DertekError
from dertek.providers.factory import build_provider
from dertek.providers.openai_auth import OpenAIAuthManager, OpenAICredentialStore
from dertek.runtime import SessionStore, build_runtime, load_settings, update_saved_settings

app = typer.Typer(
    help="Dertek, a two-speed coding agent. Run it from a project or pass --workspace.",
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True},
)
sessions_app = typer.Typer(help="List and manage persisted Dertek sessions.")
auth_app = typer.Typer(help="Manage OpenAI authentication.")
app.add_typer(sessions_app, name="sessions")
app.add_typer(auth_app, name="auth")
console = Console()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace", "-C", help="Workspace directory (default: current directory)."
        ),
    ] = Path("."),
    provider: Annotated[str | None, typer.Option("--provider", help="LLM provider: openai, anthropic, or gemini.")] = None,
    auth: Annotated[
        OpenAIAuthMode | None, typer.Option("--auth", help="OpenAI authentication mode.")
    ] = None,
    small_model: Annotated[
        str | None, typer.Option("--small-model", help="Model for Jev-classified small tasks.")
    ] = None,
    large_model: Annotated[
        str | None, typer.Option("--large-model", help="Model for major or uncertain tasks.")
    ] = None,
    approval_mode: Annotated[
        ApprovalMode | None,
        typer.Option(
            "--approval-mode",
            help="Shell approval mode: on-request, never, or auto.",
        ),
    ] = None,
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
            openai_auth=auth,
            small_model=small_model,
            large_model=large_model,
            approval_mode=approval_mode,
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
    table.add_row("OpenAI authentication", settings.openai_auth.value)
    table.add_row("Small model", settings.small_model)
    table.add_row("Small reasoning", settings.small_reasoning_effort)
    table.add_row("Large model", settings.large_model)
    table.add_row("Large reasoning", settings.large_reasoning_effort)
    if settings.openai_auth == OpenAIAuthMode.CHATGPT:
        credentials = OpenAICredentialStore().load()
        if credentials is None:
            auth_status = "missing — run 'dertek auth login'"
        elif credentials.expires_at <= time.time():
            auth_status = "expired — refresh will be attempted on use"
        else:
            auth_status = "signed in"
        table.add_row("ChatGPT credentials", auth_status)
    else:
        table.add_row("OPENAI_API_KEY", "set" if os.getenv("OPENAI_API_KEY") else "missing")
    table.add_row("TYPESAFE_API_KEY", "set" if os.getenv("TYPESAFE_API_KEY") else "missing (heuristic router fallback)")
    table.add_row("Approval mode", settings.approval_mode)
    console.print(table)


@auth_app.command("login")
def auth_login(
    device_code: Annotated[
        bool, typer.Option("--device-code", help="Use a code on another device.")
    ] = False,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Print the browser URL without opening it.")
    ] = False,
) -> None:
    """Sign in to ChatGPT for OpenAI subscription-backed model access."""
    manager = OpenAIAuthManager()

    async def login() -> None:
        if device_code:
            await manager.login_device(
                lambda url, code: console.print(
                    f"Open [link={url}]{url}[/link] and enter [bold]{code}[/bold]."
                )
            )
        else:
            await manager.login_browser(
                open_browser=not no_browser,
                show_url=lambda url: console.print(f"Open this URL to sign in:\n{url}"),
            )

    try:
        asyncio.run(login())
        update_saved_settings(openai_auth=OpenAIAuthMode.CHATGPT.value)
    except DertekError as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print("[green]Signed in to ChatGPT.[/green]")


@auth_app.command("status")
def auth_status() -> None:
    """Show ChatGPT sign-in status without exposing credentials."""
    credentials = OpenAICredentialStore().load()
    if credentials is None:
        console.print("Not signed in to ChatGPT.")
        raise typer.Exit(1)
    status = "expired; refresh will be attempted" if credentials.expires_soon(0) else "valid"
    console.print(f"ChatGPT credentials: {status}")
    console.print(f"Account: …{credentials.account_id[-6:]}")


@auth_app.command("logout")
def auth_logout() -> None:
    """Remove locally stored ChatGPT credentials."""
    removed = OpenAIAuthManager().logout()
    console.print("Signed out of ChatGPT." if removed else "No ChatGPT login was stored.")


@app.command("models")
def list_models(
    auth: Annotated[
        OpenAIAuthMode | None, typer.Option("--auth", help="OpenAI authentication mode.")
    ] = None,
) -> None:
    """List models available through the selected OpenAI authentication mode."""
    settings = load_settings()
    mode = auth or settings.openai_auth
    provider = build_provider("openai", openai_auth=mode)
    try:
        model_ids = asyncio.run(provider.list_models())
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc
    table = Table(title=f"OpenAI models ({mode.value})")
    table.add_column("Model")
    for model_id in model_ids:
        table.add_row(model_id)
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
