from dertek.core.session import Session
from dertek.events import AgentEvent, EventType
from dertek.models import AgentRunResult
from dertek.runtime.factory import ContextualEventSink, DertekRuntime
from dertek.runtime.storage import AppPaths, SessionStore


class Collector:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def test_contextual_events_have_stable_session_run_and_sequence() -> None:
    collector = Collector()
    sink = ContextualEventSink(collector)
    run_id = sink.begin("session-1")
    sink.emit(AgentEvent(EventType.ROUTE, "route"))
    sink.emit(AgentEvent(EventType.TOOL_STARTED, "read_file"))

    assert [event.sequence for event in collector.events] == [1, 2]
    assert {event.session_id for event in collector.events} == {"session-1"}
    assert {event.run_id for event in collector.events} == {run_id}


class FakeAgent:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def run(self, prompt: str) -> AgentRunResult:
        self.session.begin_turn(prompt).response = "saved"
        self.session.turns += 1
        return AgentRunResult("saved", 1, "chat", 1.0)


async def test_runtime_saves_completed_session_and_emits_lifecycle(tmp_path) -> None:
    session = Session(workspace=tmp_path)
    store = SessionStore(AppPaths(tmp_path / ".dertek"))
    collector = Collector()
    runtime = DertekRuntime(FakeAgent(session), store, ContextualEventSink(collector))

    result = await runtime.run("remember this")

    assert result.text == "saved"
    assert store.load(session.id).history[0].response == "saved"
    assert [event.type for event in collector.events] == [
        EventType.RUN_STARTED,
        EventType.RUN_FINISHED,
    ]
