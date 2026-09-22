from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TaskRoute(StrEnum):
    CHAT = "chat"
    CODE = "code"
    DEBUG = "debug"
    SEARCH = "search"
    COMMAND = "command"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ModelTier(StrEnum):
    SMALL = "small"
    LARGE = "large"


class TaskIntent(StrEnum):
    INSPECT = "inspect"
    EXPLAIN = "explain"
    MODIFY = "modify"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"


class Complexity(StrEnum):
    TRIVIAL = "trivial"
    BOUNDED = "bounded"
    COMPLEX = "complex"


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    LOW_MUTATION = "low_mutation"
    HIGH_MUTATION = "high_mutation"
    SECURITY_SENSITIVE = "security_sensitive"


class TaskScope(StrEnum):
    ONE_FILE = "one_file"
    SEVERAL_FILES = "several_files"
    REPOSITORY_WIDE = "repository_wide"
    UNKNOWN = "unknown"


class Workflow(StrEnum):
    ANSWER_DIRECTLY = "answer_directly"
    SEARCH_FIRST = "search_first"
    INSPECT_FIRST = "inspect_first"
    TEST_FIRST = "test_first"
    EDIT_FIRST = "edit_first"


class ToolProfile(StrEnum):
    NONE = "none"
    READ_ONLY = "read_only"
    EDITING = "editing"
    DEBUGGING = "debugging"
    COMMAND = "command"
    UNRESTRICTED = "unrestricted"


class VerificationLevel(StrEnum):
    NONE = "none"
    REREAD = "reread"
    DIFF = "diff"
    TARGETED_TEST = "targeted_test"
    FULL_TEST = "full_test"


class ProgressState(StrEnum):
    ON_TRACK = "on_track"
    BLOCKED = "blocked"
    SCOPE_EXPANDED = "scope_expanded"
    COMPLETE = "complete"


class FailureCategory(StrEnum):
    NONE = "none"
    STALE_CONTEXT = "stale_context"
    PERMISSION = "permission"
    DEPENDENCY = "dependency"
    TEST_FAILURE = "test_failure"
    TOOL_ERROR = "tool_error"
    AMBIGUOUS = "ambiguous"


class NextAction(StrEnum):
    CONTINUE = "continue"
    RETRY = "retry"
    INSPECT = "inspect"
    TEST = "test"
    ESCALATE = "escalate"
    FINISH = "finish"


@dataclass(slots=True)
class Judgment:
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class IntakeDecision:
    route: TaskRoute
    confidence: float = 0.0
    probabilities: dict[str, float] = field(default_factory=dict)
    source: str = "unknown"
    model_tier: ModelTier = ModelTier.LARGE
    model_confidence: float = 0.0
    model_probabilities: dict[str, float] = field(default_factory=dict)
    intent: TaskIntent = TaskIntent.INSPECT
    complexity: Complexity = Complexity.COMPLEX
    risk: RiskLevel = RiskLevel.READ_ONLY
    scope: TaskScope = TaskScope.UNKNOWN
    workflow: Workflow = Workflow.INSPECT_FIRST
    tool_profile: ToolProfile = ToolProfile.UNRESTRICTED
    verification: VerificationLevel = VerificationLevel.NONE
    judgments: dict[str, Judgment] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RouteDecision = IntakeDecision


@dataclass(slots=True)
class CheckpointState:
    prompt: str
    step: int
    trigger: str
    intake: IntakeDecision
    current_model_tier: ModelTier
    tool_evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class CheckpointDecision:
    progress: ProgressState = ProgressState.ON_TRACK
    failure: FailureCategory = FailureCategory.NONE
    scope_expanded: bool = False
    next_action: NextAction = NextAction.CONTINUE
    model_tier: ModelTier = ModelTier.LARGE
    verification: VerificationLevel = VerificationLevel.NONE
    source: str = "unknown"
    judgments: dict[str, Judgment] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationState:
    prompt: str
    intake: IntakeDecision
    current_model_tier: ModelTier
    tool_evidence: list[dict[str, Any]] = field(default_factory=list)
    had_errors: bool = False
    had_mutations: bool = False


@dataclass(slots=True)
class VerificationDecision:
    complete: bool
    evidence_sufficient: bool
    next_action: NextAction = NextAction.FINISH
    source: str = "unknown"
    judgments: dict[str, Judgment] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RouteResolution:
    route: TaskRoute | None
    confidence: float
    band: ConfidenceBand
    apply_as_constraint: bool
