"""Application entry point and orchestration layer for the predesign tool."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from engine.chemistry import (
    RocketCEABackend,
    ThermochemistryBackend,
    ThermochemistryBackendError,
    ThermochemistryBackendUnavailableError,
)
from engine.flow import FlowCase, adapt_inputs_for_flow_case, classify_input_flow_case
from engine.geometry import build_thermochemistry_profile, generate_nozzle_contour, size_engine_geometry
from engine.io import export_bundle, export_geometry_to_csv, export_geometry_to_json
from engine.models import BellContourVariant, ChemistryMode, ExportBundle, InputParameters, OFSweepResult
from engine.thermal_analysis import ThermalAnalysisInputs, ThermalAnalysisResult, run_thermal_analysis
from engine.unit_system import UnitPreset
from engine.utils.validation import InputValidationError, ensure_valid_input


class EngineDesignApplication:
    """Orchestrate validation, thermochemistry, geometry and export."""

    def __init__(self, backend: ThermochemistryBackend) -> None:
        self._backend = backend

    def run_case(self, inputs: InputParameters) -> ExportBundle:
        """Run a full engine predesign case for validated inputs."""

        ensure_valid_input(inputs)
        flow_case = classify_input_flow_case(inputs)
        effective_inputs = adapt_inputs_for_flow_case(inputs, flow_case)
        thermo = self._backend.calculate(effective_inputs)
        geometry = size_engine_geometry(effective_inputs, thermo)
        if flow_case.flow_case is FlowCase.SUBSONIC:
            geometry.optimal_expansion_ratio = None
            geometry.notes.append(
                "Subsonic / unchoked plausibility case: divergent nozzle geometry disabled for the MVP."
            )
        contour = generate_nozzle_contour(
            geometry,
            method=effective_inputs.contour_method,
            bell_variant=effective_inputs.bell_variant,
            bell_length_fraction_percent=effective_inputs.bell_length_fraction_percent,
            manual_nozzle_length_m=effective_inputs.manual_nozzle_length_m,
            convergent_half_angle_deg=effective_inputs.convergent_half_angle_deg,
            throat_upstream_radius_m=effective_inputs.throat_upstream_radius_m,
            throat_downstream_radius_m=effective_inputs.throat_downstream_radius_m,
            chamber_corner_radius_m=effective_inputs.chamber_corner_radius_m,
            include_diverging_section=flow_case.flow_case is FlowCase.CHOKED_SUPERSONIC,
        )
        thermochemistry_profile = build_thermochemistry_profile(contour, geometry, thermo)
        of_sweep = self._backend.build_of_sweep(effective_inputs)
        return ExportBundle(
            inputs=effective_inputs,
            thermochemistry=thermo,
            geometry=geometry,
            contour=contour,
            thermochemistry_profile=thermochemistry_profile,
            of_sweep=of_sweep,
        )

    def estimate_ambient_matched_expansion_ratio(
        self,
        inputs: InputParameters,
    ) -> float | None:
        """Return a preliminary ambient-matched Ae/At estimate for the current operating point."""

        ensure_valid_input(inputs)
        return self._backend.estimate_ambient_matched_expansion_ratio(inputs)

    def build_of_sweep(self, inputs: InputParameters) -> OFSweepResult:
        """Build only the O/F sweep for the selected propellant pair."""

        ensure_valid_input(inputs)
        return self._backend.build_of_sweep(
            adapt_inputs_for_flow_case(inputs, classify_input_flow_case(inputs))
        )

    def run_thermal_analysis(
        self,
        bundle: ExportBundle,
        thermal_inputs: ThermalAnalysisInputs,
    ) -> ThermalAnalysisResult:
        """Run the annulus-cooling reference model on the committed Current Design bundle."""

        return run_thermal_analysis(bundle, thermal_inputs)

    def export_case(
        self,
        bundle: ExportBundle,
        output_stem: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> dict[str, Path]:
        """Export a computed bundle to JSON and CSV files."""

        return export_bundle(bundle, output_stem, unit_preset=unit_preset)

    def export_geometry_json(
        self,
        bundle: ExportBundle,
        target_path: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> Path:
        """Export geometry and contour data to JSON."""

        return export_geometry_to_json(bundle, target_path, unit_preset=unit_preset)

    def export_geometry_csv(
        self,
        bundle: ExportBundle,
        target_path: str | Path,
        unit_preset: UnitPreset = UnitPreset.SI,
    ) -> Path:
        """Export the discretized contour to CSV."""

        return export_geometry_to_csv(bundle, target_path, unit_preset=unit_preset)


def build_example_inputs() -> InputParameters:
    """Return a reusable LOX/RP-1 example case in SI units."""

    return InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=20.0,
        ambient_pressure_pa=101_325.0,
        contraction_ratio=3.0,
        characteristic_length_m=1.1,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        bell_variant=BellContourVariant.PARABOLA,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line interface for non-GUI runs."""

    parser = argparse.ArgumentParser(
        description=(
            "Start the Tkinter GUI or run the built-in LOX/RP-1 example case "
            "without the GUI."
        )
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run the built-in example case in the terminal instead of starting the GUI.",
    )
    parser.add_argument(
        "--export-stem",
        type=Path,
        default=None,
        help="Base path for JSON/CSV export files, for example outputs/example_case.",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Run the case without writing export files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Start the GUI by default and keep a CLI fallback for scripted usage."""

    parser = build_argument_parser()
    args = parser.parse_args(argv)

    application = EngineDesignApplication(backend=RocketCEABackend())

    if not args.no_gui:
        from engine.gui import MainWindow

        window = MainWindow(
            controller=application,
            example_input_factory=build_example_inputs,
        )
        window.mainloop()
        return 0

    inputs = build_example_inputs()

    try:
        bundle = application.run_case(inputs)
    except InputValidationError as exc:
        print(f"Input validation error:\n{exc}")
        return 1
    except ThermochemistryBackendUnavailableError as exc:
        print(exc)
        return 2
    except ThermochemistryBackendError as exc:
        print(f"Thermochemistry error:\n{exc}")
        return 3

    print("Calculation completed successfully.")
    print(f"Tc: {bundle.thermochemistry.chamber_temperature_k:.1f} K")
    print(f"c*: {bundle.thermochemistry.c_star_m_s:.2f} m/s")
    print(f"At: {bundle.geometry.throat_area_m2:.6f} m^2")
    print(f"Ae: {bundle.geometry.exit_area_m2:.6f} m^2")
    print(f"m_dot: {bundle.geometry.mass_flow_kg_per_s:.3f} kg/s")
    if bundle.of_sweep is not None:
        if bundle.of_sweep.stoichiometric_mixture_ratio is not None:
            print(
                "O/F sweep: "
                f"stoich={bundle.of_sweep.stoichiometric_mixture_ratio:.3f}"
            )
        else:
            print("O/F sweep: stoichiometric point unavailable")

    if not args.no_export:
        export_stem = args.export_stem or Path("outputs") / "example_case"
        written_files = application.export_case(bundle, export_stem)
        for label, path in written_files.items():
            print(f"{label}: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
