# Price-Taker Test Case Walkthrough (Double Simulation Loop)

## 0. What question does this test case answer?

### What the test is validating
The `pricetaker` test suite validates construction and behavior of the **`PriceTakerModel` formulation stack** (LMP data ingestion, representative-day clustering, multiperiod model assembly, UC-like constraints, cashflow/objective utilities), not the Prescient-driven double-loop plugin execution.

Evidence:
- `PriceTakerModel` tests instantiate `PriceTakerModel()` repeatedly and call methods like `append_lmp_data`, `build_multiperiod_model`, `add_capacity_limits`, `add_ramping_limits`, `add_startup_shutdown`, `add_hourly_cashflows`, `add_overall_cashflows`. File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py`.
- No `DoubleLoopCoordinator`, `Bidder`, `Tracker`, `Forecaster`, or `Prescient().simulate(...)` appears in `idaes/apps/grid_integration/pricetaker/` or `idaes/apps/grid_integration/pricetaker/tests/` (code search result in this repo).

### What “price taker” means here
Conceptually: a resource that accepts market prices (cannot influence prices) and optimizes operations/design against exogenous LMP time series / representative days. Source: `docs/reference_guides/apps/grid_integration/multiperiod/Price_Taker.rst`.

Implementation context: `PriceTakerModel` is a multiperiod optimization container with LMP-driven objective and optional UC-like constraints through `UnitCommitmentData` utilities. File: `idaes/apps/grid_integration/pricetaker/price_taker_model.py`.

### Important scope clarification
A **full DA+RT Prescient double-loop run** exists in `idaes/apps/grid_integration/tests/test_integration.py` (using `DoubleLoopCoordinator` with testing bidder/tracker), but that integration test is not wired to `PriceTakerModel`. So this walkthrough maps:
1. What the actual price-taker tests build and validate.
2. How full double-loop execution works in this codebase.
3. What bridge is missing to run `PriceTakerModel` directly through DA/RT callbacks.

---

## 1. System setting and scenario definition

### What the price-taker tests actually model
The price-taker tests define **single-node/multiperiod process formulations**, not full Prescient network cases. Typical test flowsheets use:
- `simple_flowsheet_func`: scalar vars + one block (`blk`) with `power`, `op_mode`, `LMP`. File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py:36`.
- `build_foo_flowsheet`: one `OperationModel` (`op_blk`) and flowsheet-level expressions. File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py:79`.
- `build_power_cycle_with_storage`: two `OperationModel` blocks (`ngcc`, `coal_pp`) + one `StorageModel` (`battery`). File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py:90`.

No explicit bus/network topology is modeled in these tests (no Prescient network object in this test path).

### Time/horizon settings used in tests
- Default horizon if not set: `24` hours (warning-backed property default). File: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:191`.
- Explicit examples in tests:
  - `horizon_length=2`, `num_representative_days=3` in representative-day tests. File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py:356`.
  - `horizon_length=12`, `num_representative_days=2` in rep-day UC/ramping tests. File: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py:837`.
  - Full-signal case: `horizon_length=len(lmp_data)` and `num_representative_days=1` set automatically when not clustering. File: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:337`.

### Prescient UC/SCED in this test path
- In `pricetaker/tests`: no Prescient UC/SCED solve invocation.
- In full double-loop integration test (`test_integration.py`): Prescient is invoked with RUC/SCED options (`ruc_horizon=48`, `sced_horizon=4`, `sced_frequency_minutes=60`). File: `idaes/apps/grid_integration/tests/test_integration.py:89`.

### System Summary Table

