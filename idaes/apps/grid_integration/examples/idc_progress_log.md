# IDC Load Bidding Progress Log

This file records the development history of the IDC bidding-load workflow in
the grid integration examples. It is intended to be updated as each checkpoint
is completed so we have a clear running history of what changed, why it changed,
and what the current state of the workflow is.

## Scope

Main IDC-related files in this workflow:

- [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv)
- [idc_utils.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_utils.py)
- [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py)
- [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py)
- [idc_load_prescient_plugin.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_prescient_plugin.py)
- [idc_load_v1_1_run.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1_run.py)
- [run_thermal_generator_comparison.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/run_thermal_generator_comparison.py)
- [prescient_lmp_stats.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/prescient_lmp_stats.py)
- [export_lmp_forecast_arrays.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/export_lmp_forecast_arrays.py)

## Development History

### 1. Initial IDC bidding-load integration

Goal:
- Build a first IDC example that can bid as a controllable load into the
  existing Prescient 5-bus case.

Main choices:
- Reuse the Prescient 5-bus RTS-GMLC-style case as the baseline system.
- Target an existing load key in the case instead of inventing a new load object.
- Use `bus4` as the controllable load because it is a valid load key in the
  5-bus case.

Work completed:
- Confirmed that Egret/Prescient creates load elements keyed by bus name for
  the 5-bus case.
- Created [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv) as a custom IDC asset table.
- Created [idc_utils.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_utils.py) to load IDC input data, bus data, and price statistics.
- Created [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py) with the first `InternetDataCenter` model.
- Created [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py) for a simple load bidder.
- Created [idc_load_prescient_plugin.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_prescient_plugin.py) to inject load bids into Prescient.
- Created [idc_load_v1_1_run.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1_run.py) as the runner.

Result:
- The end-to-end Prescient loop ran successfully.
- `bus4` demand was overridden by the plugin as intended.

Reference checkpoint:
- Git tag: `idc-load-hourly-profile-checkpoint`
- Commit: `0ee0692a3`

### 2. Hourly preferred-load profile

Goal:
- Replace a single constant IDC load value with an hourly profile.

Main changes:
- Extended [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv) with `Preferred Load MW 1` through `Preferred Load MW 24`.
- Updated `IDCLoadModelData` and `assemble_model_data()` in [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py) to read an hourly preferred-load profile.
- Updated `populate_model()` so `preferred_load[t]` was initialized hour by hour.
- Updated `update_model()` and the RT bidder logic so the preferred-load profile shifted with the simulated real-time hour.

Result:
- The hourly preferred-load profile flowed correctly through the bidder and into
  Prescient.
- `bus4` demand in `bus_detail.csv` followed the intended hourly pattern.

Reference checkpoint:
- Commit message: `Add hourly IDC bidding load profile integration`
- Tag: `idc-load-hourly-profile-checkpoint`

### 3. First price-responsive objective

Goal:
- Make the IDC load respond to energy price instead of only replaying the
  preferred-load profile.

Main changes:
- Added `energy_price[t]` as a mutable parameter in [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py).
- Updated [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py) to fetch DA and RT price forecasts and pass them into the model before solve.
- Added a real objective in the IDC model so Pyomo optimized the cost expression instead of only finding a feasible point.

Important fixes made during this stage:
- Corrected `self.service_value` to `m.service_value` in the objective.
- Fixed duplicate `b.total_cost` definition.
- Made `_select_price_series()` more robust to different return types from the forecaster.
- Added validation for empty scenario forecasts in `_select_price_series()`.

Result:
- The IDC model became price-responsive.
- The first price-responsive behavior was very bang-bang, often choosing `0` or a high service level.

Relevant commits:
- `dd69585c3` added service value in IDC data/objective
- `ac17f7287` removed duplicate `b.total_cost`
- `1b0ff4d22` improved `_select_price_series()`
- `f23f1f0c4` corrected service value usage in the model objective
- `8d4fcccc0` added more bidder robustness checks

### 4. LMP comparison and utility scripts

Goal:
- Understand whether the hard-coded price statistics in `utils.py` were
  consistent with the 5-bus case.

