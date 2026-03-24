import os
from types import ModuleType

import pyomo.environ as pyo
from pyomo.common.config import ConfigDict, ConfigValue

from idaes.apps.grid_integration import PlaceHolderForecaster
from idaes.apps.grid_integration.load_bidder import LoadBidder
from idaes.apps.grid_integration.examples.idc_load_v1_1 import InternetDataCenter
from idaes.apps.grid_integration.examples.idc_utils import (
    rts_gmlc_load_dataframe,
    rts_gmlc_bus_dataframe,
    daily_da_price_means,
    daily_rt_price_means,
    daily_da_price_stds,
    daily_rt_price_stds,
)

this_module_dir = os.path.dirname(__file__)

load_name = "bus4"
day_ahead_bidding_horizon = 48
real_time_bidding_horizon = 4
n_scenario = 10

forecaster = PlaceHolderForecaster(
    daily_da_price_means=daily_da_price_means,
    daily_rt_price_means=daily_rt_price_means,
    daily_da_price_stds=daily_da_price_stds,
    daily_rt_price_stds=daily_rt_price_stds,
)

solver = pyo.SolverFactory("cbc")

bidding_model_object = InternetDataCenter(
    load_dataframe=rts_gmlc_load_dataframe,
    rts_gmlc_bus_dataframe=rts_gmlc_bus_dataframe,
    load_name=load_name,
)

load_bidder = LoadBidder(
    bidding_model_object=bidding_model_object,
    day_ahead_horizon=day_ahead_bidding_horizon,
    real_time_horizon=real_time_bidding_horizon,
    n_scenario=n_scenario,
    solver=solver,
    forecaster=forecaster,
)


class PrescientPluginModule(ModuleType):
    def __init__(self, get_configuration, register_plugins):
        self.get_configuration = get_configuration
        self.register_plugins = register_plugins


class IDCLoadPlugin:
    def __init__(self, bidder):
        self.bidder = bidder

    def get_configuration(self, key):
        config = ConfigDict()

        config.declare(
            "bidding_load",
            ConfigValue(
                domain=str,
                default=self.bidder.bidding_model_object.model_data.load_name,
                description="Specifies the load we derive bidding strategies for.",
            ),
        ).declare_as_argument("--bidding-load")

        return config

    def register_plugins(self, context, options, plugin_config):
        self.plugin_config = plugin_config

        context.register_before_ruc_solve_callback(self.bid_into_DAM)
        context.register_before_operations_solve_callback(self.bid_into_RTM)
        context.register_finalization_callback(self.write_plugin_results)

    @property
    def prescient_plugin_module(self):
        return PrescientPluginModule(self.get_configuration, self.register_plugins)

    def _get_load_dict(self, instance):
        load_name = self.plugin_config["bidding_load"]
        loads = instance.data["elements"].get("load", {})

        if load_name not in loads:
            available = ", ".join(str(k) for k in loads.keys())
            raise KeyError(
                f"Load '{load_name}' not found in Prescient instance. "
                f"Available loads: [{available}]"
            )

        return loads[load_name]

    def _ensure_time_series(self, load_dict, horizon):
        p_load = load_dict.get("p_load", 0.0)

        if isinstance(p_load, dict) and p_load.get("data_type") == "time_series":
            values = list(p_load["values"])
        else:
            values = [float(p_load)]

        # Some load entries start as scalars, so pad them out before overwriting
        # a full DA or RT bidding horizon.
        if len(values) < horizon:
            fill_value = float(values[-1]) if len(values) > 0 else 0.0
            values.extend([fill_value] * (horizon - len(values)))

        load_dict["p_load"] = {
            "data_type": "time_series",
            "values": values,
        }
        return load_dict["p_load"]["values"]


    def _pass_DA_bid_to_prescient(self, options, ruc_instance, bids):
        load_name = self.plugin_config["bidding_load"]
        load_dict = self._get_load_dict(ruc_instance)

        horizon = options.ruc_horizon
        values = self._ensure_time_series(load_dict, horizon)

        # Day-ahead bids are written into the forward-looking RUC load series.
        for t in range(horizon):
            values[t] = bids[t][load_name]["p_load"]


    def _pass_RT_bid_to_prescient(self, options, sced_instance, bids, hour):
        load_name = self.plugin_config["bidding_load"]
        load_dict = self._get_load_dict(sced_instance)

        horizon = options.sced_horizon
        values = self._ensure_time_series(load_dict, horizon)

        # Real-time bids are keyed by global hour, but SCED consumes a local
        # 0..horizon-1 series for the current solve.
        for k in range(horizon):
            values[k] = bids[hour + k][load_name]["p_load"]


    def bid_into_DAM(self, options, simulator, ruc_instance, ruc_date, ruc_hour):
        bids = self.bidder.compute_day_ahead_bids(date=ruc_date, hour=0)
        self._pass_DA_bid_to_prescient(options, ruc_instance, bids)

    def bid_into_RTM(self, options, simulator, sced_instance):
        date = simulator.time_manager.current_time.date
        hour = simulator.time_manager.current_time.hour

        bids = self.bidder.compute_real_time_bids(date=date, hour=hour)
        self._pass_RT_bid_to_prescient(options, sced_instance, bids, hour)

    def write_plugin_results(self, options, simulator):
        self.bidder.write_results(path=options.output_directory)


plugin = IDCLoadPlugin(load_bidder)

get_configuration = plugin.get_configuration
register_plugins = plugin.register_plugins
