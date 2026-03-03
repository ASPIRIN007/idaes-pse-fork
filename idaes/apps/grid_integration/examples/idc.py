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
IDC example model object for IDAES grid_integration.

This file mirrors the public API style of thermal_generator.py so that the
existing Bidder/Tracker/Coordinator classes can use it without core changes.

High-level modeling choice in this version:
- IDC electrical import is represented by `grid_import[h] >= 0`.
- Market-facing power is represented by `P_V[h] = -grid_import[h]`.
  This means the IDC appears as negative injection at the interface.
"""

from collections import deque
from numbers import Real

import pandas as pd
import pyomo.environ as pyo


# A small default case so this model can be instantiated quickly.
# The user can override all values via `idc_case_data`.
DEFAULT_IDC_CASE_DATA = {
    # Initial queued workload before the optimization horizon starts.
    "initial_backlog": 5.0,
    # Maximum number of servers that can be active.
    "n_servers_max": 120.0,
    # Workload service throughput per active server per time step.
    "service_rate_per_server": 0.8,
    # Idle IT power consumed by each active server (MW).
    "it_power_idle_per_server": 0.02,
    # Additional IT power per unit served workload (MW per unit service).
    "it_power_per_service": 0.08,
    # Cooling coefficient of performance (dimensionless, > 0).
    "cooling_cop": 3.0,
    # Fixed non-IT/non-cooling facility power (MW).
    "misc_power": 5.0,
    # Contracted/import electrical limit (MW).
    "grid_import_max": 45.0,
    # Cost penalty coefficient for dropped work.
    "drop_penalty": 150.0,
    # Cost penalty coefficient for backlog carry-over.
    "backlog_penalty": 25.0,
    # Exogenous arrivals profile; this default is a flat profile.
    "arrivals": [80.0] * 48,
}


class IDCModelData:
    """
    Minimal model-data container compatible with Bidder/Coordinator expectations.

    Why this class exists:
    - Bidder expects `model_data` to expose generator meta-data fields.
    - Coordinator iterates over model_data fields to pass static values to Prescient.
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
        # Name of the Prescient generator record being replaced/targeted.
        self.gen_name = gen_name
        # Bus where the targeted Prescient generator sits.
        self.bus = bus
        # Minimum and maximum bid power bounds expected by bidder logic.
        self.p_min = p_min
        self.p_max = p_max
        # Default power cost points used by bidder curve assembly.
        self.p_cost = p_cost
        # Optional fixed commitment signal (None means unfixed).
        self.fixed_commitment = fixed_commitment
        # If True, bidder always injects default p_cost points.
        self.include_default_p_cost = include_default_p_cost

    @property
    def generator_type(self):
        # NOTE:
        # Coordinator currently supports thermal/renewable branches in static
        # parameter handling. To remain compatible with that path, this model
        # reports "thermal" here even though the underlying physical entity is IDC.
        return "thermal"

    def __iter__(self):
        # Coordinator iterates model_data as (field, value) pairs.
        # This dynamic collection includes non-private, non-callable attributes.
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
        # Standard iterator protocol support.
        self._index += 1
        if self._index >= len(self._collection):
            self._index = -1
            raise StopIteration
        name = self._collection[self._index]
        return name, getattr(self, name)


