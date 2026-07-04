"""
Backtest core — pure, importable logic shared by the Tier-2B script and the
"Should I Sell?" dashboard.

This module holds ONLY computation (no printing, no plotting, no file writes),
so both `scripts/tier2b_backtest.py` and `app/dashboard.py` can import the same
functions and there is a single source of truth for the farmer strategy math.

STRATEGIES (farmer harvests Nov–Dec, holds X tonnes; Dec = offset 0):
  S1 "Sell at harvest"    — sell 100% in December
  S2 "Hold to June"       — sell 100% the following June
  S3 "Quarterly tranches" — sell 25% each in Dec, Mar, Jun, Sep
  S4 "Hold to September"  — sell 100% the following September
  S5 "Two-batch"          — 50% Dec, 50% June
Storage loss ~0.5%/month held (weight/quality); no financing cost assumed.
"""

import pandas as pd
from statsmodels.tsa.seasonal import STL

STORAGE_LOSS_PM = 0.005  # 0.5% weight/quality loss per month held

# offset 0 = December of harvest year; offset k = k months later
STRATEGIES = {
    "S1 Sell at harvest (Dec)": [(0, 1.00)],
    "S2 Hold to June":          [(6, 1.00)],
    "S3 Quarterly tranches":    [(0, 0.25), (3, 0.25), (6, 0.25), (9, 0.25)],
    "S4 Hold to September":     [(9, 1.00)],
    "S5 Two-batch (Dec+Jun)":   [(0, 0.50), (6, 0.50)],
}

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sell_month(harvest_year, offset):
    """Return (year, month) for a sale `offset` months after the harvest-year December."""
    base = pd.Timestamp(f"{harvest_year}-12-01")
    target = base + pd.DateOffset(months=offset)
    return target.year, target.month


def _get_price(prices, year, month):
    """Look up a monthly price by (year, month); return None if missing."""
    try:
        return prices.loc[f"{year}-{month:02d}-01"]
    except KeyError:
        return None


def strategy_revenue(prices, harvest_year, legs, storage_loss_pm=STORAGE_LOSS_PM):
    """Revenue per kg for one strategy in one harvest year, or None if any leg's
    price is unavailable. Storage loss is applied per month held."""
    total = 0.0
    for offset, frac in legs:
        yr, mo = sell_month(harvest_year, offset)
        p = _get_price(prices, yr, mo)
        if p is None:
            return None
        effective = p * (1 - storage_loss_pm) ** offset
        total += frac * effective
    return total


def backtest_by_year(prices, harvest_years=range(2010, 2025),
                     strategies=STRATEGIES, storage_loss_pm=STORAGE_LOSS_PM):
    """Return a DataFrame indexed by harvest_year with one column per strategy
    holding revenue-per-kg (NaN where a year is incomplete)."""
    data = {}
    for name, legs in strategies.items():
        data[name] = {
            hy: strategy_revenue(prices, hy, legs, storage_loss_pm)
            for hy in harvest_years
        }
    df = pd.DataFrame(data)
    df.index.name = "harvest_year"
    return df


def backtest_strategies(prices, harvest_years=range(2010, 2025),
                        strategies=STRATEGIES, storage_loss_pm=STORAGE_LOSS_PM):
    """Summary DataFrame (one row per strategy) sorted by avg revenue, with
    columns: strategy, avg_vnd_per_kg, n_harvests, best_year, worst_year, std.
    Mirrors the output of scripts/tier2b_backtest.py."""
    by_year = backtest_by_year(prices, harvest_years, strategies, storage_loss_pm)
    rows = []
    for name in strategies:
        col = by_year[name].dropna()
        rows.append({
            "strategy": name,
            "avg_vnd_per_kg": round(col.mean(), 0),
            "n_harvests": int(col.count()),
            "best_year": int(col.idxmax()),
            "worst_year": int(col.idxmin()),
            "std": round(col.std(), 0),
        })
    return (pd.DataFrame(rows)
            .sort_values("avg_vnd_per_kg", ascending=False)
            .reset_index(drop=True))


def seasonal_pattern_pct(prices):
    """Trend-free STL seasonal component, averaged by calendar month and
    expressed as % of the mean price. Returns a Series indexed 1..12."""
    s = prices.dropna()
    res = STL(s, period=12, robust=True).fit()
    seas = res.seasonal.to_frame("seasonal")
    seas["month"] = seas.index.month
    monthly = seas.groupby("month")["seasonal"].mean()
    return monthly / s.mean() * 100
