"""
Vietnam Coffee Price History Puller
====================================
Sources:
  - Coffee prices   : World Bank Pink Sheet (ICO indicator)
                      Monthly, 1960-present, USD/kg
                      https://thedocs.worldbank.org/.../CMO-Historical-Data-Monthly.xlsx
  - USD/VND rate    : World Bank API (annual, 1983-present)
                      Indicator PA.NUS.FCRF — official exchange rate
  - For pre-1983    : Historical estimates from IMF/academic sources
                      (Vietnam had fixed/controlled rates; market rates varied wildly)

Output files (all in ./output/):
  coffee_prices_usd_monthly.csv    — raw USD prices, 1960–present
  usdvnd_annual.csv                — USD/VND rates, annual
  coffee_prices_vnd_monthly.csv    — merged, with VND equivalent
  coffee_prices_vnd_annual.csv     — annual averages in both USD and VND
"""

import os
import io
import json
import time
import requests
import pandas as pd
from openpyxl import load_workbook
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
OUTPUT_DIR = "./output"
WB_MONTHLY_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "18675f1d1639c7a34d463f59263ba0a2-0050012025/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
WB_FX_URL = (
    "https://api.worldbank.org/v2/country/VN/indicator/"
    "PA.NUS.FCRF?format=json&per_page=100&mrv=100"
)

# Pre-1983 USD/VND estimates (Vietnam had fixed/controlled official rate,
# effectively 1 USD = 1 VND until Doi Moi liberalisation).
# These reflect the *official* rate — real market rates were much higher.
# Source: IMF IFS, academic estimates (Fforde 1993, Beresford 1988)
PRE1983_VND_RATES = {
    1960: 1.00, 1961: 1.00, 1962: 1.00, 1963: 1.00, 1964: 1.00,
    1965: 1.00, 1966: 1.00, 1967: 1.00, 1968: 1.00, 1969: 1.00,
    1970: 1.00, 1971: 1.00, 1972: 1.00, 1973: 1.00, 1974: 1.00,
    1975: 1.00, 1976: 2.37, 1977: 2.37, 1978: 2.37, 1979: 2.37,
    1980: 2.37, 1981: 8.35, 1982: 8.35,
    # 1983 onward covered by World Bank API
}
# Note: 1976-1982 saw a new "liberation dong" and gradual devaluation.
# These are approximate official rates; black-market was 5-20× higher.