Main changes:
- Added [prescient_lmp_stats.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/prescient_lmp_stats.py) to run a longer vanilla Prescient case and compute hourly DA/RT LMP statistics.
- Added [export_lmp_forecast_arrays.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/export_lmp_forecast_arrays.py) to export the four placeholder-forecaster arrays automatically from `bus_detail.csv`.
- Added [run_thermal_generator_comparison.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/run_thermal_generator_comparison.py) to compare vanilla Prescient and plugin-modified runs more easily.

Findings:
- The empirical bus-level arrays from repeated 5-bus simulations were not a
  strong enough hour-by-hour match to prove they were the origin of the
  hard-coded `utils.py` values.
- The hard-coded `utils.py` values still looked like a better stylized
  placeholder forecast profile than the bus4 empirical arrays.

Relevant commit:
- `7033d5247` added helper scripts for comparing and validating the forecast arrays

### 5. Backlog-based IDC formulation

Goal:
- Move from a preferred-load-based formulation to an IDC-native workload and
  backlog formulation.

Main modeling shift:
- Replace the old `preferred_load` formulation with:
  - `workload_arrival[t]`
  - `work_served[t]`
  - `backlog[t]`
  - `initial_backlog`
  - `backlog_penalty`

Main changes:
- Reworked [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv) to remove preferred-load columns and add workload/backlog inputs.
- Reworked [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py):
  - removed preferred-load-centered logic
  - added workload arrival and backlog state
  - added backlog balance constraints
  - linked `work_served[t]` to `P_load[t]`
  - added `get_implemented_profile()` and `get_last_backlog()` helpers
- Updated [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py):
  - switched RT profile shifting from `preferred_load` to `workload_arrival`
  - added backlog carryover support using `initial_backlog`
  - wired IDC `record_results()` and `write_results()` so `idc_load_detail.csv` is produced

Result:
- The model became stateful in an IDC-specific way.
- `idc_load_detail.csv` now records workload arrival, served work, backlog, and cost.

Relevant commit:
- `c600933f5` backlog formulation, removal of preferred load, comparison script, and IDC detail logging

### 6. Backlog stabilization refinements

Goal:
- Reduce unrealistic backlog growth and extreme deferral.

Main changes:
- Added `Max Backlog` to [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv) and enforced `backlog[t] <= max_backlog` in [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py).
- Added `Nondeferrable Fraction` to [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv).
- Enforced a minimum-served-work constraint:
  - `work_served[t] >= nondeferrable_fraction * workload_arrival[t]`

Current values in the example:
- `Max Backlog = 60.0`
- `Nondeferrable Fraction = 0.6`

Result:
- Backlog is now capped.
- A fixed share of workload is always served immediately.
- The backlog model behaves more consistently and is easier to interpret from
  `idc_load_detail.csv`.

### 7. Result logging and bidder regression coverage

Goal:
- Make the IDC internal result log easier to analyze and add a regression guard
  for the new backlog-carryover behavior in the bidder.

Main changes:
- Updated [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py)
  so `record_results()` accepts `market=None, **kwargs` and writes a `Market`
  column into `idc_load_detail.csv`.
- Updated [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py)
  so both DA and RT solves pass the market label through to
  `record_results(...)`.
- Added [test_load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/tests/test_load_bidder.py)
  to cover backlog propagation across successive real-time bidding solves.

Result:
- `idc_load_detail.csv` now distinguishes day-ahead and real-time solves.
- The backlog-carryover path in `LoadBidder` has a focused unit regression test.
- Verified with:
  - `pytest -q idaes/apps/grid_integration/tests/test_load_bidder.py`
  - result: `1 passed`

## Current Status

The IDC workflow currently supports:

- bidding a flexible load into the Prescient 5-bus case
- DA and RT price-responsive bidding
- workload-arrival-based scheduling
- backlog state and backlog carryover in RT
- hard backlog cap
- nondeferrable workload fraction
- detailed internal logging through `idc_load_detail.csv`
- market-labeled IDC result rows
- a regression test covering RT backlog carryover in `LoadBidder`

The workflow is now beyond a simple “preferred load profile” example and has a
stateful IDC-specific formulation.

## Current Working State

