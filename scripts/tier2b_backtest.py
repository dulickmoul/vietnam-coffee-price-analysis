"""
TIER 2B — Clean Seasonality + Farmer Strategy Backtest
=======================================================
Key finding from Tier 2A: trend strength 0.97 vs seasonal 0.009.
The naive "monthly premium" is contaminated by trend years (2023-24
prices doubled WITHIN the year, making Oct-Dec look artificially good).

Honest approach:
1. Extract STL seasonal component by month (trend-free seasonal signal)
2. Backtest actual farmer strategies on real prices — this is the
   definitive answer because it accounts for both trend and seasonality.

STRATEGIES TESTED (farmer harvests in Nov-Dec, has X tonnes):
  S1 "Sell at harvest"      — sell 100% in December
  S2 "Hold to mid-year"     — sell 100% in following June
  S3 "Quarterly tranches"   — sell 25% each in Dec, Mar, Jun, Sep
  S4 "Hold to Sep (max)"    — sell 100% in following September
  S5 "Two-batch"            — 50% Dec, 50% June
Costs modeled: storage loss ~0.5%/month (weight loss, quality risk),
  no financing cost assumed (farmer-owned warehouse).
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

OUT = "./analysis"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "#FAF7F2",
    "axes.edgecolor": "#E8E0D5", "axes.grid": True, "grid.color": "#E8E0D5",
    "grid.linewidth": 0.6, "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "figure.dpi": 150,
})
ROBUSTA="#7B5E3A"; ARABICA="#C8924A"; GREEN="#4A7C59"; RED="#B94040"; BLUE="#3A6B8A"

from statsmodels.tsa.seasonal import STL

dom = pd.read_csv("./output/lamdong_coffee_prices_monthly.csv", parse_dates=["date"]).set_index("date")
wb  = pd.read_csv("./output/coffee_prices_vnd_monthly.csv", parse_dates=["date"]).set_index("date")

# ── PART 1: CLEAN STL SEASONAL PATTERN BY MONTH ──────────────────────────────
print("="*70)
print("PART 1 — TREND-FREE SEASONAL PATTERN (STL seasonal component)")
print("="*70)

month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def stl_monthly_seasonal(series, label):
    s = series.dropna()
    res = STL(s, period=12, robust=True).fit()
    seas = res.seasonal.to_frame("seasonal")
    seas["month"] = seas.index.month
    monthly = seas.groupby("month")["seasonal"].mean()
    print(f"\n[{label}] — average STL seasonal component by month:")
    for m in range(1, 13):
        bar = "█" * int(abs(monthly[m]) / max(abs(monthly).max(), 1e-9) * 20)
        sign = "+" if monthly[m] >= 0 else "-"
        print(f"  {month_names[m-1]}: {monthly[m]:>+8.1f}  {sign}{bar}")
    return monthly

seas_dom = stl_monthly_seasonal(dom["lamdong_robusta_vnd_kg"], "Lâm Đồng VND/kg 2010-2026")
seas_wb  = stl_monthly_seasonal(wb["robusta_usd_kg"]*1000, "World ICO USD (×1000 for scale) 1960-2025")

# Express domestic seasonal as % of mean price
mean_dom = dom["lamdong_robusta_vnd_kg"].mean()
seas_dom_pct = seas_dom / mean_dom * 100
print(f"\n[Lâm Đồng seasonal as % of avg price ({mean_dom:,.0f} VND/kg)]")
best_m = seas_dom_pct.idxmax(); worst_m = seas_dom_pct.idxmin()
for m in range(1, 13):
    print(f"  {month_names[m-1]}: {seas_dom_pct[m]:>+5.2f}%")
print(f"\n  → Seasonal HIGH month: {month_names[best_m-1]} ({seas_dom_pct[best_m]:+.2f}%)")
print(f"  → Seasonal LOW month : {month_names[worst_m-1]} ({seas_dom_pct[worst_m]:+.2f}%)")
print(f"  → Total seasonal range: {seas_dom_pct.max()-seas_dom_pct.min():.2f} percentage points")
print("  → CONCLUSION: seasonality is real but SMALL relative to trend moves.")

# ── PART 2: STRATEGY BACKTEST ────────────────────────────────────────────────
print("\n" + "="*70)
print("PART 2 — FARMER STRATEGY BACKTEST (2010-2025 harvests)")
print("="*70)

prices = dom["lamdong_robusta_vnd_kg"].copy()

# Strategy math now lives in scripts/backtest_core.py — a single source of truth
# shared with the "Should I Sell?" dashboard (app/dashboard.py).
from backtest_core import (
    STRATEGIES as strategies,
    backtest_strategies,
    backtest_by_year,
)

harvest_years = range(2010, 2025)  # 2010..2024 harvests (2024 harvest sells into 2025)

summary = backtest_strategies(prices, harvest_years)
print(f"\n{'Strategy':<28} {'Avg VND/kg':>11} {'Std':>9}")
print("-"*52)
for _, r in summary.iterrows():
    print(f"{r['strategy']:<28} {r['avg_vnd_per_kg']:>11,.0f} {r['std']:>9,.0f}")

base_rev = summary[summary["strategy"]=="S1 Sell at harvest (Dec)"]["avg_vnd_per_kg"].values[0]
print(f"\nPremium vs selling at harvest (S1):")
for _, r in summary.iterrows():
    if r["strategy"] != "S1 Sell at harvest (Dec)":
        diff = r["avg_vnd_per_kg"] - base_rev
        pct = diff / base_rev * 100
        print(f"  {r['strategy']:<28} {diff:>+9,.0f} VND/kg  ({pct:+.1f}%)")

# Per-year winner analysis
print(f"\nYear-by-year winner:")
all_years = backtest_by_year(prices, harvest_years)
all_years["winner"] = all_years.idxmax(axis=1)
win_counts = all_years["winner"].value_counts()
for s, c in win_counts.items():
    print(f"  {s:<28} won {c}/{len(all_years)} harvest years")

# Concrete money example: 5-tonne farmer
print(f"\n5-TONNE FARMER EXAMPLE (typical smallholder, 2010-2024 harvests):")
for _, r in summary.iterrows():
    total_m = r["avg_vnd_per_kg"] * 5000 / 1e6
    print(f"  {r['strategy']:<28} {total_m:>8,.1f}M VND/year average")
s_best = summary.iloc[0]
diff_total = (s_best["avg_vnd_per_kg"] - base_rev) * 5000 * 15 / 1e6
print(f"\n  → Over 15 harvests, best strategy ({s_best['strategy']}) earned")
print(f"    {diff_total:,.0f}M VND more than selling at harvest (5-tonne farm).")

# Save
all_years.to_csv(f"{OUT}/strategy_backtest_by_year.csv")
summary.to_csv(f"{OUT}/strategy_backtest_summary.csv", index=False)

# ── CHART: strategy comparison ───────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5),
                                gridspec_kw={"width_ratios": [1.1, 2]})

# Left: average revenue bars
colors = [GREEN if s == summary.iloc[0]["strategy"] else ROBUSTA for s in summary["strategy"]]
ax1.barh(summary["strategy"].str[:20], summary["avg_vnd_per_kg"]/1000, color=colors, alpha=0.9)
ax1.set_xlabel("Avg revenue (K VND/kg)")
ax1.set_title("Strategy Average Revenue\n(2010–2024 harvests)")
ax1.invert_yaxis()

# Right: year-by-year lines
for s in strategies:
    series = all_years[s]
    lw = 2.2 if s == summary.iloc[0]["strategy"] else 1.1
    alpha = 1.0 if s == summary.iloc[0]["strategy"] else 0.55
    ax2.plot(series.index, series.values/1000, label=s[:24], lw=lw, alpha=alpha)
ax2.set_xlabel("Harvest year")
ax2.set_ylabel("Revenue (K VND/kg)")
ax2.set_title("Revenue per kg by Strategy and Harvest Year")
ax2.legend(fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT}/strategy_backtest.png", bbox_inches="tight")
plt.close()
print(f"\n  ✓ Chart: strategy_backtest.png")

# ── CHART: clean seasonal pattern ────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 5))
vals = [seas_dom_pct[m] for m in range(1,13)]
cols = [GREEN if v > 0 else RED for v in vals]
ax.bar(month_names, vals, color=cols, alpha=0.9)
ax.axhline(0, color="#2C1F0E", lw=0.8)
ax.set_ylabel("Seasonal effect (% of avg price)")
ax.set_title("True Seasonal Pattern — Lâm Đồng Robusta (STL, trend removed)")
for i, v in enumerate(vals):
    ax.text(i, v + (0.05 if v > 0 else -0.12), f"{v:+.1f}%", ha="center", fontsize=8)
plt.tight_layout()
plt.savefig(f"{OUT}/clean_seasonal_pattern.png", bbox_inches="tight")
plt.close()
print(f"  ✓ Chart: clean_seasonal_pattern.png")

print("\n✅ Backtest complete.")