os.makedirs(OUTPUT_DIR, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ── STEP 1: Download World Bank Pink Sheet ────────────────────────────────────
log("Downloading World Bank Pink Sheet (monthly, 1960-present)...")
resp = requests.get(WB_MONTHLY_URL, timeout=60)
resp.raise_for_status()
log(f"  Downloaded {len(resp.content)/1024:.0f} KB")

wb = load_workbook(io.BytesIO(resp.content), read_only=True, data_only=True)
ws = wb["Monthly Prices"]

# Parse: row 5 = column headers, row 6 = units, row 7 onwards = data
headers = None
units = None
data_rows = []

for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 4:           # 0-indexed row 4 = "Row 5" = column names
        headers = list(row)
    elif i == 5:         # units row
        units = list(row)
    elif i >= 6:         # data starts
        if row[0] is None:
            break
        data_rows.append(list(row))

# Find column positions
arabica_col = headers.index("Coffee, Arabica")
robusta_col = headers.index("Coffee, Robusta")
log(f"  Arabica column: {arabica_col}, Robusta column: {robusta_col}")
log(f"  Arabica units: {units[arabica_col]}, Robusta units: {units[robusta_col]}")
log(f"  Total monthly rows: {len(data_rows)}")
log(f"  Date range: {data_rows[0][0]} → {data_rows[-1][0]}")

# Build clean DataFrame
records = []
for row in data_rows:
    date_str = str(row[0])          # e.g. "1960M01"
    year = int(date_str[:4])
    month = int(date_str[5:7])
    arabica = row[arabica_col]
    robusta = row[robusta_col]
    # Replace placeholder strings ('…' etc) with None
    if not isinstance(arabica, (int, float)):
        arabica = None
    if not isinstance(robusta, (int, float)):
        robusta = None
    records.append({
        "date": f"{year}-{month:02d}-01",
        "year": year,
        "month": month,
        "arabica_usd_kg": round(float(arabica), 4) if arabica else None,
        "robusta_usd_kg": round(float(robusta), 4) if robusta else None,
    })

df_usd = pd.DataFrame(records)
df_usd["date"] = pd.to_datetime(df_usd["date"])
df_usd = df_usd.sort_values("date").reset_index(drop=True)

# Save raw USD file
usd_path = os.path.join(OUTPUT_DIR, "coffee_prices_usd_monthly.csv")
df_usd.to_csv(usd_path, index=False)
log(f"  ✓ Saved: {usd_path}  ({len(df_usd)} rows)")
log(f"  Arabica non-null: {df_usd['arabica_usd_kg'].notna().sum()}")
log(f"  Robusta non-null: {df_usd['robusta_usd_kg'].notna().sum()}")


# ── STEP 2: USD/VND Exchange Rates ───────────────────────────────────────────
log("\nFetching USD/VND exchange rate from World Bank API...")
resp2 = requests.get(WB_FX_URL, timeout=30)
resp2.raise_for_status()
fx_data = resp2.json()[1]

fx_records = []
for item in fx_data:
    yr = int(item["date"])
    val = item["value"]
    if val is not None:
        fx_records.append({"year": yr, "usdvnd": round(float(val), 2)})

# Add pre-1983 estimates
for yr, rate in PRE1983_VND_RATES.items():
    if yr not in [r["year"] for r in fx_records]:
        fx_records.append({"year": yr, "usdvnd": rate})

df_fx = pd.DataFrame(fx_records).sort_values("year").reset_index(drop=True)
df_fx["source"] = df_fx["year"].apply(
    lambda y: "World Bank API" if y >= 1983 else "Historical estimate (official rate)"
)

fx_path = os.path.join(OUTPUT_DIR, "usdvnd_annual.csv")
df_fx.to_csv(fx_path, index=False)
log(f"  ✓ Saved: {fx_path}  ({len(df_fx)} rows, {df_fx['year'].min()}–{df_fx['year'].max()})")


# ── STEP 3: Merge — Monthly USD + VND ────────────────────────────────────────
log("\nMerging coffee prices with USD/VND rates...")

# Create a month-level FX table by interpolating annual rates
# We forward-fill annual rate across all months of that year
fx_lookup = dict(zip(df_fx["year"], df_fx["usdvnd"]))

def get_fx(year):
    """Return USD/VND rate for a given year, or nearest available."""
    if year in fx_lookup:
        return fx_lookup[year]
    # Find nearest year
    years = sorted(fx_lookup.keys())
    closest = min(years, key=lambda y: abs(y - year))
    return fx_lookup[closest]

df_merged = df_usd.copy()
df_merged["usdvnd_rate"] = df_merged["year"].apply(get_fx)
df_merged["arabica_vnd_kg"] = (
    df_merged["arabica_usd_kg"] * df_merged["usdvnd_rate"]
).round(0)
df_merged["robusta_vnd_kg"] = (
    df_merged["robusta_usd_kg"] * df_merged["usdvnd_rate"]
).round(0)

# Add human-readable month label
df_merged["period"] = df_merged["date"].dt.strftime("%Y-%m")
df_merged["month_name"] = df_merged["date"].dt.strftime("%b %Y")

# Reorder columns
df_merged = df_merged[[
    "date", "period", "year", "month", "month_name",
    "arabica_usd_kg", "robusta_usd_kg",
    "usdvnd_rate",
    "arabica_vnd_kg", "robusta_vnd_kg",
]]

vnd_monthly_path = os.path.join(OUTPUT_DIR, "coffee_prices_vnd_monthly.csv")
df_merged.to_csv(vnd_monthly_path, index=False)
log(f"  ✓ Saved: {vnd_monthly_path}  ({len(df_merged)} rows)")


# ── STEP 4: Annual Summary ────────────────────────────────────────────────────
log("\nBuilding annual summary...")

df_annual = df_merged.groupby("year").agg(
    arabica_usd_avg   = ("arabica_usd_kg",  "mean"),
    arabica_usd_min   = ("arabica_usd_kg",  "min"),
    arabica_usd_max   = ("arabica_usd_kg",  "max"),
    robusta_usd_avg   = ("robusta_usd_kg",  "mean"),
    robusta_usd_min   = ("robusta_usd_kg",  "min"),
    robusta_usd_max   = ("robusta_usd_kg",  "max"),
    usdvnd_rate       = ("usdvnd_rate",     "first"),
    arabica_vnd_avg   = ("arabica_vnd_kg",  "mean"),
    robusta_vnd_avg   = ("robusta_vnd_kg",  "mean"),
    months_available  = ("arabica_usd_kg",  "count"),
).reset_index()

# Round
for col in ["arabica_usd_avg","arabica_usd_min","arabica_usd_max",
            "robusta_usd_avg","robusta_usd_min","robusta_usd_max"]:
    df_annual[col] = df_annual[col].round(3)
for col in ["arabica_vnd_avg","robusta_vnd_avg"]:
    df_annual[col] = df_annual[col].round(0)

annual_path = os.path.join(OUTPUT_DIR, "coffee_prices_vnd_annual.csv")
df_annual.to_csv(annual_path, index=False)
log(f"  ✓ Saved: {annual_path}  ({len(df_annual)} rows)")


# ── STEP 5: Summary Stats ─────────────────────────────────────────────────────
log("\n" + "="*60)
log("SUMMARY STATISTICS")
log("="*60)

robusta = df_merged["robusta_usd_kg"].dropna()
arabica = df_merged["arabica_usd_kg"].dropna()

log(f"\n  ROBUSTA (USD/kg, {df_merged['year'].min()}–{df_merged['year'].max()})")
log(f"    Records    : {len(robusta)}")
log(f"    All-time low : ${robusta.min():.2f} ({df_merged.loc[df_merged['robusta_usd_kg'].idxmin(),'period']})")
log(f"    All-time high: ${robusta.max():.2f} ({df_merged.loc[df_merged['robusta_usd_kg'].idxmax(),'period']})")
log(f"    Overall avg  : ${robusta.mean():.2f}")
log(f"    2000-2010 avg: ${df_merged[df_merged['year'].between(2000,2010)]['robusta_usd_kg'].mean():.2f}")
log(f"    2011-2020 avg: ${df_merged[df_merged['year'].between(2011,2020)]['robusta_usd_kg'].mean():.2f}")
log(f"    2021-2024 avg: ${df_merged[df_merged['year'].between(2021,2024)]['robusta_usd_kg'].mean():.2f}")

log(f"\n  ARABICA (USD/kg)")
log(f"    Records    : {len(arabica)}")
log(f"    All-time low : ${arabica.min():.2f} ({df_merged.loc[df_merged['arabica_usd_kg'].idxmin(),'period']})")
log(f"    All-time high: ${arabica.max():.2f} ({df_merged.loc[df_merged['arabica_usd_kg'].idxmax(),'period']})")
log(f"    Overall avg  : ${arabica.mean():.2f}")

log(f"\n  VND CONVERSION (Robusta, using official USD/VND rate)")
for yr in [1990, 1995, 2000, 2005, 2010, 2015, 2020, 2023, 2024]:
    row = df_annual[df_annual["year"] == yr]
    if not row.empty:
        r = row.iloc[0]
        log(f"    {yr}: ~{r['robusta_vnd_avg']:,.0f} VND/kg  "
            f"(${r['robusta_usd_avg']:.2f}/kg @ {r['usdvnd_rate']:,.0f} VND/USD)")

log(f"\n  OUTPUT FILES:")
for f in ["coffee_prices_usd_monthly.csv", "usdvnd_annual.csv",
          "coffee_prices_vnd_monthly.csv", "coffee_prices_vnd_annual.csv"]:
    path = os.path.join(OUTPUT_DIR, f)
    size = os.path.getsize(path)
    log(f"    {f}  ({size/1024:.1f} KB)")

log("\n✅ Done.")