| Item | Value | Where defined (file:path) |
|---|---|---|
| Prescient network generators | Not modeled in `pricetaker/tests` | `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py` |
| Prescient network loads | Not modeled in `pricetaker/tests` | `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py` |
| Price signal source | List/Series/DF passed to `append_lmp_data` | `idaes/apps/grid_integration/pricetaker/price_taker_model.py:221` |
| External sample LMP dataset | `lmp_data.csv` (8760 hourly rows + header) | `idaes/apps/grid_integration/pricetaker/tests/lmp_data.csv`, loaded in `test_clustering.py:35` |
| Default horizon length | 24 | `idaes/apps/grid_integration/pricetaker/price_taker_model.py:191` |
| Representative days | Optional clustering (`num_representative_days`) | `idaes/apps/grid_integration/pricetaker/price_taker_model.py:224` |
| Multiperiod index | `set_days`, `set_time`, `period[d,t]` | `idaes/apps/grid_integration/pricetaker/price_taker_model.py:344` |
| Full double-loop RUC horizon (separate integration test) | 48 | `idaes/apps/grid_integration/tests/test_integration.py:109` |
| Full double-loop SCED horizon (separate integration test) | 4 | `idaes/apps/grid_integration/tests/test_integration.py:97` |
| Full double-loop SCED frequency (separate integration test) | 60 minutes | `idaes/apps/grid_integration/tests/test_integration.py:108` |

---

## 2. Physical parameters and constraints defined by the test case

### Generator-/operation-like quantities in `PriceTakerModel` tests
In price-taker tests, these are not `GeneratorModelData` objects. They are represented as **`OperationModel` block variables/config data** and UC helper data.

#### Capacity limits
- Method: `add_capacity_limits(op_block_name, commodity, capacity, op_range_lb)`.
- Constraint form: `op_range_lb * capacity * op_mode[t] <= commodity[t] <= capacity * op_mode[t]`.
- Internal storage: block named `<op_block>_<commodity>_limits`.
- Files:
  - API and implementation: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:654`.
  - Generated constraints: `idaes/apps/grid_integration/pricetaker/unit_commitment.py:180`.
- Format:
  - `capacity`: float or Pyomo `Param/Var/Expression`.
  - `op_range_lb`: fraction [0,1].

#### Ramping limits
- Method: `add_ramping_limits(op_block_name, commodity, capacity, startup_rate, shutdown_rate, rampup_rate, rampdown_rate)`.
- Internal data contract via `UnitCommitmentData` (`startup_rate`, `shutdown_rate`, `rampup_rate`, `rampdown_rate`, `capacity`).
- Files:
  - API: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:723`.
  - Constraints: `idaes/apps/grid_integration/pricetaker/unit_commitment.py:205`.
- Format: fractional rates [0,1], capacity as scalar or Pyomo object.

#### Startup/shutdown + min up/down
- Method: `add_startup_shutdown(op_block_name, des_block_name=None, minimum_up_time=1, minimum_down_time=1)`.
- Requires operation block attributes: `op_mode`, `startup`, `shutdown`.
- Uses `install_unit` from design block if `des_block_name` is supplied.
- Files:
  - API: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:813`.
  - Constraint builder: `idaes/apps/grid_integration/pricetaker/unit_commitment.py:137`.

#### Cost/cashflow terms
- Hourly: `add_hourly_cashflows(revenue_streams, operational_costs)` builds `total_hourly_cost`, `total_hourly_revenue`, `net_hourly_cash_inflow` on each `period[d,t]` block.
- Overall: `add_overall_cashflows(...)` builds CAPEX/FOM/tax/profit/NPV variables and expressions in `cashflows` block.
- Files:
  - Hourly: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:897`.
  - Overall: `idaes/apps/grid_integration/pricetaker/price_taker_model.py:997`.

### Load-related quantities
- Explicit load demand profiles are **not defined** in these price-taker tests.
- Exogenous market signal is LMP time series (`lmp_data`) rather than a load model.
- Files: `idaes/apps/grid_integration/pricetaker/tests/test_price_taker_model.py` + `price_taker_model.py`.

