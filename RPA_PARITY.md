# AstraForge / RPA 2.3 Parity Audit

This audit compares AstraForge with the locally installed RPA 2.3.2 Standard
edition. The comparison uses the RPA user manual, engineering reports and
example configuration files. No RPA binaries were decompiled and no
proprietary implementation code was copied.

## Implemented and Verified

| Area | AstraForge status | Verification |
|---|---|---|
| Equilibrium, frozen and frozen-at-throat chemistry | Implemented through RocketCEA | Backend tests and real LOX/RP-1 application run |
| Chamber, throat and exit thermochemical states | Implemented | Profile and RocketCEA backend tests |
| O/F optimization sweep | Implemented | Backend and GUI plot tests |
| First-order thrust-chamber sizing | Implemented | `At = F/(Cf pc)`, `mdot = pc At/c*`, `Ae = eps At`, `Vc = L* At` tests |
| Conical nozzle | Implemented | Contour and export tests |
| TOP/Rao parabolic bell | Implemented | `pygasflow` Rao chart interpolation and contour tests |
| Bell divergence efficiency | Implemented from RPA equation 20 | Dedicated equation and delivered-performance tests |
| Conical divergence efficiency | Implemented from RPA equation 16 | Nozzle geometry tests |
| Delivered performance | Implemented from the RPA correction-factor structure | New loss-breakdown and performance tests |
| Finite-rate chamber loss | Implemented from RPA equations 10-12 for O2/H2, O2/kerosene and N2O4/UDMH | Propellant-family and pressure tests |
| Multi-phase nozzle loss | Implemented from RPA equations 21-23 | Zero-condensate and bounded-result tests |
| Nozzle separation screening | Implemented with the Mach-dependent Schmucker criterion from RPA equation 39 | Criterion and contour-marker tests |
| Altitude performance | Implemented with explicit pressure thrust and a 1976 standard-atmosphere model | Reference-pressure and map-grid tests |
| Throttle map | Implemented as a fast preliminary fixed-thermochemistry screen | Altitude/throttle grid tests |
| Bartz gas-side heat transfer | Implemented | Thermal-analysis test suite |
| Regenerative annulus reference model | Implemented | Station solver, pressure-drop and network tests |
| Variable regenerative-channel thermal/hydraulic solution | Implemented | Shape-aware hydraulics plus iterated Bartz/radiation/wall/rib/coolant coupling and energy-conservation tests |
| RPA channel-wall coolant correlations and rib/fin factor | Implemented as explicit comparison models | Equation-level tests |
| Gaseous film two-zone mixing | Implemented | RPA mixing-coordinate and coefficient-sum tests |
| Liquid-film heating and vaporization | Implemented as a screening march | Energy-balance and phase-transition tests |
| Radiation and participating-media screening | Implemented | Thermal-analysis tests |
| Thermal resistance network | Implemented with build/commit/staleness workflow | Network and GUI workflow tests |
| Geometry, thermochemistry and plot export | Implemented | JSON/CSV/PNG/SVG export tests |
| RPA configuration interchange | Liquid bipropellant subset implemented | 35 of 37 bundled RPA examples parse; monopropellant and solid mixtures are rejected explicitly |
| RPA reference benchmark capture | Implemented for console performance tables | SSME, Aestus, RD-170 and Vulcain-2 ideal/delivered references stored as structured JSON |
| STEP/STL cooling geometry | Implemented | FreeCAD integration test verifies separate gas, liner and helical channel B-Reps plus assembly STL |
| CFD verification meshes | Implemented for axisymmetric gas and representative 3-D channel domains | Gmsh integration test verifies MSH/VTK files, physical groups, tetrahedra and watertight channel boundary |
| Pump, turbine and shaft-power analysis | Implemented as a preliminary component kernel | Equation tests verify pump pressure work, isentropic turbine expansion, mechanical efficiency and one/two-shaft closure |
| RPA cycle configuration mapping | Implemented for the local turbopump examples | All 12 RPA cycle-analysis examples map cycle type, pumps, boosters, branches, preburners/gas generators and turbines |

The first same-input LOX/RP-1 round trip is within `+0.140%` for ideal vacuum
specific impulse and `+0.734%` for delivered vacuum specific impulse. Details
and interpretation rules are stored in `benchmarks/README.md`.

## Formula Corrections Made During This Audit