class IDCModel:
    """
    IDC process model object with the same public API pattern as ThermalGenerator.

    This class is designed to be passed directly into:
    - Tracker(tracking_model_object=...)
    - Bidder(bidding_model_object=...)
    """

    def __init__(
        self,
        rts_gmlc_generator_dataframe,
        rts_gmlc_bus_dataframe,
        generator="10_STEAM",
        idc_case_data=None,
        idc_name="IDC_1",
    ):
        # Save target generator key and user-facing IDC identifier.
        self.generator = generator
        self.idc_name = idc_name

        # Copy case data (default or user-provided), then validate.
        self.idc_case_data = dict(
            DEFAULT_IDC_CASE_DATA if idc_case_data is None else idc_case_data
        )
        self._validate_case_data()

        # Merge generator and bus tables so generator -> bus name lookup is easy.
        merged = rts_gmlc_generator_dataframe.merge(
            rts_gmlc_bus_dataframe[["Bus ID", "Bus Name"]],
            how="left",
            left_on="Bus ID",
            right_on="Bus ID",
        ).set_index("GEN UID", inplace=False)

        # Ensure the selected targeted generator exists in dataset.
        if generator not in merged.index:
            raise ValueError(
                f"Generator '{generator}' not found in RTS-GMLC generator data."
            )

        # Bus name is required by bidder/forecaster interfaces.
        bus_name = merged.loc[generator, "Bus Name"]

        # In this version, market-facing power is negative import:
        # P_V in [-grid_import_max, -misc_power] (both are <= 0).
        p_min = -float(self.idc_case_data["grid_import_max"])
        p_max = -float(self.idc_case_data["misc_power"])

        # Build model_data object consumed by Bidder/Coordinator.
        self._model_data = IDCModelData(
            gen_name=generator,
            bus=bus_name,
            p_min=p_min,
            p_max=p_max,
            p_cost=[(p_min, 0.0), (p_max, 0.0)],
            fixed_commitment=None,
            include_default_p_cost=True,
        )

        # List of result dataframes; written once at end.
        self.result_list = []

    def _validate_case_data(self):
        """
        Validate input dictionary for required keys and simple consistency rules.
        """
        # Required keys for this IDC model.
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

        # Fail fast if any required fields are missing.
        missing = [k for k in required if k not in self.idc_case_data]
        if missing:
            raise ValueError(f"idc_case_data is missing required keys: {missing}")

        # These keys must be numeric and nonnegative.
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

        # COP must be strictly positive to avoid division by zero/nonphysical values.
        if self.idc_case_data["cooling_cop"] <= 0:
            raise ValueError("idc_case_data['cooling_cop'] must be > 0.")

        # Keep feasible lower bound for P_V range in this formulation.
        if self.idc_case_data["grid_import_max"] <= self.idc_case_data["misc_power"]:
            raise ValueError(
                "idc_case_data['grid_import_max'] must be strictly greater than "
                "'misc_power'."
            )

    @staticmethod
    def _arrival_at_t(arrivals, t):
        """
        Read arrivals at time index t from dict/list/scalar formats.
        """
        # If arrivals is dict, use explicit value at t (default to 0).
        if isinstance(arrivals, dict):
            return float(arrivals.get(t, 0.0))

        # If arrivals is list/tuple, use t-th value; hold last value beyond length.
        if isinstance(arrivals, (list, tuple)):
            if len(arrivals) == 0:
                return 0.0
            if t < len(arrivals):
                return float(arrivals[t])
            return float(arrivals[-1])

        # If arrivals is scalar, use same value for all t.
        if isinstance(arrivals, Real):
            return float(arrivals)

        # Unsupported arrivals input type.
        raise ValueError(
            "idc_case_data['arrivals'] must be a dict, list/tuple, or scalar."
        )

    @property
    def model_data(self):
        # Exposes metadata expected by bidder/coordinator.
        return self._model_data

    def populate_model(self, b, horizon):
        """
        Build one horizon optimization block on `b`.
        """
        params = self.idc_case_data

        # Time set exactly in thermal style: 0..horizon-1.
        b.HOUR = pyo.Set(initialize=list(range(horizon)))

        # ----------------------
        # Parameters (constants)
        # ----------------------
        # Mutable initial backlog so update_model can roll horizon state.
        b.initial_backlog = pyo.Param(
            initialize=float(params["initial_backlog"]), mutable=True
        )
        b.n_servers_max = pyo.Param(
            initialize=float(params["n_servers_max"]), mutable=False
        )
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
        b.grid_import_max = pyo.Param(
            initialize=float(params["grid_import_max"]), mutable=False
        )
        b.drop_penalty = pyo.Param(initialize=float(params["drop_penalty"]), mutable=False)
        b.backlog_penalty = pyo.Param(
            initialize=float(params["backlog_penalty"]), mutable=False
        )

        # Mutable prior power marker (kept for state continuity style parity).
        b.pre_P_V = pyo.Param(initialize=-float(params["misc_power"]), mutable=True)

        # Exogenous arrivals by time step.
        b.arrivals = pyo.Param(
            b.HOUR,
            initialize={t: self._arrival_at_t(params["arrivals"], t) for t in range(horizon)},
            mutable=False,
        )

        # ----------------
        # Decision variables
        # ----------------
        # Queue dynamics states and decisions.
        b.backlog = pyo.Var(
            b.HOUR,
            initialize=float(params["initial_backlog"]),
            within=pyo.NonNegativeReals,
        )
        b.service = pyo.Var(b.HOUR, initialize=0.0, within=pyo.NonNegativeReals)
        b.drop = pyo.Var(b.HOUR, initialize=0.0, within=pyo.NonNegativeReals)

        # IDC operating intensity.
        b.servers_on = pyo.Var(b.HOUR, initialize=1.0, within=pyo.NonNegativeReals)

        # Internal power components.
        b.it_power = pyo.Var(
            b.HOUR,
            initialize=float(params["misc_power"]),
            within=pyo.NonNegativeReals,
        )
        b.cooling_power = pyo.Var(
            b.HOUR,
            initialize=float(params["misc_power"]) / max(float(params["cooling_cop"]), 1.0),
            within=pyo.NonNegativeReals,
        )
        b.grid_import = pyo.Var(
            b.HOUR,
            initialize=float(params["misc_power"]),
            within=pyo.NonNegativeReals,
        )

        # Market-facing virtual power output (negative for import).
        b.P_V = pyo.Var(
            b.HOUR,
            initialize=-float(params["misc_power"]),
            bounds=(-float(params["grid_import_max"]), 0.0),
            within=pyo.Reals,
        )

        # ----------------------
        # IDC physics constraints
        # ----------------------
        # 1) Backlog transition: previous queue + arrivals - service - dropped.
        def backlog_dynamics_rule(b, h):
            prev = b.initial_backlog if h == 0 else b.backlog[h - 1]
            return b.backlog[h] == prev + b.arrivals[h] - b.service[h] - b.drop[h]

        b.backlog_dynamics_con = pyo.Constraint(b.HOUR, rule=backlog_dynamics_rule)

        # 2) Cannot process/drop more work than currently available.
        def service_backlog_rule(b, h):
            prev = b.initial_backlog if h == 0 else b.backlog[h - 1]
            return b.service[h] + b.drop[h] <= prev + b.arrivals[h]

        b.service_backlog_con = pyo.Constraint(b.HOUR, rule=service_backlog_rule)

        # 3) Server upper bound.
        def server_max_rule(b, h):
            return b.servers_on[h] <= b.n_servers_max

        b.server_max_con = pyo.Constraint(b.HOUR, rule=server_max_rule)

        # 4) Service throughput capacity.
        def service_cap_rule(b, h):
            return b.service[h] <= b.service_rate_per_server * b.servers_on[h]

        b.service_cap_con = pyo.Constraint(b.HOUR, rule=service_cap_rule)

        # 5) IT power lower bound from idle + load terms.
        def it_power_rule(b, h):
            return b.it_power[h] >= (
                b.it_power_idle_per_server * b.servers_on[h]
                + b.it_power_per_service * b.service[h]
            )

        b.it_power_con = pyo.Constraint(b.HOUR, rule=it_power_rule)

        # 6) Cooling power lower bound from COP relation.
        def cooling_cop_rule(b, h):
            return b.cooling_power[h] >= b.it_power[h] / b.cooling_cop

        b.cooling_cop_con = pyo.Constraint(b.HOUR, rule=cooling_cop_rule)

        # 7) Facility power balance.
        def facility_power_rule(b, h):
            return (
                b.grid_import[h] == b.it_power[h] + b.cooling_power[h] + b.misc_power
            )

        b.facility_power_con = pyo.Constraint(b.HOUR, rule=facility_power_rule)

        # 8) Import cap.
        def grid_cap_rule(b, h):
            return b.grid_import[h] <= b.grid_import_max

        b.grid_cap_con = pyo.Constraint(b.HOUR, rule=grid_cap_rule)

        # 9) Virtual output mapping for market interface.
        def virtual_power_rule(b, h):
            return b.P_V[h] == -b.grid_import[h]

        b.virtual_power_con = pyo.Constraint(b.HOUR, rule=virtual_power_rule)

        # ----------------
        # Cost expressions
        # ----------------
        # Penalize dropped work and backlog.
        def penalty_cost_rule(b, h):
            return b.drop_penalty * b.drop[h] + b.backlog_penalty * b.backlog[h]

        b.penalty_cost = pyo.Expression(b.HOUR, rule=penalty_cost_rule)
        # Tracker/Bidder read `total_cost` property as (`expr_name`, weight).
        b.tot_cost = pyo.Expression(b.HOUR, rule=penalty_cost_rule)

    def update_model(self, b, implemented_power_output, implemented_backlog=None, **kwargs):
        """
        Roll horizon state after implemented control actions.
        """
        # Save latest implemented market-facing power.
        b.pre_P_V = round(float(implemented_power_output[-1]), 4)

        # Update initial backlog for next horizon from implemented trajectory.
        if implemented_backlog is not None and len(implemented_backlog) > 0:
            b.initial_backlog = round(float(implemented_backlog[-1]), 4)
        else:
            b.initial_backlog = round(float(pyo.value(b.backlog[0])), 4)

    @staticmethod
    def get_implemented_profile(b, last_implemented_time_step):
        """
        Return implemented profile dict in the exact style Tracker expects.
        """
        # Implemented power trace over realized sub-horizon.
        implemented_power_output = deque(
            [pyo.value(b.P_V[t]) for t in range(last_implemented_time_step + 1)]
        )
        # Implemented backlog trace (used for state roll-forward).
        implemented_backlog = deque(
            [pyo.value(b.backlog[t]) for t in range(last_implemented_time_step + 1)]
        )
        return {
            "implemented_power_output": implemented_power_output,
            "implemented_backlog": implemented_backlog,
        }

    @staticmethod
    def get_last_delivered_power(b, last_implemented_time_step):
        """
        Return delivered/implemented market-facing power at last implemented step.
        """
        return pyo.value(b.P_V[last_implemented_time_step])

    def record_results(self, b, date=None, hour=None, **kwargs):
        """
        Save model detail rows for each horizon time to an internal list.
        """
        df_list = []
        for t in b.HOUR:
            # Build one row of detail output for horizon index t.
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

            # Allow caller to append extra fields.
            for key, value in kwargs.items():
                result_dict[key] = value

            # Convert row dict to one-row dataframe and buffer it.
            result_df = pd.DataFrame.from_dict(result_dict, orient="index")
            df_list.append(result_df.T)

        # Buffer per-solve results; write once at simulation end.
        self.result_list.append(pd.concat(df_list))

    def write_results(self, path):
        """
        Write all buffered detail rows into a CSV.
        """
        pd.concat(self.result_list).to_csv(path, index=False)

    @property
    def power_output(self):
        """
        Name of market-facing power variable used by Bidder/Tracker references.
        """
        return "P_V"

    @property
    def total_cost(self):
        """
        Cost expression accessor in thermal-style tuple format.
        """
        return ("tot_cost", 1)
