# Double Loop Code Execution Map

## 1️⃣ Simulation Entry Point

### Invocation pattern

- No CLI entrypoint is defined inside `idaes/apps/grid_integration/` (no `argparse`/`click` or `if __name__ == '__main__'` in this subtree). [Source: idaes/apps/grid_integration/examples, idaes/apps/grid_integration/tests]
- Execution is driven by Prescient simulation startup: `prescient_simulator.Prescient().simulate(**options)`. [Source: idaes/apps/grid_integration/examples/thermal_generator.py:800, idaes/apps/grid_integration/tests/test_integration.py:156, idaes/apps/grid_integration/tests/test_integration.py:167]

### Coordinator construction

- Concrete class: `DoubleLoopCoordinator`. [Source: idaes/apps/grid_integration/coordinator.py:30]
- Constructed in plugin modules:
  - `coordinator = DoubleLoopCoordinator(...)` in `thermal_generator_prescient_plugin.py`. [Source: idaes/apps/grid_integration/examples/thermal_generator_prescient_plugin.py:93]
  - `coordinator = DoubleLoopCoordinator(...)` in integration test plugin. [Source: idaes/apps/grid_integration/tests/self_scheduler_integration_test_plugin.py:25]
  - Also constructed directly in integration tests. [Source: idaes/apps/grid_integration/tests/test_integration.py:34]

### How Coordinator is passed into Prescient

Two concrete paths are present:

1. Module-style plugin path:
- Plugin module exports:
  - `get_configuration = coordinator.get_configuration`
  - `register_plugins = coordinator.register_plugins`
  [Source: idaes/apps/grid_integration/examples/thermal_generator_prescient_plugin.py:100, idaes/apps/grid_integration/tests/self_scheduler_integration_test_plugin.py:32]
- Prescient options reference module path string in `options['plugin']['doubleloop']['module']`. [Source: idaes/apps/grid_integration/examples/thermal_generator.py:792]

2. In-memory plugin object path:
- `DoubleLoopCoordinator.prescient_plugin_module` returns `PrescientPluginModule(self.get_configuration, self.register_plugins)`. [Source: idaes/apps/grid_integration/coordinator.py:24, idaes/apps/grid_integration/coordinator.py:126]
- Tests pass this object into Prescient plugin config: `"module": coordinator.prescient_plugin_module`. [Source: idaes/apps/grid_integration/tests/test_integration.py:126]

## 2️⃣ Prescient Plugin Registration

Registration site:
- `DoubleLoopCoordinator.register_plugins(self, context, options, plugin_config)` [Source: idaes/apps/grid_integration/coordinator.py:58]

Registered callbacks and lifecycle stage mapping:

1. `initialize_customized_results`
- Hook: `context.register_initialization_callback(...)`
- Stage: initialization
- Purpose: initialize extension result buffers in simulator data manager.
- Source: `idaes/apps/grid_integration/coordinator.py:75`, `idaes/apps/grid_integration/coordinator.py:129`

2. `push_hourly_stats_to_forecaster`
- Hook: `context.register_for_hourly_stats(...)`
- Stage: hourly stats publication
- Purpose: forward Prescient hourly stats to forecaster.
- Source: `idaes/apps/grid_integration/coordinator.py:76`, `idaes/apps/grid_integration/coordinator.py:147`

3. `update_static_params`
- Hooks:
  - `register_after_get_initial_actuals_model_for_sced_callback`
  - `register_after_get_initial_actuals_model_for_simulation_actuals_callback`
  - `register_after_get_initial_forecast_model_for_ruc_callback`
- Stage: model initialization for SCED/simulation actuals/RUC forecast
- Purpose: copy static generator data from IDAES model data into Prescient generator dict.
- Source: `idaes/apps/grid_integration/coordinator.py:77`, `idaes/apps/grid_integration/coordinator.py:80`, `idaes/apps/grid_integration/coordinator.py:83`, `idaes/apps/grid_integration/coordinator.py:448`

