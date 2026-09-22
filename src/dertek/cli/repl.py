from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm

from dertek.runtime.factory import DertekRuntime


async def cli_approval(console: Console, tool_name: str, detail: str) -> bool:
    console.print(f"\n[yellow]Approval requested[/yellow] for [bold]{tool_name}[/bold]")
    console.print(detail)
    return Confirm.ask("Allow?", default=False, console=console)


async def run_repl(runtime: DertekRuntime, console: Console) -> None:
    console.print("[bold]Dertek 0.1[/bold]  Type /exit to quit, /reset to reset model context.\n")
    while True:
        try:
            prompt = console.input("[bold green]> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            break
        if prompt == "/reset":
            runtime.session.reset_provider_context()
            runtime.sessions.save(runtime.session)
            console.print("[dim]Provider context reset.[/dim]")
            continue
        try:
            result = await runtime.run(prompt)
            console.print(f"\n{result.text}\n")
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
