

from numbers import Real
import pyomo.environ as pyo
import pandas as pd
import os


class IDCLoadModelData:
    """
    Simple model-data container for one IDC bidding load.
    """

    def __init__(
        self,
        load_name,
        bus,
        bus_id,
        p_min,
        p_max,
        workload_arrival,
        initial_backlog,
        backlog_penalty,
        max_backlog,
        nondeferrable_fraction,
        service_value,
    ):
        self.load_name = load_name
        self.bus = bus
        self.bus_id = bus_id
        self.p_min = float(p_min)
        self.p_max = float(p_max)
        self.workload_arrival = [float(v) for v in workload_arrival]
        self.initial_backlog = float(initial_backlog)
        self.backlog_penalty = float(backlog_penalty)
        self.max_backlog = float(max_backlog)
        self.nondeferrable_fraction = float(nondeferrable_fraction)
        self.service_value = float(service_value)


class InternetDataCenter:
    """
    Internet Data Center (IDC) load model.
    This model represents an IDC as a flexible load that serves arriving
    workload subject to power limits while carrying unfinished work as backlog.
    """

    def __init__(
        self,
        load_dataframe,
        rts_gmlc_bus_dataframe,
        load_name="bus4",
    ):
        self.load = load_name

        merged_load_dataframe = load_dataframe.merge(
            rts_gmlc_bus_dataframe[["Bus ID", "Bus Name"]],
            left_on="Bus",
            right_on="Bus Name",
        )

        self._model_data_dict = self.assemble_model_data(
            load_name=load_name,
            load_params=merged_load_dataframe,
        )

        self._model_data = IDCLoadModelData(
            load_name=self._model_data_dict["Load Name"],
            bus=self._model_data_dict["Bus"],
            bus_id=self._model_data_dict["Bus ID"],
            p_min=self._model_data_dict["P Min MW"],
            p_max=self._model_data_dict["P Max MW"],
            workload_arrival=self._model_data_dict["Workload Arrival"],
            initial_backlog=self._model_data_dict["Initial Backlog"],
            backlog_penalty=self._model_data_dict["Backlog Penalty"],
            max_backlog=self._model_data_dict["Max Backlog"],
            nondeferrable_fraction=self._model_data_dict["Nondeferrable Fraction"],
            service_value=self._model_data_dict["Service Value"],
        )

        self.result_list = []

    def assemble_model_data(self, load_name, load_params):
        """
        Assemble IDC load model data for the selected load.
        """
        selected = load_params[load_params["Load Name"] == load_name].copy()

        if selected.empty:
            raise ValueError(f"Load '{load_name}' not found in load dataframe.")

        if len(selected) > 1:
            raise ValueError(
                f"Multiple rows found for load '{load_name}'. "
                "Expected exactly one row."
            )

        row = selected.iloc[0]

        workload_arrival_cols = [
            col for col in load_params.columns if col.startswith("Workload Arrival ")
        ]

        if not workload_arrival_cols:
            raise ValueError(
                "No workload arrival columns found. "
                "Expected columns like 'Workload Arrival 1', 'Workload Arrival 2', ..."
            )

        workload_arrival_cols = sorted(
            workload_arrival_cols, key=lambda x: int(x.split()[-1])
        )

        workload_arrival_profile = [float(row[col]) for col in workload_arrival_cols]

        model_data = {
            "Load Name": row["Load Name"],
            "Bus": row["Bus"],
            "Bus ID": row["Bus ID"],
            "P Min MW": row["P Min MW"],
            "P Max MW": row["P Max MW"],
            "Workload Arrival": workload_arrival_profile,
            "Initial Backlog": row["Initial Backlog"],
            "Backlog Penalty": row["Backlog Penalty"],
            "Max Backlog": row["Max Backlog"],
            "Nondeferrable Fraction": row["Nondeferrable Fraction"],
            "Service Value": row["Service Value"],
        }

        return model_data


    @property
    def model_data(self):
        """
        Get the model data for the IDC load.
        """
        return self._model_data

    def populate_model(self, b, horizon):
        """
        Build the IDC load model on block ``b`` for the given horizon.
        """
        model_data = self._model_data_dict

        b.HOUR = pyo.Set(initialize=range(horizon))

        b.p_min = pyo.Param(
            initialize=float(model_data["P Min MW"]),
            mutable=False,
        )
        b.p_max = pyo.Param(
            initialize=float(model_data["P Max MW"]),
            mutable=False,
        )

        workload_arrival_profile = model_data["Workload Arrival"]
        workload_arrival_init = {}
        for t in range(horizon):
            if t < len(workload_arrival_profile):
                workload_arrival_init[t] = float(workload_arrival_profile[t])
            else:
                workload_arrival_init[t] = float(workload_arrival_profile[-1])

        b.workload_arrival = pyo.Param(
            b.HOUR,
            initialize=workload_arrival_init,
            mutable=True,
        )

        b.initial_backlog = pyo.Param(
            initialize=float(model_data["Initial Backlog"]),
            mutable=True,
        )

        b.backlog_penalty = pyo.Param(
            initialize=float(model_data["Backlog Penalty"]),
            mutable=True,
        )
        b.max_backlog = pyo.Param(
            initialize=min(
                float(model_data["Max Backlog"]),
                0.0,
            ),
            mutable=False,
        )
        b.nondeferrable_fraction = pyo.Param(
            initialize=float(model_data["Nondeferrable Fraction"]),
            mutable=False,
        )

        b.energy_price = pyo.Param(
            b.HOUR,
            initialize=0.0,
            mutable=True,
        )

        b.service_value = pyo.Param(
            initialize=float(model_data["Service Value"]),
            mutable=True,
        )

        b.P_load = pyo.Var(
            b.HOUR,
            initialize={
                t: min(workload_arrival_init[t], float(model_data["P Max MW"]))
                for t in b.HOUR
            },
            bounds=(float(model_data["P Min MW"]), float(model_data["P Max MW"])),
            within=pyo.NonNegativeReals,
        )

        b.work_served = pyo.Var(
            b.HOUR,
            initialize=workload_arrival_init,
            within=pyo.NonNegativeReals,
        )

        b.backlog = pyo.Var(
            b.HOUR,
            initialize=0.0,
            within=pyo.NonNegativeReals,
        )

        def served_load_link_rule(m, t):
            return m.work_served[t] == m.P_load[t]

        b.served_load_link = pyo.Constraint(
            b.HOUR,
            rule=served_load_link_rule,
        )

        # A fixed share of each hour's arriving workload is treated as
        # non-deferrable and must be served immediately.
        def nondeferrable_service_rule(m, t):
            return m.work_served[t] >= m.nondeferrable_fraction * m.workload_arrival[t]

        b.nondeferrable_service = pyo.Constraint(
            b.HOUR,
            rule=nondeferrable_service_rule,
        )

        # Served work in each hour cannot exceed the work currently available:
        # the incoming workload plus any carried backlog.
        def served_work_limit_rule(m, t):
            if t == 0:
                return m.work_served[t] <= m.initial_backlog + m.workload_arrival[t]
            return m.work_served[t] <= m.backlog[t - 1] + m.workload_arrival[t]

        b.served_work_limit = pyo.Constraint(
            b.HOUR,
            rule=served_work_limit_rule,
        )

        def backlog_balance_rule(m, t):
            if t == 0:
                return (
                    m.backlog[t]
                    == m.initial_backlog + m.workload_arrival[t] - m.work_served[t]
                )
            return (
                m.backlog[t]
                == m.backlog[t - 1] + m.workload_arrival[t] - m.work_served[t]
            )

        b.backlog_balance = pyo.Constraint(
            b.HOUR,
            rule=backlog_balance_rule,
        )

        # Keep backlog within a hard cap so the load cannot defer more work than
        # it could plausibly recover from with available capacity.
        def backlog_limit_rule(m, t):
            return m.backlog[t] <= m.max_backlog

        b.backlog_limit = pyo.Constraint(
            b.HOUR,
            rule=backlog_limit_rule,
        )

        def total_cost_rule(m, t):
            return (
                m.energy_price[t] * m.P_load[t]
                - m.service_value * m.work_served[t]
                + m.backlog_penalty * m.backlog[t]
            )

        b.total_cost = pyo.Expression(
            b.HOUR,
            rule=total_cost_rule,
        )

        b.obj = pyo.Objective(
            expr=sum(b.total_cost[t] for t in b.HOUR),
            sense=pyo.minimize,
        )

    def update_model(self, b, workload_arrival=None, initial_backlog=None):
        """
        Update mutable model inputs for the IDC load block.
        """
        if workload_arrival is not None:
            for t in b.HOUR:
                if isinstance(workload_arrival, Real):
                    b.workload_arrival[t] = float(workload_arrival)
                elif isinstance(workload_arrival, dict):
                    b.workload_arrival[t] = float(
                        workload_arrival.get(t, pyo.value(b.workload_arrival[t]))
                    )
                elif isinstance(workload_arrival, (list, tuple)):
                    if len(workload_arrival) == 0:
                        raise ValueError("workload_arrival list/tuple cannot be empty.")
                    elif t < len(workload_arrival):
                        b.workload_arrival[t] = float(workload_arrival[t])
                    else:
                        b.workload_arrival[t] = float(workload_arrival[-1])
                else:
                    raise TypeError(
                        "workload_arrival must be a scalar, list/tuple, or dict."
                    )

        if initial_backlog is not None:
            b.initial_backlog = float(initial_backlog)

    @staticmethod
    def get_implemented_profile(b, last_implemented_time_step):
        """
        Get the implemented workload-serving profile from the last solve.

        Args:
            b: Pyomo block
            last_implemented_time_step: last implemented time index

        Returns:
            dict: implemented profile information
        """
        implemented_power = [
            pyo.value(b.P_load[t]) for t in range(last_implemented_time_step + 1)
        ]
        implemented_work_served = [
            pyo.value(b.work_served[t]) for t in range(last_implemented_time_step + 1)
        ]
        implemented_backlog = [
            pyo.value(b.backlog[t]) for t in range(last_implemented_time_step + 1)
        ]

        return {
            "implemented_power": implemented_power,
            "implemented_work_served": implemented_work_served,
            "implemented_backlog": implemented_backlog,
        }


    @staticmethod
    def get_last_backlog(b, last_implemented_time_step):
        """
        Return the last implemented backlog value.

        Args:
            b: Pyomo block
            last_implemented_time_step: last implemented time index

        Returns:
            float: backlog at the last implemented time step
        """
        return pyo.value(b.backlog[last_implemented_time_step])


    def record_results(self, b, date=None, hour=None, market=None, **kwargs):
        """
        Record solved IDC model results for the current block.
        """
        df_list = []
        load_name = self.model_data.load_name

        for t in b.HOUR:
            result_dict = {
                "Date": date,
                "Hour": hour,
                "Market": market,
                "Time": t,
                "Load": load_name,
                "P Load [MW]": pyo.value(b.P_load[t]),
                "Workload Arrival": pyo.value(b.workload_arrival[t]),
                "Work Served": pyo.value(b.work_served[t]),
                "Backlog": pyo.value(b.backlog[t]),
                "Total Cost [$]": pyo.value(b.total_cost[t]),
            }
            df_list.append(pd.DataFrame([result_dict]))

        self.result_list.append(pd.concat(df_list, ignore_index=True))

    def write_results(self, path):
        """
        Write recorded IDC model results to CSV.
        """
        if len(self.result_list) == 0:
            return

        pd.concat(self.result_list, ignore_index=True).to_csv(
            os.path.join(path, "idc_load_detail.csv"),
            index=False,
        )

    @property
    def power_output(self):
        """
        Name of the power-output variable used by the bidder.
        """
        return "P_load"

    @property
    def total_cost(self):
        """
        Name and weight of the total-cost expression used by the bidder.
        """
        return ("total_cost", 1)
