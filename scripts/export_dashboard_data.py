"""
Export the backtest results to a JSON blob and embed it into the static
dashboard at docs/index.html.

The static page is a zero-dependency, single-file "Should I Sell?" tool that
runs entirely in the browser (double-click to open, or host on GitHub Pages).
Its numbers come from scripts/backtest_core.py — the SAME code the Streamlit
app and the Tier-2B analysis use — so all three can never drift.

Run:  python scripts/export_dashboard_data.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backtest_core import (  # noqa: E402
    MONTH_NAMES,
    STRATEGIES,
    backtest_strategies,
    seasonal_pattern_pct,
)

STRATEGY_BLURB = {
    "S1 Sell at harvest (Dec)": "Sell 100% in December, right after harvest.",
    "S2 Hold to June": "Store the whole crop and sell in June.",
    "S3 Quarterly tranches": "Sell 25% each in Dec, Mar, Jun, Sep.",
    "S4 Hold to September": "Store the whole crop and sell in September.",
    "S5 Two-batch (Dec+Jun)": "Sell half in December, half in June.",
}
RISK_ADJUSTED_PICK = "S3 Quarterly tranches"

DATA_TAG = "dashboard-data"  # <script id="dashboard-data" type="application/json">


def build_data():
    prices = pd.read_csv(
        ROOT / "data" / "lamdong_coffee_prices_monthly.csv", parse_dates=["date"]
    ).set_index("date")["lamdong_robusta_vnd_kg"]

    summary = backtest_strategies(prices)
    seasonal = seasonal_pattern_pct(prices)  # Series indexed 1..12
    valid = prices.dropna()
    base = summary.loc[
        summary["strategy"] == "S1 Sell at harvest (Dec)", "avg_vnd_per_kg"
    ].iloc[0]

    strategies = []
    for _, r in summary.iterrows():
        strategies.append({
            "name": r["strategy"],
            "blurb": STRATEGY_BLURB.get(r["strategy"], ""),
            "avg": int(r["avg_vnd_per_kg"]),
            "std": int(r["std"]),
            "best_year": int(r["best_year"]),
            "worst_year": int(r["worst_year"]),
            "premium_pct": round((r["avg_vnd_per_kg"] - base) / base * 100, 1),
            "recommended": r["strategy"] == RISK_ADJUSTED_PICK,
        })

    return {
        "months": MONTH_NAMES,
        "latest": {
            "label": valid.index.max().strftime("%b %Y"),
            "month": int(valid.index.max().month),
            "price": int(round(valid.iloc[-1])),
        },
        "coverage": (
            f"{valid.index.min():%b %Y}–{valid.index.max():%b %Y}"
        ),
        "mean_price": int(round(valid.mean())),
        "n_harvests": int(summary["n_harvests"].iloc[0]),
        "seasonal_pct": [round(float(seasonal[m]), 2) for m in range(1, 13)],
        "seasonal_peak_month": int(seasonal.idxmax()),
        "strategies": strategies,
    }


def main():
    data = build_data()
    payload = json.dumps(data, indent=2, ensure_ascii=False)

    # Keep a standalone JSON copy too (handy for other consumers).
    (ROOT / "docs" / "dashboard_data.json").write_text(payload + "\n", encoding="utf-8")

    # Inject into the embedded <script> block so index.html stays self-contained.
    index = ROOT / "docs" / "index.html"
    html = index.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(<script id="{DATA_TAG}" type="application/json">)(.*?)(</script>)',
        re.DOTALL,
    )
    if not pattern.search(html):
        raise SystemExit(f"Could not find <script id={DATA_TAG}> block in {index}")
    html = pattern.sub(lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3), html)
    index.write_text(html, encoding="utf-8")

    print(f"Embedded {len(data['strategies'])} strategies into {index}")
    print(f"Latest: {data['latest']['label']} @ {data['latest']['price']:,} VND/kg")


if __name__ == "__main__":
    main()
