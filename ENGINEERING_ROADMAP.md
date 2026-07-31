# AstraForge Engineering Architecture Roadmap

## Product Target

AstraForge is intended to cover the complete preliminary-design workflow of
RPA while providing substantially more control over regenerative and film
cooling. Cooling geometry must not exist as an independent GUI approximation.
One committed geometric definition must drive:

- thermal and hydraulic calculations
- engine and cooling-channel CAD
- gas and coolant fluid volumes
- CFD surface and volume meshes
- boundary-condition metadata
- tabular station output and reports

## Current Verified Baseline

- 169 automated tests pass after the RPA delivered-performance,
  configuration-compatibility and variable-cooling work.
- The real RocketCEA LOX/RP-1 example completes.
- Existing uncommitted R-network and thermal-GUI work remains preserved.
- The current implementation is functionally useful, but several modules have
  accumulated multiple responsibilities:
  - `engine/thermal_analysis.py`: domain models, network building, correlations,
    integration, radiation, mechanics and summaries
  - `engine/gui/main_window.py`: application state, orchestration, workflow,
    file operations and view coordination
  - `engine/gui/thermal_analysis_page.py`: input models, workflow, plotting and
    large result views

No large file will be split merely to reduce line count. Extraction happens
only when tests establish an interface and the replacement is behaviorally
equivalent.

## Implemented Cooling Foundation

- Stable engine stations share axial position, wall arc length, radius,
  tangent, curvature and region identifiers.
- Channel geometry varies by station and supports rectangular, trapezoidal,
  rounded rectangular, semicircular, circular/tubular, racetrack and custom
  polygon sections.
- The channel solver includes shape-aware laminar friction/Nusselt values,
  Haaland rough-wall friction, Gnielinski heat transfer, helical path length,
  variable-area acceleration, optional minor losses, pitch/ligament checks and
  Dean-number diagnostics.
- RPA coolant-specific regenerative Nusselt relations and the channel rib/fin
  surface factor are available as explicit comparison functions.
- Gaseous film mixing and liquid-film heating/vaporization follow the equations
  documented in the local RPA thermal-analysis report.
- The Cooling Design GUI exposes variable injector/throat/exit profiles,
  hydraulic/coolant results, film inputs, plots, station tables and CSV export.
- Multiple independent or parallel circuits can be assigned to axial segments;
  local heat-load fractions are validated against over-allocation.

- Variable channels are directly coupled to Bartz gas-side convection, an
  optional grey-gas radiation contribution, temperature-dependent liner
  conductivity, wall conduction, the RPA rib/fin area factor and the marching
  coolant temperature/pressure solution.
- The coupled solver iterates the heat-flux field to a wall-temperature
  tolerance. Cooling Design reports hot- and coolant-side wall temperatures,
  local convective/radiative/total heat flux and the effective coolant-side
  coefficient in its plots, table and CSV output.

The remaining thermal gates are multilayer/coating and closeout conduction,
coaxial-shell/tubular jackets, axial wall conduction and full two-way
film/surface-layer chemistry coupling.

## Implemented CAD and CFD Foundation

- FreeCAD creates real B-Rep STEP assemblies with separately named hot-gas
  volume, cooled liner and representative or fully patterned helical channel
  fluid bodies.
- Channel fluid bodies can be subtracted from the liner when the channel count
  is constant. Variable-count layouts are exported transparently as one
  representative channel because a single continuous circumferential pattern
  would be geometrically misleading.
- STEP schema is detected from the written file. The local FreeCAD engine
  writes AP214; AP242 remains the release target when the CAD backend supports
  it reliably.
- STL is emitted as a secondary tessellated assembly.
- Gmsh creates an axisymmetric 2-D hot-gas flowfield and a full 3-D
  representative helical coolant-channel mesh in MSH 4.1 and VTK.
- Named gas boundaries cover inlet, axis, hot wall, nozzle exit and throat.
  Named coolant boundaries cover volume, walls, inlet and outlet.
- The CFD manifest records SI coordinates, boundary IDs, source files, Gmsh
  consistency checks, cell counts, area/volume ranges, edge-aspect ratios and
  channel-volume watertightness.

## Implemented Engine-Cycle Foundation

- Pump components close incompressible pressure work from mass flow, density,
  pressure rise and efficiency and report hydraulic/shaft work plus estimated
  inefficiency heating.
- Turbine components use the ideal-gas isentropic temperature drop with
  explicit isentropic and mechanical efficiencies.
- Single combined or two independent shafts solve one turbine working-fluid
  flow per shaft to close pump, accessory and turbine power.
- Gas-generator, staged-combustion, full-flow staged-combustion and expander
  topology labels have explicit open/closed-cycle mass-flow accounting.
- All 12 local RPA cycle-analysis examples map their main pumps, booster pumps,
  branch counts, gas-generators/preburners and turbines into SI cycle seeds.
- The Engine Cycle GUI provides editable component inputs, KPI cards, component
  tables, power/flow plots and CSV export.