4. `bid_into_DAM`
- Hook: `context.register_before_ruc_solve_callback(...)`
- Stage: before RUC solve
- Purpose: compute DA bids and write them into RUC instance.
- Source: `idaes/apps/grid_integration/coordinator.py:86`, `idaes/apps/grid_integration/coordinator.py:468`

5. `fetch_DA_prices`
- Hook: `context.register_after_ruc_generation_callback(...)`
- Stage: after RUC generation
- Purpose: persist DA LMPs on coordinator state.
- Source: `idaes/apps/grid_integration/coordinator.py:87`, `idaes/apps/grid_integration/coordinator.py:512`

6. `fetch_DA_dispatches`
- Hook: `context.register_after_ruc_generation_callback(...)`
- Stage: after RUC generation
- Purpose: persist DA cleared dispatch on coordinator state.
- Source: `idaes/apps/grid_integration/coordinator.py:88`, `idaes/apps/grid_integration/coordinator.py:545`

7. `push_day_ahead_stats_to_forecaster`
- Hook: `context.register_after_ruc_generation_callback(...)`
- Stage: after RUC generation
- Purpose: push DA result statistics into forecaster history/state.
- Source: `idaes/apps/grid_integration/coordinator.py:89`, `idaes/apps/grid_integration/coordinator.py:161`

8. `bid_into_RTM`
- Hook: `context.register_before_operations_solve_callback(...)`
- Stage: before SCED/operations solve
- Purpose: compute RT bids and inject into SCED model data.
- Source: `idaes/apps/grid_integration/coordinator.py:92`, `idaes/apps/grid_integration/coordinator.py:616`

9. `track_sced_signal`
- Hook: `context.register_after_operations_callback(...)`
- Stage: after SCED/operations callback
- Purpose: build dispatch tracking signal, solve tracker, update bidder/tracker models.
- Source: `idaes/apps/grid_integration/coordinator.py:93`, `idaes/apps/grid_integration/coordinator.py:718`

10. `update_observed_dispatch`
- Hook: `context.register_update_operations_stats_callback(...)`
- Stage: operations stats update
- Purpose: write delivered power to Prescient observed dispatch dictionaries (used by settlement path).
- Source: `idaes/apps/grid_integration/coordinator.py:94`, `idaes/apps/grid_integration/coordinator.py:759`

11. `activate_pending_DA_data`
- Hook: `context.register_after_ruc_activation_callback(...)`
- Stage: after RUC activation
- Purpose: advance `next_*` DA state into `current_*` state.
- Source: `idaes/apps/grid_integration/coordinator.py:95`, `idaes/apps/grid_integration/coordinator.py:791`

12. `write_plugin_results`
- Hook: `context.register_finalization_callback(...)`
- Stage: finalization
- Purpose: write bidder and tracker results to output directory.
- Source: `idaes/apps/grid_integration/coordinator.py:96`, `idaes/apps/grid_integration/coordinator.py:816`

Note on ordering:
- Callbacks are registered in a specific sequence in `register_plugins`, but exact callback execution order guarantees inside Prescient for callbacks sharing the same hook (e.g., three `after_ruc_generation` callbacks) are not proven in this repository alone. Not clear from code; requires runtime inspection.

## 3️⃣ Day-Ahead (DA) Execution Call Chain

### DA Callback Execution Order

Prescient invokes:
- `DoubleLoopCoordinator.bid_into_DAM(options, simulator, ruc_instance, ruc_date, ruc_hour)`
  - File: `idaes/apps/grid_integration/coordinator.py:468`

That function calls:
1. (If not first day) `project_tracking_trajectory(options, simulator, options.ruc_execution_hour)`
- File: `idaes/apps/grid_integration/coordinator.py:494`
- Internal calls:
  - `_clone_tracking_model()` [Source: `idaes/apps/grid_integration/coordinator.py:341`]
  - `assemble_project_tracking_signal(...)` [Source: `idaes/apps/grid_integration/coordinator.py:346`]
  - `projection_tracker.track_market_dispatch(...)` [Source: `idaes/apps/grid_integration/coordinator.py:350`, `idaes/apps/grid_integration/tracker.py:283`]
