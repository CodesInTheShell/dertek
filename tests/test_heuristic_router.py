from pathlib import Path

import pytest

from dertek.router.heuristic import HeuristicRouter
from dertek.router.models import TaskRoute


@pytest.mark.asyncio
async def test_router_detects_debug(tmp_path: Path) -> None:
    decision = await HeuristicRouter().route("why is this pytest failing with an exception?", tmp_path)
    assert decision.route == TaskRoute.DEBUG
