# Double Loop Demo Run Report (2026-03-01)

## Run status
- Status: SUCCESS (completed simulation end-to-end)
- Run timestamp: 2026-03-01 10:38:08 EST
- Output directory: `/var/folders/w5/vzcfrmvn4pd_ld2d5b_9vs9w0000gr/T/doubleloop_demo_cbc__ke55vnd`

## Inputs used

### 1) Data input
- `data_path`: `/Users/vardhans/Projects/idaes-pse/idaes/tests/prescient/5bus`
- `input_format`: `rts-gmlc`

### 2) Market simulation configuration
- `start_date`: `07-10-2020`
- `num_days`: `1`
- `sced_horizon`: `4`
- `ruc_horizon`: `48`
- `sced_frequency_minutes`: `60`
- `simulate_out_of_sample`: `True`
- `run_sced_with_persistent_forecast_errors`: `True`
- `compute_market_settlements`: `True`
- `day_ahead_pricing`: `LMP`
- `reserve_factor`: `0.0`
- `monitor_all_contingencies`: `False`

### 3) Solver input
- `deterministic_ruc_solver`: `cbc`
- `sced_solver`: `cbc`
- `ruc_mipgap`: `0.01`
- `deterministic_ruc_solver_options`: `{feas: off, DivingF: on}`
- `symbolic_solver_labels`: `True`
- `output_solver_logs`: `False`

### 4) Double-loop plugin input
- Plugin key: `plugin.doubleloop`
- `bidding_generator`: `10_STEAM`
- Plugin module: `coordinator.prescient_plugin_module`
- Coordinator wiring:
  - Bidder: `make_testing_bidder()`
  - Tracker: `make_testing_tracker()`
  - Projection tracker: `make_testing_tracker()`

### 5) Price thresholds input
- `price_threshold`: `1000`
- `contingency_price_threshold`: `100`
- `reserve_price_threshold`: `5`

## Outputs produced

### 1) Output files generated
- `bidder_detail.csv`
- `bidding_model_detail.csv`
- `bus_detail.csv`
- `contingency_detail.csv`
- `daily_summary.csv`
- `hourly_gen_summary.csv`
- `hourly_summary.csv`
- `line_detail.csv`
- `overall_simulation_output.csv`
- `plots/`
- `renewables_detail.csv`
- `reserves_detail.csv`
- `runtimes.csv`
- `thermal_detail.csv`
- `tracker_detail.csv`
- `tracking_model_detail.csv`
- `virtual_detail.csv`

### 2) Key aggregated results
From `overall_simulation_output.csv` (1 row):
- `Total demand`: `2922.689`
- `Total costs`: `24951.415285`
- `Total fixed costs`: `15672.975`
- `Total generation costs`: `9278.440285`
- `Total renewables curtailment`: `312.635`
- `Cumulative average price`: `8.537143`
- `Total payments`: `35050.827354`

From `daily_summary.csv` (1 row for `2020-07-10`):
- `Demand`: `2922.689`
- `Renewables available`: `1666.075`
- `Renewables used`: `1353.44`
- `Average price`: `8.537143`
- `Total payments`: `35050.827354`

### 3) Double-loop specific artifacts
- `bidder_detail.csv`: 144 rows, 24 columns
- `tracker_detail.csv`: 96 rows, 7 columns
- `bidding_model_detail.csv`: 1440 rows, 10 columns
- `tracking_model_detail.csv`: 96 rows, 8 columns

These confirm the double-coordinator flow ran through DA bidding, RT bidding, tracking, and result export.

## Notes
- Prescient emitted deprecation warnings during run, but simulation completed successfully.
- This was a 1-day demo run for workflow validation.