- Mutates:
  - `projection_tracker.daily_stats` (recorded during repeated tracking solves; then reset to `None`) [Source: `idaes/apps/grid_integration/coordinator.py:362`, `idaes/apps/grid_integration/tracker.py:315`]

2. `bidder.update_day_ahead_model(**full_projected_trajectory)`
- File: `idaes/apps/grid_integration/coordinator.py:498`
- Bidder call path: `update_day_ahead_model` -> `_update_model` -> `bidding_model_object.update_model(...)` for each scenario.
- Source: `idaes/apps/grid_integration/bidder.py:649`, `idaes/apps/grid_integration/bidder.py:675`

3. `bidder.compute_day_ahead_bids(date=ruc_date)`
- File: `idaes/apps/grid_integration/coordinator.py:501`
- Bidder call path:
  - `forecaster.forecast_day_ahead_and_real_time_prices(...)` [Source: `idaes/apps/grid_integration/bidder.py:526`]
  - `_compute_bids(...)` and `record_bids(...)` [Source: `idaes/apps/grid_integration/bidder.py:534`, `idaes/apps/grid_integration/bidder.py:504`]
- Mutates:
  - bidder result buffers (`bids_result_list`, model result records) [Source: `idaes/apps/grid_integration/bidder.py:1293`, `idaes/apps/grid_integration/bidder.py:717`]

4. Coordinator state mutation in `bid_into_DAM`:
- `self.current_bids = bids` on first day [Source: `idaes/apps/grid_integration/coordinator.py:503`]
- `self.next_bids = bids` always [Source: `idaes/apps/grid_integration/coordinator.py:505`]

5. `_pass_DA_bid_to_prescient(options, ruc_instance, bids)`
- File: `idaes/apps/grid_integration/coordinator.py:272`
- Internal call: `_update_bids(gen_dict, bids, start_hour=0, horizon=options.ruc_horizon)` [Source: `idaes/apps/grid_integration/coordinator.py:292`]

That function writes into Prescient generator dictionary fields:
- `p_cost` (time-series of piecewise cost curves)
- `p_max`, `p_min`, `p_min_agc`, `p_max_agc`, `fixed_commitment`
- `min_up_time`, `min_down_time`, `startup_capacity`, `shutdown_capacity`, `startup_fuel`, `startup_cost`
- Also removes `p_fuel` when `p_cost` is set.
[Source: `idaes/apps/grid_integration/coordinator.py:211`, `idaes/apps/grid_integration/coordinator.py:251`, `idaes/apps/grid_integration/coordinator.py:223`]

After RUC generation, Prescient invokes:
6. `fetch_DA_prices(...)`
- Mutates:
  - `current_avail_DA_prices` (first day: DA prices only; later: `current_DA_prices + DA_prices`)
  - `next_DA_prices`
- Source: `idaes/apps/grid_integration/coordinator.py:512`, `idaes/apps/grid_integration/coordinator.py:539`, `idaes/apps/grid_integration/coordinator.py:543`

7. `fetch_DA_dispatches(...)`
- Mutates:
  - `current_avail_DA_dispatches` (first day: DA dispatches only; later: `current_DA_dispatches + DA_dispatches`)
  - `next_DA_dispatches`
- Source: `idaes/apps/grid_integration/coordinator.py:545`, `idaes/apps/grid_integration/coordinator.py:578`, `idaes/apps/grid_integration/coordinator.py:585`

8. `push_day_ahead_stats_to_forecaster(...)`
- Calls `bidder.forecaster.fetch_day_ahead_stats_from_prescient(...)`
- Mutates forecaster internal history (implementation-specific; e.g., backcaster historical DA series).
- Source: `idaes/apps/grid_integration/coordinator.py:183`, `idaes/apps/grid_integration/forecaster.py:654`

