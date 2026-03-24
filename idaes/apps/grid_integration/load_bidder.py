import os
import pandas as pd
import pyomo.environ as pyo


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

        self.load = self.bidding_model_object.model_data.load_name

        self.day_ahead_model = self.formulate_DA_bidding_problem()
        self.real_time_model = self.formulate_RT_bidding_problem()

        self.bids_result_list = []

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

        return bids

    def _get_real_time_preferred_load(self, hour):
        full_profile = self.bidding_model_object.model_data.preferred_load
        # Helper function to shift the preferred-load profile so the
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

        preferred_load = self._get_real_time_preferred_load(hour)
        self.update_real_time_model(preferred_load=preferred_load)

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
        if len(self.bids_result_list) == 0:
            return

        pd.concat(self.bids_result_list, ignore_index=True).to_csv(
            os.path.join(path, "load_bidder_detail.csv"),
            index=False,
        )
