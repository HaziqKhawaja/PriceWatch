"""HTML rendering for each mock store (plain f-strings, everything escaped)."""

import json
from decimal import Decimal
from html import escape

from mock_retailers.catalog import CATALOG, ITEM_IDS, SKU_PREFIX, STORE_NAMES
from mock_retailers.pricing import quote

NOT_FOUND_HTML = (
    "<!doctype html><html><head><title>Not found</title></head>"
    "<body><h1>404 - Page not found</h1><p>The page you requested does not exist.</p></body></html>"
)


def sku(store_key: str, item_id: int) -> str:
    return f"{SKU_PREFIX[store_key]}-{item_id}"


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def _was(price: Decimal) -> Decimal:
    return (price * Decimal("1.18")).quantize(Decimal("0.01"))


def _related(store_key: str, item_id: int, tick: int) -> list[tuple[int, str, Decimal]]:
    out = []
    for other in ITEM_IDS:
        if other != item_id and len(out) < 3:
            p, _ = quote(store_key, other, tick)
            out.append((other, CATALOG[store_key][other].title, p))
    return out


def _page(store_key: str, title: str, head_extra: str, body: str) -> str:
    name = STORE_NAMES[store_key]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)} | {name}</title>{head_extra}</head><body>{body}</body></html>"
    )


def render_shopalpha(item_id: int, tick: int) -> str:
    item = CATALOG["shopalpha"][item_id]
    price, in_stock = quote("shopalpha", item_id, tick)
    ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": item.title,
        "sku": sku("shopalpha", item_id),
        "offers": {
            "@type": "Offer",
            "price": f"{price:.2f}",
            "priceCurrency": "USD",
            "availability": "https://schema.org/" + ("InStock" if in_stock else "OutOfStock"),
        },
    }
    # Escape "<" so a title can never terminate the script element.
    ld_json = json.dumps(ld, indent=1).replace("<", "\\u003c")
    related = "".join(
        f'<li><a href="/items/{i}">{escape(t)}</a> <em>{_money(p)}</em></li>'
        for i, t, p in _related("shopalpha", item_id, tick)
    )
    body = f"""
<header><a href="/">ShopAlpha</a> <nav><a href="#">Deals</a> <a href="#">New</a>
<a href="#">Support</a></nav><p>Free shipping on orders over $35!</p></header>
<p><a href="/">Home</a> &gt; <a href="#">Catalog</a> &gt; {escape(item.title)}</p>
<main>
<h1>{escape(item.title)}</h1>
<p>Was {_money(_was(price))} - limited time offer. Financing from $12.00/mo.</p>
<p>{"Available now." if in_stock else "Currently unavailable."}</p>
<h2>Customers also viewed</h2><ul>{related}</ul>
</main>
<footer>&copy; ShopAlpha. Gift cards from $10.00.</footer>
"""
    head = f'<script type="application/ld+json">\n{ld_json}\n</script>'
    return _page("shopalpha", item.title, head, body)


def render_betamart(item_id: int, tick: int) -> str:
    item = CATALOG["betamart"][item_id]
    price, in_stock = quote("betamart", item_id, tick)
    stock = "in_stock" if in_stock else "out_of_stock"
    related = "".join(
        f'<li data-related-price="{p:.2f}"><a href="/items/{i}">{escape(t)}</a> '
        f"<span>{_money(p)}</span></li>"
        for i, t, p in _related("betamart", item_id, tick)
    )
    body = f"""
<div class="topbar">Spend $75.00 and get free returns</div>
<nav><a href="/">BetaMart</a> | <a href="#">Departments</a> | <a href="#">Clearance</a></nav>
<p><a href="/">Home</a> / <a href="#">Shop</a> / {escape(item.title)}</p>
<div id="product" data-sku="{sku("betamart", item_id)}" data-price="{price:.2f}"
     data-currency="USD" data-stock="{stock}">
  <h1 data-title>{escape(item.title)}</h1>
  <p>List price <s>{_money(_was(price))}</s></p>
  <p>{"Ships in 1-2 days" if in_stock else "Notify me when back in stock"}</p>
</div>
<section><h2>You may also like</h2><ul>{related}</ul></section>
<footer>BetaMart Rewards: earn $5.00 per $100.00 spent.</footer>
"""
    return _page("betamart", item.title, "", body)


def render_gammagoods(item_id: int, tick: int) -> str:
    item = CATALOG["gammagoods"][item_id]
    price, in_stock = quote("gammagoods", item_id, tick)
    related = "".join(
        f'<li><a href="/items/{i}">{escape(t)}</a> '
        f'<span class="price-small">{_money(p)}</span></li>'
        for i, t, p in _related("gammagoods", item_id, tick)
    )
    body = f"""
<div class="banner">Free shipping over $50.00 &bull; Extended warranty from $9.99</div>
<ul class="breadcrumbs"><li><a href="/">Home</a></li><li><a href="#">Products</a></li></ul>
<div class="product">
  <h1 class="product-title">{escape(item.title)}</h1>
  <span class="sku">{sku("gammagoods", item_id)}</span>
  <span class="was-price">{_money(_was(price))}</span>
  <span class="price">{_money(price)}</span>
  <p class="stock-status">{"In stock" if in_stock else "Out of stock"}</p>
</div>
<div class="related"><h2>Related products</h2><ul>{related}</ul></div>
<footer>GammaGoods &copy; all rights reserved.</footer>
"""
    return _page("gammagoods", item.title, "", body)


RENDERERS = {
    "shopalpha": render_shopalpha,
    "betamart": render_betamart,
    "gammagoods": render_gammagoods,
}
