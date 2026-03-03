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
from importlib import resources
from pathlib import Path
from numbers import Number
from typing import Dict, Union

import pytest

from idaes.apps.grid_integration.examples.idc import IDCModel
from idaes.apps.grid_integration.examples.utils import (
    rts_gmlc_bus_dataframe,
    rts_gmlc_generator_dataframe,
)

PrescientOptions = Dict[str, Union[str, bool, Number, dict]]


class TestIDCIntegration:
    @pytest.fixture
    def idc_plugin_path(self) -> Path:
        with resources.as_file(
            resources.files("idaes.apps.grid_integration.examples").joinpath(
                "idc_prescient_plugin.py"
            )
        ) as p:
            return Path(p)

    @pytest.fixture
    def data_path(self) -> Path:
        with resources.as_file(
            resources.files("idaes.tests.prescient.5bus").joinpath("__init__.py")
        ) as pkg_file:
            return pkg_file.parent

    @pytest.mark.unit
    def test_idc_model_builds(self):
        model = IDCModel(
            rts_gmlc_generator_dataframe=rts_gmlc_generator_dataframe,
            rts_gmlc_bus_dataframe=rts_gmlc_bus_dataframe,
            generator="10_STEAM",
        )
        assert model.model_data.gen_name == "10_STEAM"
        assert model.power_output == "P_V"

    @pytest.mark.unit
    def test_idc_plugin_path_exists(self, idc_plugin_path: Path):
        assert idc_plugin_path.is_file()

    @pytest.fixture
    def idc_sim_options(
        self, data_path: Path, idc_plugin_path: Path, tmp_path: Path
    ) -> PrescientOptions:
        output_dir = tmp_path / "idc_integration_output"
        output_dir.mkdir()
        return {
            "data_path": str(data_path),
            "input_format": "rts-gmlc",
            "simulate_out_of_sample": True,
            "run_sced_with_persistent_forecast_errors": True,
            "output_directory": str(output_dir),
            "start_date": "07-10-2020",
            "num_days": 1,
            "sced_horizon": 4,
            "ruc_mipgap": 0.01,
            "reserve_factor": 0.0,
            "deterministic_ruc_solver": "cbc",
            "day_ahead_pricing": "LMP",
            "symbolic_solver_labels": True,
            "deterministic_ruc_solver_options": {"feas": "off", "DivingF": "on"},
            "sced_solver": "cbc",
            "sced_frequency_minutes": 60,
            "ruc_horizon": 48,
            "compute_market_settlements": True,
            "monitor_all_contingencies": False,
            "output_solver_logs": False,
            "price_threshold": 1000,
            "contingency_price_threshold": 100,
            "reserve_price_threshold": 5,
            "plugin": {
                "doubleloop": {
                    "module": str(idc_plugin_path),
                    "bidding_generator": "10_STEAM",
                }
            },
        }

    @pytest.mark.integration
    def test_idc_negative_load_hits_prescient_min_power_limit(
        self, idc_sim_options: PrescientOptions
    ):
        prescient_simulator = pytest.importorskip(
            "prescient.simulator",
            reason="Prescient (optional dependency) not available",
        )

        with pytest.raises(ValueError, match="MinimumPowerOutput"):
            prescient_simulator.Prescient().simulate(**idc_sim_options)