1. Combustion efficiency no longer multiplies fixed-geometry thrust directly.
   Following the RPA correction structure, it reduces delivered `c*` and
   specific impulse and therefore changes mass flow. It cancels out of `Cf`.
2. Ambient pressure thrust is now kept separate from the corrected vacuum
   momentum term. This avoids multiplying back pressure by nozzle efficiency.
3. The cosine divergence correction is now restricted to conical nozzles.
   Bell nozzles use the empirical RPA equation 20.
4. The previous constant wall-to-ambient separation threshold is replaced by
   the Mach-dependent Schmucker criterion used by RPA.
5. The declared `pygasflow` dependency is installed in the active development
   environment, restoring reproducible Rao/TOP calculations.
6. Exact-vacuum RPA cases (`Pa = 0`) now bypass RocketCEA's ambient-nozzle
   helper and use the already calculated vacuum `Isp` and `Cf`, avoiding a
   division by zero during cycle-example import.

## Present but More Limited Than RPA

| Area | Current limitation |
|---|---|
| Frozen flow | Supports equilibrium, fully frozen and frozen at the throat; it does not yet support an arbitrary downstream freeze station such as `Af/At = 3` |
| Finite-area chamber | RocketCEA receives contraction ratio, but AstraForge does not expose RPA's full injector-face-to-nozzle-inlet iteration and pressure-loss report |
| Friction loss | User-selectable factor and wall-shear contour integration are connected; the complete RPA momentum-thickness reconstruction is not yet implemented |
| Throttle analysis | Fast map scales chamber pressure and retains the committed thermochemical state; RPA can recompute the full finite-area thermochemical solution per throttle point |
| Thermal cooling | Annulus and variable-channel Bartz/radiation/liner/rib/coolant coupling are active; multilayer closeout, coaxial-shell and tubular-wall solvers are not complete |
| Film / boundary-layer cooling | Gaseous mixing and liquid heating/vaporization are active as screening models; station-composition/Ievlev coupling and delivered-performance loss are not complete |
| Engine cycles | Pump/turbine components, open/closed-cycle mass accounting and shaft closure are active; preburner chemistry, branch/booster flow closure and topology-wide pressure iteration are not complete |
| Structural analysis | Screening stresses and margins are available; this is not a qualified FEM or life model |
| RPA configuration import | Liquid bipropellant, unit and core geometry/performance fields are mapped; RPA-only cycle/cooling blocks are preserved in the parsed document but not yet applied to domain models |

## RPA Features Not Yet Implemented

- full multi-component propellant mixture editor and custom thermodynamic database editor
- nested parameter analysis
- stand-alone propellant analysis
- arbitrary suddenly-frozen nozzle station
- TIC/TOC method-of-characteristics contour construction
- detailed friction integration from momentum thickness or wall shear
- interzonal boundary-layer-cooling performance calculation
- station-composition-coupled Ievlev film effectiveness and interzonal loss
- multilayer closeout, coaxial-shell and tubular-wall cooling-jacket solvers
- complete topology-level gas-generator, staged-combustion, expander and
  full-flow mass/pressure/thermochemistry iteration
- booster-pump, branch-flow, turbomachinery geometry/speed and engine dry-mass analysis
- monopropellant and solid-mixture mapping from RPA configuration files
- scripting API equivalent to the RPA JavaScript and SDK interfaces

## AstraForge Cooling and CFD Target Beyond RPA

AstraForge will use one committed cooling-layout definition for the solver,
CAD and CFD outputs. The target includes:

- stationwise-variable channel count, height, width, rib width and wall thickness
- configurable helicity/helix pitch and channel orientation
- rectangular, trapezoidal, rounded, semicircular, tubular, racetrack and
  custom-polygon channel sections
- several coolant circuits and cooling segments
- gaseous and liquid film-cooling slots
- conjugate liner/rib/closeout resistance networks
- pressure-dependent coolant properties and full pressure-loss reconstruction
- STEP output for the engine solids and coolant fluid volumes
- tagged gas-flow and channel meshes in Gmsh and VTK-compatible formats
- boundary-condition and units manifests for CFD verification

The detailed data ownership and implementation gates are defined in
`ENGINEERING_ROADMAP.md`.

These remaining items are separate engineering modules, not cosmetic switches.
They should be added with reference cases and numerical acceptance tolerances
before being described as RPA-equivalent.
