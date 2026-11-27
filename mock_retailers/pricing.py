"""Deterministic seeded random walk for mock prices and stock.

The price offset at a tick is the sum of the last WINDOW per-tick shocks (each a
reproducible function of store/item/tick), so cost is O(WINDOW) per quote and the
tick-to-tick move is at most 2 * SHOCK of the base price (5%).
"""

import random
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from mock_retailers.catalog import CATALOG

WINDOW = 40
SHOCK = 0.025
MAX_DRIFT = 0.30
OUT_OF_STOCK_RATE = 0.15


@lru_cache(maxsize=65536)
def _shock(store_key: str, item_id: int, tick: int) -> float:
    return random.Random(f"price:{store_key}:{item_id}:{tick}").uniform(-SHOCK, SHOCK)


def quote(store_key: str, item_id: int, tick: int) -> tuple[Decimal, bool]:
    base = CATALOG[store_key][item_id].base_price
    drift = sum(_shock(store_key, item_id, t) for t in range(tick - WINDOW + 1, tick + 1))
    drift = max(-MAX_DRIFT, min(MAX_DRIFT, drift))
    price = (base * Decimal(repr(round(1 + drift, 6)))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    in_stock = random.Random(f"stock:{store_key}:{item_id}:{tick}").random() >= OUT_OF_STOCK_RATE
    return price, in_stock
