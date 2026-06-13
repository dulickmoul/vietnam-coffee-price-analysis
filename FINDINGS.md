# When Should a Vietnamese Coffee Farmer Sell?
## A 66-Year Data Analysis — Key Findings (Tier 2)

*Analysis of World Bank/ICO monthly prices (1960–2025) and Lâm Đồng domestic farm-gate prices (2010–2026). Methods: STL decomposition, one-sample t-tests on detrended monthly premiums, volatility regime analysis, and a 15-harvest strategy backtest with storage costs.*

---

## Finding 1 — Trend dominates. Seasonality barely exists.

STL decomposition shows **trend strength of 0.97 vs seasonal strength of 0.009** in Lâm Đồng prices. Translation: which *year* you sell in matters ~100× more than which *month*. The total seasonal swing is only ±3.5% around the average — meanwhile prices tripled between 2022 and 2024.

**Implication for farmers:** Obsessing over the perfect month is optimizing the small lever. The big lever is recognizing multi-year cycles (supply shocks, El Niño years) — and quality premiums.

## Finding 2 — The conventional wisdom about "best month" is partly wrong.

The often-repeated advice is "hold until June–August when supply is tightest." Our trend-free STL seasonal pattern shows the opposite for Lâm Đồng 2010–2026:

| Seasonal HIGH | Seasonal LOW |
|---|---|
| **Oct (+2.6%), Nov (+3.3%), Dec (+1.8%)** | **Apr (−2.7%), May (−3.6%), Jun (−2.0%)** |

Why? The price peak comes in the **pre-harvest squeeze (Oct–Nov)** when old-crop stocks are nearly exhausted but the new harvest hasn't fully hit the market. The trough comes **Jan–May** when the harvest volume has fully flooded local buying stations. The "June–August premium" narrative reflects the within-crop-year pattern (prices recover from the post-harvest dump), but in calendar terms, a farmer holding beans from December is selling into a *recovering* market, not a peak one.

**Caveat stated honestly:** the 2010–2026 window contains the 2023–24 supercycle where prices rose continuously into harvest. Some of the Oct–Nov premium is supercycle bleed-through. The 66-year world price series shows almost no stable monthly seasonality at all (no month statistically significant, all |premium| < 1.5%).

## Finding 3 — The strategy backtest: holding wins small on average, loses often.

Simulating 5 selling strategies across 15 harvests (2010–2024), with 0.5%/month storage loss:

| Strategy | Avg VND/kg | vs. selling at harvest |
|---|---|---|
| Hold to September | 48,973 | **+3.0%** |
| Quarterly tranches (25% × 4) | 48,409 | +1.8% |
| Hold to June | 47,678 | +0.2% |
| Two-batch (Dec + Jun) | 47,622 | +0.1% |
| Sell at harvest (Dec) | 47,567 | baseline |

**The twist:** "Sell at harvest" won 9 of 15 individual years. "Hold to September" won only 4 — but those 4 included the supercycle years where holding paid massively. Holding is a **positive-expectation, high-variance strategy whose entire premium comes from rare big years.**

For a 5-tonne smallholder, the best strategy earned **~105 million VND more over 15 harvests** (~7M VND/year) than harvest-time selling — meaningful but not life-changing, and it required the discipline (and cash buffer) to hold through 11 years where it didn't pay.

**Practical recommendation that survives the data:** quarterly tranches. It captured 60% of the holding premium with lower variance and guaranteed cash flow — the realistic strategy for a farmer who has bills to pay.

## Finding 4 — Volatility regimes: the market is structurally calmer than the 1990s, except when it isn't.

| Era | Annualized volatility | Max drawdown |
|---|---|---|
| ICA Regulated (1962–89) | 22.7% | −74% |
| Post-ICA crash (1989–94) | **34.3%** | −43% |
| Free market (1995–2009) | 23.4% | **−84%** |
| Modern era (2010–22) | **15.6%** | −48% |
| Supercycle (2023–25) | 27.6% | −37% |

The 2000–04 price crisis remains the deepest drawdown in coffee history (−84%). The modern era was the calmest until the supercycle re-ignited volatility. A farmer's "worst case" planning number should not come from the last decade.

---

## Data & methods notes
- World Bank Pink Sheet (ICO indicator prices), 792 monthly observations, 1960–2025
- Lâm Đồng farm-gate series: USDA GAIN local price digitization + trade press + curated benchmarks, with documented −400 VND/kg Lâm Đồng discount vs Đắk Lắk benchmark
- STL: robust=True, period=12; significance: one-sample t-test on within-year relative prices
- Backtest assumes 0.5%/month storage loss, no financing cost, sells at monthly average price
- Limitation: domestic series is partly reconstructed (2010–2014 from press benchmarks); pre-2010 domestic farm-gate prices are not publicly available in machine-readable form