### Storage-related quantities
- `StorageModel` defines `initial_holdup`, `final_holdup`, `charge_rate`, `discharge_rate` and a holdup balance with charge/discharge efficiencies.
- Files:
  - Model: `idaes/apps/grid_integration/pricetaker/design_and_operation_models.py:501`.
  - Auto-linking behavior in multiperiod build when storage blocks are found: `price_taker_model.py:371`.

### Price-taking assumption in code
- LMP is treated as input parameter (`LMP` mutable `Param` in operation blocks) and injected per period from `rep_days_lmp[d][t]` during model build.
- Files:
  - `OperationModel` LMP declaration: `design_and_operation_models.py:419`.
  - LMP assignment in multiperiod: `price_taker_model.py:362`.

---

## 3. How the test case constructs required objects (the “contract”)

### What `pricetaker/tests` constructs
`pricetaker/tests` constructs:
- `PriceTakerModel`
- optional `DesignModel`, `OperationModel`, `StorageModel`
- UC helper data (`UnitCommitmentData`, internally)
- no `Forecaster`, `Bidder`, `Tracker`, `DoubleLoopCoordinator`

### What full double-loop requires (separate integration path)
Full DA/RT loop requires:
- Forecaster
- Bidder
- Tracker
- ProjectionTracker
- DoubleLoopCoordinator
- Prescient plugin binding

These are constructed in `idaes/apps/grid_integration/tests/util.py` + `test_integration.py`, not in `pricetaker/tests`.

### Object Construction Table

| Object | Constructed where | Inputs required | What it produces |
|---|---|---|---|
| `PriceTakerModel` | `pricetaker/tests/test_price_taker_model.py` | none at ctor; later LMP data + flowsheet func | multiperiod optimization container `period[d,t]` |
| `DesignModel` (optional) | `test_price_taker_model.py` fixture/tests | design model function or fixed/variable design data | install binary, capex/fom, design constraints |
| `OperationModel` (optional) | `test_price_taker_model.py` helper flowsheets | model function or polynomial surrogate config; optional UC fields | op vars (`op_mode/startup/shutdown`), LMP param, operation constraints |
| `StorageModel` (optional) | `test_price_taker_model.py:121` | efficiencies, holdup/rate bounds | storage dynamics constraints |
| `UnitCommitmentData` (internal) | created in `PriceTakerModel._retrieve_uc_data` | commodity name, capacity, rates, op range | validated UC/ramping metadata for constraint builders |
| `Forecaster` | Not constructed in `pricetaker/tests`; constructed in `tests/util.py` as `ExampleForecaster` | prediction behavior | DA/RT scenario forecasts |
| `Bidder` | Not in `pricetaker/tests`; in `tests/util.py` via `Bidder(...)` | model object, DA/RT horizons, `n_scenario`, solver, forecaster | DA/RT bid dicts |
| `Tracker` | Not in `pricetaker/tests`; in `tests/util.py` via `Tracker(...)` | tracking model object, `tracking_horizon`, `n_tracking_hour`, solver | implemented profiles and delivered power |
| `ProjectionTracker` | Not in `pricetaker/tests`; second tracker in `test_integration.py` | same as tracker | projected daily trajectory for DA model update |
| `DoubleLoopCoordinator` | `tests/test_integration.py` | bidder, tracker, projection_tracker | Prescient callback registration and loop orchestration |

---

## 4. How Prescient is configured and invoked in the test

### In the actual price-taker tests
No Prescient invocation occurs in `idaes/apps/grid_integration/pricetaker/tests/`.

### In the full double-loop integration test (separate path)
- Prescient options fixture: `prescient_options` with `data_path`, `input_format='rts-gmlc'`, `ruc_horizon=48`, `sced_horizon=4`, `sced_frequency_minutes=60`, `compute_market_settlements=True`, solvers, etc.
  - File: `idaes/apps/grid_integration/tests/test_integration.py:89`.
- Plugin attachment:
  - `prescient_options['plugin']['doubleloop']['module'] = coordinator.prescient_plugin_module`.
  - File: `idaes/apps/grid_integration/tests/test_integration.py:124`.
