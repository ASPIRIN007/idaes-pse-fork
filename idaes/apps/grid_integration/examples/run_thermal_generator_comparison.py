#################################################################################
# The Institute for the Design of Advanced Energy Systems Integrated Platform
# Framework (IDAES IP) was produced under the DOE Institute for the
# Design of Advanced Energy Systems (IDAES).
#
# Copyright (c) 2018-2026 by the software owners: The Regents of the
# University of California, through Lawrence Berkeley National Laboratory,
# National Technology & Engineering Solutions of Sandia, LLC, Carnegie Mellon
# University, West Virginia University Research Corporation, et al.
# All rights reserved.  Please see the files COPYRIGHT.md and LICENSE.md
# for full copyright and license information.
#################################################################################
"""
Run the 5-bus thermal-generator example twice and compare outputs.

This script produces:
1. A baseline Prescient run without the double-loop plugin.
2. A plugin-enabled Prescient run using the thermal generator example.
3. Comparison plots and a small summary CSV in a shared plots directory.

Example:
    python -m idaes.apps.grid_integration.examples.run_thermal_generator_comparison
"""

from __future__ import annotations

import argparse
from datetime import datetime
from importlib import resources
import os
from pathlib import Path
import tempfile

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "matplotlib"),
)
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from pyomo.common.dependencies import attempt_import

from idaes.apps.grid_integration.examples.utils import (
    prescient_5bus,
    rts_gmlc_bus_dataframe,
    rts_gmlc_generator_dataframe,
)

prescient_simulator, prescient_avail = attempt_import("prescient.simulator")


def _get_plugin_path() -> Path:
    with resources.as_file(
        resources.files("idaes.apps.grid_integration.examples").joinpath(
            "thermal_generator_prescient_plugin.py"
        )
    ) as plugin_path:
        return Path(plugin_path)


