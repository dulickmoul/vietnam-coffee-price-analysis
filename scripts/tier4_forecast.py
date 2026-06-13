"""
TIER 4 — FORECAST MODEL COMPARISON + SUPERCYCLE STRESS TEST
============================================================
Question: could ANY standard model have predicted the 2023-25 supercycle?

Design:
  Data    : Robusta USD/kg monthly (World Bank/ICO), 1960-2025
  Split A "Normal test"     : train 1990-2014, test 2015-2019 (calm era)
  Split B "Supercycle test" : train 1990-2020, test 2021-2025 (stress)

Models:
  M1 Naive          (last value carried forward)
  M2 Seasonal naive (value 12 months ago)
  M3 SARIMA(1,1,1)(1,0,1,12)
  M4 Holt-Winters ETS (additive trend+season, damped)
  M5 Prophet
  M6 XGBoost (lags 1-12, month dummies, rolling stats)

Two forecast modes:
  - STATIC: fit once, forecast entire horizon (what naive deployment does)
  - ROLLING: refit each month, 1-step ahead (best realistic case)

Metrics: RMSE, MAPE, plus "directional accuracy" for rolling mode.
"""

import pandas as pd
import numpy as np
import warnings, os, logging
warnings.filterwarnings("ignore")
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from prophet import Prophet
import xgboost as xgb

OUT = "./analysis"
plt.rcParams.update({
    "figure.facecolor":"white","axes.facecolor":"#FAF7F2","axes.edgecolor":"#E8E0D5",
    "axes.grid":True,"grid.color":"#E8E0D5","grid.linewidth":0.6,"font.size":10,
    "axes.titlesize":12,"axes.titleweight":"bold","figure.dpi":150})
ROBUSTA="#7B5E3A"; ARABICA="#C8924A"; GREEN="#4A7C59"; RED="#B94040"; BLUE="#3A6B8A"; PURPLE="#6B4E8A"

df = pd.read_csv("./output/coffee_prices_vnd_monthly.csv", parse_dates=["date"]).set_index("date")
y = df["robusta_usd_kg"].dropna().asfreq("MS")

def mape(a, f): return np.mean(np.abs((a - f) / a)) * 100
def rmse(a, f): return np.sqrt(np.mean((a - f) ** 2))

# ── MODEL WRAPPERS (STATIC MULTI-STEP) ───────────────────────────────────────
def f_naive(train, h):       return np.repeat(train.iloc[-1], h)
def f_snaive(train, h):
    last12 = train.iloc[-12:].values
    return np.tile(last12, int(np.ceil(h/12)))[:h]
def f_sarima(train, h):
    m = SARIMAX(np.log(train), order=(1,1,1), seasonal_order=(1,0,1,12),
                enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    return np.exp(m.forecast(h))
def f_ets(train, h):
    m = ExponentialSmoothing(train, trend="add", damped_trend=True,
                             seasonal="add", seasonal_periods=12).fit()
    return m.forecast(h).values
def f_prophet(train, h):
    tdf = train.reset_index(); tdf.columns = ["ds","y"]
    m = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                daily_seasonality=False)
    m.fit(tdf)
    fut = m.make_future_dataframe(periods=h, freq="MS")
    fc = m.predict(fut)
    return fc["yhat"].iloc[-h:].values

def make_features(series):
    d = pd.DataFrame({"y": series})
    for l in [1,2,3,6,12]:
        d[f"lag{l}"] = d["y"].shift(l)
    d["roll6_mean"] = d["y"].shift(1).rolling(6).mean()
    d["roll12_mean"] = d["y"].shift(1).rolling(12).mean()
    d["mom12"] = d["y"].shift(1) / d["y"].shift(13) - 1
    d["month"] = d.index.month
    return d

def f_xgboost(train, h):
    # Recursive multi-step
    hist = train.copy()
    feats = make_features(hist).dropna()
    X, Y = feats.drop(columns="y"), feats["y"]
    model = xgb.XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.05,
                             subsample=0.9, verbosity=0)
    model.fit(X, Y)
    preds = []
    for i in range(h):
        f = make_features(hist).iloc[[-1]].drop(columns="y")
        # shift index forward one month for prediction context
        p = model.predict(f)[0]
        preds.append(p)
        next_idx = hist.index[-1] + pd.DateOffset(months=1)
        hist = pd.concat([hist, pd.Series([p], index=[next_idx])])
    return np.array(preds)

MODELS = {
    "Naive": f_naive, "Seasonal naive": f_snaive, "SARIMA": f_sarima,
    "Holt-Winters": f_ets, "Prophet": f_prophet, "XGBoost": f_xgboost,
}

# ── EXPERIMENT ────────────────────────────────────────────────────────────────
splits = {
    "A: Normal era (test 2015-2019)":      ("1990-01-01","2014-12-01","2015-01-01","2019-12-01"),
    "B: Supercycle (test 2021-2025)":      ("1990-01-01","2020-12-01","2021-01-01","2025-12-01"),
}

all_results = []
forecasts_store = {}