After RUC activation, Prescient invokes:
9. `activate_pending_DA_data(...)`
- Mutates:
  - `current_bids`, `next_bids`
  - `current_DA_prices`, `next_DA_prices`
  - `current_DA_dispatches`, `next_DA_dispatches`
  - `current_avail_DA_prices`, `current_avail_DA_dispatches`
- Source: `idaes/apps/grid_integration/coordinator.py:805`

### DA Data Flow Summary

Inputs:
- `ruc_date`, `ruc_hour`, `ruc_instance`, simulator time state, forecaster outputs, tracker projection profiles. [Source: `idaes/apps/grid_integration/coordinator.py:468`, `idaes/apps/grid_integration/bidder.py:526`]

Outputs:
- RUC generator dictionary updated with DA bids.
- Coordinator DA state fields (`next_DA_prices`, `next_DA_dispatches`, then `current_*` on activation).
- Forecaster updated with DA market stats.
[Source: `idaes/apps/grid_integration/coordinator.py:272`, `idaes/apps/grid_integration/coordinator.py:512`, `idaes/apps/grid_integration/coordinator.py:791`, `idaes/apps/grid_integration/coordinator.py:161`]

State transitions (`next_*`, `current_*`):
- Produced in post-RUC callbacks: `next_bids`, `next_DA_prices`, `next_DA_dispatches`.
- Promoted in `activate_pending_DA_data`: `current_* <- next_*`, `next_* <- None`.
[Source: `idaes/apps/grid_integration/coordinator.py:505`, `idaes/apps/grid_integration/coordinator.py:543`, `idaes/apps/grid_integration/coordinator.py:585`, `idaes/apps/grid_integration/coordinator.py:805`]

## 4️⃣ Real-Time (RT) Execution Call Chain

### RT Callback Execution Order

Prescient invokes:
1. `DoubleLoopCoordinator.bid_into_RTM(options, simulator, sced_instance)`
- File: `idaes/apps/grid_integration/coordinator.py:616`

That function calls:
- `bidder.compute_real_time_bids(date, hour, realized_day_ahead_prices=self.current_avail_DA_prices, realized_day_ahead_dispatches=self.current_avail_DA_dispatches)`
  - File: `idaes/apps/grid_integration/coordinator.py:636`
  - Bidder internals:
    - `forecaster.forecast_real_time_prices(...)` [Source: `idaes/apps/grid_integration/bidder.py:562`]
    - `_pass_realized_day_ahead_dispatches(...)` mutates DA dispatch fix/unfix and underbid slack fix/unfix in RT model blocks [Source: `idaes/apps/grid_integration/bidder.py:622`]
    - `_pass_realized_day_ahead_prices(...)` mutates RT model DA price params (using realized + fallback forecast) [Source: `idaes/apps/grid_integration/bidder.py:584`]
    - `_compute_bids(...)` returns RT bid dictionary [Source: `idaes/apps/grid_integration/bidder.py:573`]
- `_pass_RT_bid_to_prescient(...)` writes RT bids into SCED generator data via `_update_bids(..., start_hour=hour, horizon=options.sced_horizon)`.
  - File: `idaes/apps/grid_integration/coordinator.py:587`

SCED solve interaction:
- Prescient performs operations/SCED solve after `before_operations_solve` callback.
- Exact solver internals are in Prescient, outside this repository. Not clear from code; requires runtime inspection.