Right now the code builds an IDC bidding-load model on top of the existing
Prescient 5-bus case, targets `bus4` as the controllable load, and solves both
day-ahead and real-time bidding problems using workload arrivals, backlog
carryover, price forecasts, and a bounded service model. The runner produces
Prescient outputs in `demo_outputs/idc_load_v1_1_*`, including
`load_bidder_detail.csv`, `bus_detail.csv`, and `idc_load_detail.csv`. In the
current state, the model is successfully modifying `bus4` demand, writing its
internal backlog/work-served trajectory, labeling those rows by market, and
carrying backlog through the RT loop. The backlog is now bounded by a hard cap
and a nondeferrable workload fraction. The RT behavior can still look somewhat
bursty because the horizon is short and the formulation is still intentionally
simple and linear.

## Key Interfaces Between Files

### Data flow overview

The current file-to-file flow is:

1. [idc_load_data.csv](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_data.csv)
   provides the IDC asset parameters and workload profile.
2. [idc_utils.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_utils.py)
   reads the IDC CSV, the 5-bus case bus data, and the placeholder price
   statistics.
3. [idc_load_v1_1.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1.py)
   converts the CSV row into model data and builds the Pyomo optimization model.
4. [load_bidder.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/load_bidder.py)
   uses the IDC model object, pulls forecasts from the forecaster, solves DA/RT
   problems, assembles Prescient-compatible load bids, records bidder-level
   results, and forwards IDC-model results to `idc_load_detail.csv`.
5. [idc_load_prescient_plugin.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_prescient_plugin.py)
   injects those bids into Prescient callbacks by modifying the target load’s
   `p_load` time series.
6. [idc_load_v1_1_run.py](/Users/vardhans/Projects/idaes-pse/idaes/apps/grid_integration/examples/idc_load_v1_1_run.py)
   points Prescient at the 5-bus dataset and runs the whole example.

### What `load_bidder.py` expects from `idc_load_v1_1.py`

`LoadBidder` currently expects the bidding model object to provide:

- methods:
  - `populate_model(...)`
  - `update_model(...)`
  - `record_results(...)`
  - `write_results(...)`
  - `get_implemented_profile(...)`
  - `get_last_backlog(...)`
- `model_data` attributes:
  - `load_name`
  - `bus`
  - `workload_arrival`
  - `initial_backlog`
- model-level properties:
  - `power_output`
  - `total_cost`

If these names or signatures change in the IDC model, the bidder will likely
break first.

### What the plugin expects from the bidder

The plugin assumes:

- `LoadBidder.compute_day_ahead_bids(...)` and
  `LoadBidder.compute_real_time_bids(...)` return bids in the form:
  `{market_hour: {load_name: {"p_load": value}}}`
- `LoadBidder.write_results(path)` writes bidder-side result files
- the target load exists in `instance.data["elements"]["load"]`

If the bid dictionary shape changes, the plugin’s Prescient write-back logic
must be updated too.

## Known Fragile Spots

- The current RT behavior is still somewhat bursty because:
  - the RT horizon is short
  - the model is linear
  - there is no terminal backlog penalty yet
- `work_served[t] == P_load[t]` is a simplifying assumption, not a deeply
  physical conversion model. It is intentionally simple for now.
- The backlog carryover logic is lightweight and currently handled in the bidder
  using `initial_backlog`, not yet through a full tracker/coordinator design.
- There is currently only a focused unit test for backlog carryover in
  `LoadBidder`; broader end-to-end test coverage for the IDC path is still
  limited.
- The placeholder forecaster is still a stylized statistical forecast model,
  not a realistic trained forecasting model.
- The IDC formulation is now workload/backlog-based, so any older code or
  comments that still mention “preferred load” should be treated with caution.
- The 5-bus case is still the underlying system of record. The IDC plugin does
  not define a new market case; it modifies an existing load in the Prescient
  case.

## Known Limitations / Likely Next Refinements

- RT behavior can still be somewhat bursty.
- There is no terminal backlog penalty yet.
- Work served is currently linked 1:1 to electrical load for simplicity.
- Workload is still represented as a single aggregate stream rather than
  multiple classes such as batch vs interactive demand.
- A richer tracker/coordinator design may still be needed if IDC internal state
  becomes more complex.

## How To Update This Log

For each future checkpoint, append:

1. the goal of the checkpoint
2. the main files changed
3. the main modeling/code changes
4. the observed result
5. the commit hash or tag if available
