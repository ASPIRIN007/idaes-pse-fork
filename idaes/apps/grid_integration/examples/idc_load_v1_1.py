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
        preferred_load,
        shortfall_penalty,
        excess_penalty,
    ):
        self.load_name = load_name
        self.bus = bus
        self.bus_id = bus_id
        self.p_min = float(p_min)
        self.p_max = float(p_max)
        self.preferred_load = [float(v) for v in preferred_load]
        self.shortfall_penalty = float(shortfall_penalty)
        self.excess_penalty = float(excess_penalty)


class InternetDataCenter:
    """
    Internet Data Center (IDC) load model.
    This is a simple bidding-load model with bounded demand and
    linear penalties for deviating from preferred load.
    """

    segment_number = 4

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
            preferred_load=self._model_data_dict["Preferred Load Profile MW"],
            shortfall_penalty=self._model_data_dict["Shortfall Penalty"],
            excess_penalty=self._model_data_dict["Excess Penalty"],
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

        preferred_load_cols = [
            col for col in load_params.columns
            if col.startswith("Preferred Load MW ")
        ]

        if not preferred_load_cols:
            raise ValueError(
                "No preferred load profile columns found. "
                "Expected columns like 'Preferred Load MW 1', 'Preferred Load MW 2', ..."
            )

        preferred_load_cols = sorted(
            preferred_load_cols,
            key=lambda x: int(x.split()[-1])
        )

        preferred_load_profile = [float(row[col]) for col in preferred_load_cols]

        model_data = {
            "Load Name": row["Load Name"],
            "Bus": row["Bus"],
            "Bus ID": row["Bus ID"],
            "P Min MW": row["P Min MW"],
            "P Max MW": row["P Max MW"],
            "Preferred Load Profile MW": preferred_load_profile,
            "Shortfall Penalty": row["Shortfall Penalty"],
            "Excess Penalty": row["Excess Penalty"],
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

        preferred_load_profile = model_data["Preferred Load Profile MW"]

        preferred_load_init = {}
        for t in range(horizon):
            if t < len(preferred_load_profile):
                preferred_load_init[t] = float(preferred_load_profile[t])
            else:
                preferred_load_init[t] = float(preferred_load_profile[-1])

        b.preferred_load = pyo.Param(
            b.HOUR,
            initialize=preferred_load_init,
            mutable=True,
        )
        b.energy_price = pyo.Param(
            b.HOUR,
            initialize=0.0,
            mutable=True,
)

        b.shortfall_penalty = pyo.Param(
            initialize=float(model_data["Shortfall Penalty"]),
            mutable=True,
        )
        b.excess_penalty = pyo.Param(
            initialize=float(model_data["Excess Penalty"]),
            mutable=True,
        )

        b.P_load = pyo.Var(
            b.HOUR,
            initialize=preferred_load_init,
            bounds=(float(model_data["P Min MW"]), float(model_data["P Max MW"])),
            within=pyo.NonNegativeReals,
        )

        b.load_shortfall = pyo.Var(
            b.HOUR,
            initialize=0.0,
            within=pyo.NonNegativeReals,
        )
        b.load_excess = pyo.Var(
            b.HOUR,
            initialize=0.0,
            within=pyo.NonNegativeReals,
        )

        def preferred_load_balance_rule(m, t):
            return (
                m.P_load[t]
                + m.load_shortfall[t]
                - m.load_excess[t]
                == m.preferred_load[t]
            )

        b.preferred_load_balance = pyo.Constraint(
            b.HOUR,
            rule=preferred_load_balance_rule,
        )

        def total_cost_rule(m, t):
            return (
                m.energy_price[t] * m.P_load[t]
                + m.shortfall_penalty * m.load_shortfall[t]
                + m.excess_penalty * m.load_excess[t]
            )
        b.total_cost = pyo.Expression(
        b.HOUR,
        rule=total_cost_rule,
        )

        b.obj = pyo.Objective(
        expr=sum(b.total_cost[t] for t in b.HOUR),
        sense=pyo.minimize,
        )


        b.total_cost = pyo.Expression(
            b.HOUR,
            rule=total_cost_rule,
        )

    def update_model(self, b, preferred_load=None):
        """
        Update mutable model inputs for the IDC load block.
        """
        if preferred_load is None:
            return

        for t in b.HOUR:
            if isinstance(preferred_load, Real):
                b.preferred_load[t] = float(preferred_load)
            elif isinstance(preferred_load, dict):
                b.preferred_load[t] = float(
                    preferred_load.get(t, pyo.value(b.preferred_load[t]))
                )
            elif isinstance(preferred_load, (list, tuple)):
                if len(preferred_load) == 0:
                    raise ValueError("preferred_load list/tuple cannot be empty.")
                elif t < len(preferred_load):
                    b.preferred_load[t] = float(preferred_load[t])
                else:
                    b.preferred_load[t] = float(preferred_load[-1])
            else:
                raise TypeError(
                    "preferred_load must be a scalar, list/tuple, or dict."
                )

    def record_results(self, b, date=None, hour=None):
        """
        Record solved IDC model results for the current block.
        """
        df_list = []
        load_name = self.model_data.load_name

        for t in b.HOUR:
            result_dict = {
                "Date": date,
                "Hour": hour,
                "Time": t,
                "Load": load_name,
                "P Load [MW]": pyo.value(b.P_load[t]),
                "Preferred Load [MW]": pyo.value(b.preferred_load[t]),
                "Load Shortfall [MW]": pyo.value(b.load_shortfall[t]),
                "Load Excess [MW]": pyo.value(b.load_excess[t]),
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