def _make_output_root(output_root: str | None) -> Path:
    if output_root is not None:
        root = Path(output_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parents[4]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = repo_root / "demo_outputs" / f"thermal_generator_compare_{timestamp}"

    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_options(output_dir: Path, num_days: int, reserve_factor: float) -> dict:
    return {
        "data_path": str(prescient_5bus),
        "input_format": "rts-gmlc",
        "simulate_out_of_sample": True,
        "run_sced_with_persistent_forecast_errors": True,
        "output_directory": str(output_dir),
        "start_date": "07-10-2020",
        "num_days": num_days,
        "sced_horizon": 4,
        "ruc_horizon": 48,
        "compute_market_settlements": True,
        "day_ahead_pricing": "LMP",
        "ruc_mipgap": 0.01,
        "symbolic_solver_labels": True,
        "reserve_factor": reserve_factor,
        "deterministic_ruc_solver": "cbc",
        "sced_solver": "cbc",
        "sced_frequency_minutes": 60,
        "monitor_all_contingencies": False,
        "output_solver_logs": False,
    }


def run_case(
    output_dir: Path,
    generator: str,
    num_days: int,
    reserve_factor: float,
    use_plugin: bool,
) -> Path:
    if not prescient_avail:
        raise RuntimeError("Prescient is not available in this environment.")

    options = _build_options(
        output_dir=output_dir,
        num_days=num_days,
        reserve_factor=reserve_factor,
    )

    if use_plugin:
        options["plugin"] = {
            "doubleloop": {
                "module": str(_get_plugin_path()),
                "bidding_generator": generator,
            }
        }

    print(
        f"Running {'plugin' if use_plugin else 'baseline'} case into: {output_dir}"
    )
    prescient_simulator.Prescient().simulate(**options)
    return output_dir


def _read_csv(output_dir: Path, file_name: str) -> pd.DataFrame | None:
    file_path = output_dir / file_name
    if not file_path.exists():
        return None
    return pd.read_csv(file_path)


def _with_time_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    hour = out["Hour"].astype(int)
    if "Minute" in out.columns:
        minute = out["Minute"].astype(int)
    else:
        minute = pd.Series(0, index=out.index)

    if "Date" in out.columns:
        date = pd.to_datetime(out["Date"])
        day_offset = (date - date.min()).dt.days
    else:
        day_offset = pd.Series(0, index=out.index)

    out["time_index_hr"] = day_offset * 24 + hour + minute / 60.0
    return out


def _get_generator_bus(generator: str) -> str:
    row = rts_gmlc_generator_dataframe.loc[
        rts_gmlc_generator_dataframe["GEN UID"] == generator
    ]
    if row.empty:
        raise ValueError(f"Generator {generator!r} not found in RTS-GMLC generator data.")

    bus_id = row.iloc[0]["Bus ID"]
    bus_row = rts_gmlc_bus_dataframe.loc[rts_gmlc_bus_dataframe["Bus ID"] == bus_id]
    if bus_row.empty:
        raise ValueError(f"Bus ID {bus_id!r} not found in RTS-GMLC bus data.")

    return str(bus_row.iloc[0]["Bus Name"])


def _save_plot(fig, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_hourly_summary_comparison(
    baseline_dir: Path,
    plugin_dir: Path,
    plots_dir: Path,
) -> pd.DataFrame:
    baseline = _read_csv(baseline_dir, "hourly_summary.csv")
    plugin = _read_csv(plugin_dir, "hourly_summary.csv")

    if baseline is None or plugin is None:
        raise FileNotFoundError("hourly_summary.csv is required in both output folders.")

    baseline = _with_time_index(baseline)
    plugin = _with_time_index(plugin)

    merged = baseline.merge(
        plugin,
        on=["Date", "Hour", "time_index_hr"],
        suffixes=("_baseline", "_plugin"),
    )

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    axes[0].plot(
        merged["time_index_hr"], merged["Price_baseline"], label="Baseline", linewidth=2
    )
    axes[0].plot(
        merged["time_index_hr"], merged["Price_plugin"], label="Plugin", linewidth=2
    )
    axes[0].set_ylabel("System Price")
    axes[0].set_title("Hourly System Price Comparison")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        merged["time_index_hr"],
        merged["TotalCosts_baseline"],
        label="Baseline",
        linewidth=2,
    )
    axes[1].plot(
        merged["time_index_hr"],
        merged["TotalCosts_plugin"],
        label="Plugin",
        linewidth=2,
    )
    axes[1].set_xlabel("Hour")
    axes[1].set_ylabel("Total Costs")
    axes[1].set_title("Hourly Total Cost Comparison")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    _save_plot(fig, plots_dir / "hourly_summary_comparison.png")

    return pd.DataFrame(
        [
            {
                "metric": "mean_system_price",
                "baseline": merged["Price_baseline"].mean(),
                "plugin": merged["Price_plugin"].mean(),
                "delta_plugin_minus_baseline": (
                    merged["Price_plugin"].mean() - merged["Price_baseline"].mean()
                ),
            },
            {
                "metric": "mean_total_cost",
                "baseline": merged["TotalCosts_baseline"].mean(),
                "plugin": merged["TotalCosts_plugin"].mean(),
                "delta_plugin_minus_baseline": (
                    merged["TotalCosts_plugin"].mean()
                    - merged["TotalCosts_baseline"].mean()
                ),
            },
        ]
    )


def plot_generator_dispatch_comparison(
    baseline_dir: Path,
    plugin_dir: Path,
    plots_dir: Path,
    generator: str,
) -> pd.DataFrame:
    baseline = _read_csv(baseline_dir, "thermal_detail.csv")
    plugin = _read_csv(plugin_dir, "thermal_detail.csv")

    if baseline is None or plugin is None:
        raise FileNotFoundError("thermal_detail.csv is required in both output folders.")

    baseline = _with_time_index(baseline)
    plugin = _with_time_index(plugin)

    baseline = baseline.loc[baseline["Generator"] == generator].copy()
    plugin = plugin.loc[plugin["Generator"] == generator].copy()

    merged = baseline.merge(
        plugin,
        on=["Date", "Hour", "Minute", "Generator", "time_index_hr"],
        suffixes=("_baseline", "_plugin"),
    )

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    axes[0].plot(
        merged["time_index_hr"],
        merged["Dispatch_baseline"],
        label="Baseline Dispatch",
        linewidth=2,
    )
    axes[0].plot(
        merged["time_index_hr"],
        merged["Dispatch_plugin"],
        label="Plugin Dispatch",
        linewidth=2,
    )
    axes[0].set_ylabel("MW")
    axes[0].set_title(f"{generator} Dispatch Comparison")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].step(
        merged["time_index_hr"],
        merged["Unit State_baseline"].astype(int),
        where="post",
        label="Baseline Unit State",
        linewidth=2,
    )
    axes[1].step(
        merged["time_index_hr"],
        merged["Unit State_plugin"].astype(int),
        where="post",
        label="Plugin Unit State",
        linewidth=2,
    )
    axes[1].set_ylabel("On/Off")
    axes[1].set_title(f"{generator} Commitment Comparison")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    axes[2].plot(
        merged["time_index_hr"],
        merged["Unit Cost_baseline"],
        label="Baseline Unit Cost",
        linewidth=2,
    )
    axes[2].plot(
        merged["time_index_hr"],
        merged["Unit Cost_plugin"],
        label="Plugin Unit Cost",
        linewidth=2,
    )
    axes[2].set_xlabel("Hour")
    axes[2].set_ylabel("Cost")
    axes[2].set_title(f"{generator} Unit Cost Comparison")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    _save_plot(fig, plots_dir / f"{generator}_dispatch_comparison.png")

    return pd.DataFrame(
        [
            {
                "metric": f"{generator}_mean_dispatch",
                "baseline": merged["Dispatch_baseline"].mean(),
                "plugin": merged["Dispatch_plugin"].mean(),
                "delta_plugin_minus_baseline": (
                    merged["Dispatch_plugin"].mean()
                    - merged["Dispatch_baseline"].mean()
                ),
            },
            {
                "metric": f"{generator}_online_hours",
                "baseline": merged["Unit State_baseline"].astype(int).sum(),
                "plugin": merged["Unit State_plugin"].astype(int).sum(),
                "delta_plugin_minus_baseline": (
                    merged["Unit State_plugin"].astype(int).sum()
                    - merged["Unit State_baseline"].astype(int).sum()
                ),
            },
        ]
    )


