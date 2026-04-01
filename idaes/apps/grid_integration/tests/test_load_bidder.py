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
from types import SimpleNamespace

import pyomo.environ as pyo
import pytest
from pyomo.opt.base.solvers import OptSolver

from idaes.apps.grid_integration.load_bidder import LoadBidder


class DummyForecaster:
    def forecast_day_ahead_prices(self, date, hour, bus, horizon, n_samples):
        return {0: [10.0] * horizon}

    def forecast_real_time_prices(self, date, hour, bus, horizon, n_samples):
        return {0: [10.0] * horizon}


class DummySolver(OptSolver):
    def __init__(self):
        super().__init__(type="dummy")

    def solve(self, model, tee=False):
        arrival0 = pyo.value(model.workload_arrival[0])
        initial_backlog = pyo.value(model.initial_backlog)
        served0 = min(1.0, initial_backlog + arrival0)

        model.P_load[0].set_value(served0)
        model.work_served[0].set_value(served0)
        model.backlog[0].set_value(initial_backlog + arrival0 - served0)

        for t in model.HOUR:
            if t == 0:
                continue
            model.P_load[t].set_value(0.0)
            model.work_served[t].set_value(0.0)
            model.backlog[t].set_value(model.backlog[t - 1].value + model.workload_arrival[t].value)

        return SimpleNamespace()


class DummyBiddingModel:
    def __init__(self):
        self.model_data = SimpleNamespace(
            load_name="bus4",
            bus="bus4",
            workload_arrival=[2.0, 3.0, 4.0, 5.0],
            initial_backlog=5.0,
        )

    def populate_model(self, model, horizon):
        model.HOUR = pyo.Set(initialize=range(horizon))
        model.initial_backlog = pyo.Param(initialize=self.model_data.initial_backlog, mutable=True)
        model.workload_arrival = pyo.Param(
            model.HOUR,
            initialize={t: self.model_data.workload_arrival[t] for t in range(horizon)},
            mutable=True,
        )
        model.energy_price = pyo.Param(model.HOUR, initialize=0.0, mutable=True)
        model.P_load = pyo.Var(model.HOUR, initialize=0.0)
        model.work_served = pyo.Var(model.HOUR, initialize=0.0)
        model.backlog = pyo.Var(model.HOUR, initialize=0.0)

    def update_model(self, model, workload_arrival=None, initial_backlog=None):
        if workload_arrival is not None:
            for t in model.HOUR:
                model.workload_arrival[t] = float(workload_arrival[t])
        if initial_backlog is not None:
            model.initial_backlog = float(initial_backlog)

    @staticmethod
    def get_implemented_profile(model, last_implemented_time_step):
        return {
            "implemented_backlog": [
                pyo.value(model.backlog[t]) for t in range(last_implemented_time_step + 1)
            ]
        }

    @staticmethod
    def get_last_backlog(model, last_implemented_time_step):
        return pyo.value(model.backlog[last_implemented_time_step])

    def record_results(self, model, date=None, hour=None, market=None, **kwargs):
        return None

    def write_results(self, path):
        return None

    @property
    def power_output(self):
        return "P_load"

    @property
    def total_cost(self):
        return ("total_cost", 1)


@pytest.mark.unit
def test_real_time_backlog_is_carried_forward():
    bidder = LoadBidder(
        bidding_model_object=DummyBiddingModel(),
        day_ahead_horizon=4,
        real_time_horizon=4,
        n_scenario=1,
        solver=DummySolver(),
        forecaster=DummyForecaster(),
    )

    bidder.compute_real_time_bids(date="2020-07-10", hour=0)
    first_backlog = bidder.current_backlog

    assert first_backlog == 6.0

    bidder.compute_real_time_bids(date="2020-07-10", hour=1)
    second_backlog = bidder.current_backlog

    assert second_backlog == 8.0
    assert pyo.value(bidder.real_time_model.initial_backlog) == first_backlog
