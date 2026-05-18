# AstraForge

AstraForge is a local Python desktop application for early liquid rocket engine
predesign. The current focus is a practical predesign workflow for a
regeneratively cooled LOX/RP-1 class engine with:

- RocketCEA-backed thermochemistry
- chamber / throat / nozzle geometry predesign
- explicit Current Design workspace with draft / preview / committed separation
- contour generation and export
- annulus-cooling thermal-analysis MVP
- table-based coolant and wall-material property lookup
- preliminary thermal / mechanical screening tables

The codebase keeps the main concerns separated:

- `engine/models.py` contains the shared SI-based dataclasses and enums.
- `engine/chemistry/` hides RocketCEA behind a dedicated backend interface.
- `engine/geometry/` sizes the engine and generates/exportable contours.
- `engine/thermal_analysis.py` contains the station-wise cooling MVP solver.
- `engine/properties/` loads editable coolant and solid-material property tables.
- `engine/io/` handles JSON and CSV exports.
- `engine/gui/` provides the Tkinter desktop interface and matplotlib plots.

## Project Goal

The application accepts engine starting values such as:

- fuel / oxidizer
- chamber pressure
- thrust
- mixture ratio
- ambient pressure
- chemistry mode
- contour family
- optional chamber / nozzle overrides

It then computes:

- RocketCEA thermochemistry for `equilibrium`, `frozen` and `frozen-at-throat`
- first-order performance values such as `Tc`, `c*`, `Isp` and `Cf`
- a preliminary chamber/nozzle geometry with `At`, `Ae`, `rt`, `re`, `Ac`,
  chamber length and mass flow
- discretized `r(x)` contours for plotting, inspection and export
- station-based thermochemistry profiles from chamber to exit
- clickable O/F sweeps
- preliminary chamber / throat / TOP nozzle design helpers
- station-wise annulus-cooling thermal-analysis reference results

## Branding

- The desktop GUI uses the visible application name `AstraForge`.
- The source repository keeps the base vector asset at `assets/astraforge_icon.svg`.
- The current desktop app and EXE branding use:
  - `assets/astraforge_logo.png`
  - `assets/astraforge_taskbar.ico`

## Python Version

- Python 3.11+

The latest local test run in this environment used Python 3.14.

## Installation

1. Optionally create a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install the requirements:

```bash
python -m pip install -r requirements.txt
```

## RocketCEA Notes

The application uses RocketCEA only inside
`engine/chemistry/rocketcea_backend.py`.

- If RocketCEA is installed and importable, AstraForge uses real CEA data.
- If RocketCEA is missing or cannot be imported, the application shows a
  readable error instead of crashing silently.
- The packaged EXE bundles the RocketCEA files it needs at runtime, including
  package data and Python source files that RocketCEA opens directly.

## Starting the Project

Start the GUI:

```bash
python app.py
```

Run the built-in example case without the GUI:

```bash
python app.py --no-gui --export-stem outputs/example_case
```

Run the tests:

```bash
python -m pytest
```

Build the GUI EXE:

```bash
python -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\build_gui_exe.ps1
```

The latest executable is written to:

- `dist\AstraForge.exe`
- plus a timestamped copy such as `dist\AstraForge_vYYYYMMDD_HHMMSS.exe`

## GUI Tabs

The current GUI is organized into these tabs:

1. `Project Management`
   - project mode switch
   - optional mission / requirement / budget context
   - guided-project vs. sandbox behavior

2. `Overview`
   - compact dashboard summary
   - module-status overview
   - MBSE-style project context display

3. `Initial Design`
   - baseline starting inputs
   - first setup before committing a Current Design

4. `Current Design Workspace`
   - primary design page
   - editable chamber / throat / nozzle / material draft inputs
   - explicit `Update Geometry Preview`
   - explicit `Commit Draft & Recalculate Current Design`
   - narrow committed / preview geometry viewer
   - species / notes popout on contour-point selection
   - O/F sweep popout

5. `Geometry Details`
   - secondary committed-geometry detail view
   - geometry summary and export-oriented context

6. `Thermal Analysis`
   - annulus-cooling MVP reference model
   - read-only committed design context
   - optional radiation screening controls
   - solver settings
   - table-based coolant / material properties
   - pressure reconstruction for pump-fed predesign
   - station result table with thermal and preliminary mechanical screening values
   - separate plot window with export

7. `Comparison`
   - reference / current comparison baseline

8. `Report`
   - report placeholder plus property-table inspection views

## Current Design and Geometry Workflow

The app intentionally separates three roles:

- `Initial Design`
  - editable baseline used to seed the first committed design
- `Current Design Workspace`
  - the main working page for draft edits, preview and explicit commit/recalculate
- `Geometry Details`
  - secondary detail/export context for the committed geometry state

Geometry changes are intentionally explicit:

- draft edits do not silently overwrite the committed `Current Design`
- the right-side contour viewer stays on the committed model until `Update Geometry Preview`
- `Update Geometry Preview` creates only a temporary draft overlay
- `Commit Draft & Recalculate Current Design` is the only step that creates a new authoritative bundle
- `Thermal Analysis`, `Export` and report-oriented views always use the committed contour, never the uncommitted draft preview
- some Current Design fields become read-only once geometry values have been committed from the workspace geometry path

