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
        self.solver.solve(self.day_ahead_model, tee=False)

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

    def compute_real_time_bids(self, date, hour=0):
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

    def write_results(self, path):
        if len(self.bids_result_list) == 0:
            return

        pd.concat(self.bids_result_list, ignore_index=True).to_csv(
            os.path.join(path, "load_bidder_detail.csv"),
            index=False,
        )