---

# TIER 3 — What Actually Drives Vietnamese Coffee Prices?

*Drivers tested on 792 months (1960–2025): NOAA ONI (El Niño index), Brent crude, Arabica prices. Methods: lagged cross-correlation, OLS with Newey-West HAC errors, event study.*

## Finding 5 — El Niño leads Robusta prices by exactly 13 months.

Cross-correlating the ONI index against 12-month price changes at every lag from 0–24 months, the correlation peaks at **lag 13 (r = +0.115)** — independently replicating the published academic finding that ENSO affects coffee prices at a 13–15 month lag. The mechanism: El Niño drought hits the Central Highlands → the *next* harvest (12–14 months later) is short → prices rally.

**Practical rule for farmers:** when NOAA declares a strong El Niño, expect elevated prices roughly one year later — that's the harvest to consider holding.

## Finding 6 — Event study: +14% one year after an El Niño peak.

Across the 8 strongest El Niño events since 1965 (ONI ≥ 1.5), the average Robusta price path:

| Months after peak | Avg price (peak = 100) |
|---|---|
| +6 | 106.5 |
| +12 | **114.2** |
| +18 | **118.4** |
| +24 | 108.8 (fading) |

The rally builds for ~18 months, then fades as replanting and supply response kick in. The 2023–24 supercycle followed this script almost perfectly — just with a bigger amplitude.

## Finding 7 — Arabica is the dominant co-mover; oil is noise.

Multivariate regression on 12-month Robusta changes (R² = 0.60):
- **Arabica price changes: coef 0.74, p < 0.001.** A 10% Arabica move associates with a 7.4% Robusta move. The two markets are one global coffee complex — substitution by roasters transmits shocks between them.
- ONI (13-mo lag): positive but weakened to p = 0.18 once Arabica is included — because El Niño hits Brazil's Arabica too, so the Arabica term absorbs much of the climate signal.
- Brent oil: insignificant (p = 0.37). Input-cost stories about fuel driving coffee prices don't hold at this frequency.

**Takeaway for the LinkedIn writeup:** watch Brazil and the Arabica board, not the oil price. And watch the ENSO forecast — it's the only publicly available 12-month leading indicator a farmer can use for free.

---

# TIER 4 — Can Any Model Forecast Coffee Prices? (Stress Test)

*Six models (Naive, Seasonal Naive, SARIMA, Holt-Winters, Prophet, XGBoost) tested on two splits: a "normal era" test (2015–19) and the supercycle stress test (2021–25, trained on 1990–2020). Static multi-step and rolling 1-step-ahead modes.*

## Finding 8 — Every standard model catastrophically missed the supercycle.

Static 5-year-ahead forecasts trained on 1990–2020:

| Model | Normal era MAPE | Supercycle MAPE |
|---|---|---|
| SARIMA | **16.1%** (best) | 43.1% |
| Holt-Winters | 19.0% | 39.9% |
| Prophet | 46.9% (worst) | 35.0% |
| XGBoost | 19.5% | **30.9%** (least bad) |
| Naive | 17.7% | 43.4% |

No model trained on 30 years of history came close to predicting the 2024 spike to $4.50/kg — because nothing like it existed in the training data. XGBoost "won" only because its recursive forecasts drifted upward; it did not foresee the spike.

## Finding 9 — At one-month horizon, fancy models barely beat "tomorrow = today."

Rolling 1-step-ahead forecasts (refit every month) through the supercycle:

| Model | MAPE | Directional accuracy |
|---|---|---|
| SARIMA | 5.1% | **67.8%** |
| Naive (last value) | 5.4% | — |
| Holt-Winters | 5.4% | 45.8% |
| XGBoost | 6.0% | 45.8% |

SARIMA's error advantage over naive is just 0.3 percentage points. Coffee prices are close to a random walk at monthly frequency. SARIMA's real edge is **directional**: it called the up/down direction correctly 68% of months — meaningfully better than a coin flip, and the only forecast output a farmer could actually use.

## Finding 10 — The honest conclusion of the whole project.

1. **Forecasting the level is nearly futile**; supercycles are regime breaks that history-based models cannot see coming.
2. **The usable signals are structural, not statistical curve-fits:** the 13-month El Niño lead (Tier 3), the Arabica co-movement, and the pre-harvest seasonal squeeze (Tier 2).
3. **For the farmer**, the data supports a simple playbook: sell in tranches by default; tilt toward holding when (a) NOAA has declared a strong El Niño in the past year, or (b) the Arabica board is rallying hard. Ignore oil prices and ignore precise month-timing.

*This "models fail, structure wins" narrative is the project's intellectual spine — it demonstrates statistical maturity rather than naive ML enthusiasm.*
