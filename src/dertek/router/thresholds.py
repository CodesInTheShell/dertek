from __future__ import annotations

from dataclasses import dataclass

from dertek.router.models import ConfidenceBand, RouteDecision, RouteResolution


@dataclass(frozen=True, slots=True)
class RouterThresholds:
    high: float = 0.90
    medium: float = 0.65

    def __post_init__(self) -> None:
        if not 0 <= self.medium <= self.high <= 1:
            raise ValueError("Router thresholds must satisfy 0 <= medium <= high <= 1")

    def resolve(self, decision: RouteDecision) -> RouteResolution:
        if decision.confidence >= self.high:
            return RouteResolution(
                route=decision.route,
                confidence=decision.confidence,
                band=ConfidenceBand.HIGH,
                apply_as_constraint=True,
            )
        if decision.confidence >= self.medium:
            return RouteResolution(
                route=decision.route,
                confidence=decision.confidence,
                band=ConfidenceBand.MEDIUM,
                apply_as_constraint=False,
            )
        return RouteResolution(
            route=None,
            confidence=decision.confidence,
            band=ConfidenceBand.LOW,
            apply_as_constraint=False,
        )
