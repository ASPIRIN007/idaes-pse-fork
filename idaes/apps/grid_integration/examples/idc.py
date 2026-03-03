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
from collections import deque
from numbers import Real

import pandas as pd
import pyomo.environ as pyo


DEFAULT_IDC_CASE_DATA = {
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


class IDCModelData:
    """
    Lightweight model-data object compatible with Bidder/Tracker/Coordinator.
    """

    def __init__(
        self,
        gen_name,
        bus,
        p_min,
        p_max,
        p_cost,
        fixed_commitment=None,
        include_default_p_cost=True,
    ):
        self.gen_name = gen_name
        self.bus = bus
        self.p_min = p_min
        self.p_max = p_max
        self.p_cost = p_cost
        self.fixed_commitment = fixed_commitment
        self.include_default_p_cost = include_default_p_cost

    @property
    def generator_type(self):
        # Coordinator does not support "virtual" in _update_static_params; use
        # the closest supported type while preserving IDC dispatch behavior.
        return "thermal"

    def __iter__(self):
        if not hasattr(self, "_collection"):
            self._collection = [
                name
                for name in dir(self)
                if not name.startswith("__")
                and not name.startswith("_")
                and not callable(getattr(self, name))
            ]
            self._index = -1
        return self

    def __next__(self):
        self._index += 1
        if self._index >= len(self._collection):
            self._index = -1
            raise StopIteration
        name = self._collection[self._index]
        return name, getattr(self, name)


class IDCModel:
    """
    IDC model object with the same public interface style as ThermalGenerator.
    """

    def __init__(
        self,
        rts_gmlc_generator_dataframe,
        rts_gmlc_bus_dataframe,
        generator="10_STEAM",
        idc_case_data=None,
        idc_name="IDC_1",
    ):
        self.generator = generator
        self.idc_name = idc_name
        self.idc_case_data = dict(DEFAULT_IDC_CASE_DATA if idc_case_data is None else idc_case_data)
        self._validate_case_data()

        merged = rts_gmlc_generator_dataframe.merge(
            rts_gmlc_bus_dataframe[["Bus ID", "Bus Name"]],
            how="left",
            left_on="Bus ID",
            right_on="Bus ID",
        ).set_index("GEN UID", inplace=False)
        if generator not in merged.index:
            raise ValueError(f"Generator '{generator}' not found in RTS-GMLC generator data.")
        bus_name = merged.loc[generator, "Bus Name"]

        p_min = -float(self.idc_case_data["grid_import_max"])
        p_max = -float(self.idc_case_data["misc_power"])
        self._model_data = IDCModelData(
            gen_name=generator,
            bus=bus_name,
            p_min=p_min,
            p_max=p_max,
            p_cost=[(p_min, 0.0), (p_max, 0.0)],
            fixed_commitment=None,
            include_default_p_cost=True,
        )

        self.result_list = []

    def _validate_case_data(self):
        required = [
            "initial_backlog",
            "n_servers_max",
            "service_rate_per_server",
            "it_power_idle_per_server",
            "it_power_per_service",
            "cooling_cop",
            "misc_power",
            "grid_import_max",
            "drop_penalty",
            "backlog_penalty",
            "arrivals",
        ]
        missing = [k for k in required if k not in self.idc_case_data]
        if missing:
            raise ValueError(f"idc_case_data is missing required keys: {missing}")

        nonnegative_keys = [
            "initial_backlog",
            "n_servers_max",
            "service_rate_per_server",
            "it_power_idle_per_server",
            "it_power_per_service",
            "misc_power",
            "grid_import_max",
            "drop_penalty",
            "backlog_penalty",
        ]
        for key in nonnegative_keys:
            val = self.idc_case_data[key]
            if not isinstance(val, Real):
                raise ValueError(f"idc_case_data['{key}'] must be numeric.")
            if val < 0:
                raise ValueError(f"idc_case_data['{key}'] must be nonnegative.")

        if self.idc_case_data["cooling_cop"] <= 0:
            raise ValueError("idc_case_data['cooling_cop'] must be > 0.")

        if self.idc_case_data["grid_import_max"] <= self.idc_case_data["misc_power"]:
            raise ValueError(
                "idc_case_data['grid_import_max'] must be strictly greater than 'misc_power'."
            )

    @staticmethod
    def _arrival_at_t(arrivals, t):
        if isinstance(arrivals, dict):
            return float(arrivals.get(t, 0.0))
        if isinstance(arrivals, (list, tuple)):
            if len(arrivals) == 0:
                return 0.0
            if t < len(arrivals):
                return float(arrivals[t])
            return float(arrivals[-1])
        if isinstance(arrivals, Real):
            return float(arrivals)
        raise ValueError("idc_case_data['arrivals'] must be a dict, list/tuple, or scalar.")

    @property
    def model_data(self):
        return self._model_data

    def populate_model(self, b, horizon):
        params = self.idc_case_data
        b.HOUR = pyo.Set(initialize=list(range(horizon)))

        b.initial_backlog = pyo.Param(initialize=float(params["initial_backlog"]), mutable=True)
        b.n_servers_max = pyo.Param(initialize=float(params["n_servers_max"]), mutable=False)
        b.service_rate_per_server = pyo.Param(
            initialize=float(params["service_rate_per_server"]), mutable=False
        )
        b.it_power_idle_per_server = pyo.Param(
            initialize=float(params["it_power_idle_per_server"]), mutable=False
        )
        b.it_power_per_service = pyo.Param(
            initialize=float(params["it_power_per_service"]), mutable=False
        )
        b.cooling_cop = pyo.Param(initialize=float(params["cooling_cop"]), mutable=False)
        b.misc_power = pyo.Param(initialize=float(params["misc_power"]), mutable=False)
        b.grid_import_max = pyo.Param(initialize=float(params["grid_import_max"]), mutable=False)
        b.drop_penalty = pyo.Param(initialize=float(params["drop_penalty"]), mutable=False)
        b.backlog_penalty = pyo.Param(initialize=float(params["backlog_penalty"]), mutable=False)
        b.pre_P_V = pyo.Param(initialize=-float(params["misc_power"]), mutable=True)
        b.arrivals = pyo.Param(
            b.HOUR,
            initialize={t: self._arrival_at_t(params["arrivals"], t) for t in range(horizon)},
            mutable=False,
        )

        b.backlog = pyo.Var(
            b.HOUR, initialize=float(params["initial_backlog"]), within=pyo.NonNegativeReals
        )
        b.service = pyo.Var(b.HOUR, initialize=0.0, within=pyo.NonNegativeReals)
        b.drop = pyo.Var(b.HOUR, initialize=0.0, within=pyo.NonNegativeReals)
        b.servers_on = pyo.Var(b.HOUR, initialize=1.0, within=pyo.NonNegativeReals)
        b.it_power = pyo.Var(b.HOUR, initialize=float(params["misc_power"]), within=pyo.NonNegativeReals)
        b.cooling_power = pyo.Var(
            b.HOUR, initialize=float(params["misc_power"]) / max(float(params["cooling_cop"]), 1.0), within=pyo.NonNegativeReals
        )
        b.grid_import = pyo.Var(
            b.HOUR, initialize=float(params["misc_power"]), within=pyo.NonNegativeReals
        )
        b.P_V = pyo.Var(
            b.HOUR,
            initialize=-float(params["misc_power"]),
            bounds=(-float(params["grid_import_max"]), 0.0),
            within=pyo.Reals,
        )

        def backlog_dynamics_rule(b, h):
            prev = b.initial_backlog if h == 0 else b.backlog[h - 1]
            return b.backlog[h] == prev + b.arrivals[h] - b.service[h] - b.drop[h]

        b.backlog_dynamics_con = pyo.Constraint(b.HOUR, rule=backlog_dynamics_rule)

        def service_backlog_rule(b, h):
            prev = b.initial_backlog if h == 0 else b.backlog[h - 1]
            return b.service[h] + b.drop[h] <= prev + b.arrivals[h]

        b.service_backlog_con = pyo.Constraint(b.HOUR, rule=service_backlog_rule)

        def server_max_rule(b, h):
            return b.servers_on[h] <= b.n_servers_max

        b.server_max_con = pyo.Constraint(b.HOUR, rule=server_max_rule)

        def service_cap_rule(b, h):
            return b.service[h] <= b.service_rate_per_server * b.servers_on[h]

        b.service_cap_con = pyo.Constraint(b.HOUR, rule=service_cap_rule)

        def it_power_rule(b, h):
            return b.it_power[h] >= (
                b.it_power_idle_per_server * b.servers_on[h]
                + b.it_power_per_service * b.service[h]
            )

        b.it_power_con = pyo.Constraint(b.HOUR, rule=it_power_rule)

        def cooling_cop_rule(b, h):
            return b.cooling_power[h] >= b.it_power[h] / b.cooling_cop

        b.cooling_cop_con = pyo.Constraint(b.HOUR, rule=cooling_cop_rule)

        def facility_power_rule(b, h):
            return b.grid_import[h] == b.it_power[h] + b.cooling_power[h] + b.misc_power

        b.facility_power_con = pyo.Constraint(b.HOUR, rule=facility_power_rule)

        def grid_cap_rule(b, h):
            return b.grid_import[h] <= b.grid_import_max

        b.grid_cap_con = pyo.Constraint(b.HOUR, rule=grid_cap_rule)

        def virtual_power_rule(b, h):
            return b.P_V[h] == -b.grid_import[h]

        b.virtual_power_con = pyo.Constraint(b.HOUR, rule=virtual_power_rule)

        def penalty_cost_rule(b, h):
            return b.drop_penalty * b.drop[h] + b.backlog_penalty * b.backlog[h]

        b.penalty_cost = pyo.Expression(b.HOUR, rule=penalty_cost_rule)
        b.tot_cost = pyo.Expression(b.HOUR, rule=penalty_cost_rule)

    def update_model(self, b, implemented_power_output, implemented_backlog=None, **kwargs):
        b.pre_P_V = round(float(implemented_power_output[-1]), 4)
        if implemented_backlog is not None and len(implemented_backlog) > 0:
            b.initial_backlog = round(float(implemented_backlog[-1]), 4)
        else:
            b.initial_backlog = round(float(pyo.value(b.backlog[0])), 4)

    @staticmethod
    def get_implemented_profile(b, last_implemented_time_step):
        implemented_power_output = deque(
            [pyo.value(b.P_V[t]) for t in range(last_implemented_time_step + 1)]
        )
        implemented_backlog = deque(
            [pyo.value(b.backlog[t]) for t in range(last_implemented_time_step + 1)]
        )
        return {
            "implemented_power_output": implemented_power_output,
            "implemented_backlog": implemented_backlog,
        }

    @staticmethod
    def get_last_delivered_power(b, last_implemented_time_step):
        return pyo.value(b.P_V[last_implemented_time_step])

    def record_results(self, b, date=None, hour=None, **kwargs):
        df_list = []
        for t in b.HOUR:
            result_dict = {
                "Resource": self.idc_name,
                "Generator": self.generator,
                "Date": date,
                "Hour": hour,
                "Horizon [hr]": int(t),
                "Backlog": float(round(pyo.value(b.backlog[t]), 4)),
                "Service": float(round(pyo.value(b.service[t]), 4)),
                "Drop": float(round(pyo.value(b.drop[t]), 4)),
                "Servers On": float(round(pyo.value(b.servers_on[t]), 4)),
                "IT Power [MW]": float(round(pyo.value(b.it_power[t]), 4)),
                "Cooling Power [MW]": float(round(pyo.value(b.cooling_power[t]), 4)),
                "Grid Import [MW]": float(round(pyo.value(b.grid_import[t]), 4)),
                "Virtual Output P_V [MW]": float(round(pyo.value(b.P_V[t]), 4)),
                "Penalty Cost [$]": float(round(pyo.value(b.penalty_cost[t]), 4)),
                "Total Cost [$]": float(round(pyo.value(b.tot_cost[t]), 4)),
            }
            for key, value in kwargs.items():
                result_dict[key] = value

            result_df = pd.DataFrame.from_dict(result_dict, orient="index")
            df_list.append(result_df.T)

        self.result_list.append(pd.concat(df_list))

    def write_results(self, path):
        pd.concat(self.result_list).to_csv(path, index=False)

    @property
    def power_output(self):
        return "P_V"

    @property
    def total_cost(self):
        return ("tot_cost", 1)
