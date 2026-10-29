"""Signal events fire once, on the right bar, and never from data that wasn't known yet."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stocklab.config import IndicatorSettings, SignalSettings
from stocklab.features.indicators import compute_indicators, to_wide
from stocklab.ingestion.calendar import sessions
from stocklab.signals.detect import crossed_above, detect_signals
from stocklab.signals.levels import active_levels, find_levels
from tests.conftest import make_history

CFG = SignalSettings(pivot_window=3)


def _frame(n: int = 30, **cols) -> pd.DataFrame:
    """A neutral prices+indicators frame (nothing crosses anything) with overrides."""
    days = sessions(date(2024, 1, 2), date(2024, 6, 28))[:n]
    base = {
        "ticker": "AAA",
        "date": days,
        "close": 100.0,
        "high": 101.0,
        "low": 99.0,
        "volume": 1_000_000.0,
        "volume_sma": 1_000_000.0,
        "sma_50": 100.0,
        "sma_200": 110.0,
        "rsi": 50.0,
        "macd": -1.0,
        "macd_signal": 0.0,
        "macd_hist": -1.0,
        "bb_upper": 110.0,
        "bb_lower": 90.0,
        "bb_pctb": 0.5,
    }
    df = pd.DataFrame({k: base[k] for k in base}, index=range(n))
    for k, v in cols.items():
        df[k] = v
    return df


def _events(df, cfg=CFG):
    sig, _ = detect_signals(df, cfg)
    return list(
        zip(sig["signal"], sig["date"].map({d: i for i, d in enumerate(df["date"])}), strict=True)
    )


def test_crossed_above_fires_once_and_ignores_warm_up():
    a = pd.Series([np.nan, 1, 2, 3, 3, 1, 3])
    assert crossed_above(a, 2).tolist() == [False, False, False, True, False, False, True]
    assert crossed_above(2, a).tolist() == [False, False, False, False, False, True, False]
    # First real value already above: no previous value to cross from, so no event
    b = pd.Series([np.nan, np.nan, 5.0, 6.0])
    assert not crossed_above(b, 1).any()


def test_golden_and_death_cross():
    fast = [100.0] * 10 + [115.0] * 10 + [100.0] * 10  # up through 110 at 10, back down at 20
    assert _events(_frame(sma_50=fast)) == [("golden_cross", 10), ("death_cross", 20)]


def test_cross_needs_both_averages_warmed_up():
    slow = [np.nan] * 5 + [110.0] * 25
    fast = [120.0] * 30  # above the slow line from the first bar it exists
    assert _events(_frame(sma_50=fast, sma_200=slow)) == []


def test_rsi_fires_on_leaving_the_zone_not_entering():
    rsi = [50, 40, 25, 20, 28, 35, 45, 60, 75, 80, 72, 65, 50] + [50] * 17
    assert _events(_frame(rsi=rsi)) == [
        ("rsi_oversold_recovery", 5),  # 28 -> 35, back above 30
        ("rsi_overbought_reversal", 11),  # 72 -> 65, back below 70
    ]


def test_macd_crosses():
    macd = [-1.0] * 10 + [1.0] * 10 + [-1.0] * 10
    assert _events(_frame(macd=macd)) == [("macd_bullish_cross", 10), ("macd_bearish_cross", 20)]


def test_bollinger_breakouts():
    close = [100.0] * 10 + [112.0, 113.0] + [100.0] * 8 + [88.0] + [100.0] * 9
    hi = [c + 1 for c in close]
    lo = [c - 1 for c in close]
    assert _events(_frame(close=close, high=hi, low=lo, pivot_window=3)) == [
        ("bb_breakout_up", 10),
        ("bb_breakout_down", 20),
    ]


def test_signal_row_contents():
    df = _frame(sma_50=[100.0] * 10 + [115.0] * 20, volume=[2_000_000.0] * 30)
    sig, _ = detect_signals(df, CFG)
    row = sig.iloc[0]
    assert row.signal == "golden_cross" and row.direction == "bullish"
    assert row.price == 100.0 and row.value == 115.0 and row.volume_ratio == 2.0
    assert "crossed above SMA 200" in row.detail


# -- support / resistance --------------------------------------------------------------


def _peak_frame(peak_at: int, peak: float, after: list[float]) -> pd.DataFrame:
    """Flat at 100, a spike high at `peak_at`, then the given closes."""
    n = peak_at + 1 + len(after)
    close = [100.0] * (peak_at + 1) + after
    high = [101.0] * n
    high[peak_at] = peak
    low = [c - 1 for c in close]
    high = [max(h, c + 0.5) for h, c in zip(high, close, strict=True)]
    return _frame(n=n, close=close, high=high, low=low)


def test_swing_high_is_confirmed_window_bars_later():
    df = _peak_frame(10, 105.0, [100.0] * 10)
    lv = find_levels(df, window=3)
    res = lv[lv["level_type"] == "resistance"]
    assert res["pivot_idx"].tolist() == [10]
    assert res["conf_idx"].tolist() == [13]
    assert res["price"].tolist() == [105.0]


def test_level_is_not_usable_before_it_is_confirmed():
    df = _peak_frame(10, 105.0, [100.0] * 10)
    act = active_levels(df, find_levels(df, 3), max_age=250)["resistance"]
    assert act[:14].isna().all()  # confirmed at the close of bar 13 -> usable from 14
    assert act[14] == 105.0


def test_breakout_before_confirmation_does_not_count():
    # Close jumps above the 105 swing high on bar 12, before it's confirmed (bar 13)
    early = _peak_frame(10, 105.0, [100.0, 106.0, 106.0, 106.0, 106.0, 106.0] + [106.0] * 5)
    assert ("resistance_breakout", 12) not in _events(early)
    # Same jump after confirmation is a breakout
    late = _peak_frame(10, 105.0, [100.0] * 5 + [106.0] * 6)
    assert ("resistance_breakout", 16) in _events(late)


def test_old_levels_expire():
    df = _peak_frame(10, 105.0, [100.0] * 5 + [106.0] * 6)
    cfg = SignalSettings(pivot_window=3, max_level_age=4)
    assert not any(name == "resistance_breakout" for name, _ in _events(df, cfg))


def test_flat_top_is_one_level():
    df = _frame(n=20, high=[101.0] * 8 + [105.0, 105.0] + [101.0] * 10)
    res = find_levels(df, 3).query("level_type == 'resistance'")
    assert res["pivot_idx"].tolist() == [8]


# -- whole-pipeline properties ---------------------------------------------------------


@pytest.fixture(scope="module")
def real_frame():
    prices = make_history("AAA", date(2021, 1, 4), date(2023, 12, 29), seed=3)
    wide = to_wide(compute_indicators(prices, IndicatorSettings()))
    return prices, prices.merge(wide, on=["ticker", "date"], how="left")


def test_no_lookahead(real_frame):
    """Signals up to day t are identical whether or not later bars exist."""
    prices, full = real_frame
    cut = 500
    part_prices = prices.iloc[:cut]
    part = part_prices.merge(
        to_wide(compute_indicators(part_prices, IndicatorSettings())),
        on=["ticker", "date"],
        how="left",
    )
    cfg = SignalSettings()
    sig_full, _ = detect_signals(full, cfg)
    sig_part, _ = detect_signals(part, cfg)
    last = part["date"].iloc[-1]
    expected = sig_full[sig_full["date"] <= last].reset_index(drop=True)
    pd.testing.assert_frame_equal(sig_part, expected)


def test_every_signal_type_appears_on_realistic_data(real_frame):
    _, full = real_frame
    sig, levels = detect_signals(full, SignalSettings())
    assert set(sig["direction"]) == {"bullish", "bearish"}
    assert {
        "macd_bullish_cross",
        "bb_breakout_up",
        "resistance_breakout",
        "support_breakdown",
    } <= set(sig["signal"])
    assert not sig.duplicated(["date", "signal"]).any()
    assert (levels["confirmed_date"] > levels["pivot_date"]).all()


def test_settings_validation():
    with pytest.raises(ValueError):
        SignalSettings(rsi_oversold=70, rsi_overbought=30)
    with pytest.raises(ValueError):
        SignalSettings(cross_fast_sma=200, cross_slow_sma=50)
    from stocklab.config import Settings

    with pytest.raises(ValueError, match="not in indicators.sma_windows"):
        Settings.model_validate(
            {
                "data": {"tickers": ["A"], "start_date": "2020-01-01"},
                "signals": {"cross_fast_sma": 30},
            }
        )
