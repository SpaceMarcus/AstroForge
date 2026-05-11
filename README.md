# AstraForge

This project is a local Python desktop application for the early predesign of a
regeneratively cooled LOX/RP-1 rocket engine. The codebase keeps the main
concerns separated:

- `engine/models.py` contains the shared SI-based dataclasses and enums.
- `engine/chemistry/` hides RocketCEA behind a dedicated backend interface.
- `engine/geometry/` sizes the engine and generates/exportable nozzle contours.
- `engine/io/` handles JSON and CSV exports.
- `engine/gui/` provides the Tkinter desktop interface and matplotlib plots.

## Project Goal

The application accepts engine starting values such as fuel, oxidizer, chamber
pressure, thrust, mixture ratio, expansion ratio, ambient pressure, optional
`Ac/At`, optional `L*`, chemistry mode and contour method. It then computes:

- RocketCEA thermochemistry for `equilibrium`, `frozen` and `frozen-at-throat`
- first-order performance values such as `Tc`, `c*`, `Isp` and `Cf`
- a preliminary chamber/nozzle geometry with `At`, `Ae`, `rt`, `re`, optional
  `Ac`, `rc`, chamber length and mass flow
- a discretized contour `r(x)` for plotting and export
- station-based thermochemistry profiles from chamber, throat and exit states
- a clickable O/F sweep for vacuum Isp or `c*`
- approximate adiabatic wall temperature and boundary-layer thickness values

## Branding

- The desktop GUI uses the visible application name `AstraForge`.
- The project ships an icon asset at `assets/astraforge_icon.svg`.
- Tkinter window-icon support for SVG assets is platform-dependent, so the SVG
  asset is included directly and can also be reused later for EXE branding.

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

- If RocketCEA is installed and importable, the application uses real CEA data.
- If RocketCEA is missing or cannot be imported, the application does not crash.
  A readable error message is shown in the CLI or GUI.
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

The resulting executable is written to `dist\RocketEnginePredesign.exe`.

## GUI Tabs

The current GUI is organized into five tabs:

1. `Overview`
   - editable inputs
   - calculate / load example / export all / clear errors
   - mixture-ratio sweep
   - species and notes panel
   - interactive contour plot with throat, exit, optimal-expansion and separation markers
2. `Geometry and Material`
   - geometry summary
   - dedicated geometry JSON / CSV export
   - prepared liner-material and coating inputs
   - second contour view for local point inspection
3. `Thermochemie`
   - dominant mass fractions along the nozzle axis
4. `Comparison`
   - reference conical / best variant yet / current nozzle comparison baseline
5. `Report`
   - placeholder tab prepared for structured AstraForge reports

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

The geometry tab also offers dedicated geometry-only exports:

- `*_geometry.json` style JSON output with geometry plus contour
- `*_geometry.csv` style contour CSV output

The thermochemistry profile CSV includes local:

- adiabatic wall temperature
- velocity boundary-layer thickness
- thermal boundary-layer thickness
- local velocity and Reynolds number
- species mass and mole fractions

The GUI export dialogs use the `outputs/` directory by default.

## Important Simplifications

This version intentionally targets a robust predesign workflow, not a full
engine simulation:

- no custom chemical equilibrium solver
- no complete Bray or mixed-flow physics model
- no cooling-channel calculation
- no structural or liner stress model
- no 2D/3D heat-conduction model
- no aerospike implementation yet
- first-order sizing with `At = F / (Cf * Pc)`
- chamber length as an equivalent cylindrical length derived from `L*`
- contour families currently include `Conical`, `Bell` and a visible future `Aerospike` option
- within `Bell`, only `Parabola` is numerically implemented right now
- `TIC` and `TOC` are prepared in the UI but intentionally blocked until dedicated geometry logic is added
- RocketCEA does not choose the contour type; RocketCEA provides chemistry,
  while the contour is generated in `engine/geometry/contour.py`
- local profile values along `x` are based on exact RocketCEA chamber/throat/exit
  stations plus interpolation between them
- adiabatic wall temperature and boundary-layer thickness values use a simple
  turbulent boundary-layer approximation and should be treated as engineering
  estimates
- the current separation marker uses a first-order Summerfield-style wall-pressure criterion

## Architecture and Future Extensions

The current structure is set up so later additions can be attached cleanly:

- Bartz heat-transfer correlations can attach to the contour/profile layer
- Bray or mixed-flow logic can be added above the thermochemistry interface
- regenerative cooling can build on `GeometryResult`, `NozzlePoint` and the
  local profile states
- aerospike support can be added later as another contour family without having
  to break the RocketCEA backend boundary

## Project Structure

```text
project_root/
  app.py
  requirements.txt
  README.md
  engine/
    __init__.py
    models.py
    chemistry/
      __init__.py
      base.py
      rocketcea_backend.py
    geometry/
      __init__.py
      sizing.py
      contour.py
    gui/
      __init__.py
      main_window.py
      input_panel.py
      result_panel.py
      plotting.py
    io/
      __init__.py
      export.py
    utils/
      __init__.py
      validation.py
  tests/
    test_sizing.py
    test_validation.py
    test_rocketcea_backend.py
    test_export.py
    test_app_service.py
```
