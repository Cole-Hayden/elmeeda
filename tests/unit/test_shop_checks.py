from time import perf_counter

import pytest

from issue_tracker.application.shop_checks import (
    ShopChecker,
    ShopFailure,
    ShopFault,
    ShopUnavailableError,
)
from issue_tracker.infrastructure.mock_data import ROCKDALE_JUNCTION, WOODRIDGE_FLEET


async def test_healthy_shop_answers_with_its_own_state() -> None:
    assert await ShopChecker().check(ROCKDALE_JUNCTION) == ROCKDALE_JUNCTION


async def test_no_open_bay_only_changes_the_bays() -> None:
    checker = ShopChecker()
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.NO_OPEN_BAY)

    shop = await checker.check(ROCKDALE_JUNCTION)

    assert shop.open_bays == 0
    assert shop.name == ROCKDALE_JUNCTION.name


async def test_error_fault_raises() -> None:
    checker = ShopChecker()
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.ERROR)

    with pytest.raises(ShopUnavailableError) as failed:
        await checker.check(ROCKDALE_JUNCTION)

    assert failed.value.failure is ShopFailure.ERROR


async def test_timeout_fault_waits_for_the_deadline() -> None:
    checker = ShopChecker(timeout_seconds=0.05)
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.TIMEOUT)
    started = perf_counter()

    with pytest.raises(ShopUnavailableError) as failed:
        await checker.check(ROCKDALE_JUNCTION)

    assert failed.value.failure is ShopFailure.TIMEOUT
    assert perf_counter() - started >= 0.05


async def test_one_failing_shop_does_not_lose_the_others() -> None:
    checker = ShopChecker(timeout_seconds=0.05)
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.TIMEOUT)

    available, unavailable = await checker.check_all([ROCKDALE_JUNCTION, WOODRIDGE_FLEET])

    assert available == [WOODRIDGE_FLEET]
    assert [(item.shop, item.failure) for item in unavailable] == [
        (ROCKDALE_JUNCTION, ShopFailure.TIMEOUT)
    ]


async def test_clearing_a_fault_restores_the_shop() -> None:
    checker = ShopChecker()
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.ERROR)
    checker.set_fault(ROCKDALE_JUNCTION.shop_id, ShopFault.NONE)

    assert await checker.check(ROCKDALE_JUNCTION) == ROCKDALE_JUNCTION