for split_name, (tr0, tr1, te0, te1) in splits.items():
    train = y[tr0:tr1]
    test  = y[te0:te1]
    h = len(test)
    print("="*70)
    print(f"SPLIT {split_name}  (train {len(train)}mo, test {h}mo)")
    print("="*70)
    print(f"{'Model':<16} {'RMSE':>8} {'MAPE':>8}")
    fc_dict = {}
    for name, fn in MODELS.items():
        try:
            fc = fn(train, h)
            fc = np.asarray(fc, dtype=float)[:h]
            r, m = rmse(test.values, fc), mape(test.values, fc)
            print(f"{name:<16} {r:>8.3f} {m:>7.1f}%")
            all_results.append({"split": split_name, "model": name,
                                "mode": "static", "rmse": round(r,3), "mape": round(m,2)})
            fc_dict[name] = pd.Series(fc, index=test.index)
        except Exception as e:
            print(f"{name:<16} FAILED: {e}")
    forecasts_store[split_name] = (train, test, fc_dict)

# ── ROLLING 1-STEP for supercycle split (realistic deployment) ───────────────
print("\n" + "="*70)
print("ROLLING 1-STEP-AHEAD (refit monthly) — Supercycle test 2021-2025")
print("="*70)
tr0, tr1, te0, te1 = splits["B: Supercycle (test 2021-2025)"]
test = y[te0:te1]
roll_models = {"SARIMA": f_sarima, "Holt-Winters": f_ets, "XGBoost": f_xgboost,
               "Naive": f_naive}
print(f"{'Model':<16} {'RMSE':>8} {'MAPE':>8} {'DirAcc':>8}")
rolling_store = {}
for name, fn in roll_models.items():
    preds = []
    for t in test.index:
        train_t = y[:t - pd.DateOffset(months=1)]
        try:
            p = fn(train_t, 1)
            preds.append(float(np.asarray(p)[0]))
        except Exception:
            preds.append(np.nan)
    preds = pd.Series(preds, index=test.index)
    valid = preds.dropna().index
    r = rmse(test[valid].values, preds[valid].values)
    m = mape(test[valid].values, preds[valid].values)
    # directional accuracy
    actual_dir = np.sign(test[valid].diff().dropna())
    pred_dir = np.sign((preds[valid] - test[valid].shift(1)).dropna())
    common = actual_dir.index.intersection(pred_dir.index)
    da = (actual_dir[common] == pred_dir[common]).mean() * 100
    print(f"{name:<16} {r:>8.3f} {m:>7.1f}% {da:>7.1f}%")
    all_results.append({"split": "B rolling 1-step", "model": name,
                        "mode": "rolling", "rmse": round(r,3), "mape": round(m,2),
                        "dir_acc": round(da,1)})
    rolling_store[name] = preds

pd.DataFrame(all_results).to_csv(f"{OUT}/forecast_model_comparison.csv", index=False)

# ── CHARTS ───────────────────────────────────────────────────────────────────
# Chart 1: supercycle static forecasts vs reality
train, test, fc_dict = forecasts_store["B: Supercycle (test 2021-2025)"]
fig, ax = plt.subplots(figsize=(11.5, 6))
ctx = y["2015-01-01":"2025-12-01"]
ax.plot(ctx.index, ctx.values, color="#2C1F0E", lw=2.2, label="ACTUAL", zorder=10)
colors = {"Naive":"#999","Seasonal naive":ARABICA,"SARIMA":BLUE,
          "Holt-Winters":GREEN,"Prophet":PURPLE,"XGBoost":RED}
for name, fc in fc_dict.items():
    ax.plot(fc.index, fc.values, lw=1.5, ls="--", color=colors[name], label=name, alpha=0.85)
ax.axvline(pd.Timestamp("2021-01-01"), color="#2C1F0E", ls=":", lw=1)
ax.text(pd.Timestamp("2021-02-01"), ax.get_ylim()[1]*0.95, "← train | test →", fontsize=9)
ax.set_ylabel("Robusta USD/kg")
ax.set_title("The Supercycle Stress Test: Every Standard Model Missed 2024\n(static multi-step forecasts, trained on 1990–2020)")
ax.legend(fontsize=8, ncol=2)
plt.tight_layout(); plt.savefig(f"{OUT}/supercycle_stress_test.png", bbox_inches="tight"); plt.close()
print("\n  ✓ Chart: supercycle_stress_test.png")

# Chart 2: rolling forecasts track better
fig, ax = plt.subplots(figsize=(11.5, 5.5))
ax.plot(test.index, test.values, color="#2C1F0E", lw=2.2, label="ACTUAL", zorder=10)
for name, preds in rolling_store.items():
    ax.plot(preds.index, preds.values, lw=1.3, ls="--", color=colors.get(name,"#888"),
            label=f"{name} (rolling)", alpha=0.85)
ax.set_ylabel("Robusta USD/kg")
ax.set_title("Rolling 1-Step Forecasts Track the Supercycle — But Always One Step Behind")
ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(f"{OUT}/rolling_forecasts.png", bbox_inches="tight"); plt.close()
print("  ✓ Chart: rolling_forecasts.png")

print("\n✅ Tier 4 complete.")
