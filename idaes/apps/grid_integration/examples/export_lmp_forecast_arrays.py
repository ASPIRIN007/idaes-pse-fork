from pathlib import Path

import pandas as pd


def export_lmp_forecast_arrays(output_directory, bus_name="bus4", output_file=None):
    """
    Read Prescient bus_detail.csv output and export the four forecast arrays
    used by the placeholder forecaster.
    """
    output_directory = Path(output_directory)
    bus_detail_path = output_directory / "bus_detail.csv"

    if not bus_detail_path.exists():
        raise FileNotFoundError(f"Could not find {bus_detail_path}")

    df = pd.read_csv(bus_detail_path)
    df = df[df["Bus"] == bus_name].copy()

    if df.empty:
        raise ValueError(f"No rows found for bus '{bus_name}' in {bus_detail_path}.")

    hourly_stats = (
        df.groupby("Hour")[["LMP", "LMP DA"]]
        .agg(["mean", "std"])
        .sort_index()
    )

    arrays = {
        "daily_da_price_means": hourly_stats[("LMP DA", "mean")].fillna(0.0).tolist(),
        "daily_da_price_stds": hourly_stats[("LMP DA", "std")].fillna(0.0).tolist(),
        "daily_rt_price_means": hourly_stats[("LMP", "mean")].fillna(0.0).tolist(),
        "daily_rt_price_stds": hourly_stats[("LMP", "std")].fillna(0.0).tolist(),
    }

    lines = []
    for name, values in arrays.items():
        lines.append(f"{name} = [")
        for value in values:
            lines.append(f"    {value},")
        lines.append("]")
        lines.append("")

    output_text = "\n".join(lines).rstrip() + "\n"

    if output_file is None:
        output_file = output_directory / f"{bus_name}_lmp_forecast_arrays.py"
    else:
        output_file = Path(output_file)

    output_file.write_text(output_text)

    print(f"Wrote forecast arrays to: {output_file}")

    return {
        "output_file": str(output_file),
        **arrays,
    }


if __name__ == "__main__":
    latest_output = sorted(Path("demo_outputs").glob("prescient_lmp_stats_*"))[-1]
    export_lmp_forecast_arrays(output_directory=latest_output, bus_name="bus4")