- Entrypoint:
  - `prescient_simulator.Prescient().simulate(**bidder_sim_options)`.
  - File: `idaes/apps/grid_integration/tests/test_integration.py:156`.

### Why this matters for your question
If you need a **price-taker case under DA+RT callbacks**, you need a bridge from `PriceTakerModel` to `Bidder`/`Tracker` interfaces. That bridge is not present in `pricetaker/tests`.

---

## 5. One-iteration execution trace (DA + RT)

This section shows the concrete DA/RT callback execution in current code (`coordinator.py`).

Important: this call chain is exercised by `tests/test_integration.py` with testing bidder/tracker, not by `pricetaker/tests`. Prescient-internal substep ordering beyond callback boundaries requires runtime inspection of Prescient internals.

### Day-Ahead iteration trace (one DA run)

1. Prescient callback: `bid_into_DAM(options, simulator, ruc_instance, ruc_date, ruc_hour)`.
- File: `idaes/apps/grid_integration/coordinator.py`.
- Input: RUC instance/date/hour + simulator time state.
- Purpose: generate and inject DA bids before RUC solve.

2. If not first day, coordinator projects tracker trajectory:
- `project_tracking_trajectory(...)` -> `assemble_project_tracking_signal(...)` + `projection_tracker.track_market_dispatch(...)`.
- Files: `coordinator.py`, `tracker.py`.
- Output: `full_projected_trajectory` dict.

3. Coordinator updates bidder DA model state:
- `self.bidder.update_day_ahead_model(**full_projected_trajectory)`.
- File: `coordinator.py`; bidder method in `bidder.py`.

4. Coordinator requests DA bids:
- `bids = self.bidder.compute_day_ahead_bids(date=ruc_date)`.
- Bidder pulls forecasts using `forecaster.forecast_day_ahead_and_real_time_prices(...)`.
- File: `bidder.py`.

5. Bid dict structure produced by bidder (conceptual key schema):
- `bids[t][gen]['p_cost']`, `p_min`, `p_max`, `p_min_agc`, `p_max_agc`, `startup_capacity`, `shutdown_capacity`, optional `fixed_commitment`.
- File: `idaes/apps/grid_integration/bidder.py` (`_assemble_bids` implementation).

6. Coordinator stages state:
- `current_bids` (first day only), `next_bids`.
- File: `coordinator.py`.

7. Coordinator injects DA bids into Prescient:
- `_pass_DA_bid_to_prescient(...)` -> `_update_bids(...)`.
- Prescient generator dict fields updated: `p_cost` (time-series piecewise curves), `p_max`, `p_min`, `p_min_agc`, `p_max_agc`, `fixed_commitment`, `min_up_time`, `min_down_time`, `startup_capacity`, `shutdown_capacity`, `startup_fuel`, `startup_cost`.
- File: `coordinator.py`.

8. Prescient solves RUC (internal to Prescient).
- Not clear from local code; requires runtime inspection for internal solver call chain.

9. Post-RUC callbacks:
- `fetch_DA_prices(...)` stores `next_DA_prices` and `current_avail_DA_prices`.
- `fetch_DA_dispatches(...)` stores `next_DA_dispatches` and `current_avail_DA_dispatches`.
- `push_day_ahead_stats_to_forecaster(...)` forwards DA result to forecaster.
- File: `coordinator.py`.

10. Activation callback:
- `activate_pending_DA_data(...)` promotes `next_*` to `current_*` and resets `next_*` to `None`.
- File: `coordinator.py`.

### Real-Time iteration trace (one RT hour)

1. Prescient callback: `bid_into_RTM(options, simulator, sced_instance)`.
- File: `coordinator.py`.

2. Coordinator requests RT bids:
- `compute_real_time_bids(date, hour, realized_day_ahead_prices=current_avail_DA_prices, realized_day_ahead_dispatches=current_avail_DA_dispatches)`.
- File: `bidder.py`.

