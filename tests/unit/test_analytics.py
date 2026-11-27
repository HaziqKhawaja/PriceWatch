from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.services.analytics import (
    COLUMNS,
    add_moving_averages,
    build_trends,
    compute_stats,
    filter_outliers,
    resample_daily,
    snapshots_to_frame,
)

NOW = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)


def ts(day: int, hour: int = 0, month: int = 3) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def frame(prices, start_day=1, stock=None):
    rows = [
        (ts(start_day + i), p, True if stock is None else stock[i]) for i, p in enumerate(prices)
    ]
    return snapshots_to_frame(rows)


def test_snapshots_to_frame_dtypes_and_sorting():
    df = snapshots_to_frame(
        [(ts(3), Decimal("30.50"), False), (ts(1), 10, True), (ts(2), 20.0, True)]
    )
    assert list(df.columns) == COLUMNS
    assert str(df["scraped_at"].dtype) == "datetime64[ns, UTC]"
    assert df["price"].dtype == "float64"
    assert df["in_stock"].dtype == "bool"
    assert df["price"].tolist() == [10.0, 20.0, 30.5]
    assert df["in_stock"].tolist() == [True, True, False]


def test_snapshots_to_frame_empty():
    df = snapshots_to_frame([])
    assert df.empty
    assert list(df.columns) == COLUMNS
    assert str(df["scraped_at"].dtype) == "datetime64[ns, UTC]"
    assert df["price"].dtype == "float64"
    assert df["in_stock"].dtype == "bool"


def test_filter_outliers_drops_nonpositive_and_nan():
    df = frame([10.0, 0.0, -5.0, float("nan"), 12.0])
    assert filter_outliers(df)["price"].tolist() == [10.0, 12.0]


def test_filter_outliers_iqr_applied_at_eight_points():
    base = [10, 11, 10, 12, 11, 10, 11]
    spike = filter_outliers(frame([*base, 100]))
    assert 100 not in spike["price"].tolist()
    assert len(spike) == 7
    dip = filter_outliers(frame([100, 101, 100, 102, 101, 100, 101, 10]))
    assert 10 not in dip["price"].tolist()
    assert len(dip) == 7


def test_filter_outliers_not_applied_at_seven_points():
    df = frame([10, 11, 10, 12, 11, 10, 100])
    assert len(filter_outliers(df)) == 7


def test_resample_last_of_day_and_ffill_gap():
    rows = [
        (ts(1, 8), 10.0, True),
        (ts(1, 20), 12.0, False),
        (ts(4, 9), 9.0, True),
    ]
    daily = resample_daily(snapshots_to_frame(rows))
    assert daily.index.name == "date"
    assert len(daily) == 4
    assert daily["price"].tolist() == [12.0, 12.0, 12.0, 9.0]
    assert daily["in_stock"].tolist() == [False, False, False, True]
    assert daily["in_stock"].dtype == "bool"
    assert daily.index[0] == pd.Timestamp("2026-03-01", tz="UTC")
    assert daily.index[-1] == pd.Timestamp("2026-03-04", tz="UTC")


def test_resample_empty():
    daily = resample_daily(snapshots_to_frame([]))
    assert daily.empty
    assert list(daily.columns) == ["price", "in_stock"]
    assert daily.index.name == "date"


def test_moving_averages_known_values():
    daily = add_moving_averages(resample_daily(frame(range(1, 11))))
    assert daily["ma_7"].iloc[-1] == 7.0
    assert daily["ma_30"].iloc[-1] == 5.5
    assert daily["ma_7"].iloc[0] == 1.0


def test_compute_stats_exact_values():
    daily = add_moving_averages(resample_daily(frame([10.0, 20.0, 15.0, 12.0])))
    stats = compute_stats(daily, 10.0)
    assert stats == {
        "current": 12.0,
        "min": 10.0,
        "max": 20.0,
        "mean": 14.25,
        "pct_change": 20.0,
        "is_all_time_low": False,
        "vs_30d_avg_pct": -15.79,
    }


def test_compute_stats_single_row():
    daily = add_moving_averages(resample_daily(frame([9.99])))
    stats = compute_stats(daily, 9.99)
    assert stats["pct_change"] == 0.0
    assert stats["current"] == 9.99
    assert stats["vs_30d_avg_pct"] == 0.0
    assert stats["is_all_time_low"] is True