The next cycle gate is topology-level pressure and mass-flow closure through
preburners/gas generators, branch flows and booster pumps, followed by
thermochemistry-backed turbine working-fluid properties and engine dry-mass
sizing.

## Canonical Geometry and Station Model

All downstream modules will use a shared axial/arc-length station model.

### Engine station

Each station owns:

- axial coordinate `x`
- hot-gas-wall arc length `s`
- inner radius and area
- local contour tangent and curvature
- chamber/nozzle region
- gas thermochemical state
- hot-wall, liner, coating and closeout thicknesses
- material identifiers and local temperatures
- cooling-segment and coolant-circuit identifiers

Station locations are generated once and then refined without changing stable
station IDs. Solver results, plots, CAD sections and mesh boundaries refer to
these IDs.

### Cooling segment

Cooling segments are piecewise definitions over station ranges. A segment can
select:

- regenerative channels
- annulus
- tubular wall
- coaxial shell
- radiation cooling
- film cooling
- ablative or uncooled screening
- combinations such as channels plus film cooling

Segment boundaries are explicit geometric events and become named CAD/mesh
faces.

### Regenerative channel definition

Every variable may be constant, linearly interpolated, spline-controlled or
defined by station keyframes:

- channel count
- channel height and width
- rib width
- hot-wall thickness
- closeout thickness
- corner radii
- roughness
- helix angle or helix pitch
- channel rotation/orientation
- local blockage
- manifold and collector loss coefficients

Supported cross-section families:

- rectangular
- trapezoidal
- rounded rectangular
- semicircular
- circular/tubular
- racetrack
- user-defined closed polygon

The model stores both the nominal section and its manufactured section after
minimum-radius, minimum-wall and process constraints are applied.

### Film-cooling definition

Film slots and peripheral injection rows own:

- station/range location
- injected species or coolant circuit
- mass-flow fraction or absolute flow
- slot height, width, angle and circumference coverage
- injection temperature and pressure
- gaseous or liquid state
- evaporation and mixing model
- core/film mixture ratios

Film mass flow participates in total engine mass balance, thermal protection
and delivered-performance loss.

## Solver Architecture

The current annulus solver remains a verified reference implementation.
New capabilities attach through explicit interfaces:

1. `GasSideModel`
   - Bartz
   - Ievlev
   - user correlation
   - radiation and participating-media contribution
2. `CoolantGeometryModel`
   - annulus, channels, tubes and coaxial shell
3. `CoolantTransportModel`
   - temperature/pressure-dependent properties
   - developing and fully developed flow
   - curvature, rotation and roughness corrections
4. `WallConductionModel`
   - multilayer radial conduction
   - rib-fin correction
   - optional axial conduction
5. `FilmCoolingModel`
   - gaseous film
   - liquid-film evaporation
   - boundary-layer/core mixing
6. `MechanicalScreeningModel`
   - pressure stress
   - thermal strain
   - manufacturing and material constraints

Every model reports its correlation name, source, validity range and any
extrapolation.

## CAD Outputs

STEP is the primary neutral CAD output. Exportable objects will include:

- hot-gas fluid volume
- liner solid
- individual or patterned channel fluid volumes
- ribs
- closeout/jacket
- film slots
- manifolds and collectors when modeled
- complete thrust-chamber assembly

The preferred export is STEP AP242 with stable part names and station-derived
reference planes. STL remains a secondary tessellated output.

## CFD and Mesh Outputs

Mesh export is separated from CAD tessellation.

### Gas flowfield

- axisymmetric 2D meridional mesh
- optional periodic 3D sector
- optional full 3D volume
- boundary groups: injector/inlet, axis or periodic faces, hot wall, throat,
  nozzle exit and film inlets

### Cooling channels

- single-channel periodic sector
- selected channel group
- full cooling circuit
- boundary groups: coolant inlet, outlet, heated wall, ribs, closeout,
  symmetry/periodic faces and manifolds

### Formats

- Gmsh `.msh` as the primary tagged mesh
- VTK/VTU for inspection and verification
- STL/STEP surfaces for external meshing
- CSV station profiles
- a JSON manifest containing SI units, coordinate system, reference pressure,
  material names, boundary tags, periodic angle and source design fingerprint

Mesh-quality output includes minimum/maximum cell volume, aspect ratio,
skewness, orthogonality where available and a watertightness report.

## Redundancy and Placeholder Policy

1. Solver-owned values are never duplicated as editable GUI state.
2. Preview and committed calculations use the same engineering functions.
3. Disabled future controls are removed from production views until their
   solver is active.
4. The R-network builder and thermal-analysis page share one cooling-layout
   model instead of copying inputs between pages.
5. Report and comparison views consume committed result objects; they do not
   recalculate formulas.
6. Duplicate unit conversion, validation and export formatting is centralized.
7. Legacy code is removed only after reference tests prove equivalent behavior.

## Implementation Gates

Each capability moves through the same gates:

1. domain model and validation
2. equation-level unit tests
3. RPA or published reference case
4. solver integration
5. GUI controls
6. CAD representation
7. mesh representation
8. export and report metadata
9. regression and visual QA

An option is not exposed as complete before gates 1-4 pass.