def plot_bus_lmp_comparison(
    baseline_dir: Path,
    plugin_dir: Path,
    plots_dir: Path,
    bus_name: str,
) -> pd.DataFrame:
    baseline = _read_csv(baseline_dir, "bus_detail.csv")
    plugin = _read_csv(plugin_dir, "bus_detail.csv")

    if baseline is None or plugin is None:
        raise FileNotFoundError("bus_detail.csv is required in both output folders.")

    baseline = _with_time_index(baseline)
    plugin = _with_time_index(plugin)

    baseline = baseline.loc[baseline["Bus"] == bus_name].copy()
    plugin = plugin.loc[plugin["Bus"] == bus_name].copy()

    merged = baseline.merge(
        plugin,
        on=["Date", "Hour", "Minute", "Bus", "time_index_hr"],
        suffixes=("_baseline", "_plugin"),
    )

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    axes[0].plot(
        merged["time_index_hr"], merged["LMP_baseline"], label="Baseline LMP", linewidth=2
    )
    axes[0].plot(
        merged["time_index_hr"], merged["LMP_plugin"], label="Plugin LMP", linewidth=2
    )
    axes[0].set_ylabel("RT LMP")
    axes[0].set_title(f"{bus_name} Real-Time LMP Comparison")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(
        merged["time_index_hr"],
        merged["LMP DA_baseline"],
        label="Baseline DA LMP",
        linewidth=2,
    )
    axes[1].plot(
        merged["time_index_hr"],
        merged["LMP DA_plugin"],
        label="Plugin DA LMP",
        linewidth=2,
    )
    axes[1].set_xlabel("Hour")
    axes[1].set_ylabel("DA LMP")
    axes[1].set_title(f"{bus_name} Day-Ahead LMP Comparison")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    _save_plot(fig, plots_dir / f"{bus_name}_lmp_comparison.png")

    return pd.DataFrame(
        [
            {
                "metric": f"{bus_name}_mean_rt_lmp",
                "baseline": merged["LMP_baseline"].mean(),
                "plugin": merged["LMP_plugin"].mean(),
                "delta_plugin_minus_baseline": (
                    merged["LMP_plugin"].mean() - merged["LMP_baseline"].mean()
                ),
            },
            {
                "metric": f"{bus_name}_mean_da_lmp",
                "baseline": merged["LMP DA_baseline"].mean(),
                "plugin": merged["LMP DA_plugin"].mean(),
                "delta_plugin_minus_baseline": (
                    merged["LMP DA_plugin"].mean() - merged["LMP DA_baseline"].mean()
                ),
            },
        ]
    )


