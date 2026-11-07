import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from issue_tracker.domain.maintenance_shop import MaintenanceShop


class ShopFault(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    ERROR = "error"
    NO_OPEN_BAY = "no_open_bay"


class ShopFailure(StrEnum):
    TIMEOUT = "shop_timeout"
    ERROR = "shop_error"


class ShopUnavailableError(Exception):
    """The shop gave no usable answer, so nothing is known about its bays or prices."""

    def __init__(self, failure: ShopFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class UnavailableShop:
    shop: MaintenanceShop
    failure: ShopFailure


class ShopChecker:
    """Stands in for calling each shop's own system, so one shop can fail while others answer.

    Faults are held in memory because they're a live demo control, not business data, and a
    restart clearing them is the safe outcome. A timeout really does wait for the deadline.
    """

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._faults: dict[UUID, ShopFault] = {}

    def fault_for(self, shop_id: UUID) -> ShopFault:
        return self._faults.get(shop_id, ShopFault.NONE)

    def set_fault(self, shop_id: UUID, fault: ShopFault) -> None:
        self._faults[shop_id] = fault

    async def _ask_shop(self, shop: MaintenanceShop) -> MaintenanceShop:
        match self.fault_for(shop.shop_id):
            case ShopFault.TIMEOUT:
                await asyncio.Event().wait()
            case ShopFault.ERROR:
                raise ShopUnavailableError(ShopFailure.ERROR)
            case ShopFault.NO_OPEN_BAY:
                return replace(shop, open_bays=0)
        return shop

    async def check(self, shop: MaintenanceShop) -> MaintenanceShop:
        """Return the shop as it currently answers, or raise ShopUnavailableError."""
        try:
            return await asyncio.wait_for(self._ask_shop(shop), self._timeout_seconds)
        except TimeoutError:
            raise ShopUnavailableError(ShopFailure.TIMEOUT) from None

    async def check_all(
        self, shops: Iterable[MaintenanceShop]
    ) -> tuple[list[MaintenanceShop], list[UnavailableShop]]:
        """Ask every shop at once, so one that hangs doesn't hold up the others' answers."""
        shop_list = list(shops)
        answers = await asyncio.gather(
            *(self.check(shop) for shop in shop_list), return_exceptions=True
        )
        available: list[MaintenanceShop] = []
        unavailable: list[UnavailableShop] = []
        for shop, answer in zip(shop_list, answers, strict=True):
            if isinstance(answer, ShopUnavailableError):
                unavailable.append(UnavailableShop(shop, answer.failure))
            elif isinstance(answer, BaseException):
                raise answer
            else:
                available.append(answer)
        return available, unavailable
