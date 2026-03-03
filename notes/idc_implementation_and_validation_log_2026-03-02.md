# IDC Implementation and Validation Log (2026-03-02)

## Scope
Implement IDC model integration artifacts in `idaes/apps/grid_integration` and validate execution path without modifying core framework files (`bidder.py`, `tracker.py`, `coordinator.py`, `forecaster.py`).

## Chronological activity log

### 1) IDC model object implemented
- File created: `idaes/apps/grid_integration/examples/idc.py`
- Added `IDCModel` with thermal-style interface and method signatures:
  - `__init__`
  - `populate_model`
  - `update_model`
  - `get_implemented_profile`
  - `get_last_delivered_power`
  - `record_results`
  - `write_results`
  - `power_output`
  - `total_cost`
- Added local `IDCModelData` compatibility class for Bidder/Tracker/Coordinator.
- Implemented requested IDC constraints (excluding cooling cap as instructed):
  - backlog dynamics
  - service + drop <= available work
  - server max
  - service capacity
  - IT power lower bound
  - cooling COP lower bound
  - facility power balance
  - grid import cap
- Enforced virtual-generator sign convention in model:
  - `grid_import >= 0`
  - `P_V == -grid_import`
- Added constructor sanity checks for missing keys and invalid values.

### 2) IDC Prescient plugin implemented
- File created: `idaes/apps/grid_integration/examples/idc_prescient_plugin.py`
- Mirrored thermal plugin pattern:
  - `generator = "10_STEAM"`
  - `tracking_horizon = 4`
  - `day_ahead_bidding_horizon = 48`
  - `real_time_bidding_horizon = tracking_horizon`
  - `n_scenario = 10`
  - `n_tracking_hour = 1`
- Created forecaster from `examples/utils.py` placeholder arrays.
- Instantiated tracking/projection/bidding `IDCModel` objects.
- Instantiated `Tracker`, `Bidder`, `DoubleLoopCoordinator`.
- Exported exact plugin hooks:
  - `get_configuration = coordinator.get_configuration`
  - `register_plugins = coordinator.register_plugins`

### 3) Initial object-level checks run
Command:
```bash
.venv/bin/python - <<'PY'
from idaes.apps.grid_integration.examples.idc import IDCModel
from idaes.apps.grid_integration.examples.utils import rts_gmlc_generator_dataframe, rts_gmlc_bus_dataframe
m = IDCModel(rts_gmlc_generator_dataframe, rts_gmlc_bus_dataframe, generator='10_STEAM')
print('IDCModel OK', m.model_data.gen_name, m.model_data.bus, m.model_data.p_min, m.model_data.p_max)
PY
```
Result: PASS (`IDCModel OK ...`)

Command:
```bash
.venv/bin/python - <<'PY'
import idaes.apps.grid_integration.examples.idc_prescient_plugin as p
print('PLUGIN OK', p.generator, type(p.idc_bidder).__name__, type(p.idc_tracker).__name__)
PY
```
Result: PASS (`PLUGIN OK 10_STEAM Bidder Tracker`)

### 4) Added requested run script
- File created: `idaes/apps/grid_integration/examples/idc_run.py`
- Behavior:
  - Builds Prescient options for 5bus
  - Uses IDC plugin module path
  - Runs 1-day simulation by default
- Patched script to run directly from repo (adds repo root to `sys.path` when run as file).

### 5) Added IDC integration tests
- File created: `idaes/apps/grid_integration/tests/test_idc_integration.py`
- Tests added:
  - `test_idc_model_builds` (unit)
  - `test_idc_plugin_path_exists` (unit)
  - `test_idc_negative_load_hits_prescient_min_power_limit` (integration)

### 6) Tests executed
Command:
```bash
.venv/bin/pytest -q idaes/apps/grid_integration/tests/test_idc_integration.py::TestIDCIntegration::test_idc_model_builds idaes/apps/grid_integration/tests/test_idc_integration.py::TestIDCIntegration::test_idc_plugin_path_exists
```
Result: PASS (`2 passed`)

Command:
```bash
.venv/bin/pytest -q idaes/apps/grid_integration/tests/test_idc_integration.py::TestIDCIntegration::test_idc_negative_load_hits_prescient_min_power_limit
```
Result: PASS (`1 passed`) because expected `ValueError` was raised.

### 7) End-to-end run script executed
Command:
```bash
.venv/bin/python idaes/apps/grid_integration/examples/idc_run.py
```
Result: FAIL as expected for current negative-load mapping.

Observed terminal error (core blocker):
- `ValueError: Invalid parameter value: MinimumPowerOutput[('10_STEAM', 1)] = '-0.45'`
- `Value not in parameter domain NonNegativeReals`

Interpretation:
- Prescient/Egret unit commitment model enforces nonnegative `MinimumPowerOutput` for thermal generator records.
- Replacing `10_STEAM` with negative dispatch (`p_min < 0`) at this interface fails before full market run completes.

## Final status
- IDC model + plugin + run script + tests are in place.
- Unit checks pass.
- Full Prescient run is blocked by Prescient domain restriction on `MinimumPowerOutput` for the replaced thermal generator record.

## Files created/updated in this task
- `idaes/apps/grid_integration/examples/idc.py`
- `idaes/apps/grid_integration/examples/idc_prescient_plugin.py`
- `idaes/apps/grid_integration/examples/idc_run.py`
- `idaes/apps/grid_integration/tests/test_idc_integration.py`
- `notes/idc_implementation_and_validation_log_2026-03-02.md`

## Recommended next technical step
To complete a true negative-load IDC integration while keeping core files untouched, add IDC-specific adapter classes in `examples/`:
- a custom bidder that maps internal IDC negative power to Prescient-compatible nonnegative bid fields, and
- a custom coordinator adapter that maps Prescient dispatch back into IDC sign convention before tracking updates.
