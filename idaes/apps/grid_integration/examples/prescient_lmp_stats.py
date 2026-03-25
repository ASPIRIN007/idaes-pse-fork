from datetime import datetime
from importlib import resources
from pathlib import Path

import pandas as pd
from pyomo.common.dependencies import attempt_import

from idaes.apps.grid_integration.examples.idc_utils import prescient_5bus

prescient_simulator, prescient_avail = attempt_import("prescient.simulator")


def _compute_hourly_stats(bus_detail_path, bus_name):
    """
    Compute hourly mean and standard deviation for DA and RT LMPs at a bus.
    """
    df = pd.read_csv(bus_detail_path)
    df = df[df["Bus"] == bus_name].copy()

    if df.empty:
        raise ValueError(f"No rows found for bus '{bus_name}' in {bus_detail_path}.")

    hourly_stats = (
        df.groupby("Hour")[["LMP", "LMP DA"]]
        .agg(["mean", "std"])
        .sort_index()
    )

    rt_mean = hourly_stats[("LMP", "mean")].fillna(0.0).tolist()
    rt_std = hourly_stats[("LMP", "std")].fillna(0.0).tolist()
    da_mean = hourly_stats[("LMP DA", "mean")].fillna(0.0).tolist()
    da_std = hourly_stats[("LMP DA", "std")].fillna(0.0).tolist()

    return {
        "hourly_stats": hourly_stats,
        "daily_rt_price_means": rt_mean,
        "daily_rt_price_stds": rt_std,
        "daily_da_price_means": da_mean,
        "daily_da_price_stds": da_std,
    }


def run_vanilla_prescient_lmp_stats(
    bus_name="bus4",
    start_date="07-01-2020",
    num_days=365,
):
    """
    Run a vanilla Prescient simulation on the 5-bus case and compute hourly
    LMP mean/std statistics for one bus.
    """
    if not prescient_avail:
        raise RuntimeError("Prescient not available.")

    repo_root = Path(__file__).resolve().parents[4]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = repo_root / "demo_outputs" / f"prescient_lmp_stats_{ts}"
    outdir.mkdir(parents=True, exist_ok=True)

    options = {
        "data_path": str(prescient_5bus),
        "input_format": "rts-gmlc",
        "simulate_out_of_sample": True,
        "run_sced_with_persistent_forecast_errors": True,
        "output_directory": str(outdir),
        "start_date": start_date,
        "num_days": num_days,
        "sced_horizon": 4,
        "ruc_horizon": 48,
        "ruc_mipgap": 0.01,
        "reserve_factor": 0.0,
        "deterministic_ruc_solver": "cbc",
        "sced_solver": "cbc",
        "sced_frequency_minutes": 60,
        "compute_market_settlements": True,
        "monitor_all_contingencies": False,
        "output_solver_logs": False,
    }

    print(f"Running vanilla Prescient case into: {outdir}")
    prescient_simulator.Prescient().simulate(**options)

    stats = _compute_hourly_stats(outdir / "bus_detail.csv", bus_name=bus_name)

    print(f"\nHourly LMP statistics for {bus_name}")
    print(stats["hourly_stats"])
    print("\nCopy/paste arrays")
    print(f"daily_da_price_means = {stats['daily_da_price_means']}")
    print(f"daily_da_price_stds = {stats['daily_da_price_stds']}")
    print(f"daily_rt_price_means = {stats['daily_rt_price_means']}")
    print(f"daily_rt_price_stds = {stats['daily_rt_price_stds']}")

    return {
        "output_directory": str(outdir),
        **stats,
    }


if __name__ == "__main__":
    run_vanilla_prescient_lmp_stats()