3. Bidder RT preprocessing:
- `forecast_real_time_prices(...)` from forecaster.
- `_pass_realized_day_ahead_dispatches(...)` fixes/unfixes DA coupling vars and underbid slack.
- `_pass_realized_day_ahead_prices(...)` writes realized DA prices (with fallback forecast when needed).
- File: `bidder.py`.

4. Coordinator injects RT bids:
- `_pass_RT_bid_to_prescient(...)` -> `_update_bids(...)` with `start_hour=hour`, `horizon=options.sced_horizon`.
- File: `coordinator.py`.

5. Prescient solves SCED (internal to Prescient).
- Not clear from local code; requires runtime inspection for internals.

6. Post-operations callback: `track_sced_signal(...)`.
- Assembles tracking signal via `assemble_sced_tracking_market_signals(...)`.
- Dispatch retrieval: `sced_instance.data['elements']['generator'][gen_name]['pg']['values']`.
- Signal structure: list with first value from current SCED dispatch, followed by DA look-ahead dispatch values up to tracking horizon.
- File: `coordinator.py`.

7. Tracker solve:
- `implemented_profiles = tracker.track_market_dispatch(market_dispatch=..., date=..., hour=...)`.
- Output: implemented profile dict (e.g., power profile keys required by model object).
- File: `tracker.py`.

8. Coordinator updates internal models:
- `tracker.update_model(**implemented_profiles)`.
- `bidder.update_real_time_model(**implemented_profiles)`.
- File: `coordinator.py`.

9. Settlement/stats linkage:
- `update_observed_dispatch(...)` writes `tracker.get_last_delivered_power()` into matching observed dispatch map in `ops_stats` (`observed_thermal_dispatch_levels`, `observed_renewables_levels`, `observed_virtual_dispatch_levels`).
- File: `coordinator.py`, `tracker.py`.

---

## 6. What functions must a new test case implement?

This checklist combines what `coordinator.py` expects at runtime with what bidder/tracker abstract APIs require.

### Case Author Checklist

#### Required components
1. **Bidding model object** used by bidder must provide:
- `populate_model`, `update_model`, `record_results` methods.
- `power_output`, `total_cost`, `model_data` attributes.
- Source: `idaes/apps/grid_integration/bidder.py` input checks and usage.

2. **Tracking model object** used by tracker must provide:
- `populate_model`, `get_implemented_profile`, `update_model`, `get_last_delivered_power`, `record_results`, `write_results` methods.
- `power_output`, `total_cost` attributes.
- Source: `idaes/apps/grid_integration/tracker.py` input checks.

3. **Forecaster** must provide:
- `forecast_day_ahead_and_real_time_prices`, `forecast_day_ahead_prices`, `forecast_real_time_prices`.
- For Prescient feedback path: `fetch_hourly_stats_from_prescient`, `fetch_day_ahead_stats_from_prescient`.
- Source: `idaes/apps/grid_integration/forecaster.py` abstract classes.

4. **Bidder** must implement:
- `compute_day_ahead_bids`, `compute_real_time_bids`, `update_day_ahead_model`, `update_real_time_model`, `write_results`.
- Source: `idaes/apps/grid_integration/bidder.py`.

5. **Coordinator** expects bidder/tracker/projection_tracker objects and uses callback methods in Prescient lifecycle.
- Source: `idaes/apps/grid_integration/coordinator.py`.

#### Required data formats
1. **Bid format returned by bidder** must be time-indexed dict keyed by generator with fields consumed by `_update_bids`:
- Required mapping keys include `p_cost`, `p_max`, `p_min`, `p_min_agc`, `p_max_agc`, `fixed_commitment`, `min_up_time`, `min_down_time`, `startup_capacity`, `shutdown_capacity`, `startup_fuel`, `startup_cost` (as applicable).
- Source: `coordinator.py` `_update_bids` mapping.

