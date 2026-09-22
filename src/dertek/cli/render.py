from __future__ import annotations

from rich.console import Console
from rich.text import Text

from dertek.events import AgentEvent, EventType


class RichEventSink:
    def __init__(self, console: Console) -> None:
        self.console = console

    def emit(self, event: AgentEvent) -> None:
        if event.type == EventType.ROUTE:
            band = event.data.get("band", "")
            source = event.data.get("source", "")
            model_tier = event.data.get("model_tier", "")
            model = event.data.get("model", "")
            effort = event.data.get("reasoning_effort", "")
            self.console.print(
                f"[dim]route: {event.message} [{band}, {source}] "
                f"model: {model_tier} ({model}, reasoning={effort})[/dim]"
            )
        elif event.type == EventType.TOOL_STARTED:
            self.console.print(f"[cyan]●[/cyan] {event.message}")
        elif event.type == EventType.TOOL_DENIED:
            self.console.print(f"[yellow]●[/yellow] {event.message}")
        elif event.type == EventType.MODEL_ESCALATED:
            self.console.print(f"[yellow]↗[/yellow] {event.message}")
        elif event.type == EventType.DECISION_STARTED:
            self.console.print(f"[dim]jev: {event.message}[/dim]")
        elif event.type == EventType.INFO:
            self.console.print(f"[dim]{event.message}[/dim]")
        elif event.type == EventType.ERROR:
            self.console.print(Text(event.message, style="red"))