Prescient invokes after operations:
2. `track_sced_signal(options, simulator, sced_instance, lmp_sced)`
- File: `idaes/apps/grid_integration/coordinator.py:718`
- Calls:
  - `assemble_sced_tracking_market_signals(...)` [Source: `idaes/apps/grid_integration/coordinator.py:741`]
    - Retrieves SCED dispatch from `sced_instance.data['elements']['generator'][gen_name]['pg']['values']` [Source: `idaes/apps/grid_integration/coordinator.py:670`]
    - Combines first SCED dispatch point + future DA dispatch look-ahead [Source: `idaes/apps/grid_integration/coordinator.py:705`, `idaes/apps/grid_integration/coordinator.py:712`]
  - `tracker.track_market_dispatch(market_dispatch=..., date=..., hour=...)` [Source: `idaes/apps/grid_integration/coordinator.py:749`, `idaes/apps/grid_integration/tracker.py:283`]
    - Tracker mutates dispatch params, solves optimization, records results, updates `daily_stats` [Source: `idaes/apps/grid_integration/tracker.py:299`, `idaes/apps/grid_integration/tracker.py:311`, `idaes/apps/grid_integration/tracker.py:326`]
  - `tracker.update_model(**implemented_profiles)` and `bidder.update_real_time_model(**implemented_profiles)`
    - File: `idaes/apps/grid_integration/coordinator.py:754`

Delivered power update / settlement handoff:
3. `update_observed_dispatch(options, simulator, ops_stats)`
- File: `idaes/apps/grid_integration/coordinator.py:759`
- Calls `tracker.get_last_delivered_power()` [Source: `idaes/apps/grid_integration/coordinator.py:787`, `idaes/apps/grid_integration/tracker.py:361`]
- Mutates Prescient operations stats dictionaries:
  - `ops_stats.observed_thermal_dispatch_levels[g]`
  - `ops_stats.observed_renewables_levels[g]`
  - `ops_stats.observed_virtual_dispatch_levels[g]`
  (only the dict containing generator `g` is updated)
- Source: `idaes/apps/grid_integration/coordinator.py:779`

### RT Data Flow Summary

Dispatch retrieval mechanism:
- SCED dispatch read from `sced_instance` generator `pg` time-series values. [Source: `idaes/apps/grid_integration/coordinator.py:670`]

Tracking solve location:
- `Tracker.track_market_dispatch(...)` in `idaes/apps/grid_integration/tracker.py:283`.

Settlement update location:
- `DoubleLoopCoordinator.update_observed_dispatch(...)` writes delivered power into Prescient observed dispatch stats structures. [Source: `idaes/apps/grid_integration/coordinator.py:759`]

## 5️⃣ State Mutation Table

| Stage | File | Function | State Variables Modified | Purpose |
|---|---|---|---|---|
| DA pre-RUC | `idaes/apps/grid_integration/coordinator.py` | `bid_into_DAM` | `current_bids` (first day), `next_bids` | Stage DA bids prior to activation |
| DA pre-RUC (non-first day) | `idaes/apps/grid_integration/coordinator.py` | `project_tracking_trajectory` | `projection_tracker.daily_stats` (then reset to `None`) | Project full-day trajectory for bidder state advancement |
| DA pre-RUC (non-first day) | `idaes/apps/grid_integration/bidder.py` | `update_day_ahead_model` / `_update_model` | bidding model internals across scenarios | Advance DA bidder model state |
| DA post-RUC | `idaes/apps/grid_integration/coordinator.py` | `fetch_DA_prices` | `current_avail_DA_prices`, `next_DA_prices` | Store DA prices and make available window |
| DA post-RUC | `idaes/apps/grid_integration/coordinator.py` | `fetch_DA_dispatches` | `current_avail_DA_dispatches`, `next_DA_dispatches` | Store DA dispatch and make available window |
| DA activation | `idaes/apps/grid_integration/coordinator.py` | `activate_pending_DA_data` | `current_bids`, `next_bids`, `current_DA_prices`, `next_DA_prices`, `current_DA_dispatches`, `next_DA_dispatches`, `current_avail_DA_prices`, `current_avail_DA_dispatches` | Promote next-day DA data into active state |
| RT pre-SCED | `idaes/apps/grid_integration/bidder.py` | `_pass_realized_day_ahead_dispatches` | `real_time_model.fs[s].day_ahead_power[t]` fixed/unfixed, `real_time_underbid_power[t]` fixed/unfixed | Enforce/relax DA coupling in RT optimization |
| RT pre-SCED | `idaes/apps/grid_integration/bidder.py` | `_pass_realized_day_ahead_prices` | `real_time_model.fs[s].day_ahead_energy_price[t]` | Populate DA realized/forecast prices for RT solve |
| RT pre-SCED | `idaes/apps/grid_integration/coordinator.py` | `_pass_RT_bid_to_prescient` / `_update_bids` | `sced_instance.data['elements']['generator'][gen]` bid fields | Push RT bids into Prescient SCED input |
| RT post-SCED | `idaes/apps/grid_integration/tracker.py` | `track_market_dispatch` | `model.power_dispatch[t]`, tracking constraints active/deactive, `daily_stats`, tracker result buffers | Solve tracking and persist implemented profile history |
| RT post-SCED | `idaes/apps/grid_integration/coordinator.py` | `track_sced_signal` | tracker model state (`tracker.update_model`), bidder RT model state (`bidder.update_real_time_model`) | Advance internal plant models using implemented profiles |
| RT stats update | `idaes/apps/grid_integration/coordinator.py` | `update_observed_dispatch` | `ops_stats.observed_thermal_dispatch_levels`, `ops_stats.observed_renewables_levels`, `ops_stats.observed_virtual_dispatch_levels` | Expose delivered power to Prescient settlement/stats pipeline |