def plot_bidder_comparison(plugin_dir: Path, plots_dir: Path, generator: str) -> None:
    bidder_detail = _read_csv(plugin_dir, "bidder_detail.csv")
    if bidder_detail is None or bidder_detail.empty:
        return

    bidder_detail = bidder_detail.loc[bidder_detail["Generator"] == generator].copy()
    if bidder_detail.empty:
        return

    power_columns = sorted(
        [c for c in bidder_detail.columns if c.startswith("Power ") and c.endswith("[MW]")]
    )
    if not power_columns:
        return

    bidder_detail["Hour"] = bidder_detail["Hour"].astype(int)

    fig, ax = plt.subplots(figsize=(11, 5))
    for col in power_columns[:4]:
        ax.plot(
            bidder_detail["Hour"],
            pd.to_numeric(bidder_detail[col], errors="coerce"),
            label=col.replace(" [MW]", ""),
            linewidth=2,
        )

    ax.set_xlabel("Market Hour")
    ax.set_ylabel("MW")
    ax.set_title(f"{generator} Plugin Bid Power Breakpoints")
    ax.grid(True, alpha=0.3)
    ax.legend()

    _save_plot(fig, plots_dir / f"{generator}_bid_breakpoints.png")


def create_analysis(
    baseline_dir: Path,
    plugin_dir: Path,
    generator: str,
) -> Path:
    plots_dir = plugin_dir.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    summary_frames = []
    summary_frames.append(
        plot_hourly_summary_comparison(baseline_dir, plugin_dir, plots_dir)
    )
    summary_frames.append(
        plot_generator_dispatch_comparison(
            baseline_dir=baseline_dir,
            plugin_dir=plugin_dir,
            plots_dir=plots_dir,
            generator=generator,
        )
    )

    bus_name = _get_generator_bus(generator)
    summary_frames.append(
        plot_bus_lmp_comparison(
            baseline_dir=baseline_dir,
            plugin_dir=plugin_dir,
            plots_dir=plots_dir,
            bus_name=bus_name,
        )
    )
    plot_bidder_comparison(plugin_dir=plugin_dir, plots_dir=plots_dir, generator=generator)

    summary = pd.concat(summary_frames, ignore_index=True)
    summary.to_csv(plots_dir / "comparison_summary.csv", index=False)
    return plots_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline and plugin thermal-generator Prescient cases and compare outputs."
    )
    parser.add_argument("--generator", default="10_STEAM", help="Generator to bid.")
    parser.add_argument(
        "--num-days", type=int, default=2, help="Number of simulation days."
    )
    parser.add_argument(
        "--reserve-factor",
        type=float,
        default=0.0,
        help="Reserve factor passed to Prescient.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Optional root output directory. Defaults under demo_outputs/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = _make_output_root(args.output_root)

    baseline_dir = output_root / "baseline"
    plugin_dir = output_root / "plugin"

    run_case(
        output_dir=baseline_dir,
        generator=args.generator,
        num_days=args.num_days,
        reserve_factor=args.reserve_factor,
        use_plugin=False,
    )
    run_case(
        output_dir=plugin_dir,
        generator=args.generator,
        num_days=args.num_days,
        reserve_factor=args.reserve_factor,
        use_plugin=True,
    )

    plots_dir = create_analysis(
        baseline_dir=baseline_dir,
        plugin_dir=plugin_dir,
        generator=args.generator,
    )

    print(f"Baseline outputs: {baseline_dir}")
    print(f"Plugin outputs:   {plugin_dir}")
    print(f"Comparison plots: {plots_dir}")


if __name__ == "__main__":
    main()
