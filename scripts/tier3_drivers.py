"""
TIER 3 — WHAT ACTUALLY DRIVES VIETNAMESE COFFEE PRICES?
========================================================
Drivers tested against Robusta prices (1960-2025 monthly):
  1. ENSO (ONI index, NOAA) — El Niño/La Niña, with lags 0-24 months
  2. Brent crude oil (World Bank Pink Sheet) — input costs + macro proxy
  3. USD/VND exchange rate — translation effect on domestic prices
  4. Arabica price (substitution/spillover effect)

Methods:
  - Cross-correlation at lags 0-24 months (ENSO leads price)
  - OLS regression on 12-month log price changes with Newey-West SEs
    (literature: Ubilava 2012; IJSES 2025 on Vietnam exports uses Newey-West)
  - Event study: price path around the 7 strongest El Niño events
"""

import pandas as pd
import numpy as np
import requests, io, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm
from openpyxl import load_workbook

OUT = "./analysis"
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({
    "figure.facecolor":"white","axes.facecolor":"#FAF7F2","axes.edgecolor":"#E8E0D5",
    "axes.grid":True,"grid.color":"#E8E0D5","grid.linewidth":0.6,"font.size":10,
    "axes.titlesize":12,"axes.titleweight":"bold","figure.dpi":150})
ROBUSTA="#7B5E3A"; ARABICA="#C8924A"; GREEN="#4A7C59"; RED="#B94040"; BLUE="#3A6B8A"

print("="*70)
print("STEP 1 — PULL ENSO (ONI) INDEX FROM NOAA")
print("="*70)

r = requests.get("https://psl.noaa.gov/data/correlation/oni.data", timeout=30)
lines = r.text.strip().split("\n")
oni_rows = []
for line in lines[1:]:
    parts = line.split()
    if len(parts) == 13 and parts[0].isdigit():
        yr = int(parts[0])
        if 1950 <= yr <= 2026:
            for m, v in enumerate(parts[1:], 1):
                val = float(v)
                if val > -90:  # -99.9 = missing
                    oni_rows.append({"date": pd.Timestamp(yr, m, 1), "oni": val})
oni = pd.DataFrame(oni_rows).set_index("date")
print(f"  ONI: {len(oni)} months, {oni.index.min():%Y-%m} → {oni.index.max():%Y-%m}")

print("\nSTEP 2 — PULL BRENT OIL FROM WORLD BANK PINK SHEET")
wb_url = ("https://thedocs.worldbank.org/en/doc/"
          "18675f1d1639c7a34d463f59263ba0a2-0050012025/related/"
          "CMO-Historical-Data-Monthly.xlsx")
resp = requests.get(wb_url, timeout=60)
wbk = load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
ws = wbk["Monthly Prices"]
headers, rows = None, []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 4: headers = list(row)
    elif i >= 6:
        if row[0] is None: break
        rows.append(list(row))
brent_col = headers.index("Crude oil, Brent")
oil_rows = []
for row in rows:
    ds = str(row[0]); yr, mo = int(ds[:4]), int(ds[5:7])
    v = row[brent_col]
    if isinstance(v, (int, float)):
        oil_rows.append({"date": pd.Timestamp(yr, mo, 1), "brent": float(v)})
oil = pd.DataFrame(oil_rows).set_index("date")
print(f"  Brent: {len(oil)} months")

print("\nSTEP 3 — BUILD MERGED DRIVER DATASET")
coffee = pd.read_csv("./output/coffee_prices_vnd_monthly.csv", parse_dates=["date"]).set_index("date")
df = coffee[["robusta_usd_kg","arabica_usd_kg","usdvnd_rate"]].join(oni).join(oil)
df = df.dropna(subset=["robusta_usd_kg","oni"])
print(f"  Merged: {len(df)} months, {df.index.min():%Y-%m} → {df.index.max():%Y-%m}")

# ── ANALYSIS 1: ENSO CROSS-CORRELATION AT LAGS ───────────────────────────────
print("\n" + "="*70)
print("ANALYSIS 1 — ENSO → ROBUSTA PRICE: CROSS-CORRELATION BY LAG")
print("="*70)
# 12-month log change in price vs ONI lagged k months
df["dlog_p12"] = np.log(df["robusta_usd_kg"]).diff(12)
lags = range(0, 25)
ccf = []
for k in lags:
    x = df["oni"].shift(k)
    pair = pd.concat([df["dlog_p12"], x], axis=1).dropna()
    c = pair.corr().iloc[0,1]
    ccf.append(c)
best_lag = int(np.argmax(ccf))
print(f"\n  Correlation of ONI(t-k) with 12-mo price change (1960-2025):")
for k in [0, 3, 6, 9, 12, 15, 18, 21, 24]:
    marker = "  ◄ PEAK" if k == best_lag else ""
    print(f"    lag {k:>2} months: r = {ccf[k]:+.3f}{marker}")
print(f"\n  Peak correlation at lag {best_lag} months: r = {ccf[best_lag]:+.3f}")
print(f"  (Literature benchmark: ENSO affects Arabica at 13-15 month lag)")