## Chamber / Nozzle Predesign Features

The geometry workflow currently supports:

- chamber `L*` selection with justification and commit workflow
- chamber `Ac/At` selection with justification and commit workflow
- throat upstream / downstream blend-radius editing
- TOP / Rao bell-angle support through `pygasflow`
- conical and bell contour families
- bell-length handling by manual length or `Lf [%]`
- preliminary divergent-loss handling for nozzle decisions

## Thermal Analysis MVP

The current thermal-analysis module is intentionally an MVP reference model.

What it does:

- uses the committed Current Design contour / geometry state
- builds stations along the inner wall
- applies an annulus-cooling reference model
- computes station-wise coolant temperature rise, wall temperatures, heat pickup
  and cooling-side pressure drop
- reconstructs required cooling inlet pressure and required pump discharge
  pressure for pump-fed predesign
- supports editable table-based coolant and wall-material properties
- includes preliminary stress / strain screening values in the station table

What it currently shows:

- read-only design context
- annulus gap, roughness, flow direction and pressure assumptions
- solver settings
- optional radiation and participating-media screening controls
- station result table
- separate plot window with selectable `x` / `y` quantities
- plot export as `CSV`, `TXT`, `PNG` and `SVG`

Important current assumptions:

- only the annulus reference model is active
- detailed channel cooling is planned for a later version
- spacer ribs are shown only as a mechanical assumption and are not included in
  the MVP calculation
- cooling-side correlations assume fully developed annular flow
- material and strength data are screening-level predesign data, not qualified allowables
- preliminary mechanical screening is not FEM and not a structural qualification
- this is acceptable for MVP predesign, but still a simplifying assumption

## Default Example Values

The GUI loads a LOX/RP-1 example case immediately:

- Fuel: `RP-1`
- Oxidizer: `LOX`
- `Pc = 70 bar`
- `Thrust = 100000 N`
- `O/F = 2.6`
- `eps = 20`
- `Pa = 1.01325 bar`
- `Ac/At = 3.0`
- `L* = 1.1 m`
- `chemistry mode = equilibrium`
- `nozzle family = bell`
- `bell subtype = parabola`

## Export

The full-case export writes:

- `*.json`
- `*_summary.csv`
- `*_contour.csv`
- `*_thermo_profile.csv`

The geometry workflow also offers dedicated geometry exports:

- geometry JSON with contour and geometry state
- geometry CSV for discretized contour output

The thermal plot window also supports export of the currently shown plot as:

- `CSV`
- `TXT`
- `PNG`
- `SVG`

The GUI export dialogs use the `outputs/` directory by default.

## Important Simplifications

This version intentionally targets a robust predesign workflow, not a final
engine design tool.

- no custom chemical equilibrium solver
- no full channel-by-channel regenerative cooling solver yet
- no detailed rib/spacer thermal-hydraulic model yet
- no full structural or liner stress model
- no 2D/3D conjugate heat-conduction model
- no complete injector-face thermal model yet
- no aerospike implementation yet
- first-order sizing remains central to the workflow
- chamber length is still based on equivalent `L*`-driven predesign logic
- contour families currently include `Conical`, `Bell` and a visible future
  `Aerospike` option
- within `Bell`, only `Parabola` is numerically active right now
- `TIC` and `TOC` are visible as future work but intentionally not implemented
- thermal-analysis results are suitable for trend and predesign work, not final
  certification-level thermal design
- the current chamber/head-end heat-flux treatment is still a predesign
  approximation and should be reviewed critically

## Architecture and Future Extensions

The current structure is set up so later additions can attach cleanly:

- more detailed heat-transfer correlations can attach to the contour/profile
  layer
- full regenerative channel cooling can build on the current thermal-analysis
  interfaces
- more detailed TOP / TIC / TOC nozzle construction can extend the dedicated
  nozzle-geometry helpers
- aerospike support can be added later as another contour family without
  breaking the RocketCEA boundary

## Project Structure

```text
project_root/
  app.py
  gui_launcher.py
  build_gui_exe.ps1
  RocketEnginePredesign.spec
  requirements.txt
  README.md
  assets/
    astraforge_icon.svg
    astraforge_logo.png
    astraforge_taskbar.ico
  engine/
    __init__.py
    models.py
    performance_preview.py
    project_state.py
    thermal_analysis.py
    geometry_preview.py
    nozzle_geometry.py
    nozzle_preview.py
    chamber_geometry.py
    properties/
      __init__.py
      property_tables.py
    chemistry/
      __init__.py
      base.py
      rocketcea_backend.py
    geometry/
      __init__.py
      sizing.py
      contour.py
      separation.py
    gui/
      __init__.py
      current_design_page.py
      main_window.py
      input_panel.py
      result_panel.py
      plotting.py
      property_tables_panel.py
      project_panels.py
      chamber_geometry_panel.py
      thermal_analysis_page.py
    io/
      __init__.py
      export.py
      preset.py
    utils/
      __init__.py
      validation.py
  data/
    properties/
      propellant_property_tables_nist_style.json
      solid_material_properties_screening_v1.json
  tests/
    test_app_service.py
    test_export.py
    test_nozzle_preview.py
    test_performance_preview.py
    test_property_tables.py
    test_thermal_analysis.py
```
