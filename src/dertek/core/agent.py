from __future__ import annotations

from collections.abc import Awaitable, Callable

from dertek.config import Settings
from dertek.core.context import build_instructions
from dertek.core.session import Session, SessionTurn, ToolRecord, utc_now
from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.hooks.manager import HookManager
from dertek.models import AgentRequest, AgentRunResult
from dertek.providers.base import LLMProvider
from dertek.router.base import Router
from dertek.router.thresholds import RouterThresholds
from dertek.tools.registry import ToolRegistry

ApprovalHandler = Callable[[str, str], Awaitable[bool]]


async def deny_approval(tool_name: str, detail: str) -> bool:
    del tool_name, detail
    return False


class Agent:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: LLMProvider,
        router: Router,
        tools: ToolRegistry,
        hooks: HookManager,
        session: Session,
        events: EventSink | None = None,
        approval_handler: ApprovalHandler = deny_approval,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.router = router
        self.tools = tools
        self.hooks = hooks
        self.session = session
        self.events = events or NullEventSink()
        self.approval_handler = approval_handler
        self.thresholds = RouterThresholds(
            high=settings.router_high_confidence,
            medium=settings.router_medium_confidence,
        )

    async def run(self, prompt: str) -> AgentRunResult:
        turn = self.session.begin_turn(prompt)
        try:
            return await self._run(prompt, turn)
        except Exception as exc:
            turn.error = str(exc)
            turn.finished_at = utc_now()
            self.session.updated_at = turn.finished_at
            raise

    async def _run(self, prompt: str, turn: SessionTurn) -> AgentRunResult:
        decision = await self.router.route(prompt, self.session.workspace)
        turn.route = {
            "route": decision.route.value,
            "confidence": decision.confidence,
            "probabilities": decision.probabilities,
            "source": decision.source,
        }
        resolution = self.thresholds.resolve(decision)
        self.events.emit(
            AgentEvent(
                EventType.ROUTE,
                f"Route: {decision.route.value} ({decision.confidence:.2f})",
                {
                    "route": decision.route.value,
                    "confidence": decision.confidence,
                    "band": resolution.band.value,
                    "source": decision.source,
                },
            )
        )

        instructions = build_instructions(str(self.session.workspace), resolution)
        tool_schemas = self.tools.schemas_for_resolution(resolution)
        input_items: str | list[dict[str, object]] = prompt

        for step in range(1, self.settings.max_steps + 1):
            self.events.emit(
                AgentEvent(EventType.MODEL_STARTED, "Thinking", {"step": step})
            )
            response = await self.provider.generate(
                AgentRequest(
                    model=self.settings.model,
                    instructions=instructions,
                    input_items=input_items,
                    tools=tool_schemas,
                    continuation_token=self.session.continuation_token,
                )
            )
            self.session.continuation_token = response.continuation_token
            self.events.emit(
                AgentEvent(
                    EventType.MODEL_FINISHED,
                    "Model response received",
                    {"step": step, "tool_calls": len(response.tool_calls)},
                )
            )

            if not response.tool_calls:
                self.session.turns += 1
                result = AgentRunResult(
                    text=response.text,
                    steps=step,
                    route=decision.route.value,
                    route_confidence=decision.confidence,
                )
                turn.response = result.text
                turn.finished_at = utc_now()
                self.session.updated_at = turn.finished_at
                return result

            provider_outputs: list[dict[str, object]] = []
            for call in response.tool_calls:
                record = ToolRecord(name=call.name, arguments=call.arguments, call_id=call.id)
                turn.tools.append(record)
                self.events.emit(
                    AgentEvent(
                        EventType.TOOL_STARTED,
                        f"{call.name}",
                        {"tool": call.name, "arguments": call.arguments},
                    )
                )

                hook_decision = await self.hooks.pre_tool(call)
                if hook_decision.action == "deny":
                    result = self.tools.denied_result(call, hook_decision.reason)
                    self.events.emit(
                        AgentEvent(
                            EventType.TOOL_DENIED,
                            f"Denied {call.name}: {hook_decision.reason}",
                            {"tool": call.name},
                        )
                    )
                else:
                    if hook_decision.action == "ask":
                        record.approval_reason = hook_decision.reason
                        self.events.emit(
                            AgentEvent(
                                EventType.APPROVAL_REQUIRED,
                                f"Approval required for {call.name}",
                                {"tool": call.name, "reason": hook_decision.reason},
                            )
                        )
                        approved = await self.approval_handler(call.name, hook_decision.reason)
                        record.approved = approved
                        if not approved:
                            result = self.tools.denied_result(call, "User did not approve the tool call")
                        else:
                            result = await self.tools.execute(call)
                    else:
                        result = await self.tools.execute(call)

                result = await self.hooks.post_tool(call, result)
                record.output = result.output
                record.is_error = result.is_error
                record.truncated = result.truncated
                record.finished_at = utc_now()
                self.events.emit(
                    AgentEvent(
                        EventType.TOOL_FINISHED,
                        f"Finished {call.name}",
                        {
                            "tool": call.name,
                            "is_error": result.is_error,
                            "truncated": result.truncated,
                        },
                    )
                )
                provider_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.id,
                        "output": result.as_provider_output(),
                    }
                )

            input_items = provider_outputs

        raise RuntimeError(
            f"Dertek reached the maximum of {self.settings.max_steps} agent steps without a final answer."
        )
