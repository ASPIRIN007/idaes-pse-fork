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
Convenience script to run IDC plugin with Prescient on bundled 5bus data.

This script is intentionally small:
- resolve plugin path
- assemble Prescient options
- run simulation
"""

from importlib import resources
from pathlib import Path
import tempfile
import sys

# If run as a plain script (`python idc_run.py`), ensure repo root is on sys.path
# so `import idaes...` resolves.
if __package__ is None or __package__ == "":
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from pyomo.common.dependencies import attempt_import

from idaes.apps.grid_integration.examples.utils import prescient_5bus

# Optional dependency import pattern used across this project.
prescient_simulator, prescient_avail = attempt_import("prescient.simulator")


def run_idc_demo(num_days=1):
    """
    Run an IDC double-loop simulation for `num_days`.
    """
    # Fail early with clear error if Prescient is missing.
    if not prescient_avail:
        raise RuntimeError("Prescient (optional dependency) is not available.")

    # Resolve plugin module path shipped in this package.
    with resources.as_file(
        resources.files("idaes.apps.grid_integration.examples").joinpath(
            "idc_prescient_plugin.py"
        )
    ) as p:
        plugin_path = str(Path(p))

    # Use temp output directory for quick demos.
    output_directory = tempfile.mkdtemp(prefix="idc_doubleloop_")

    # Prescient simulation options; mirrors thermal example defaults.
    options = {
        "data_path": prescient_5bus,
        "input_format": "rts-gmlc",
        "simulate_out_of_sample": True,
        "run_sced_with_persistent_forecast_errors": True,
        "output_directory": output_directory,
        "start_date": "07-10-2020",
        "num_days": num_days,
        "sced_horizon": 4,
        "compute_market_settlements": True,
        "day_ahead_pricing": "LMP",
        "ruc_mipgap": 0.01,
        "symbolic_solver_labels": True,
        "reserve_factor": 0.0,
        "deterministic_ruc_solver": "cbc",
        "sced_solver": "cbc",
        "sced_frequency_minutes": 60,
        "ruc_horizon": 48,
        "plugin": {
            "doubleloop": {
                "module": plugin_path,
                "bidding_generator": "10_STEAM",
            }
        },
    }

    # Print output path so user can inspect csv artifacts after run.
    print(f"IDC demo output directory: {output_directory}")

    # Execute simulation.
    prescient_simulator.Prescient().simulate(**options)

    # Return path for callers (tests/scripts) to inspect.
    return output_directory


if __name__ == "__main__":
    # Default run for direct script execution.
    run_idc_demo(num_days=1)
