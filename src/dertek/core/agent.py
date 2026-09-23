from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from dertek.config import Settings
from dertek.core.context import build_decision_instructions
from dertek.core.session import Session, SessionTurn, ToolRecord, utc_now
from dertek.events import AgentEvent, EventSink, EventType, NullEventSink
from dertek.hooks.manager import HookManager
from dertek.models import AgentRequest, AgentRunResult
from dertek.providers.base import LLMProvider
from dertek.router.base import DecisionEngine
from dertek.router.models import (
    CheckpointDecision,
    CheckpointState,
    ConfidenceBand,
    IntakeDecision,
    ModelTier,
    NextAction,
    TaskIntent,
    TaskScope,
    VerificationDecision,
    VerificationLevel,
    VerificationState,
)
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
        router: DecisionEngine,
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
        self.thresholds = RouterThresholds(settings.router_high_confidence, settings.router_medium_confidence)

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
        intake = await self._intake(prompt, turn)
        resolution = self.thresholds.resolve(intake)
        trusted = resolution.band == ConfidenceBand.HIGH
        tool_profile_trusted = trusted and self._judgment_confident(
            intake, "tool_profile", high=True
        )
        current_tier = self._initial_tier(intake)
        current_model, reasoning_effort = self._model_config(current_tier)
        if self.session.model and self.session.model != current_model:
            self.session.reset_provider_context()
        turn.model = current_model
        turn.model_tier = current_tier.value
        turn.reasoning_effort = reasoning_effort
        self.session.model = current_model
        turn.route = intake.to_dict()

        self.events.emit(AgentEvent(EventType.ROUTE, f"Route: {intake.route.value} ({intake.confidence:.2f})", {
            "route": intake.route.value, "confidence": intake.confidence, "band": resolution.band.value,
            "source": intake.source, "model_tier": current_tier.value, "model_confidence": intake.model_confidence,
            "model": current_model, "reasoning_effort": reasoning_effort, "workflow": intake.workflow.value,
            "tool_profile": intake.tool_profile.value,
        }))

        instructions = build_decision_instructions(str(self.session.workspace), intake, trusted=trusted)
        tool_schemas = self.tools.schemas_for_profile(
            intake.tool_profile, trusted=tool_profile_trusted
        )
        input_items: str | list[dict[str, object]] = prompt
        checkpoint_count = 0
        correction_pending = False
        had_mutations = False
        had_errors = False
        verification_level = (
            intake.verification
            if self._judgment_confident(intake, "verification")
            else VerificationLevel.NONE
        )

        for step in range(1, self.settings.max_steps + 1):
            self.events.emit(AgentEvent(EventType.MODEL_STARTED, "Thinking", {"step": step, "model": current_model, "model_tier": current_tier.value}))
            response = await self.provider.generate(AgentRequest(
                model=current_model, instructions=instructions, input_items=input_items,
                tools=tool_schemas, continuation_token=self.session.continuation_token,
                reasoning_effort=reasoning_effort,
            ))
            self.session.continuation_token = response.continuation_token
            self.events.emit(AgentEvent(EventType.MODEL_FINISHED, "Model response received", {"step": step, "tool_calls": len(response.tool_calls), "model_tier": current_tier.value}))

            if not response.tool_calls:
                if correction_pending:
                    warning = "\n\nVerification warning: this corrected response was not re-verified because Dertek permits one verification cycle per turn."
                    return self._finish(response.text + warning, step, intake, current_tier, current_model, reasoning_effort, turn, "corrected_unverified")
                verification = await self._maybe_verify(
                    prompt, intake, current_tier, turn, response.text, had_errors, had_mutations,
                    verification_level,
                )
                if verification and (not verification.complete or not verification.evidence_sufficient):
                    correction_pending = True
                    turn.verification_status = "correction_requested"
                    correction = self._correction_request(verification, response.text)
                    if (
                        current_tier == ModelTier.SMALL
                        and verification.next_action == NextAction.ESCALATE
                    ):
                        old_model = current_model
                        current_tier = ModelTier.LARGE
                        current_model, reasoning_effort = self._model_config(current_tier)
                        transition = {
                            "from": "small",
                            "to": "large",
                            "reason": "verification",
                            "step": step,
                            "at": utc_now(),
                        }
                        turn.model_transitions.append(transition)
                        turn.model = current_model
                        turn.model_tier = current_tier.value
                        turn.reasoning_effort = reasoning_effort
                        self.session.model = current_model
                        self.session.continuation_token = None
                        self.events.emit(
                            AgentEvent(
                                EventType.MODEL_ESCALATED,
                                f"Escalated {old_model} to {current_model}",
                                transition,
                            )
                        )
                        correction = self._handoff(
                            prompt,
                            intake,
                            turn,
                            CheckpointDecision(
                                next_action=NextAction.ESCALATE,
                                model_tier=ModelTier.LARGE,
                                source=verification.source,
                            ),
                        ) + "\n" + correction
                    input_items = correction
                    continue
                status = "passed" if verification else "skipped"
                return self._finish(response.text, step, intake, current_tier, current_model, reasoning_effort, turn, status)

            provider_outputs: list[dict[str, object]] = []
            batch_mutation = False
            batch_error = False
            for call in response.tool_calls:
                record = ToolRecord(call.name, call.arguments, call.id)
                turn.tools.append(record)
                self.events.emit(AgentEvent(EventType.TOOL_STARTED, call.name, {"tool": call.name, "arguments": call.arguments}))
                result = await self._execute_tool(call, record)
                result = await self.hooks.post_tool(call, result)
                record.output, record.is_error, record.truncated = result.output, result.is_error, result.truncated
                record.finished_at = utc_now()
                batch_error = batch_error or result.is_error
                batch_mutation = batch_mutation or self.tools.is_mutating(call.name)
                self.events.emit(AgentEvent(EventType.TOOL_FINISHED, f"Finished {call.name}", {"tool": call.name, "is_error": result.is_error, "truncated": result.truncated}))
                provider_outputs.append({"type": "function_call_output", "call_id": call.id, "output": result.as_provider_output()})

            had_errors = had_errors or batch_error
            had_mutations = had_mutations or batch_mutation
            input_items = provider_outputs
            trigger = self._checkpoint_trigger(intake, turn, step, current_tier, batch_error, batch_mutation)
            if trigger and self._checkpoint_allowed(turn, checkpoint_count):
                checkpoint_count += 1
                checkpoint = await self._checkpoint(prompt, intake, turn, step, current_tier, trigger)
                if checkpoint.verification != VerificationLevel.NONE:
                    verification_level = checkpoint.verification
                if current_tier == ModelTier.SMALL and (
                    checkpoint.model_tier == ModelTier.LARGE or checkpoint.next_action == NextAction.ESCALATE
                ):
                    old_model = current_model
                    current_tier = ModelTier.LARGE
                    current_model, reasoning_effort = self._model_config(current_tier)
                    transition = {"from": "small", "to": "large", "reason": trigger, "step": step, "at": utc_now()}
                    turn.model_transitions.append(transition)
                    turn.model, turn.model_tier, turn.reasoning_effort = current_model, current_tier.value, reasoning_effort
                    self.session.model = current_model
                    self.session.continuation_token = None
                    input_items = self._handoff(prompt, intake, turn, checkpoint)
                    tool_schemas = self.tools.schemas_for_profile(checkpoint_tool_profile(checkpoint), trusted=True)
                    self.events.emit(AgentEvent(EventType.MODEL_ESCALATED, f"Escalated {old_model} to {current_model}", transition))

        raise RuntimeError(f"Dertek reached the maximum of {self.settings.max_steps} agent steps without a final answer.")

    async def _intake(self, prompt: str, turn: SessionTurn) -> IntakeDecision:
        self.events.emit(AgentEvent(EventType.DECISION_STARTED, "Jev intake", {"phase": "intake"}))
        if hasattr(self.router, "intake"):
            decision = await self.router.intake(prompt, self.session.workspace)
        else:
            decision = await self.router.route(prompt, self.session.workspace)  # type: ignore[attr-defined]
        turn.jev_call_count += int(decision.source != "heuristic")
        turn.decisions.append({"phase": "intake", "result": decision.to_dict(), "at": utc_now()})
        self.events.emit(AgentEvent(EventType.DECISION_FINISHED, "Jev intake complete", {"phase": "intake", "source": decision.source}))
        return decision

    async def _checkpoint(self, prompt: str, intake: IntakeDecision, turn: SessionTurn, step: int, tier: ModelTier, trigger: str) -> CheckpointDecision:
        state = CheckpointState(prompt, step, trigger, intake, tier, self._evidence(turn))
        self.events.emit(AgentEvent(EventType.DECISION_STARTED, "Jev checkpoint", {"phase": "checkpoint", "trigger": trigger}))
        decision = await self.router.checkpoint(state)
        turn.jev_call_count += int(decision.source != "heuristic")
        turn.decisions.append({"phase": "checkpoint", "trigger": trigger, "result": decision.to_dict(), "at": utc_now()})
        self.events.emit(AgentEvent(EventType.DECISION_FINISHED, "Jev checkpoint complete", {"phase": "checkpoint", "trigger": trigger, "source": decision.source, "next_action": decision.next_action.value}))
        return decision

    async def _maybe_verify(self, prompt: str, intake: IntakeDecision, tier: ModelTier, turn: SessionTurn, answer: str, had_errors: bool, had_mutations: bool, level: VerificationLevel) -> VerificationDecision | None:
        should_verify = self.settings.jev_verification_enabled and (
            level != VerificationLevel.NONE or had_mutations or had_errors
        )
        if not should_verify or turn.jev_call_count >= self.settings.max_jev_calls_per_turn:
            return None
        state = VerificationState(prompt, intake, tier, self._evidence(turn), had_errors, had_mutations)
        self.events.emit(AgentEvent(EventType.DECISION_STARTED, "Jev verification", {"phase": "verification"}))
        decision = await self.router.verify(state, answer[:8000])
        turn.jev_call_count += int(decision.source != "heuristic")
        turn.decisions.append({"phase": "verification", "result": decision.to_dict(), "at": utc_now()})
        turn.verification_status = "passed" if decision.complete and decision.evidence_sufficient else "failed"
        self.events.emit(AgentEvent(EventType.DECISION_FINISHED, "Jev verification complete", {"phase": "verification", "complete": decision.complete, "evidence_sufficient": decision.evidence_sufficient, "source": decision.source}))
        return decision

    async def _execute_tool(self, call: Any, record: ToolRecord):
        hook_decision = await self.hooks.pre_tool(call)
        if hook_decision.action == "deny":
            self.events.emit(AgentEvent(EventType.TOOL_DENIED, f"Denied {call.name}: {hook_decision.reason}", {"tool": call.name}))
            return self.tools.denied_result(call, hook_decision.reason)
        if hook_decision.action == "ask":
            record.approval_reason = hook_decision.reason
            self.events.emit(AgentEvent(EventType.APPROVAL_REQUIRED, f"Approval required for {call.name}", {"tool": call.name, "reason": hook_decision.reason}))
            record.approved = await self.approval_handler(call.name, hook_decision.reason)
            if not record.approved:
                return self.tools.denied_result(call, "User did not approve the tool call")
        elif hook_decision.auto_approved:
            record.approval_reason = hook_decision.reason
            record.approved = True
            self.events.emit(
                AgentEvent(
                    EventType.TOOL_AUTO_APPROVED,
                    f"Auto-approved {call.name}",
                    {"tool": call.name, "reason": hook_decision.reason},
                )
            )
        return await self.tools.execute(call)

    def _initial_tier(self, decision: IntakeDecision) -> ModelTier:
        return ModelTier.SMALL if decision.model_tier == ModelTier.SMALL and decision.model_confidence >= self.settings.router_medium_confidence else ModelTier.LARGE

    def _model_config(self, tier: ModelTier) -> tuple[str, str]:
        if tier == ModelTier.SMALL:
            return self.settings.small_model, self.settings.small_reasoning_effort
        return self.settings.effective_large_model, self.settings.large_reasoning_effort

    def _judgment_confident(
        self, decision: IntakeDecision, name: str, *, high: bool = False
    ) -> bool:
        judgment = decision.judgments.get(name)
        confidence = judgment.confidence if judgment else decision.confidence
        threshold = (
            self.settings.router_high_confidence
            if high
            else self.settings.router_medium_confidence
        )
        return confidence >= threshold

    def _checkpoint_allowed(self, turn: SessionTurn, count: int) -> bool:
        reserve = 1 if self.settings.jev_verification_enabled else 0
        return count < 2 and turn.jev_call_count < self.settings.max_jev_calls_per_turn - reserve

    def _checkpoint_trigger(self, intake: IntakeDecision, turn: SessionTurn, step: int, tier: ModelTier, error: bool, mutation: bool) -> str | None:
        if error:
            return "tool_error"
        if mutation:
            if intake.intent in {TaskIntent.INSPECT, TaskIntent.EXPLAIN}:
                return "workflow_change"
            return "mutation"
        scope = intake.scope if self._judgment_confident(intake, "scope") else TaskScope.UNKNOWN
        if self._scope_expanded(scope, turn):
            return "scope_expanded"
        if tier == ModelTier.SMALL and step >= self.settings.small_model_step_limit:
            return "small_step_limit"
        return None

    @staticmethod
    def _scope_expanded(scope: TaskScope, turn: SessionTurn) -> bool:
        paths = {str(record.arguments.get("path")) for record in turn.tools if record.arguments.get("path")}
        return (scope == TaskScope.ONE_FILE and len(paths) > 1) or (scope == TaskScope.SEVERAL_FILES and len(paths) > 5)

    @staticmethod
    def _evidence(turn: SessionTurn) -> list[dict[str, Any]]:
        return [
            {
                "tool": record.name,
                "arguments": {
                    key: str(value)[:1000] for key, value in record.arguments.items()
                },
                "output": (record.output or "")[:2000],
                "is_error": record.is_error,
                "truncated": record.truncated,
            }
            for record in turn.tools[-6:]
        ]

    def _handoff(self, prompt: str, intake: IntakeDecision, turn: SessionTurn, checkpoint: CheckpointDecision) -> str:
        return f"Original request: {prompt}\nIntake: {intake.to_dict()}\nCheckpoint: {checkpoint.to_dict()}\nObserved tool evidence: {self._evidence(turn)}\nContinue the task from this evidence. Do not repeat successful work unnecessarily."

    @staticmethod
    def _correction_request(verification: VerificationDecision, answer: str) -> str:
        return f"Jev verification found the candidate incomplete or insufficiently supported. Decision: {verification.to_dict()}\nCandidate answer: {answer}\nPerform one focused correction using tools if necessary, then provide the best final answer."

    def _finish(self, text: str, steps: int, intake: IntakeDecision, tier: ModelTier, model: str, effort: str, turn: SessionTurn, verification_status: str) -> AgentRunResult:
        self.session.turns += 1
        turn.response = text
        turn.finished_at = utc_now()
        turn.verification_status = verification_status
        self.session.updated_at = turn.finished_at
        return AgentRunResult(text, steps, intake.route.value, intake.confidence, model, tier.value, effort, list(turn.model_transitions), turn.jev_call_count, verification_status)


def checkpoint_tool_profile(decision: CheckpointDecision):
    from dertek.router.models import ToolProfile

    if decision.next_action == NextAction.TEST:
        return ToolProfile.DEBUGGING
    if decision.next_action in {NextAction.INSPECT, NextAction.RETRY}:
        return ToolProfile.UNRESTRICTED
    return ToolProfile.UNRESTRICTED
