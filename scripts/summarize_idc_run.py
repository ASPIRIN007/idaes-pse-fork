#!/usr/bin/env python3
"""
Summarize IDC double-loop output folder into a human-readable report.

Usage:
  python scripts/summarize_idc_run.py /path/to/idc_output_dir
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _safe_read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def _must(df: pd.DataFrame | None, name: str) -> pd.DataFrame:
    if df is None:
        raise FileNotFoundError(f"Required file missing for summary: {name}")
    return df


def _write_plot(df: pd.DataFrame, x_col: str, y_cols: list[str], out: Path, title: str) -> None:
    plt.figure(figsize=(10, 4))
    for col in y_cols:
        if col in df.columns:
            plt.plot(df[x_col], df[col], label=col)
    plt.title(title)
    plt.xlabel(x_col)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()


def summarize(output_dir: Path) -> Path:
    report_dir = output_dir / "idc_summary"
    report_dir.mkdir(exist_ok=True)

    bidder = _safe_read_csv(output_dir / "bidder_detail.csv")
    bidding_model = _safe_read_csv(output_dir / "bidding_model_detail.csv")
    tracker = _safe_read_csv(output_dir / "tracker_detail.csv")
    tracking_model = _safe_read_csv(output_dir / "tracking_model_detail.csv")
    hourly = _safe_read_csv(output_dir / "hourly_summary.csv")
    overall = _safe_read_csv(output_dir / "overall_simulation_output.csv")

    bidding_model = _must(bidding_model, "bidding_model_detail.csv")
    tracking_model = _must(tracking_model, "tracking_model_detail.csv")
    hourly = _must(hourly, "hourly_summary.csv")
    overall = _must(overall, "overall_simulation_output.csv")

    # Add a monotonically increasing row index per file for plotting.
    bidding_model = bidding_model.copy()
    tracking_model = tracking_model.copy()
    hourly = hourly.copy()
    bidding_model["row"] = range(len(bidding_model))
    tracking_model["row"] = range(len(tracking_model))
    hourly["row"] = range(len(hourly))

    # Core KPIs
    k_total_costs = float(overall.iloc[0]["Total costs"]) if "Total costs" in overall.columns else float("nan")
    k_avg_price = float(overall.iloc[0]["Cumulative average price"]) if "Cumulative average price" in overall.columns else float("nan")
    k_total_demand = float(overall.iloc[0]["Total demand"]) if "Total demand" in overall.columns else float("nan")

    k_avg_offer_bid = (
        float(bidding_model["Offered Flexibility P_offer [MW]"].mean())
        if "Offered Flexibility P_offer [MW]" in bidding_model.columns
        else float("nan")
    )
    k_avg_offer_track = (
        float(tracking_model["Offered Flexibility P_offer [MW]"].mean())
        if "Offered Flexibility P_offer [MW]" in tracking_model.columns
        else float("nan")
    )
    k_avg_backlog_bid = (
        float(bidding_model["Backlog"].mean()) if "Backlog" in bidding_model.columns else float("nan")
    )
    k_avg_backlog_track = (
        float(tracking_model["Backlog"].mean()) if "Backlog" in tracking_model.columns else float("nan")
    )

    # Plots
    _write_plot(
        bidding_model,
        "row",
        ["Offered Flexibility P_offer [MW]", "Grid Import [MW]", "Backlog"],
        report_dir / "bidding_signals.png",
        "Bidding Model Signals",
    )
    _write_plot(
        tracking_model,
        "row",
        ["Offered Flexibility P_offer [MW]", "Grid Import [MW]", "Backlog"],
        report_dir / "tracking_signals.png",
        "Tracking Model Signals",
    )
    _write_plot(
        hourly,
        "row",
        ["Price", "Demand", "TotalCosts"],
        report_dir / "market_signals.png",
        "Hourly Market Signals",
    )

    # A short top bids table for readability
    top_bid_rows = ""
    if bidder is not None and not bidder.empty:
        bid_cols = [c for c in ["Date", "Hour", "Market", "Power 0 [MW]", "Power 1 [MW]", "Cost 0 [$]", "Cost 1 [$]"] if c in bidder.columns]
        top_bid_rows = bidder[bid_cols].head(12).to_string(index=False)
    else:
        top_bid_rows = "_bidder_detail.csv missing or empty_"

    report = f"""# IDC Run Summary

Output directory: `{output_dir}`

## Key Metrics
- Total demand: `{k_total_demand:.3f}`
- Total costs: `{k_total_costs:.3f}`
- Cumulative average price: `{k_avg_price:.3f}`
- Avg offered flexibility (bidding model): `{k_avg_offer_bid:.3f}` MW
- Avg offered flexibility (tracking model): `{k_avg_offer_track:.3f}` MW
- Avg backlog (bidding model): `{k_avg_backlog_bid:.3f}`
- Avg backlog (tracking model): `{k_avg_backlog_track:.3f}`

## Quick Read
- `bidding_signals.png`: how IDC bidding model trades off flexibility/import/backlog.
- `tracking_signals.png`: realized tracking behavior.
- `market_signals.png`: market context (price, demand, total costs).

## Sample Bids (first rows)
{top_bid_rows}
"""
    report_path = report_dir / "summary.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    report_path = summarize(args.output_dir)
    print(report_path)


if __name__ == "__main__":
    main()