2. **Dispatch signal format for tracker**:
- `market_dispatch` is a Python list indexed by tracker time-set positions.
- Source: `tracker.py` `_pass_market_dispatch`; `coordinator.py` assembly methods.

3. **Tracking output format**:
- `track_market_dispatch` must return profile dict whose keys are accepted by both `tracker.update_model(**profiles)` and `bidder.update_real_time_model(**profiles)`.
- Source: `coordinator.py` `track_sced_signal`.

4. **Generator metadata contract**:
- Bidder accesses `bidding_model_object.model_data.gen_name`, `.bus`, `.generator_type`, etc.
- Source: `coordinator.py`, `bidder.py`.

For a DC/ASU case, the cleanest approach is to build a custom model object adapter that satisfies these interfaces, then plug it into `Bidder` and `Tracker`.

---

## 7. Minimal template skeleton (pseudo-code, not full code)

```python
# 1) Build your process model adapter for DA/RT bidding and tracking
class DCASUModelAdapter:
    model_data = ...  # must expose gen_name, bus, generator_type, limits/cost data
    power_output = ...
    total_cost = (..., weight)

    def populate_model(self, b, horizon):
        # declare variables/constraints/objective components
        pass

    def update_model(self, b, **profiles):
        # update backlog/inventory/state carryover
        pass

    def get_implemented_profile(self, b, last_implemented_time_step):
        # return dict, e.g. {"implemented_power_output": deque([...]), ...}
        return profiles

    def get_last_delivered_power(self, b, last_implemented_time_step):
        return delivered_power

    def record_results(self, b, **kwargs):
        pass

    def write_results(self, path):
        pass

# 2) Build forecaster
forecaster = MyForecaster(...)  # must implement DA/RT forecast + Prescient fetch hooks

# 3) Build bidder and trackers
solver = pyo.SolverFactory("cbc")
bidder = Bidder(
    bidding_model_object=DCASUModelAdapter(...),
    day_ahead_horizon=48,
    real_time_horizon=4,
    n_scenario=10,
    solver=solver,
    forecaster=forecaster,
)
tracker = Tracker(
    tracking_model_object=DCASUModelAdapter(...),
    tracking_horizon=4,
    n_tracking_hour=1,
    solver=solver,
)
projection_tracker = Tracker(
    tracking_model_object=DCASUModelAdapter(...),
    tracking_horizon=4,
    n_tracking_hour=1,
    solver=solver,
)

# 4) Build coordinator and expose plugin
coordinator = DoubleLoopCoordinator(
    bidder=bidder,
    tracker=tracker,
    projection_tracker=projection_tracker,
)

# 5) Configure Prescient
options = {
    "data_path": "...",
    "input_format": "rts-gmlc",
    "ruc_horizon": 48,
    "sced_horizon": 4,
    "sced_frequency_minutes": 60,
    "compute_market_settlements": True,
    "plugin": {
        "doubleloop": {
            "module": coordinator.prescient_plugin_module,
            "bidding_generator": bidder.bidding_model_object.model_data.gen_name,
        }
    },
    "output_directory": "...",
}

# 6) Run full double loop
prescient.simulator.Prescient().simulate(**options)

# 7) DA/RT callbacks execute via coordinator:
# bid_into_DAM -> fetch_DA_prices/dispatch -> activate_pending_DA_data
# bid_into_RTM -> track_sced_signal -> update_observed_dispatch
```

---

## Final Notes

- There is **no direct “price-taker double-loop test case”** in current repository paths.
- The `pricetaker` tests are valuable for process/multiperiod and UC-like constraint formulation validation.
- The full Prescient DA+RT callback orchestration is validated in `idaes/apps/grid_integration/tests/test_integration.py` using non-`PriceTakerModel` test adapters.
- To run a true price-taker resource in the double loop, implement adapter objects that satisfy bidder/tracker contracts and map your model state into the bid/dispatch interfaces used by `DoubleLoopCoordinator`.

