import os
import pandas as pd
import pyomo.environ as pyo
from pyomo.opt.base.solvers import OptSolver


class LoadBidder:
    """
    Simple bidder for a flexible load model.

    This bidder solves the underlying IDC model and converts the
    optimized load schedule into Prescient-compatible load bids.
    """

    def __init__(
        self,
        bidding_model_object,
        day_ahead_horizon,
        real_time_horizon,
        n_scenario,
        solver,
        forecaster,
    ):
        self.bidding_model_object = bidding_model_object
        self.day_ahead_horizon = day_ahead_horizon
        self.real_time_horizon = real_time_horizon
        self.n_scenario = n_scenario
        self.solver = solver
        self.forecaster = forecaster

        self.day_ahead_model = self.formulate_DA_bidding_problem()
        self.real_time_model = self.formulate_RT_bidding_problem()
        self._check_inputs()
        self.bids_result_list = []

        self.load = self.bidding_model_object.model_data.load_name
        self.current_backlog = self.bidding_model_object.model_data.initial_backlog



    def _check_inputs(self):
        """
        Validate the inputs required to construct the load bidder.
        """
        self._check_bidding_model_object()
        self._check_horizons()
        self._check_n_scenario()
        self._check_solver()
        self._check_forecaster()

    def _check_bidding_model_object(self):
        """
        Check whether the bidding model object provides the interface
        required by LoadBidder.
        """
        method_list = [
        "populate_model",
        "update_model",
        "get_implemented_profile",
        "get_last_backlog",
        "record_results",
        "write_results",
        ]

        msg = "Bidding model object does not have required "

        for m in method_list:
            obtained_m = getattr(self.bidding_model_object, m, None)
            if obtained_m is None:
                raise AttributeError(
                    msg + f"method '{m}()' for LoadBidder."
                )

        model_data = getattr(self.bidding_model_object, "model_data", None)
        if model_data is None:
            raise AttributeError(
                msg + "property 'model_data' for LoadBidder."
            )

        required_model_data_attrs = ["load_name", "bus", "workload_arrival", "initial_backlog"]
        for attr in required_model_data_attrs:
            if getattr(model_data, attr, None) is None:
                raise AttributeError(
                    f"bidding_model_object.model_data must provide '{attr}'."
                )

    def _check_horizons(self):
        """
        Check whether the DA and RT horizons are positive integers.
        """
        for name, value in [
            ("day_ahead_horizon", self.day_ahead_horizon),
            ("real_time_horizon", self.real_time_horizon),
        ]:
            if not isinstance(value, int):
                raise TypeError(
                    f"{name} should be an integer, but a {type(value).__name__} was given."
                )
            if value <= 0:
                raise ValueError(
                    f"{name} should be greater than zero, but {value} was given."
                )

    def _check_n_scenario(self):
        """
        Check whether the number of price scenarios is a positive integer.
        """
        if not isinstance(self.n_scenario, int):
            raise TypeError(
                f"The number of scenarios should be an integer, but a {type(self.n_scenario).__name__} was given."
            )

        if self.n_scenario <= 0:
            raise ValueError(
                f"The number of scenarios should be greater than zero, but {self.n_scenario} was given."
            )

    def _check_solver(self):
        """
        Check whether the provided solver is a valid Pyomo solver object.
        """
        if not isinstance(self.solver, OptSolver):
            raise TypeError(
                f"The provided solver {self.solver} is not a valid Pyomo solver."
            )

    def _check_forecaster(self):
        """
        Check whether the forecaster provides the methods required by LoadBidder.
        """
        required_methods = [
            "forecast_day_ahead_prices",
            "forecast_real_time_prices",
        ]

        for method_name in required_methods:
            method = getattr(self.forecaster, method_name, None)
            if method is None:
                raise AttributeError(
                    f"The forecaster must provide '{method_name}()' for LoadBidder."
                )

    def formulate_DA_bidding_problem(self):
        model = pyo.ConcreteModel()
        self.bidding_model_object.populate_model(model, self.day_ahead_horizon)
        return model

    def formulate_RT_bidding_problem(self):
        model = pyo.ConcreteModel()
        self.bidding_model_object.populate_model(model, self.real_time_horizon)
        return model

    def compute_day_ahead_bids(self, date, hour=0):

        da_prices = self._get_day_ahead_energy_price(date=date, hour=hour)
        da_price_series = self._select_price_series(da_prices)
        self._pass_energy_price(self.day_ahead_model, da_price_series)
        self.solver.solve(self.day_ahead_model, tee=False)

        # Convert the solved IDC demand schedule into the nested bid structure
        # that the Prescient plugin writes back into the load dictionary.
        bids = self._assemble_bids(
            model=self.day_ahead_model,
            start_hour=hour,
            horizon=self.day_ahead_horizon,
        )

        self.record_bids(
            bids=bids,
            model=self.day_ahead_model,
            date=date,
            hour=hour,
            market="Day-ahead",
        )
        self.bidding_model_object.record_results(
            self.day_ahead_model, 
            date=date, 
            hour=hour, 
            market="Day-ahead",
        )

        return bids

    def _get_real_time_workload_arrival(self, hour):
        full_profile = self.bidding_model_object.model_data.workload_arrival
        # Helper function to shift the workload arrival profile so the
        # RT horizon starts at the current hour
        shifted_profile = []
        for t in range(self.real_time_horizon):
            idx = hour + t
            if idx < len(full_profile):
                shifted_profile.append(float(full_profile[idx]))
            else:
                shifted_profile.append(float(full_profile[-1]))

        return shifted_profile

    def _get_day_ahead_energy_price(self, date, hour):
        """
        Fetch the day-ahead energy price forecast for the bidding load bus.
        """
        bus = self.bidding_model_object.model_data.bus

        prices = self.forecaster.forecast_day_ahead_prices(
            date=date,
            hour=hour,
            bus=bus,
            horizon=self.day_ahead_horizon,
            n_samples=self.n_scenario,
        )

        return prices

    def _select_price_series(self, prices):
        """
        Select a single deterministic price series from the forecaster output.

        For the current IDC bidder, we use the first scenario/sample when multiple
        scenarios are provided.
        """
        if isinstance(prices, dict):
            if not prices:
                raise ValueError("Received empty price forecast dictionary.")
            first_key = sorted(prices.keys())[0]
            scenario_prices = prices[first_key]

            if hasattr(scenario_prices, "tolist"):
                scenario_prices = scenario_prices.tolist()

            if not isinstance(scenario_prices, (list, tuple)):
                raise TypeError(
                    "Unsupported price forecast format for scenario "
                    f"{first_key!r}: expected a sequence of prices."
                )

            if len(scenario_prices) == 0:
                raise ValueError(
                    f"Received empty price forecast for scenario {first_key!r}."
                )

            return [float(v) for v in scenario_prices]
        if hasattr(prices, "tolist"):
            prices = prices.tolist()

        if isinstance(prices, (list, tuple)):
            if len(prices) == 0:
                raise ValueError("Received empty price forecast.")

            first_item = prices[0]

            if hasattr(first_item, "tolist"):
                first_item = first_item.tolist()

            if isinstance(first_item, (list, tuple)):
                return [float(v) for v in first_item]

            return [float(v) for v in prices]
        # Helper function to select a single price series
        # from the forecaster output, which may contain multiple scenarios/samples.
        raise TypeError("Unsupported price forecast format returned by forecaster.")

    def _get_real_time_energy_price(self, date, hour):
        """
        Fetch the real-time energy price forecast for the bidding load bus.
        """
        bus = self.bidding_model_object.model_data.bus

        prices = self.forecaster.forecast_real_time_prices(
            date=date,
            hour=hour,
            bus=bus,
            horizon=self.real_time_horizon,
            n_samples=self.n_scenario,
        )

        return prices

    def compute_real_time_bids(self, date, hour=0):

        workload_arrival = self._get_real_time_workload_arrival(hour)
        self.update_real_time_model(
            workload_arrival=workload_arrival,
            initial_backlog=self.current_backlog,
        )

        rt_prices = self._get_real_time_energy_price(date=date, hour=hour)
        rt_price_series = self._select_price_series(rt_prices)
        self._pass_energy_price(self.real_time_model, rt_price_series)

        self.solver.solve(self.real_time_model, tee=False)

        bids = self._assemble_bids(
            model=self.real_time_model,
            start_hour=hour,
            horizon=self.real_time_horizon,
        )

        self.record_bids(
            bids=bids,
            model=self.real_time_model,
            date=date,
            hour=hour,
            market="Real-time",
        )
        self.bidding_model_object.record_results(
            self.real_time_model, 
            date=date, 
            hour=hour, 
            market="Real-time",
        )

        self._update_real_time_backlog(last_implemented_time_step=0)

        return bids

    def _assemble_bids(self, model, start_hour, horizon):
        load_name = self.bidding_model_object.model_data.load_name
        bids = {}

        for t in range(horizon):
            # Prescient expects bids keyed first by market hour and then by load name.
            p_load = round(pyo.value(model.P_load[t]), 4)
            bids[start_hour + t] = {
                load_name: {
                    "p_load": p_load,
                }
            }

        return bids

    def update_day_ahead_model(self, **kwargs):
        self.bidding_model_object.update_model(self.day_ahead_model, **kwargs)

    def update_real_time_model(self, **kwargs):
        self.bidding_model_object.update_model(self.real_time_model, **kwargs)

    def _update_real_time_backlog(self, last_implemented_time_step=0):
        """
        Update the RT initial backlog using the realized backlog from the
        last implemented RT step.
        """
        self.current_backlog = self.bidding_model_object.get_last_backlog(
            self.real_time_model,
            last_implemented_time_step,
        )

    def record_bids(self, bids, model, date, hour, market):
        df_list = []

        for market_hour, load_dict in bids.items():
            p_load = load_dict[self.load]["p_load"]

            result_dict = {
                "Date": date,
                "Hour": hour,
                "Market": market,
                "Market Hour": market_hour,
                "Load": self.load,
                "P Load Bid [MW]": p_load,
            }
            df_list.append(pd.DataFrame([result_dict]))

        self.bids_result_list.append(pd.concat(df_list, ignore_index=True))

    def _pass_energy_price(self, model, energy_price):
        """
        Pass an hourly energy price series into the bidding model.
        """
        for t in model.HOUR:
            if t < len(energy_price):
                model.energy_price[t] = float(energy_price[t])
            else:
                model.energy_price[t] = float(energy_price[-1])

    def write_results(self, path):

        self.bidding_model_object.write_results(path=path)

        if len(self.bids_result_list) == 0:
            return

        pd.concat(self.bids_result_list, ignore_index=True).to_csv(
            os.path.join(path, "load_bidder_detail.csv"),
            index=False,
        )
