from importlib import resources
from pathlib import Path
from datetime import datetime

from pyomo.common.dependencies import attempt_import

from idaes.apps.grid_integration.examples.idc_utils import prescient_5bus

prescient_simulator, prescient_avail = attempt_import("prescient.simulator")


def run_idc_load_v1_1(num_days=1):
    if not prescient_avail:
        raise RuntimeError("Prescient not available.")

    repo_root = Path(__file__).resolve().parents[4]

    with resources.as_file(
        resources.files("idaes.apps.grid_integration.examples").joinpath(
            "idc_load_prescient_plugin.py"
        )
    ) as p:
        plugin_path = str(Path(p))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = repo_root / "demo_outputs" / f"idc_load_v1_1_{ts}"
    outdir.mkdir(parents=True, exist_ok=True)

    options = {
        "data_path": str(prescient_5bus),
        "input_format": "rts-gmlc",
        "simulate_out_of_sample": True,
        "run_sced_with_persistent_forecast_errors": True,
        "output_directory": str(outdir),
        "start_date": "07-10-2020",
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

    print(f"Output: {outdir}")
    prescient_simulator.Prescient().simulate(**options)

    return str(outdir)


if __name__ == "__main__":
    run_idc_load_v1_1(1)
