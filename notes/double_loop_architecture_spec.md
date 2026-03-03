# Double Simulation Loop Architecture Spec

## 1. High-Level Purpose

The double-loop framework couples process-level optimization/control models with power-market clearing to simulate multi-timescale interactions between energy systems and wholesale electricity markets (hours to yearly operations). [Source: docs/reference_guides/apps/grid_integration/index.rst, docs/reference_guides/apps/grid_integration/Introduction.rst]

The Day-Ahead (DA) loop represents forecast -> bid -> market clearing (unit commitment in Prescient). [Source: docs/reference_guides/apps/grid_integration/Introduction.rst]

The Real-Time (RT) loop represents dispatch -> tracking -> settlement (economic dispatch + resource tracking). [Source: docs/reference_guides/apps/grid_integration/Introduction.rst]

Conceptually, IDAES-side objects (`Forecaster`, `Bidder`, `Tracker`, `Coordinator`) exchange data with Prescient through plugin callbacks; the `Coordinator` is the bridge on both DA and RT paths. [Source: docs/reference_guides/apps/grid_integration/Implementation.rst, docs/reference_guides/apps/grid_integration/Coordinator.rst, idaes/apps/grid_integration/coordinator.py]

## 2. Core Objects and Responsibilities

### Coordinator

#### Responsibilities

- Registers Prescient plugin callbacks for DA/RT bidding, dispatch tracking, data activation, and finalization. [Source: idaes/apps/grid_integration/coordinator.py]
- Orchestrates data exchange among `Bidder`, `Tracker`, `Forecaster`, and Prescient. [Source: docs/reference_guides/apps/grid_integration/Implementation.rst, idaes/apps/grid_integration/coordinator.py]
- Pushes Prescient hourly and DA statistics to the forecaster. [Source: idaes/apps/grid_integration/coordinator.py]
- Transfers DA/RT bids into Prescient generator dictionaries. [Source: idaes/apps/grid_integration/coordinator.py]
- Pulls DA prices/dispatch from Prescient results and stages current/next-day state. [Source: idaes/apps/grid_integration/coordinator.py]
- Sends tracked delivered power back to Prescient observed dispatch for settlement. [Source: idaes/apps/grid_integration/coordinator.py]

#### Inputs

- Prescient callback inputs (`options`, `simulator`, `ruc_instance`, `sced_instance`, result/stat objects). [Source: idaes/apps/grid_integration/coordinator.py]
- Outputs from `Bidder` (`compute_day_ahead_bids`, `compute_real_time_bids`). [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]
- Outputs from `Tracker` (`track_market_dispatch`, `get_last_delivered_power`). [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]

#### Outputs

- Updated Prescient generator parameter dictionaries (bid/cost/time-series values). [Source: idaes/apps/grid_integration/coordinator.py]
- Forecaster updates from Prescient stats. [Source: idaes/apps/grid_integration/coordinator.py]
- Internal state transitions (`current_*`, `next_*`, `current_avail_*`). [Source: idaes/apps/grid_integration/coordinator.py]

#### When It Is Invoked

- Throughout simulation via registered Prescient plugin lifecycle callbacks (initialization, pre/post RUC, pre/post operations, stats update, finalization). [Source: idaes/apps/grid_integration/coordinator.py]

#### Key Interactions

- `Coordinator` -> `Forecaster`: `fetch_hourly_stats_from_prescient`, `fetch_day_ahead_stats_from_prescient`. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/forecaster.py]
- `Coordinator` -> `Bidder`: `compute_day_ahead_bids`, `compute_real_time_bids`, model update calls. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]
- `Coordinator` -> `Tracker`: `track_market_dispatch`, `update_model`, `get_last_delivered_power`. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]
- `Coordinator` <-> Prescient: callback registration and mutable model-data updates for RUC/SCED. [Source: idaes/apps/grid_integration/coordinator.py]

### Bidder

#### Responsibilities

- Computes DA and RT market bids from optimization models using forecast uncertainty (scenario-based in stochastic bidder classes). [Source: docs/reference_guides/apps/grid_integration/Bidder.rst, idaes/apps/grid_integration/bidder.py]
- Formulates DA/RT bidding problems and records bid outputs. [Source: idaes/apps/grid_integration/bidder.py]
- Updates bidding model state between iterations (`update_day_ahead_model`, `update_real_time_model`). [Source: idaes/apps/grid_integration/bidder.py]