## 6️⃣ Minimal Execution Timeline (Pseudo Stack Trace)

```text
Prescient().simulate(...)
  └── plugin load (module path or coordinator.prescient_plugin_module)
      └── DoubleLoopCoordinator.register_plugins(...)
          ├── register_before_ruc_solve_callback(bid_into_DAM)
          ├── register_after_ruc_generation_callback(fetch_DA_prices)
          ├── register_after_ruc_generation_callback(fetch_DA_dispatches)
          ├── register_after_ruc_generation_callback(push_day_ahead_stats_to_forecaster)
          ├── register_after_ruc_activation_callback(activate_pending_DA_data)
          ├── register_before_operations_solve_callback(bid_into_RTM)
          ├── register_after_operations_callback(track_sced_signal)
          ├── register_update_operations_stats_callback(update_observed_dispatch)
          └── register_finalization_callback(write_plugin_results)

  └── before_ruc_solve -> bid_into_DAM(...)
      ├── (if not first day) project_tracking_trajectory(...)
      │   └── projection_tracker.track_market_dispatch(...)
      ├── bidder.update_day_ahead_model(...)
      ├── bidder.compute_day_ahead_bids(...)
      └── _pass_DA_bid_to_prescient(...)

  └── RUC solve (inside Prescient)
  └── after_ruc_generation -> fetch_DA_prices(...)
  └── after_ruc_generation -> fetch_DA_dispatches(...)
  └── after_ruc_generation -> push_day_ahead_stats_to_forecaster(...)
  └── after_ruc_activation -> activate_pending_DA_data(...)

  └── before_operations_solve -> bid_into_RTM(...)
      ├── bidder.compute_real_time_bids(...)
      └── _pass_RT_bid_to_prescient(...)

  └── SCED/operations solve (inside Prescient)
  └── after_operations -> track_sced_signal(...)
      ├── assemble_sced_tracking_market_signals(...)
      ├── tracker.track_market_dispatch(...)
      ├── tracker.update_model(...)
      └── bidder.update_real_time_model(...)

  └── update_operations_stats -> update_observed_dispatch(...)
  └── finalization -> write_plugin_results(...)
```

Grounding:
- Timeline function names and hooks are from `idaes/apps/grid_integration/coordinator.py` lines 58-96 and corresponding method definitions.

## 7️⃣ Critical Integration Points (for Future DC/ASU Integration)

1. New Bidder class plug-in location
- Coordinator depends on bidder interface methods: `compute_day_ahead_bids`, `compute_real_time_bids`, `update_day_ahead_model`, `update_real_time_model`, `write_results`, and `bidding_model_object.model_data` fields.
- Invocation sites: `bid_into_DAM`, `bid_into_RTM`, `track_sced_signal`, `write_plugin_results`.
- Source: `idaes/apps/grid_integration/coordinator.py:468`, `idaes/apps/grid_integration/coordinator.py:616`, `idaes/apps/grid_integration/coordinator.py:754`, `idaes/apps/grid_integration/coordinator.py:831`, plus bidder abstract API in `idaes/apps/grid_integration/bidder.py:30`

