"""Static catalog for the mock stores: 3 stores x 5 items (ids 1001-1005)."""

from dataclasses import dataclass
from decimal import Decimal

ITEM_IDS = (1001, 1002, 1003, 1004, 1005)
SKU_PREFIX = {"shopalpha": "SA", "betamart": "BM", "gammagoods": "GG"}
STORE_NAMES = {"shopalpha": "ShopAlpha", "betamart": "BetaMart", "gammagoods": "GammaGoods"}


@dataclass(frozen=True)
class Item:
    item_id: int
    title: str
    base_price: Decimal


def _items(rows: list[tuple[str, str]]) -> dict[int, Item]:
    return {
        item_id: Item(item_id, title, Decimal(price))
        for item_id, (title, price) in zip(ITEM_IDS, rows, strict=True)
    }


CATALOG: dict[str, dict[int, Item]] = {
    "shopalpha": _items(
        [
            ("Aurora Wireless Noise-Cancelling Headphones", "129.99"),
            ("Brewmaster 12-Cup Programmable Coffee Maker", "79.50"),
            ('Lumina 27" 4K IPS Monitor', "349.00"),
            ("TrailBlaze Insulated Water Bottle 32oz", "24.95"),
            ("Vertex Mechanical Keyboard (Tenkeyless)", "89.00"),
        ]
    ),
    "betamart": _items(
        [
            ("Nimbus Robot Vacuum with Mapping", "299.99"),
            ("PixelPro Mirrorless Camera Body", "899.00"),
            ("HomeChef Stainless Steel Cookware Set (10-pc)", "189.95"),
            ("Pulse Fitness Tracker Band", "49.99"),
            ('Orbit 15" Ultrabook Laptop, 16GB/512GB', "1199.00"),
        ]
    ),
    "gammagoods": _items(
        [
            ("Titan Pro Gaming Laptop 17-inch", "1499.00"),
            ("Everyday USB-C Cable 6ft (2-pack)", "15.49"),
            ("Summit Electric Standing Desk", "1129.99"),
            ("Echo Bay Bluetooth Speaker", "59.99"),
            ("Quartz Smart Watch Series 4", "249.00"),
        ]
    ),
}