#### Inputs

- Forecasts from `Forecaster` (DA/RT price scenarios). [Source: idaes/apps/grid_integration/bidder.py, docs/reference_guides/apps/grid_integration/Bidder.rst]
- Realized DA prices/dispatches for RT bidding. [Source: idaes/apps/grid_integration/bidder.py]
- Config values: `day_ahead_horizon`, `real_time_horizon`, `n_scenario`, solver. [Source: idaes/apps/grid_integration/bidder.py]

#### Outputs

- Time-indexed bid dictionary with per-generator fields (`p_cost`, `p_min`, `p_max`, `p_min_agc`, `p_max_agc`, `startup_capacity`, `shutdown_capacity`, optional `fixed_commitment`). [Source: idaes/apps/grid_integration/bidder.py]
- Bid/result logs written at simulation end. [Source: idaes/apps/grid_integration/bidder.py]

#### Optimization Performed (if described)

- Documentation states bidder currently formulates a two-stage stochastic program for optimized time-varying bid curves, with scenario-dependent price/power pairs and convexity constraints. [Source: docs/reference_guides/apps/grid_integration/Bidder.rst]
- DA and RT example formulations for wind+PEM IES are documented, including underbid penalty in RT. [Source: docs/reference_guides/apps/grid_integration/Bidder.rst]

### Tracker

#### Responsibilities

- Solves MPC/NMPC-style tracking optimization to follow RT dispatch signals from Prescient. [Source: docs/reference_guides/apps/grid_integration/Tracker.rst, docs/reference_guides/apps/grid_integration/Introduction.rst]
- Adds dispatch, over-delivery, and under-delivery constructs to tracking model; penalizes deviation. [Source: idaes/apps/grid_integration/tracker.py]
- Returns implemented profiles and updates internal rolling statistics/state. [Source: idaes/apps/grid_integration/tracker.py]

#### Inputs

- Market dispatch trajectory/list assembled by coordinator. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]
- Tracking model object, `tracking_horizon`, `n_tracking_hour`, solver. [Source: idaes/apps/grid_integration/tracker.py]

#### Outputs

- Implemented profiles used to update tracker and bidder models. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]
- Last delivered power used by Prescient settlement/observed dispatch update. [Source: idaes/apps/grid_integration/coordinator.py]

#### Tracking Formulation Role

- RT tracking objective combines process operating cost and penalties on tracking deviation (`power_underdelivered`, `power_overdelivered`) under dispatch balance constraints. [Source: docs/reference_guides/apps/grid_integration/Tracker.rst, idaes/apps/grid_integration/tracker.py]

### Forecaster

#### Responsibilities

- Produces DA/RT market uncertainty forecasts used by bidder. [Source: docs/reference_guides/apps/grid_integration/Implementation.rst, idaes/apps/grid_integration/forecaster.py]
- In Prescient-interfacing forecasters, ingests Prescient hourly and DA stats to update internal data. [Source: idaes/apps/grid_integration/forecaster.py, idaes/apps/grid_integration/coordinator.py]

#### What Uncertainty It Models

- Market price uncertainty (e.g., LMP scenarios for DA and RT). [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, docs/reference_guides/apps/grid_integration/Bidder.rst, idaes/apps/grid_integration/forecaster.py]
- Capacity-factor forecasting appears in `PerfectForecaster` methods for renewable-PEM workflows. [Source: idaes/apps/grid_integration/forecaster.py]

#### What Data It Produces

- Scenario-indexed DA and RT price forecasts as dictionaries keyed by sample/scenario index. [Source: idaes/apps/grid_integration/forecaster.py]

## 3. Day-Ahead Loop Sequence (Step-by-Step)

