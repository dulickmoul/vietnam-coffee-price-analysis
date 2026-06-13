# When Should a Vietnamese Coffee Farmer Sell? ☕

**A 66-year data analysis of Robusta & Arabica prices — built to answer one real question my parents ask every harvest in Lâm Đồng, Vietnam.**

My family grows coffee in Di Linh, Lâm Đồng — the heart of Vietnam's Central Highlands coffee belt. After every harvest comes the same dilemma: *sell now, or hold?* Coffee only keeps about a year (two with proper storage), fertilizer bills don't wait, and prices swung from 42,000 to 131,000 and back to 85,000 VND/kg in just three years.

So I pulled **792 months of price data (1960–2025)** and tested the conventional wisdom properly.

---

## Key findings

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **The year matters ~100× more than the month.** | STL trend strength 0.97 vs seasonal strength 0.009 |
| 2 | **"Best month to sell" advice is mostly myth.** Seasonality is only ±3.5%; the peak is the Oct–Nov pre-harvest squeeze, not the mid-year window folklore suggests | Trend-free STL seasonal pattern, 2010–2026 |
| 3 | **Selling in 4 tranches wins risk-adjusted.** It captured 60% of the maximum holding premium, with lower variance and cash flow aligned to fertilizer payments | 15-harvest backtest, 5 strategies, storage costs modeled |
| 4 | **El Niño is a free 12-month leading indicator.** Prices averaged +14% twelve months after each of the 8 major El Niño peaks since 1965. You don't store coffee longer — you just learn *which crop year to be patient with* | Event study + lag-13 cross-correlation (r=+0.115), replicating published research |
| 5 | **Oil prices are noise; Arabica is the signal.** Arabica co-movement coef 0.74 (p<0.001); Brent insignificant | OLS with Newey-West HAC errors, n=779 |
| 6 | **No model can forecast the spikes.** SARIMA, Prophet, and XGBoost all missed the 2024 supercycle by 30–43% MAPE. At 1-month horizon, SARIMA beats naive by only 0.3pp — coffee is near a random walk | Dual-split stress test, static + rolling modes |

Full writeup: [`FINDINGS.md`](FINDINGS.md)

---

## The headline chart

`analysis/charts/supercycle_stress_test.png` — six standard forecasting models, trained on 30 years of data, all flatlining while the actual 2024 price rockets past them. *Nothing in history prepared any model for $4.50/kg Robusta.*

---

## Repo structure

```
├── FINDINGS.md                     # Full analysis writeup (10 findings)
├── data/
│   ├── coffee_prices_usd_monthly.csv      # 792 months, ICO/World Bank, 1960–2025
│   ├── coffee_prices_vnd_monthly.csv      # + USD/VND conversion
│   ├── lamdong_coffee_prices_monthly.csv  # Lâm Đồng farm-gate, 2010–2026
│   └── usdvnd_annual.csv                  # Exchange rates, 1960–2024
├── scripts/
│   ├── pull_coffee_prices.py       # World Bank Pink Sheet + FX pipeline
│   ├── pull_lamdong_prices.py      # Domestic price assembly (USDA GAIN + curated)
│   ├── tier2_analysis.py           # STL decomposition, seasonality, volatility
│   ├── tier2b_backtest.py          # 5-strategy farmer selling backtest
│   ├── tier3_drivers.py            # ENSO/oil/Arabica driver analysis
│   └── tier4_forecast.py           # 6-model forecast comparison + stress test
└── analysis/
    ├── charts/                     # 9 publication-ready charts
    └── *.csv                       # All intermediate results
```

## Reproduce it

```bash
pip install pandas numpy openpyxl requests statsmodels scipy matplotlib xgboost prophet

python scripts/pull_coffee_prices.py    # downloads fresh World Bank + FX data
python scripts/pull_lamdong_prices.py   # builds domestic series
python scripts/tier2_analysis.py        # seasonality + volatility
python scripts/tier2b_backtest.py       # strategy backtest
python scripts/tier3_drivers.py         # downloads NOAA ENSO, runs driver analysis
python scripts/tier4_forecast.py        # forecast comparison (slow: rolling refits)
```

All data sources are free and public: World Bank Pink Sheet (ICO indicator prices), World Bank API (FX), NOAA PSL (ONI index), USDA FAS GAIN reports.

## Data honesty notes

- The Lâm Đồng domestic series for 2010–2014 is reconstructed from trade press benchmarks; 2015+ is anchored to USDA GAIN local price series. Pre-2010 farm-gate prices are not publicly available in machine-readable form.
- The Lâm Đồng −400 VND/kg discount vs the Đắk Lắk benchmark is documented across USDA, Kamereo, and Vietnambiz price tables.
- Pre-1990 VND conversions use the *official* exchange rate, which diverged heavily from market rates before Đổi Mới.
- The backtest assumes 0.5%/month storage loss — conservative for unprotected jute bags, realistic with hermetic liners.

## About

Built by **[Du Lick Moul](https://www.linkedin.com/in/du-lick-moul/)** — data coordinator & freelance data specialist from a coffee-farming family in Di Linh, Lâm Đồng, Vietnam. The best part of this project was explaining a backtest to my mom in Vietnamese.

*If you work in agri-data, commodity analytics, or just love coffee — [let's connect on LinkedIn](https://www.linkedin.com/in/du-lick-moul/).*
