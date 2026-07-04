"""
Tests for scripts/backtest_core.py.

The key guarantee: the extracted core reproduces the numbers already committed
in analysis/strategy_backtest_summary.csv, so the refactor that split the logic
out of scripts/tier2b_backtest.py is provably behavior-preserving.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_core import (  # noqa: E402
    backtest_strategies,
    seasonal_pattern_pct,
    sell_month,
    strategy_revenue,
)


@pytest.fixture(scope="module")
def prices():
    df = pd.read_csv(
        ROOT / "data" / "lamdong_coffee_prices_monthly.csv", parse_dates=["date"]
    ).set_index("date")
    return df["lamdong_robusta_vnd_kg"]


@pytest.fixture(scope="module")
def committed_summary():
    return pd.read_csv(ROOT / "analysis" / "strategy_backtest_summary.csv")


def test_summary_matches_committed_csv(prices, committed_summary):
    """Core output must reproduce the committed summary within rounding tolerance."""
    got = backtest_strategies(prices).set_index("strategy")
    want = committed_summary.set_index("strategy")

    assert set(got.index) == set(want.index)
    for strat in want.index:
        assert got.loc[strat, "avg_vnd_per_kg"] == pytest.approx(
            want.loc[strat, "avg_vnd_per_kg"], abs=1.0
        )
        assert got.loc[strat, "std"] == pytest.approx(
            want.loc[strat, "std"], abs=1.0
        )
        assert got.loc[strat, "n_harvests"] == want.loc[strat, "n_harvests"]


def test_summary_is_sorted_by_avg_descending(prices):
    got = backtest_strategies(prices)
    avgs = got["avg_vnd_per_kg"].tolist()
    assert avgs == sorted(avgs, reverse=True)
    # S4 "Hold to September" is the historical top earner (per FINDINGS.md).
    assert got.iloc[0]["strategy"].startswith("S4")


def test_sell_month_offsets():
    assert sell_month(2024, 0) == (2024, 12)  # harvest December
    assert sell_month(2024, 6) == (2025, 6)   # rolls into next year
    assert sell_month(2024, 9) == (2025, 9)
    assert sell_month(2010, 3) == (2011, 3)


def test_storage_loss_reduces_held_revenue():
    """Holding at a flat price must lose value to storage; selling now must not."""
    idx = pd.date_range("2020-12-01", periods=13, freq="MS")
    flat = pd.Series(100_000.0, index=idx)
    sell_now = strategy_revenue(flat, 2020, [(0, 1.0)])
    hold_6mo = strategy_revenue(flat, 2020, [(6, 1.0)])
    assert sell_now == pytest.approx(100_000.0)
    assert hold_6mo < sell_now
    assert hold_6mo == pytest.approx(100_000.0 * (1 - 0.005) ** 6)


def test_missing_price_returns_none():
    idx = pd.date_range("2020-12-01", periods=2, freq="MS")
    short = pd.Series(100_000.0, index=idx)
    # Offset 6 falls outside the 2-month series -> no revenue.
    assert strategy_revenue(short, 2020, [(6, 1.0)]) is None


def test_seasonal_range_is_small(prices):
    """Headline finding: month barely matters. Seasonal swing stays modest."""
    sp = seasonal_pattern_pct(prices)
    assert sp.index.tolist() == list(range(1, 13))
    swing = sp.max() - sp.min()
    assert swing < 8.0            # small vs the multi-hundred-% trend moves
    assert sp.idxmax() == 11      # November pre-harvest squeeze is the peak
