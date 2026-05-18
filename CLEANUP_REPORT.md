# AstraForge Cleanup Report

Date: 2026-05-16

## Scope

This cleanup pass audited the active AstraForge desktop application, separated the
running codebase from a legacy duplicate distribution, verified the committed
Current Design data path, and removed clearly generated clutter. No new physics,
solver families, or UI features were introduced in this pass.

## Baseline Before Cleanup

### Commands run before changes

- `python -m compileall .`
  - Result: success
  - Note: this walked the entire working tree, including virtual environments and
    the nested legacy `AstroForge` snapshot, so the signal-to-noise ratio was poor.
- `python -m pytest -q tests`
  - Result: `89 passed`
- `python -m pytest -q`
  - Result: failed during test collection
  - Cause: the nested `AstroForge/tests` tree shadowed the active `tests/` tree and
    produced import-file-mismatch errors.

### Pre-existing structural issue found

The project contained a second full application snapshot at:

- `AstroForge/`

That nested tree contained its own `engine/`, `app.py`, `gui_launcher.py`, and
`tests/`. It was not used by the active application, but it interfered with the
default pytest discovery path.

## Active Entry Points Found

### Runtime / packaging entry points

- `gui_launcher.py`
  - dedicated EXE/GUI launcher
- `app.py`
  - CLI + orchestration entry point
- `RocketEnginePredesign.spec`
  - PyInstaller packaging entry, targets `gui_launcher.py`

### Active application root

- `engine/gui/main_window.py`
  - constructs the Tkinter notebook/tabs
  - wires Current Design, Geometry & Material, Thermal Analysis, report tables,
    export actions, and app state handoff

## Active Call Chain

### Current Design calculation path

1. UI input read:
   - `engine/gui/input_panel.py`
2. Input validation:
   - `engine/utils/validation.py`
3. Application orchestration:
   - `app.py -> EngineDesignApplication.run_case()`
4. Flow-case gate:
   - `engine/flow.py`
5. Thermochemistry backend:
   - `engine/chemistry/rocketcea_backend.py`
6. Geometry sizing:
   - `engine/geometry/sizing.py`
7. Contour generation:
   - `engine/geometry/contour.py -> generate_nozzle_contour()`
8. Thermochemistry profile remap:
   - `engine/geometry/contour.py -> build_thermochemistry_profile()`
9. Result bundle creation:
   - `engine/models.py -> ExportBundle`
10. Current Design result consumers:
    - `engine/performance_preview.py`
    - `engine/gui/result_panel.py`
    - `engine/gui/project_panels.py`
    - `engine/gui/plotting.py`
    - `engine/io/export.py`
    - `engine/thermal_analysis.py`

### Geometry sandbox / preview path

1. Runtime draft edits gathered in:
   - `engine/gui/chamber_geometry_panel.py`
   - `engine/gui/result_panel.py`
2. Preview bundle rebuilt in:
   - `engine/geometry_preview.py -> build_geometry_preview_bundle()`
3. Preview uses:
   - committed thermochemistry result from `self._current_bundle`
   - new contour from preview inputs
   - new thermochemistry profile remapped onto that preview contour

### Thermal Analysis call site

- `engine/gui/main_window.py -> calculate_thermal_analysis()`
- `app.py -> EngineDesignApplication.run_thermal_analysis()`
- `engine/thermal_analysis.py -> run_thermal_analysis()`

## Active Module Reachability Audit

A static import reachability pass was run from:

- `app.py`
- `gui_launcher.py`
- `engine/gui/main_window.py`

### Reachable active modules

- `engine/chamber_geometry.py`
- `engine/chemistry/base.py`
- `engine/chemistry/rocketcea_backend.py`
- `engine/flow.py`
- `engine/geometry/contour.py`
- `engine/geometry/separation.py`
- `engine/geometry/sizing.py`
- `engine/geometry_preview.py`
- `engine/gui/chamber_geometry_panel.py`
- `engine/gui/input_panel.py`
- `engine/gui/main_window.py`
- `engine/gui/plotting.py`
- `engine/gui/project_panels.py`
- `engine/gui/property_tables_panel.py`
- `engine/gui/result_panel.py`
- `engine/gui/thermal_analysis_page.py`
- `engine/io/export.py`
- `engine/io/preset.py`
- `engine/models.py`
- `engine/nozzle_geometry.py`
- `engine/nozzle_preview.py`
- `engine/performance_preview.py`
- `engine/project_state.py`
- `engine/properties/property_tables.py` via `engine/properties/__init__.py`
- `engine/thermal_analysis.py`
- `engine/unit_system.py`
- `engine/utils/validation.py`

### Not part of the active app runtime

- `legacy/archived_unused/AstroForge_snapshot/` (archived nested legacy copy)
- test modules under `tests/`
- generated build/cache folders

## Current Design Data Flow Verification

### Authoritative committed design object

The authoritative committed runtime object is:

- `ExportBundle` stored in `MainWindow._current_bundle`

That bundle contains:

- `inputs`
- `thermochemistry`
- `geometry`
- `contour`
- `thermochemistry_profile`
- `of_sweep`

### Authoritative contour

The authoritative contour for committed Current Design is:

- `ExportBundle.contour`

It is generated only through:

- `engine/geometry/contour.py -> generate_nozzle_contour()`

### Thermochemistry profile alignment

The thermochemistry profile that downstream consumers read is:

- `ExportBundle.thermochemistry_profile`

It is built directly from the same contour through:

