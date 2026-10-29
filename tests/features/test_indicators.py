"""Indicators match textbook formulas, never look ahead, and use the agreed price basis.

The reference implementations below are deliberately plain pandas, written from the
definitions, so a pandas-ta upgrade that changes a default gets caught here.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stocklab.config import IndicatorSettings
from stocklab.features.indicators import compute_indicators, to_wide
from tests.conftest import make_history

CFG = IndicatorSettings()


@pytest.fixture(scope="module")
def prices():
    return make_history("AAA", date(2022, 1, 3), date(2023, 12, 29), seed=7)  # ~500 bars


@pytest.fixture(scope="module")
def wide(prices):
    return prices[["ticker", "date"]].merge(
        to_wide(compute_indicators(prices, CFG)), on=["ticker", "date"], how="left"
    )


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (RMA): an EMA with alpha = 1/n."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def _close_tail(a: pd.Series, b: pd.Series, n: int = 100, rtol: float = 1e-6):
    # Recursive averages differ only in how they're seeded; after a few hundred bars
    # the seed has decayed away, so compare the tail.
    np.testing.assert_allclose(a.iloc[-n:].to_numpy(), b.iloc[-n:].to_numpy(), rtol=rtol)


def test_sma_and_volume_sma_are_rolling_means(prices, wide):
    for n in CFG.sma_windows:
        ref = prices["close"].rolling(n).mean()
        np.testing.assert_allclose(wide[f"sma_{n}"], ref, rtol=1e-12, equal_nan=True)
    ref = prices["volume"].astype(float).rolling(CFG.volume_ma_window).mean()
    np.testing.assert_allclose(wide["volume_sma"], ref, rtol=1e-12, equal_nan=True)


def _ema_sma_seeded(s: pd.Series, n: int) -> pd.Series:
    """EMA seeded with the SMA of the first n values (the TA-Lib convention), so
    nothing before day n-1 has a value and the first value is a plain average."""
    seeded = s.copy().astype(float)
    seeded.iloc[: n - 1] = np.nan
    seeded.iloc[n - 1] = s.iloc[:n].mean()
    return seeded.iloc[n - 1 :].ewm(span=n, adjust=False).mean().reindex(s.index)


def test_ema_is_sma_seeded(prices, wide):
    for n in CFG.ema_windows:
        ref = _ema_sma_seeded(prices["close"], n)
        np.testing.assert_allclose(wide[f"ema_{n}"], ref, rtol=1e-10, equal_nan=True)


def test_rsi_matches_wilder(prices, wide):
    delta = prices["close"].diff()
    gain = _wilder(delta.clip(lower=0), CFG.rsi_length)
    loss = _wilder(-delta.clip(upper=0), CFG.rsi_length)
    ref = 100 - 100 / (1 + gain / loss)
    _close_tail(wide["rsi"], ref)
    assert wide["rsi"].dropna().between(0, 100).all()


def test_macd(prices, wide):
    m = CFG.macd
    close = prices["close"]
    macd = close.ewm(span=m.fast, adjust=False).mean() - close.ewm(span=m.slow, adjust=False).mean()
    signal = macd.ewm(span=m.signal, adjust=False).mean()
    _close_tail(wide["macd"], macd, rtol=1e-4)
    _close_tail(wide["macd_signal"], signal, rtol=1e-4)
    np.testing.assert_allclose(wide["macd_hist"], wide["macd"] - wide["macd_signal"], atol=1e-9)


def test_bollinger_uses_population_std(prices, wide):
    b = CFG.bollinger
    mid = prices["close"].rolling(b.length).mean()
    sd = prices["close"].rolling(b.length).std(ddof=0)
    np.testing.assert_allclose(wide["bb_middle"], mid, rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(wide["bb_upper"], mid + b.std * sd, rtol=1e-10, equal_nan=True)
    np.testing.assert_allclose(wide["bb_lower"], mid - b.std * sd, rtol=1e-10, equal_nan=True)
    pctb = (prices["close"] - wide["bb_lower"]) / (wide["bb_upper"] - wide["bb_lower"])
    np.testing.assert_allclose(wide["bb_pctb"], pctb, rtol=1e-10, equal_nan=True)


def test_atr_matches_wilder_true_range(prices, wide):
    prev = prices["close"].shift()
    tr = pd.concat(
        [
            prices["high"] - prices["low"],
            (prices["high"] - prev).abs(),
            (prices["low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    _close_tail(wide["atr"], _wilder(tr, CFG.atr_length))


def test_every_indicator_waits_for_a_full_window(prices):
    """First stored bar (0-based) per indicator = the first with a complete window.
    Guards against values computed from a handful of days (RSI once started at bar 1)."""
    long = compute_indicators(prices, CFG)
    assert not long["value"].isna().any()  # warm-up rows dropped, not stored as null
    position = {d: i for i, d in enumerate(prices["date"])}
    first = long.groupby("indicator")["date"].min().map(position).to_dict()
    m, b = CFG.macd, CFG.bollinger
    expected = {
        **{f"sma_{n}": n - 1 for n in CFG.sma_windows},
        **{f"ema_{n}": n - 1 for n in CFG.ema_windows},
        "rsi": CFG.rsi_length,  # n changes need n+1 bars
        "atr": CFG.atr_length,  # true range needs a previous close
        "macd": m.slow - 1,
        "macd_signal": m.slow + m.signal - 2,
        "macd_hist": m.slow + m.signal - 2,
        **{k: b.length - 1 for k in ("bb_lower", "bb_middle", "bb_upper", "bb_pctb")},
        "volume_sma": CFG.volume_ma_window - 1,
    }
    assert first == expected


def test_rsi_extremes():
    up = make_history("UP", date(2023, 1, 2), date(2023, 3, 31))
    up["close"] = np.arange(len(up), dtype=float) + 100  # rises every day
    up["high"], up["low"] = up["close"] + 1, up["close"] - 1
    rsi = to_wide(compute_indicators(up, CFG))["rsi"].dropna()
    assert (rsi == 100).all()


def test_no_lookahead(prices):
    """Values up to day t are identical whether or not later bars exist."""
    cut = 400
    full = to_wide(compute_indicators(prices, CFG)).set_index("date")
    part = to_wide(compute_indicators(prices.iloc[:cut], CFG)).set_index("date")
    pd.testing.assert_frame_equal(full.loc[part.index, part.columns], part)


def test_uses_close_not_adj_close(prices):
    tampered = prices.assign(adj_close=prices["adj_close"] * 0.5)
    pd.testing.assert_frame_equal(
        compute_indicators(prices, CFG), compute_indicators(tampered, CFG)
    )


def test_params_recorded_and_windows_configurable(prices):
    cfg = IndicatorSettings(sma_windows=[10], ema_windows=[], rsi_length=7)
    long = compute_indicators(prices, cfg)
    names = set(long["indicator"])
    assert (
        "sma_10" in names and "sma_200" not in names and not any(n.startswith("ema") for n in names)
    )
    assert set(long.loc[long["indicator"] == "rsi", "params"]) == {"length=7"}


def test_short_history_gives_only_the_indicators_that_fit(prices):
    # A newly listed stock: 30 bars is enough for SMA 20 but not SMA 50/200 or MACD's signal
    long = compute_indicators(prices.iloc[:30], CFG)
    names = set(long["indicator"])
    assert {"sma_20", "rsi", "bb_upper", "atr"} <= names
    assert not {"sma_50", "sma_200", "ema_200"} & names
    assert compute_indicators(prices.iloc[:5], CFG).empty


def test_unsorted_input_and_empty_input(prices):
    shuffled = prices.sample(frac=1, random_state=0)
    pd.testing.assert_frame_equal(
        compute_indicators(shuffled, CFG), compute_indicators(prices, CFG)
    )
    assert compute_indicators(prices.iloc[:0], CFG).empty


def test_settings_validation():
    with pytest.raises(ValueError):
        IndicatorSettings(macd={"fast": 26, "slow": 12, "signal": 9})
    with pytest.raises(ValueError):
        IndicatorSettings(sma_windows=[20, 20])
    assert IndicatorSettings(sma_windows=[200, 20]).sma_windows == [20, 200]