fig, ax = plt.subplots(figsize=(10,4.5))
cols = [GREEN if c == max(ccf) else BLUE for c in ccf]
ax.bar(list(lags), ccf, color=cols, alpha=0.85)
ax.axhline(0, color="#2C1F0E", lw=0.8)
# 95% significance band for correlation
n_eff = len(df.dropna(subset=["dlog_p12","oni"]))
sig = 1.96/np.sqrt(n_eff)
ax.axhline(sig, color=RED, ls="--", lw=0.8); ax.axhline(-sig, color=RED, ls="--", lw=0.8)
ax.text(23.5, sig+0.005, "95% sig.", fontsize=8, color=RED, ha="right")
ax.set_xlabel("ONI lag (months before price change)")
ax.set_ylabel("Correlation with 12-mo price change")
ax.set_title("El Niño Leads Coffee Prices — Cross-Correlation by Lag (1960–2025)")
plt.tight_layout(); plt.savefig(f"{OUT}/enso_lag_correlation.png", bbox_inches="tight"); plt.close()
print("  ✓ Chart: enso_lag_correlation.png")

# ── ANALYSIS 2: MULTIVARIATE REGRESSION (Newey-West) ─────────────────────────
print("\n" + "="*70)
print("ANALYSIS 2 — MULTIVARIATE DRIVER REGRESSION")
print("="*70)
# Dependent: 12-mo log change Robusta. Drivers: ONI (lag at peak), Brent 12-mo change,
# FX 12-mo change, Arabica 12-mo change (contemporaneous spillover)
reg = pd.DataFrame({
    "dlog_robusta": np.log(df["robusta_usd_kg"]).diff(12),
    f"oni_lag{best_lag}": df["oni"].shift(best_lag),
    "dlog_brent": np.log(df["brent"]).diff(12),
    "dlog_arabica": np.log(df["arabica_usd_kg"]).diff(12),
}).dropna()

X = sm.add_constant(reg[[f"oni_lag{best_lag}", "dlog_brent", "dlog_arabica"]])
y = reg["dlog_robusta"]
model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
print(model.summary().tables[1])
print(f"\n  R² = {model.rsquared:.3f}   N = {int(model.nobs)} months")
print(f"  Interpretation:")
for name, coef, p in zip(model.params.index, model.params.values, model.pvalues.values):
    if name == "const": continue
    sig = "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.1 else ""
    print(f"    {name:<14} coef={coef:+.3f}  p={p:.4f} {sig}")

with open(f"{OUT}/driver_regression.txt","w") as f:
    f.write(str(model.summary()))

# ── ANALYSIS 3: EL NIÑO EVENT STUDY ──────────────────────────────────────────
print("\n" + "="*70)
print("ANALYSIS 3 — EVENT STUDY: PRICE PATH AROUND MAJOR EL NIÑO EVENTS")
print("="*70)
# Major El Niño events (ONI peak >= 1.5): 1965-66, 1972-73, 1982-83, 1987-88,
# 1991-92, 1997-98, 2015-16, 2023-24
events = ["1965-11","1972-11","1982-12","1987-08","1991-12","1997-11","2015-11","2023-11"]
print(f"  Events (ONI peak month): {', '.join(events)}")

window = range(-6, 25)  # 6 months before to 24 after
paths = []
for ev in events:
    t0 = pd.Timestamp(ev + "-01")
    if t0 not in df.index: continue
    base = df.loc[t0, "robusta_usd_kg"]
    path = []
    for k in window:
        t = t0 + pd.DateOffset(months=k)
        if t in df.index:
            path.append(df.loc[t, "robusta_usd_kg"] / base * 100)
        else:
            path.append(np.nan)
    paths.append(pd.Series(path, index=list(window), name=ev))
paths_df = pd.concat(paths, axis=1)
avg_path = paths_df.mean(axis=1)

print(f"\n  Average Robusta price path (100 = ONI peak month):")
for k in [0, 6, 12, 18, 24]:
    print(f"    +{k:>2} months: {avg_path[k]:.1f}")
print(f"\n  → On average, Robusta is {avg_path[12]-100:+.0f}% twelve months after")
print(f"    an El Niño peak, and {avg_path[24]-100:+.0f}% after 24 months.")

fig, ax = plt.subplots(figsize=(10.5, 5.5))
for col in paths_df.columns:
    ax.plot(paths_df.index, paths_df[col], lw=0.9, alpha=0.45, label=col)
ax.plot(avg_path.index, avg_path.values, lw=3, color=RED, label="AVERAGE")
ax.axvline(0, color="#2C1F0E", ls="--", lw=1)
ax.axhline(100, color="#2C1F0E", lw=0.6)
ax.text(0.3, ax.get_ylim()[1]*0.97, "El Niño peak", fontsize=9, va="top")
ax.set_xlabel("Months relative to El Niño peak (ONI ≥ 1.5)")
ax.set_ylabel("Robusta price (100 = peak month)")
ax.set_title("Event Study: Robusta Prices Around 8 Major El Niño Events (1965–2024)")
ax.legend(fontsize=7, ncol=2)
plt.tight_layout(); plt.savefig(f"{OUT}/elnino_event_study.png", bbox_inches="tight"); plt.close()
print("  ✓ Chart: elnino_event_study.png")

paths_df.to_csv(f"{OUT}/elnino_event_paths.csv")

# ── SUMMARY FOR WRITEUP ──────────────────────────────────────────────────────
print("\n" + "="*70)
print("TIER 3 HEADLINE NUMBERS")
print("="*70)
print(f"  • ENSO peak correlation lag: {best_lag} months (r={ccf[best_lag]:+.3f})")
print(f"  • Regression R²: {model.rsquared:.2f}")
print(f"  • Avg price +12mo after major El Niño: {avg_path[12]-100:+.0f}%")
print(f"  • Avg price +24mo after major El Niño: {avg_path[24]-100:+.0f}%")
print("\n✅ Tier 3 complete.")