def test_compute_stats_empty_all_none():
    stats = compute_stats(resample_daily(snapshots_to_frame([])), None)
    assert set(stats) == {
        "current",
        "min",
        "max",
        "mean",
        "pct_change",
        "is_all_time_low",
        "vs_30d_avg_pct",
    }
    assert all(v is None for v in stats.values())


def test_compute_stats_all_time_low_uses_given_min():
    daily = add_moving_averages(resample_daily(frame([10.0, 12.0])))
    assert compute_stats(daily, 12.0)["is_all_time_low"] is True
    assert compute_stats(daily, 5.0)["is_all_time_low"] is False
    assert compute_stats(daily, None)["is_all_time_low"] is False


def test_compute_stats_plain_python_types():
    daily = add_moving_averages(resample_daily(frame([10.0, 20.0, 15.0])))
    stats = compute_stats(daily, 10.0)
    for key, value in stats.items():
        if key == "is_all_time_low":
            assert type(value) is bool
        else:
            assert type(value) is float, key


def test_build_trends_window_and_ma_on_full_history():
    rows = [
        (datetime(2026, 2, 1, tzinfo=UTC) + timedelta(days=i), 10.0 + i, True) for i in range(59)
    ]
    # last day = Feb 1 + 58 = Mar 31
    history = snapshots_to_frame(rows)
    result = build_trends(history, days=10, now=NOW)
    series = result.series
    assert list(series.columns) == ["date", "price", "ma_7", "ma_30", "in_stock"]
    assert len(series) == 10
    assert series["date"].iloc[0] == date(2026, 3, 22)
    assert series["date"].iloc[-1] == date(2026, 3, 31)
    # first window day's ma_30 uses the 30 prior days: prices for i=21..50 -> mean 10+36
    day_index = (date(2026, 3, 22) - date(2026, 2, 1)).days
    expected = sum(10.0 + i for i in range(day_index - 29, day_index + 1)) / 30
    assert series["ma_30"].iloc[0] == round(expected, 2)
    assert result.stats["current"] == 68.0
    assert result.stats["min"] == series["price"].min()


def test_build_trends_include_outliers_keeps_spike():
    prices = [10, 11, 10, 12, 11, 10, 11, 500]
    history = frame(prices)
    default = build_trends(history, days=30, now=ts(8))
    kept = build_trends(history, days=30, include_outliers=True, now=ts(8))
    assert default.stats["max"] == 12.0
    assert kept.stats["max"] == 500.0
    assert len(kept.series) == 8
    assert len(default.series) == 7


def test_build_trends_all_time_min_from_full_history():
    history = frame([5.0, 20.0, 21.0, 22.0])
    result = build_trends(history, days=2, now=ts(4, 12))
    assert len(result.series) == 2
    assert result.stats["min"] == 21.0
    assert result.stats["is_all_time_low"] is False
    at_low = build_trends(frame([30.0, 20.0, 21.0, 20.0]), days=2, now=ts(4, 12))
    assert at_low.stats["is_all_time_low"] is True


def test_build_trends_not_extended_past_last_observation():
    history = frame([10.0, 11.0, 12.0])
    result = build_trends(history, days=90, now=ts(30))
    assert result.series["date"].iloc[-1] == date(2026, 3, 3)
    assert len(result.series) == 3


def test_build_trends_series_types_and_rounding():
    history = frame([10.123, 10.456, 10.789])
    series = build_trends(history, days=90, now=ts(3, 12)).series
    assert series["price"].tolist() == [10.12, 10.46, 10.79]
    assert series["in_stock"].dtype == "bool"
    assert isinstance(series["date"].iloc[0], date)


def test_build_trends_empty_history():
    result = build_trends(snapshots_to_frame([]), days=30, now=NOW)
    assert result.series.empty
    assert list(result.series.columns) == ["date", "price", "ma_7", "ma_30", "in_stock"]
    assert all(v is None for v in result.stats.values())


@pytest.mark.parametrize("include_outliers", [True, False])
def test_build_trends_single_point(include_outliers):
    result = build_trends(frame([9.5]), days=7, include_outliers=include_outliers, now=ts(1, 12))
    assert len(result.series) == 1
    assert result.stats["pct_change"] == 0.0