- `engine/geometry/contour.py -> build_thermochemistry_profile(contour, geometry, thermochemistry)`

### Thermal Analysis contour source

Thermal Analysis station generation uses:

- `bundle.contour`
- `bundle.thermochemistry_profile`

through:

- `_build_station_samples_manual()`
- `_build_station_samples_from_profile()`

There is no separate mock contour inside the active thermal solver.

## r(x) / Contour Propagation Result

### Verified propagation path

Committed Current Design:

`InputParameters -> size_engine_geometry() -> generate_nozzle_contour() -> ExportBundle.contour -> build_thermochemistry_profile() -> ExportBundle.thermochemistry_profile -> performance preview / plots / thermal analysis / exports`

Geometry sandbox preview:

`Current bundle + preview overrides -> build_geometry_preview_bundle() -> preview contour + preview thermochemistry_profile`

### Integration issue found

Before cleanup, `Thermal Analysis` and the Current Design contour plot could follow
the Geometry sandbox preview bundle when uncommitted Geometry-tab edits were
visible. That mixed committed and preview states.

### Integration fix applied

`engine/gui/main_window.py` was adjusted so that:

- `Thermal Analysis` always uses `self._current_bundle`
- Thermal Analysis context is always labeled `Committed Current Design`
- the Current Design contour plot follows the committed bundle
- the Geometry-tab contour plot follows the sandbox runtime preview bundle

This keeps Current Design and Thermal Analysis on the same committed contour while
preserving the Geometry-tab preview behavior.

## Duplicate / Legacy Logic Found

### Confirmed legacy duplicate

- `AstroForge/`
  - full duplicate application snapshot
  - duplicate `engine/`
  - duplicate `tests/`
  - duplicate `gui_launcher.py` / `app.py`
  - not imported by the active application
  - directly caused pytest collection conflicts

### Duplicate logic decision

Kept active:

- root project under `C:\Users\marcu\Desktop\Rocketengine Dev`

Archived:

- `legacy/archived_unused/AstroForge_snapshot/`

### Other duplication noted but not removed

- `.venv/` and `venv/`
  - both remain
  - not touched in this pass because they are environment/runtime choices rather
    than active application modules

## Files and Folders Kept

### Active source tree

- `app.py`
- `gui_launcher.py`
- `engine/`
- `tests/`
- `data/properties/`
- `assets/`
- `RocketEnginePredesign.spec`
- `build_gui_exe.ps1`
- `README.md`
- `requirements.txt`

### User/output history retained intentionally

- `dist/`
- `outputs/`
- `versions/`

## Files and Folders Archived

- `legacy/archived_unused/AstroForge_snapshot/`
- `legacy/archived_unused/README.md`

## Files and Folders Deleted

Clearly generated clutter removed:

- `.pytest_cache/`
- `__pycache__/`
- `build/`
- `build_temp_radiation/`
- `build_temp_radiation_species/`
- `dist_temp_radiation/`
- `dist_temp_radiation_species/`

Temporary cleanup-audit PyInstaller folders were also removed after the build check:

- `build_temp_cleanup_audit/`
- `dist_temp_cleanup_audit/`

## Additional Cleanup Controls Added

- `pytest.ini`
  - constrains default pytest discovery to the active `tests/` tree
  - excludes `legacy/`, `AstroForge/`, environments, and generated folders

- `.gitignore`
  - now ignores `legacy/archived_unused/AstroForge_snapshot/`

## Build / Test Results After Cleanup

### Commands run after cleanup

- `python -m compileall app.py gui_launcher.py engine tests`
  - Result: success
- `python -m pytest -q`
  - Result: `89 passed`
- `python app.py --no-gui --no-export`
  - Result: success
- GUI smoke:
  - Result: `gui-cleanup-smoke-ok`
- PyInstaller packaging check:
  - `python -m PyInstaller --noconfirm --distpath dist_temp_cleanup_audit --workpath build_temp_cleanup_audit RocketEnginePredesign.spec`
  - Result: success

## Risks / Unresolved Items

1. `outputs/` and `versions/` still contain user artifacts/build history.
   - Intentionally retained.

2. Two Python environments remain:
   - `.venv/`
   - `venv/`
   - They are outside the active app import path but still add directory clutter.

3. Geometry-tab JSON/CSV export intentionally uses:
   - preview bundle if preview exists
   - otherwise committed current bundle
   - This is useful for sandbox export, but it is distinct from the committed
     Current Design export behavior.

4. PyInstaller emits one non-blocking warning during build:
   - hidden import `scipy.special._cdflib` not found
   - Build still succeeds and the app starts.

5. `compileall .` is technically still noisy if run from repo root because it will
   recurse into local environments and retained artifact folders. The active
   verification path now uses targeted compile inputs instead.

## Recommended Next Cleanup Tasks

1. Decide whether both `.venv/` and `venv/` are still needed.
2. Decide whether `outputs/` and `versions/` should stay in the working tree or
   move to an external archive location.
3. Consider splitting the Geometry preview export path from the committed Current
   Design export path more explicitly in UI labels to avoid ambiguity.
4. If desired, add a small developer-oriented module map document for the active
   `app.py -> engine -> gui` call graph.

## Cleanup Summary

The active AstraForge application now has:

- a documented and verified committed Current Design pipeline
- a documented geometry preview pipeline
- Thermal Analysis tied back to the committed Current Design bundle
- default pytest discovery fixed
- the nested legacy app snapshot removed from the active runtime/test path
- generated clutter removed
- successful compile, test, GUI-start, CLI-start, and packaging checks after cleanup