1. Prescient invokes coordinator callback before RUC solve (`bid_into_DAM`). [Source: idaes/apps/grid_integration/coordinator.py]
2. If not first day, coordinator projects tracking trajectory (using projection tracker) and advances bidder DA model with projected implemented profiles. [Source: idaes/apps/grid_integration/coordinator.py]
3. Bidder requests DA+RT price forecasts from forecaster for DA horizon and scenario count. [Source: idaes/apps/grid_integration/bidder.py]
4. Bidder solves DA bidding optimization and returns DA bid dictionary. [Source: idaes/apps/grid_integration/bidder.py]
5. Coordinator stores `current_bids`/`next_bids` state and passes DA bids to Prescient RUC generator data (`p_cost`, limits, commitments). [Source: idaes/apps/grid_integration/coordinator.py]
6. Prescient clears DA market (unit commitment) and generates DA prices/dispatches. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst]
7. Post-RUC callbacks fetch DA prices and dispatches into coordinator (`next_DA_prices`, `next_DA_dispatches`, available DA arrays). [Source: idaes/apps/grid_integration/coordinator.py]
8. Coordinator pushes day-ahead stats from Prescient to forecaster for forecast-data updates. [Source: idaes/apps/grid_integration/coordinator.py]
9. After RUC activation, pending DA data becomes current (`current_* <- next_*`). [Source: idaes/apps/grid_integration/coordinator.py]

Includes required concepts:
- Time advancement: bidder and tracker models are advanced using implemented/projected profiles. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]
- Forecast generation: forecaster generates scenario DA/RT prices. [Source: idaes/apps/grid_integration/bidder.py, idaes/apps/grid_integration/forecaster.py]
- Bid construction: bidder builds bid curves/dictionaries. [Source: docs/reference_guides/apps/grid_integration/Bidder.rst, idaes/apps/grid_integration/bidder.py]
- Market clearing: Prescient RUC clears DA market. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst]
- Data storage: coordinator and bidder store state/results (`current/next`, CSV outputs). [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]

## 4. Real-Time Loop Sequence (Step-by-Step)

1. Before SCED operations solve, coordinator callback `bid_into_RTM` is invoked. [Source: idaes/apps/grid_integration/coordinator.py]
2. Coordinator calls bidder `compute_real_time_bids` with current date/hour plus realized DA prices/dispatches. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]
3. Bidder gets RT price forecasts and enforces/relaxes DA dispatch consistency in RT model depending on available realized DA horizon data. [Source: idaes/apps/grid_integration/bidder.py]
4. Coordinator passes RT bids into Prescient SCED model data for current hour/horizon. [Source: idaes/apps/grid_integration/coordinator.py]
5. Prescient dispatches real-time schedules by economic dispatch (SCED). [Source: docs/reference_guides/apps/grid_integration/Introduction.rst]
6. After operations callback, coordinator assembles tracking signal from SCED current dispatch + DA future dispatch context. [Source: idaes/apps/grid_integration/coordinator.py]
7. Tracker solves tracking problem (`track_market_dispatch`), returns implemented profiles, and coordinator updates tracker and bidder models. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]
8. During operations stats update, coordinator writes actual delivered power into Prescient observed dispatch fields for settlement usage. [Source: idaes/apps/grid_integration/coordinator.py]
9. Prescient settlement is based on actual production schedules per documented RT loop. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, docs/reference_guides/apps/grid_integration/Implementation.rst]
10. Result logging occurs in bidder/tracker objects and final write callbacks. [Source: idaes/apps/grid_integration/tracker.py, idaes/apps/grid_integration/bidder.py, idaes/apps/grid_integration/coordinator.py]

Includes required concepts:
- Dispatch retrieval: pulled from SCED instance (`pg` values). [Source: idaes/apps/grid_integration/coordinator.py]
- Tracking solve: tracker MPC solve. [Source: docs/reference_guides/apps/grid_integration/Tracker.rst, idaes/apps/grid_integration/tracker.py]
- Production update: bidder/tracker model updates from implemented profiles. [Source: idaes/apps/grid_integration/coordinator.py]
- Settlement: Prescient uses observed delivered dispatch and computes settlement. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, idaes/apps/grid_integration/coordinator.py]
- Data logging: result records in bidder/tracker, plus plugin finalization write. [Source: idaes/apps/grid_integration/bidder.py, idaes/apps/grid_integration/tracker.py, idaes/apps/grid_integration/coordinator.py]

## 5. Data Flow Interfaces

### Bid Curves Format

Conceptually documented as piecewise offer-price / operating-level pairs (price-MW segments). [Source: docs/reference_guides/apps/grid_integration/Bidder.rst]

Code-level coordinator/Prescient handoff format:
- `p_cost` represented as a time series of piecewise `cost_curve` values in generator dict.
- Additional fields include `p_min`, `p_max`, AGC bounds, startup/shutdown capacities, and optional fixed commitment.
[Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py]

