"""
TIER 2 ANALYSIS — Vietnam Coffee Prices
========================================
1. STL seasonal decomposition (Robusta, 1960-2025 World Bank + 2010-2026 domestic)
2. Monthly seasonality premium table with statistical significance
3. Volatility regime analysis (ICA era vs free market vs supercycle)
4. Key statistics for the portfolio writeup
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from statsmodels.tsa.seasonal import STL
from scipy import stats
import os

OUT = "./analysis"
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "#FAF7F2",
    "axes.edgecolor": "#E8E0D5", "axes.grid": True, "grid.color": "#E8E0D5",
    "grid.linewidth": 0.6, "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "figure.dpi": 150,
})
ROBUSTA = "#7B5E3A"; ARABICA = "#C8924A"; GREEN = "#4A7C59"; RED = "#B94040"; BLUE = "#3A6B8A"

# ── LOAD ──────────────────────────────────────────────────────────────────────
wb = pd.read_csv("./output/coffee_prices_vnd_monthly.csv", parse_dates=["date"])
dom = pd.read_csv("./output/lamdong_coffee_prices_monthly.csv", parse_dates=["date"])

wb = wb.set_index("date")
dom = dom.set_index("date")

print("="*70)
print("PART 1 — STL SEASONAL DECOMPOSITION")
print("="*70)

# ── 1A: STL on World Bank Robusta (full 66 years) ────────────────────────────
series_wb = wb["robusta_usd_kg"].dropna()
stl_wb = STL(series_wb, period=12, robust=True).fit()

# Seasonal strength metric (Hyndman): 1 - Var(resid)/Var(seasonal+resid)
def seasonal_strength(stl_result):
    resid = stl_result.resid
    seas = stl_result.seasonal
    return max(0, 1 - np.var(resid) / np.var(seas + resid))

def trend_strength(stl_result):
    resid = stl_result.resid
    trend = stl_result.trend
    return max(0, 1 - np.var(resid) / np.var(trend + resid))

ss_wb = seasonal_strength(stl_wb)
ts_wb = trend_strength(stl_wb)
print(f"\n[World Bank Robusta USD, 1960-2025]")
print(f"  Seasonal strength: {ss_wb:.3f}  (0=none, 1=fully seasonal)")
print(f"  Trend strength   : {ts_wb:.3f}")

# ── 1B: STL on domestic VND prices (2010-2026) ───────────────────────────────
series_dom = dom["lamdong_robusta_vnd_kg"].dropna()
stl_dom = STL(series_dom, period=12, robust=True).fit()
ss_dom = seasonal_strength(stl_dom)
ts_dom = trend_strength(stl_dom)
print(f"\n[Lâm Đồng domestic VND, 2010-2026]")
print(f"  Seasonal strength: {ss_dom:.3f}")
print(f"  Trend strength   : {ts_dom:.3f}")

# Plot STL decomposition for domestic prices
fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)
axes[0].plot(series_dom.index, series_dom.values/1000, color=ROBUSTA, lw=1.4)
axes[0].set_title("Lâm Đồng Robusta Price — STL Decomposition (2010–2026)")
axes[0].set_ylabel("Price (K VND/kg)")
axes[1].plot(stl_dom.trend.index, stl_dom.trend.values/1000, color=BLUE, lw=1.6)
axes[1].set_ylabel("Trend (K VND)")
axes[2].plot(stl_dom.seasonal.index, stl_dom.seasonal.values/1000, color=GREEN, lw=1.2)
axes[2].set_ylabel("Seasonal (K VND)")
axes[3].plot(stl_dom.resid.index, stl_dom.resid.values/1000, color=RED, lw=0.9)
axes[3].set_ylabel("Residual (K VND)")
axes[3].set_xlabel("Year")
plt.tight_layout()
plt.savefig(f"{OUT}/stl_decomposition_lamdong.png", bbox_inches="tight")
plt.close()
print(f"  ✓ Chart: stl_decomposition_lamdong.png")

# ── PART 2: MONTHLY SEASONALITY PREMIUM TABLE ────────────────────────────────
print("\n" + "="*70)
print("PART 2 — MONTHLY SEASONALITY: WHEN IS THE BEST TIME TO SELL?")
print("="*70)

# Method: for each year, compute each month's price relative to that year's mean
# (removes trend contamination). Then test each month's mean relative deviation.

def monthly_premium_analysis(df, price_col, label, min_years=5):
    d = df.copy()
    d = d.dropna(subset=[price_col])
    d["year"] = d.index.year
    d["month"] = d.index.month
    # Relative price: month price / year average (detrended within year)
    year_means = d.groupby("year")[price_col].transform("mean")
    d["rel"] = d[price_col] / year_means * 100  # 100 = year average

    results = []
    for m in range(1, 13):
        vals = d[d["month"] == m]["rel"]
        if len(vals) < min_years:
            continue
        t, p = stats.ttest_1samp(vals, 100)
        results.append({
            "month": m,
            "n_years": len(vals),
            "avg_rel_price": vals.mean(),
            "premium_vs_avg_%": vals.mean() - 100,
            "std": vals.std(),
            "t_stat": t,
            "p_value": p,
            "significant_5%": "YES" if p < 0.05 else "no",
        })
    res = pd.DataFrame(results)
    print(f"\n[{label}]")
    print(f"{'Month':>5} {'AvgRel':>8} {'Premium%':>9} {'p-value':>9} {'Sig?':>5}")
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    for _, r in res.iterrows():
        print(f"{month_names[int(r['month'])-1]:>5} {r['avg_rel_price']:>8.1f} "
              f"{r['premium_vs_avg_%']:>+8.1f}% {r['p_value']:>9.4f} {r['significant_5%']:>5}")
    return res

# Domestic prices (what the farmer actually gets)
prem_dom = monthly_premium_analysis(dom, "lamdong_robusta_vnd_kg", 
                                     "Lâm Đồng domestic VND/kg, 2010-2026")

# World Bank long-run (66 years — robust seasonal signal)
prem_wb = monthly_premium_analysis(wb, "robusta_usd_kg",
                                    "World Bank Robusta USD/kg, 1960-2025")

prem_dom.to_csv(f"{OUT}/seasonality_premium_domestic.csv", index=False)
prem_wb.to_csv(f"{OUT}/seasonality_premium_worldbank.csv", index=False)

# Chart: monthly premium comparison
month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
fig, ax = plt.subplots(figsize=(11, 5.5))
x = np.arange(12)
w = 0.38
dom_vals = [prem_dom[prem_dom["month"]==m+1]["premium_vs_avg_%"].values[0] if len(prem_dom[prem_dom["month"]==m+1]) else 0 for m in range(12)]
wb_vals  = [prem_wb[prem_wb["month"]==m+1]["premium_vs_avg_%"].values[0] if len(prem_wb[prem_wb["month"]==m+1]) else 0 for m in range(12)]
colors_dom = [GREEN if v > 0 else RED for v in dom_vals]
ax.bar(x - w/2, dom_vals, w, label="Lâm Đồng VND (2010–2026)", color=colors_dom, alpha=0.9)
ax.bar(x + w/2, wb_vals, w, label="World ICO USD (1960–2025)", color=BLUE, alpha=0.55)
ax.axhline(0, color="#2C1F0E", lw=0.8)
ax.set_xticks(x); ax.set_xticklabels(month_names)
ax.set_ylabel("Premium vs year average (%)")
ax.set_title("Monthly Price Premium — Best & Worst Months to Sell Coffee")
ax.legend()
# Annotate harvest window
ax.axvspan(9.5, 11.5, alpha=0.08, color=RED)
ax.axvspan(-0.5, 0.5, alpha=0.08, color=RED)
ax.text(10.5, ax.get_ylim()[1]*0.9, "HARVEST", ha="center", fontsize=8, color=RED, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT}/monthly_premium.png", bbox_inches="tight")
plt.close()
print(f"\n  ✓ Chart: monthly_premium.png")

# ── PART 3: VOLATILITY REGIMES ───────────────────────────────────────────────
print("\n" + "="*70)
print("PART 3 — VOLATILITY REGIME ANALYSIS")
print("="*70)

wb_r = wb["robusta_usd_kg"].dropna()
returns = wb_r.pct_change().dropna() * 100  # monthly % returns
rolling_vol = returns.rolling(24).std()     # 24-month rolling volatility

eras = {
    "ICA Regulated (1962–1989)":      ("1962-01-01", "1989-06-30"),
    "Post-ICA Crash (1989–1994)":     ("1989-07-01", "1994-12-31"),
    "Free Market (1995–2009)":        ("1995-01-01", "2009-12-31"),
    "Modern Era (2010–2022)":         ("2010-01-01", "2022-12-31"),
    "Supercycle (2023–2025)":         ("2023-01-01", "2025-12-31"),
}

print(f"\n{'Era':<32} {'Mean ret':>9} {'Vol(mo)':>8} {'Ann.vol':>8} {'MaxDD':>7}")
era_stats = []
for name, (start, end) in eras.items():
    r = returns[start:end]
    p = wb_r[start:end]
    # max drawdown
    cummax = p.cummax()
    dd = ((p - cummax) / cummax * 100).min()
    ann_vol = r.std() * np.sqrt(12)
    print(f"{name:<32} {r.mean():>+8.2f}% {r.std():>7.2f}% {ann_vol:>7.1f}% {dd:>6.1f}%")
    era_stats.append({"era": name, "mean_monthly_ret": round(r.mean(),3),
                      "monthly_vol": round(r.std(),3), "annualized_vol": round(ann_vol,1),
                      "max_drawdown_%": round(dd,1)})

pd.DataFrame(era_stats).to_csv(f"{OUT}/volatility_regimes.csv", index=False)

# Volatility chart
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                gridspec_kw={"height_ratios": [2, 1]})
ax1.plot(wb_r.index, wb_r.values, color=ROBUSTA, lw=1.1)
ax1.set_ylabel("Robusta USD/kg")
ax1.set_title("66 Years of Robusta Prices and Volatility Regimes")
# shade eras
era_colors = {"ICA Regulated (1962–1989)": BLUE, "Post-ICA Crash (1989–1994)": RED,
              "Free Market (1995–2009)": GREEN, "Modern Era (2010–2022)": ARABICA,
              "Supercycle (2023–2025)": RED}
for name, (start, end) in eras.items():
    ax1.axvspan(pd.Timestamp(start), pd.Timestamp(end), alpha=0.06,
                color=era_colors[name])
ax2.plot(rolling_vol.index, rolling_vol.values, color=RED, lw=1.2)
ax2.set_ylabel("24-mo rolling vol (%)")
ax2.set_xlabel("Year")
plt.tight_layout()
plt.savefig(f"{OUT}/volatility_regimes.png", bbox_inches="tight")
plt.close()
print(f"\n  ✓ Chart: volatility_regimes.png")

print("\n✅ Tier 2 analysis complete. Files in ./analysis/")