2. Tracker replacement point
- Replace object passed as `tracker` / `projection_tracker` to `DoubleLoopCoordinator` constructor.
- Must support coordinator-used API: `track_market_dispatch`, `update_model`, `get_last_delivered_power`, properties used by coordinator (`time_set`, `model`, `daily_stats`).
- Source: `idaes/apps/grid_integration/coordinator.py:35`, `idaes/apps/grid_integration/coordinator.py:312`, `idaes/apps/grid_integration/coordinator.py:749`, `idaes/apps/grid_integration/coordinator.py:787`; tracker API in `idaes/apps/grid_integration/tracker.py:19`

3. Forecaster input consumption points
- DA consumption: `Bidder.compute_day_ahead_bids` -> `forecaster.forecast_day_ahead_and_real_time_prices(...)`.
- RT consumption: `Bidder.compute_real_time_bids` -> `forecaster.forecast_real_time_prices(...)` and fallback DA forecast via `forecast_day_ahead_prices(...)`.
- Prescient-driven update ingestion: coordinator callbacks `push_hourly_stats_to_forecaster` and `push_day_ahead_stats_to_forecaster`.
- Source: `idaes/apps/grid_integration/bidder.py:526`, `idaes/apps/grid_integration/bidder.py:562`, `idaes/apps/grid_integration/bidder.py:603`, `idaes/apps/grid_integration/coordinator.py:147`, `idaes/apps/grid_integration/coordinator.py:161`

4. Prescient bid format expectation point
- Adapter path is `_update_bids` in coordinator; it maps bidder `full_bids` fields into Prescient generator dictionary schema (`p_cost` as piecewise cost-curve time-series plus operational bounds).
- Source: `idaes/apps/grid_integration/coordinator.py:187`, `idaes/apps/grid_integration/coordinator.py:211`, `idaes/apps/grid_integration/coordinator.py:251`; bidder full bid assembly at `idaes/apps/grid_integration/bidder.py:1216`

5. Settlement-delivered power write point
- `update_observed_dispatch` writes tracker delivered power into `ops_stats.observed_*` dictionaries.
- This is the coordinator handoff point from tracker output to Prescient settlement/stats pipeline.
- Source: `idaes/apps/grid_integration/coordinator.py:759`

## Coordinator Control Flow Complexity Assessment

- Is control centralized?
  - Yes. Runtime control is centralized in `DoubleLoopCoordinator.register_plugins` and the callback methods on that class. [Source: `idaes/apps/grid_integration/coordinator.py:58`]

- Where are most state mutations concentrated?
  - Coordinator methods (`bid_into_DAM`, `fetch_DA_prices`, `fetch_DA_dispatches`, `activate_pending_DA_data`, `update_observed_dispatch`) and tracker `track_market_dispatch` are the highest-density mutation points.
  - Source: `idaes/apps/grid_integration/coordinator.py:468`, `idaes/apps/grid_integration/coordinator.py:512`, `idaes/apps/grid_integration/coordinator.py:545`, `idaes/apps/grid_integration/coordinator.py:791`, `idaes/apps/grid_integration/coordinator.py:759`, `idaes/apps/grid_integration/tracker.py:283`

- What part is most fragile for extension?
  - The data-contract boundary between bidder output and `_update_bids` mapping into Prescient generator dictionaries (field names/types/time-series structure) is the most fragile, since mismatches will break RUC/SCED input translation.
  - Secondary fragile area is callback sequencing assumptions across same-hook post-RUC callbacks (ordering guarantee not confirmed in-repo). Not clear from code; requires runtime inspection.
  - Source: `idaes/apps/grid_integration/coordinator.py:187`, `idaes/apps/grid_integration/coordinator.py:87`

