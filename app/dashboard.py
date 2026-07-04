"""
"Should I Sell?" — interactive Robusta selling-strategy dashboard.

Turns the 66-year analysis in this repo into a tool a Lâm Đồng farmer can
actually use: pick the current month and farm-gate price, and see what each of
the five backtested selling strategies has historically returned — alongside
the honest caveat that the *year* matters ~100× more than the *month*.

The strategy math is imported from scripts/backtest_core.py (the same code the
Tier-2B analysis script uses), so the dashboard and the writeup can never drift.

Run:  streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_core import (  # noqa: E402
    MONTH_NAMES,
    STRATEGIES,
    backtest_strategies,
    seasonal_pattern_pct,
)

# Palette lifted from the repo's charts for visual consistency.
ROBUSTA = "#7B5E3A"
GREEN = "#4A7C59"
RED = "#B94040"

RISK_ADJUSTED_PICK = "S3 Quarterly tranches"


@st.cache_data
def load_prices():
    """Committed Lâm Đồng monthly farm-gate Robusta series (VND/kg)."""
    df = pd.read_csv(
        ROOT / "data" / "lamdong_coffee_prices_monthly.csv", parse_dates=["date"]
    ).set_index("date")
    return df["lamdong_robusta_vnd_kg"]


@st.cache_data
def compute_backtest(_prices):
    return backtest_strategies(_prices)


@st.cache_data
def compute_seasonal(_prices):
    return seasonal_pattern_pct(_prices)


def main():
    st.set_page_config(page_title="Should I Sell? · Lâm Đồng Coffee", page_icon="☕")

    prices = load_prices()
    latest_date = prices.dropna().index.max()
    latest_price = float(prices.dropna().iloc[-1])

    summary = compute_backtest(prices)
    seasonal = compute_seasonal(prices)

    st.title("☕ Should I Sell? — Lâm Đồng Robusta")
    st.caption(
        "A decision aid built on 15 harvests (2010–2024) of backtested selling "
        "strategies. Not financial advice — history is not a forecast."
    )

    # ── Inputs ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("Your situation")
        month_idx = st.selectbox(
            "Current month",
            options=list(range(1, 13)),
            index=latest_date.month - 1,
            format_func=lambda m: MONTH_NAMES[m - 1],
        )
        price = st.number_input(
            "Current farm-gate price (VND/kg)",
            min_value=0,
            value=int(round(latest_price)),
            step=500,
        )
        tonnes = st.number_input(
            "Harvest size (tonnes)", min_value=0.0, value=5.0, step=0.5
        )
        st.caption(
            f"Latest data point: {latest_date:%b %Y} · "
            f"{latest_price:,.0f} VND/kg"
        )

    # ── This month's seasonal read ────────────────────────────────────────────
    seas_now = seasonal[month_idx]
    st.subheader(f"Where {MONTH_NAMES[month_idx - 1]} sits seasonally")
    c1, c2, c3 = st.columns(3)
    c1.metric("This month's seasonal effect", f"{seas_now:+.1f}%")
    c2.metric("Full-year seasonal swing", f"{seasonal.max() - seasonal.min():.1f} pp")
    c3.metric("Seasonal peak month", MONTH_NAMES[seasonal.idxmax() - 1])
    st.info(
        "**The month barely matters.** The entire seasonal swing is only "
        f"~{seasonal.max() - seasonal.min():.0f} percentage points — the peak is the "
        "Oct–Nov pre-harvest squeeze, not the mid-year window folklore suggests. "
        "Which *crop year* you sell into swings prices by hundreds of percent, so "
        "that is the decision that actually matters."
    )

    # ── Strategy recommendation ───────────────────────────────────────────────
    st.subheader("How the five selling strategies have paid off")
    base = summary.loc[
        summary["strategy"] == "S1 Sell at harvest (Dec)", "avg_vnd_per_kg"
    ].iloc[0]

    table = summary.copy()
    table["premium_vs_harvest_%"] = (table["avg_vnd_per_kg"] - base) / base * 100
    table["your_revenue_M_VND"] = table["avg_vnd_per_kg"] * tonnes * 1000 / 1e6
    display = table.rename(
        columns={
            "strategy": "Strategy",
            "avg_vnd_per_kg": "Avg VND/kg",
            "std": "Volatility (std)",
            "premium_vs_harvest_%": "vs sell-at-harvest",
            "your_revenue_M_VND": f"Your {tonnes:g}t (M VND)",
        }
    )[
        [
            "Strategy",
            "Avg VND/kg",
            "Volatility (std)",
            "vs sell-at-harvest",
            f"Your {tonnes:g}t (M VND)",
        ]
    ]
    st.dataframe(
        display.style.format(
            {
                "Avg VND/kg": "{:,.0f}",
                "Volatility (std)": "{:,.0f}",
                "vs sell-at-harvest": "{:+.1f}%",
                f"Your {tonnes:g}t (M VND)": "{:,.1f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    pick = summary.loc[summary["strategy"] == RISK_ADJUSTED_PICK].iloc[0]
    top = summary.iloc[0]
    st.success(
        f"**Recommended: {RISK_ADJUSTED_PICK}.** It captured most of the holding "
        f"premium (avg {pick['avg_vnd_per_kg']:,.0f} VND/kg) at lower volatility "
        f"(std {pick['std']:,.0f}) than holding to a single month, and it spreads "
        "your cash flow across the year to line up with fertilizer bills. "
        f"The highest raw average was **{top['strategy']}** "
        f"({top['avg_vnd_per_kg']:,.0f} VND/kg) — but that means betting the whole "
        "crop on one month, so its swings are larger."
    )

    at_current = price * tonnes * 1000 / 1e6
    st.caption(
        f"Selling your {tonnes:g}t **today at {price:,.0f} VND/kg** would raise "
        f"~{at_current:,.1f}M VND. The table above is the *historical average* "
        "outcome of each strategy across 2010–2024, not a prediction for this crop."
    )

    # ── Seasonal chart ────────────────────────────────────────────────────────
    st.subheader("True seasonal pattern (STL, trend removed)")
    fig, ax = plt.subplots(figsize=(9, 4))
    vals = [seasonal[m] for m in range(1, 13)]
    colors = [GREEN if v > 0 else RED for v in vals]
    bars = ax.bar(MONTH_NAMES, vals, color=colors, alpha=0.9)
    bars[month_idx - 1].set_edgecolor("#2C1F0E")
    bars[month_idx - 1].set_linewidth(2.5)
    ax.axhline(0, color="#2C1F0E", lw=0.8)
    ax.set_ylabel("Seasonal effect (% of avg price)")
    ax.set_title("Lâm Đồng Robusta — your month highlighted")
    fig.tight_layout()
    st.pyplot(fig)

    with st.expander("Data-honesty notes"):
        st.markdown(
            "- Backtest assumes **0.5%/month storage loss** and a farmer-owned "
            "warehouse (no financing cost).\n"
            "- No model in the companion analysis (SARIMA, Prophet, XGBoost) could "
            "forecast the 2024 price spike — coffee is close to a random walk at "
            "short horizons. Treat every number here as *history, not a forecast*.\n"
            "- Series: committed `data/lamdong_coffee_prices_monthly.csv` "
            f"({prices.dropna().index.min():%b %Y}–{latest_date:%b %Y})."
        )


if __name__ == "__main__":
    main()
