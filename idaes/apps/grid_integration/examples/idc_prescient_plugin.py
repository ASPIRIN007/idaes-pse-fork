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
Prescient plugin wiring for IDC example.

This module follows the same pattern as thermal_generator_prescient_plugin.py:
1) create forecaster
2) create solver
3) create tracking / projection tracking model objects
4) create bidder model object
5) create coordinator
6) expose get_configuration/register_plugins for Prescient
"""

import pyomo.environ as pyo

from idaes.apps.grid_integration import Bidder
from idaes.apps.grid_integration import DoubleLoopCoordinator
from idaes.apps.grid_integration import PlaceHolderForecaster
from idaes.apps.grid_integration import Tracker
from idaes.apps.grid_integration.examples.idc import IDCModel
from idaes.apps.grid_integration.examples.utils import (
    daily_da_price_means,
    daily_da_price_stds,
    daily_rt_price_means,
    daily_rt_price_stds,
    rts_gmlc_bus_dataframe,
    rts_gmlc_generator_dataframe,
)

# Target Prescient generator key to replace/drive with IDC bidding logic.
generator = "10_STEAM"

# Horizons match existing thermal example defaults.
tracking_horizon = 4
day_ahead_bidding_horizon = 48
real_time_bidding_horizon = tracking_horizon

# Number of price scenarios in stochastic bidder.
n_scenario = 10

# Number of hours implemented each tracking solve.
n_tracking_hour = 1

# IDC case data used for all three model objects below.
idc_case_data = {
    "initial_backlog": 5.0,
    "n_servers_max": 120.0,
    "service_rate_per_server": 0.8,
    "it_power_idle_per_server": 0.02,
    "it_power_per_service": 0.08,
    "cooling_cop": 3.0,
    "misc_power": 5.0,
    "grid_import_max": 45.0,
    "drop_penalty": 150.0,
    "backlog_penalty": 25.0,
    "arrivals": [80.0] * 48,
}

# Forecaster supplies DA/RT price trajectories to bidder.
forecaster = PlaceHolderForecaster(
    daily_da_price_means=daily_da_price_means,
    daily_rt_price_means=daily_rt_price_means,
    daily_da_price_stds=daily_da_price_stds,
    daily_rt_price_stds=daily_rt_price_stds,
)

# Keep solver consistent with existing examples/tests.
solver = pyo.SolverFactory("cbc")

# ---------------------------------------------------------------------------
# 1) Tracker model object: used after SCED to follow dispatch and roll state.
# ---------------------------------------------------------------------------
tracking_model_object = IDCModel(
    rts_gmlc_generator_dataframe=rts_gmlc_generator_dataframe,
    rts_gmlc_bus_dataframe=rts_gmlc_bus_dataframe,
    generator=generator,
    idc_case_data=idc_case_data,
    idc_name="IDC_TRACKER",
)
idc_tracker = Tracker(
    tracking_model_object=tracking_model_object,
    tracking_horizon=tracking_horizon,
    n_tracking_hour=n_tracking_hour,
    solver=solver,
)

# ---------------------------------------------------------------------------
# 2) Projection tracker model object: used for DA projection roll-forward path.
# ---------------------------------------------------------------------------
projection_tracking_model_object = IDCModel(
    rts_gmlc_generator_dataframe=rts_gmlc_generator_dataframe,
    rts_gmlc_bus_dataframe=rts_gmlc_bus_dataframe,
    generator=generator,
    idc_case_data=idc_case_data,
    idc_name="IDC_PROJECTION",
)
idc_projection_tracker = Tracker(
    tracking_model_object=projection_tracking_model_object,
    tracking_horizon=tracking_horizon,
    n_tracking_hour=n_tracking_hour,
    solver=solver,
)

# ---------------------------------------------------------------------------
# 3) Bidder model object: used in DA/RT bidding optimization.
# ---------------------------------------------------------------------------
bidding_model_object = IDCModel(
    rts_gmlc_generator_dataframe=rts_gmlc_generator_dataframe,
    rts_gmlc_bus_dataframe=rts_gmlc_bus_dataframe,
    generator=generator,
    idc_case_data=idc_case_data,
    idc_name="IDC_BIDDER",
)
idc_bidder = Bidder(
    bidding_model_object=bidding_model_object,
    day_ahead_horizon=day_ahead_bidding_horizon,
    real_time_horizon=real_time_bidding_horizon,
    n_scenario=n_scenario,
    solver=solver,
    forecaster=forecaster,
)

# Coordinator binds bidder + tracker + projection tracker to Prescient callbacks.
coordinator = DoubleLoopCoordinator(
    bidder=idc_bidder,
    tracker=idc_tracker,
    projection_tracker=idc_projection_tracker,
)

# Prescient plugin contract:
# These two names must exist at module level in plugin module.
get_configuration = coordinator.get_configuration
register_plugins = coordinator.register_plugins
