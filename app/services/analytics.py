"""Pure pandas analytics for price history (no DB access)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

COLUMNS = ["scraped_at", "price", "in_stock"]
SERIES_COLUMNS = ["date", "price", "ma_7", "ma_30", "in_stock"]
STAT_KEYS = [
    "current",
    "min",
    "max",
    "mean",
    "pct_change",
    "is_all_time_low",
    "vs_30d_avg_pct",
]
MIN_POINTS_FOR_IQR = 8


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scraped_at": pd.Series(dtype="datetime64[ns, UTC]"),
            "price": pd.Series(dtype="float64"),
            "in_stock": pd.Series(dtype="bool"),
        }
    )


def snapshots_to_frame(
    rows: Iterable[tuple[datetime, Decimal | float, bool]],
) -> pd.DataFrame:
    data = [(ts, float(price), bool(stock)) for ts, price, stock in rows]
    if not data:
        return _empty_frame()
    df = pd.DataFrame(data, columns=COLUMNS)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df["price"] = df["price"].astype("float64")
    df["in_stock"] = df["in_stock"].astype(bool)
    return df.sort_values("scraped_at", kind="stable").reset_index(drop=True)


def filter_outliers(df: pd.DataFrame) -> pd.DataFrame:
    out = df[df["price"].notna() & (df["price"] > 0)]
    if len(out) >= MIN_POINTS_FOR_IQR:
        q1 = out["price"].quantile(0.25)
        q3 = out["price"].quantile(0.75)
        iqr = q3 - q1
        out = out[out["price"].between(q1 - 1.5 * iqr, q3 + 1.5 * iqr)]
    return out.copy()


def resample_daily(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        index = pd.DatetimeIndex([], tz="UTC", name="date")
        return pd.DataFrame(
            {
                "price": pd.Series(dtype="float64", index=index),
                "in_stock": pd.Series(dtype="bool", index=index),
            }
        )
    indexed = df.set_index("scraped_at").sort_index()
    price = indexed["price"].resample("1D").last().ffill()
    stock = indexed["in_stock"].astype("float64").resample("1D").last().ffill()
    daily = pd.DataFrame({"price": price, "in_stock": stock.astype(bool)})
    daily.index.name = "date"
    return daily


def add_moving_averages(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["ma_7"] = out["price"].rolling(7, min_periods=1).mean()
    out["ma_30"] = out["price"].rolling(30, min_periods=1).mean()
    return out


def _pct(new: float, base: float) -> float | None:
    if base == 0:
        return None
    return round(float((new - base) / base * 100), 2)


def compute_stats(window: pd.DataFrame, all_time_min: float | None) -> dict:
    if window.empty:
        return dict.fromkeys(STAT_KEYS)
    prices = window["price"]
    current = float(prices.iloc[-1])
    first = float(prices.iloc[0])
    pct_change = 0.0 if len(prices) == 1 else _pct(current, first)
    return {
        "current": round(current, 2),
        "min": round(float(prices.min()), 2),
        "max": round(float(prices.max()), 2),
        "mean": round(float(prices.mean()), 2),
        "pct_change": pct_change,
        "is_all_time_low": (
            False if all_time_min is None else bool(current <= float(all_time_min) + 1e-9)
        ),
        "vs_30d_avg_pct": _pct(current, float(window["ma_30"].iloc[-1])),
    }


@dataclass
class TrendsResult:
    series: pd.DataFrame
    stats: dict


def build_trends(
    history: pd.DataFrame,
    days: int,
    include_outliers: bool = False,
    now: datetime | None = None,
) -> TrendsResult:
    cleaned = history if include_outliers else filter_outliers(history)
    daily = add_moving_averages(resample_daily(cleaned))

    now = now or datetime.now(UTC)
    now_utc = pd.Timestamp(now)
    now_utc = now_utc.tz_localize("UTC") if now_utc.tzinfo is None else now_utc.tz_convert("UTC")
    cutoff = pd.Timestamp(now_utc.date() - timedelta(days=days - 1), tz="UTC")
    window = daily[daily.index >= cutoff]

    all_time_min = None if cleaned.empty else float(cleaned["price"].min())
    stats = compute_stats(window, all_time_min)

    series = window.reset_index()
    series["date"] = series["date"].dt.date
    for col in ("price", "ma_7", "ma_30"):
        series[col] = series[col].round(2)
    series["in_stock"] = series["in_stock"].astype(bool)
    return TrendsResult(series=series[SERIES_COLUMNS].reset_index(drop=True), stats=stats)
