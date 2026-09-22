from dertek.router.models import ConfidenceBand, RouteDecision, TaskRoute
from dertek.router.thresholds import RouterThresholds


def test_threshold_bands() -> None:
    thresholds = RouterThresholds(high=0.9, medium=0.65)

    high = thresholds.resolve(RouteDecision(TaskRoute.CODE, 0.95))
    assert high.band == ConfidenceBand.HIGH
    assert high.apply_as_constraint is True
    assert high.route == TaskRoute.CODE

    medium = thresholds.resolve(RouteDecision(TaskRoute.DEBUG, 0.7))
    assert medium.band == ConfidenceBand.MEDIUM
    assert medium.apply_as_constraint is False
    assert medium.route == TaskRoute.DEBUG

    low = thresholds.resolve(RouteDecision(TaskRoute.SEARCH, 0.4))
    assert low.band == ConfidenceBand.LOW
    assert low.route is None