### Dispatch Signal Format

Conceptually: Prescient RT dispatch signal sent to tracker; tracker follows it. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, docs/reference_guides/apps/grid_integration/Implementation.rst]

Code-level: tracker receives a list of dispatch values (`market_dispatch`), where element 0 is SCED dispatch and subsequent elements can be DA dispatch look-ahead values. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py]

### Schedule Format

Conceptually: DA and RT schedules are market-cleared and then tracked/implemented production schedules. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, docs/reference_guides/apps/grid_integration/Implementation.rst]

Code-level: schedules stored in coordinator arrays (`current_DA_dispatches`, `current_avail_DA_dispatches`), tracker profile dictionaries, and bidder/tracker result tables. [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/tracker.py, idaes/apps/grid_integration/bidder.py]

### Settlement Data

Conceptually: settlement based on actual energy production schedules. [Source: docs/reference_guides/apps/grid_integration/Introduction.rst, docs/reference_guides/apps/grid_integration/Implementation.rst]

Code-level: coordinator updates Prescient `observed_*_dispatch_levels` with tracker-delivered power so Prescient can compute settlement. [Source: idaes/apps/grid_integration/coordinator.py]

## 6. State Variables Across Time

State that evolves across DA/RT loops:
- Bid state: `current_bids`, `next_bids`. [Source: idaes/apps/grid_integration/coordinator.py]
- DA market signals: `current_DA_prices`, `next_DA_prices`, `current_DA_dispatches`, `next_DA_dispatches`, plus `current_avail_*` rolling availability vectors. [Source: idaes/apps/grid_integration/coordinator.py]
- Tracker historical/rolling state: `daily_stats`, internal model states via profile updates, last delivered power. [Source: idaes/apps/grid_integration/tracker.py, idaes/apps/grid_integration/coordinator.py]
- Forecaster historical data (for Prescient-integrated forecasters): stored DA/RT price histories and rolling retention windows. [Source: idaes/apps/grid_integration/forecaster.py]

Persistent information between iterations:
- Implemented profiles produced by tracking and then fed to bidder/tracker model updates.
- DA outputs computed one day become active the next day (`activate_pending_DA_data`).
[Source: idaes/apps/grid_integration/coordinator.py]

## 7. Configuration & Control Parameters

- Simulation horizon parameters:
  - `options.ruc_horizon` for DA bid insertion horizon in RUC.
  - `options.sced_horizon` for RT bid insertion horizon in SCED.
  - Bidder `day_ahead_horizon`, `real_time_horizon`.
  - Tracker `tracking_horizon` and `n_tracking_hour`.
  [Source: idaes/apps/grid_integration/coordinator.py, idaes/apps/grid_integration/bidder.py, idaes/apps/grid_integration/tracker.py]

- Scenario count:
  - Bidder `n_scenario` with positive-integer validation.
  [Source: idaes/apps/grid_integration/bidder.py]

- Solver settings:
  - Bidder and tracker require valid Pyomo `OptSolver` objects.
  [Source: idaes/apps/grid_integration/bidder.py, idaes/apps/grid_integration/tracker.py]

- Market timing parameters:
  - `options.ruc_execution_hour` used in projection before DA bidding.
  - current simulation `date`/`hour` from Prescient time manager.
  [Source: idaes/apps/grid_integration/coordinator.py]

- Config files mentioned:
  - Not specified in docs.
  [Source: docs/reference_guides/apps/grid_integration/*.rst]

## 8. Top 15 Search Targets for Code Mapping (for Step 2)

1. `DoubleLoopCoordinator`
2. `register_plugins`
3. `bid_into_DAM`
4. `fetch_DA_prices`
5. `fetch_DA_dispatches`
6. `activate_pending_DA_data`
7. `bid_into_RTM`
8. `track_sced_signal`
9. `update_observed_dispatch`
10. `Bidder.compute_day_ahead_bids`
11. `Bidder.compute_real_time_bids`
12. `Tracker.track_market_dispatch`
13. `AbstractPrescientPriceForecaster.fetch_hourly_stats_from_prescient`
14. `AbstractPrescientPriceForecaster.fetch_day_ahead_stats_from_prescient`
15. `p_cost` / `cost_curve` / `current_avail_DA_dispatches` (key interface/state keywords)

