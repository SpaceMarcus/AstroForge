"""Export helpers for completed engine design runs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from engine.models import ExportBundle
from engine.unit_system import UnitPreset, convert_to_display, get_unit_symbol


def _to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_serializable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_serializable(item) for item in value]
    return value


def bundle_to_dict(bundle: ExportBundle) -> dict[str, Any]:
    """Convert an export bundle into a JSON-serializable dictionary."""

    return _to_serializable(bundle)


def bundle_to_display_dict(bundle: ExportBundle, unit_preset: UnitPreset) -> dict[str, Any]:
    """Return a display-oriented dictionary in the selected preset."""

    return {
        "unit_preset": unit_preset.value,
        "inputs": {
            "fuel": bundle.inputs.fuel,
            "oxidizer": bundle.inputs.oxidizer,
            "chamber_pressure": _display_entry(bundle.inputs.chamber_pressure_pa, "pressure", unit_preset),
            "thrust": _display_entry(bundle.inputs.thrust_n, "force", unit_preset),
            "mixture_ratio": bundle.inputs.mixture_ratio,
            "expansion_ratio": bundle.inputs.expansion_ratio,
            "ambient_pressure": _display_entry(bundle.inputs.ambient_pressure_pa, "pressure", unit_preset),
            "contraction_ratio": bundle.inputs.contraction_ratio,
            "characteristic_length": _display_entry(bundle.inputs.characteristic_length_m, "length", unit_preset),
            "manual_nozzle_length": _display_entry(bundle.inputs.manual_nozzle_length_m, "length", unit_preset),
            "chemistry_mode": bundle.inputs.chemistry_mode.value,
            "contour_method": bundle.inputs.contour_method.value,
            "bell_variant": bundle.inputs.bell_variant.value,
            "liner_material": bundle.inputs.liner_material,
            "liner_coating_enabled": bundle.inputs.liner_coating_enabled,
            "liner_coating": bundle.inputs.liner_coating,
        },
        "thermochemistry": {
            "propellant_description": bundle.thermochemistry.propellant_description,
            "chamber_temperature": _display_entry(
                bundle.thermochemistry.chamber_temperature_k,
                "temperature",
                unit_preset,
            ),
            "c_star": _display_entry(bundle.thermochemistry.c_star_m_s, "velocity", unit_preset),
            "isp_vac": _display_entry(bundle.thermochemistry.isp_vac_s, "isp", unit_preset),
            "isp_amb": _display_entry(bundle.thermochemistry.isp_amb_s, "isp", unit_preset),
            "cf_vac": bundle.thermochemistry.cf_vac,
            "cf_amb": bundle.thermochemistry.cf_amb,
            "gamma": bundle.thermochemistry.gamma,
            "molecular_weight": _display_entry(
                bundle.thermochemistry.molecular_weight_kg_per_mol,
                "molecular_weight",
                unit_preset,
            ),
            "cp": _display_entry(bundle.thermochemistry.cp_j_per_kg_k, "specific_heat", unit_preset),
            "viscosity": _display_entry(bundle.thermochemistry.viscosity_pa_s, "viscosity", unit_preset),
            "thermal_conductivity": _display_entry(
                bundle.thermochemistry.thermal_conductivity_w_per_m_k,
                "thermal_conductivity",
                unit_preset,
            ),
            "prandtl_number": bundle.thermochemistry.prandtl_number,
            "chamber_density": _display_entry(
                bundle.thermochemistry.chamber_density_kg_per_m3,
                "density",
                unit_preset,
            ),
            "exit_pressure": _display_entry(bundle.thermochemistry.exit_pressure_pa, "pressure", unit_preset),
            "exit_temperature": _display_entry(
                bundle.thermochemistry.exit_temperature_k,
                "temperature",
                unit_preset,
            ),
            "optimal_expansion_ratio": bundle.thermochemistry.optimal_expansion_ratio,
        },
        "geometry": {
            "throat_area": _display_entry(bundle.geometry.throat_area_m2, "area", unit_preset),
            "throat_radius": _display_entry(bundle.geometry.throat_radius_m, "length", unit_preset),
            "exit_area": _display_entry(bundle.geometry.exit_area_m2, "area", unit_preset),
            "exit_radius": _display_entry(bundle.geometry.exit_radius_m, "length", unit_preset),
            "mass_flow": _display_entry(bundle.geometry.mass_flow_kg_per_s, "mass_flow", unit_preset),
            "chamber_area": _display_entry(bundle.geometry.chamber_area_m2, "area", unit_preset),
            "chamber_radius": _display_entry(bundle.geometry.chamber_radius_m, "length", unit_preset),
            "chamber_volume": _display_entry(bundle.geometry.chamber_volume_m3, "volume", unit_preset),
            "chamber_length": _display_entry(bundle.geometry.chamber_length_m, "length", unit_preset),
            "contour_length": _display_entry(bundle.geometry.contour_length_m, "length", unit_preset),
            "current_expansion_ratio": bundle.geometry.current_expansion_ratio,
            "optimal_expansion_ratio": bundle.geometry.optimal_expansion_ratio,
            "reference_conical_length": _display_entry(
                bundle.geometry.reference_conical_length_m,
                "length",
                unit_preset,
            ),
            "current_nozzle_length": _display_entry(
                bundle.geometry.current_nozzle_length_m,
                "length",
                unit_preset,
            ),
            "notes": bundle.geometry.notes,
        },
        "contour": [
            {
                "index": index,
                "x": _display_entry(point.x_m, "length", unit_preset),
                "radius": _display_entry(point.radius_m, "length", unit_preset),
                "area": _display_entry(point.area_m2, "area", unit_preset),
            }
            for index, point in enumerate(bundle.contour)
        ],
    }


def export_bundle_to_json(
    bundle: ExportBundle,
    target_path: str | Path,
    *,
    unit_preset: UnitPreset = UnitPreset.SI,
) -> Path:
    """Write the complete result bundle to a JSON file."""

    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": bundle.generated_at_utc,
        "display_unit_preset": unit_preset.value,
        "si_bundle": bundle_to_dict(bundle),
        "display": bundle_to_display_dict(bundle, unit_preset),
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def export_geometry_to_json(
    bundle: ExportBundle,
    target_path: str | Path,
    *,
    unit_preset: UnitPreset = UnitPreset.SI,
) -> Path:
    """Write only geometry-relevant content to a JSON file."""

    payload = {
        "generated_at_utc": bundle.generated_at_utc,
        "display_unit_preset": unit_preset.value,
        "fuel": bundle.inputs.fuel,
        "oxidizer": bundle.inputs.oxidizer,
        "contour_method": bundle.inputs.contour_method.value,
        "si_geometry": _to_serializable(bundle.geometry),
        "display_geometry": bundle_to_display_dict(bundle, unit_preset)["geometry"],
        "contour": [
            {
                "index": index,
                "x_si_m": point.x_m,
                "x_display": convert_to_display(point.x_m, "length", unit_preset),
                "x_unit": get_unit_symbol("length", unit_preset),
                "radius_si_m": point.radius_m,
                "radius_display": convert_to_display(point.radius_m, "length", unit_preset),
                "radius_unit": get_unit_symbol("length", unit_preset),
                "area_si_m2": point.area_m2,
                "area_display": convert_to_display(point.area_m2, "area", unit_preset),
                "area_unit": get_unit_symbol("area", unit_preset),
            }
            for index, point in enumerate(bundle.contour)
        ],
    }
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def export_geometry_to_csv(
    bundle: ExportBundle,
    target_path: str | Path,
    *,
    unit_preset: UnitPreset = UnitPreset.SI,
) -> Path:
    """Write the discretized contour to a geometry-specific CSV file."""

    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "index",
                "x_si_m",
                f"x_display_{get_unit_symbol('length', unit_preset)}",
                "radius_si_m",
                f"radius_display_{get_unit_symbol('length', unit_preset)}",
                "area_si_m2",
                f"area_display_{get_unit_symbol('area', unit_preset)}",
            ]
        )
        for index, point in enumerate(bundle.contour):
            writer.writerow(
                [
                    index,
                    point.x_m,
                    convert_to_display(point.x_m, "length", unit_preset),
                    point.radius_m,
                    convert_to_display(point.radius_m, "length", unit_preset),
                    point.area_m2,
                    convert_to_display(point.area_m2, "area", unit_preset),
                ]
            )
    return path


def export_bundle_to_csv(
    bundle: ExportBundle,
    summary_path: str | Path,
    contour_path: str | Path,
    thermo_profile_path: str | Path,
    *,
    unit_preset: UnitPreset = UnitPreset.SI,
) -> tuple[Path, Path, Path]:
    """Write summary and contour CSV files for the provided bundle."""

    summary = Path(summary_path)
    contour = Path(contour_path)
    thermo_profile = Path(thermo_profile_path)
    summary.parent.mkdir(parents=True, exist_ok=True)
    contour.parent.mkdir(parents=True, exist_ok=True)
    thermo_profile.parent.mkdir(parents=True, exist_ok=True)

    with summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section", "field", "si_value", "display_value", "display_unit"])
        for section_name, field_name, value, quantity in _summary_rows(bundle):
            writer.writerow(
                [
                    section_name,
                    field_name,
                    value,
                    convert_to_display(value, quantity, unit_preset) if value is not None and quantity else value,
                    get_unit_symbol(quantity, unit_preset) if quantity else "",
                ]
            )

    with contour.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "index",
                "x_si_m",
                f"x_display_{get_unit_symbol('length', unit_preset)}",
                "radius_si_m",
                f"radius_display_{get_unit_symbol('length', unit_preset)}",
                "area_si_m2",
                f"area_display_{get_unit_symbol('area', unit_preset)}",
            ]
        )
        for index, point in enumerate(bundle.contour):
            writer.writerow(
                [
                    index,
                    point.x_m,
                    convert_to_display(point.x_m, "length", unit_preset),
                    point.radius_m,
                    convert_to_display(point.radius_m, "length", unit_preset),
                    point.area_m2,
                    convert_to_display(point.area_m2, "area", unit_preset),
                ]
            )

    with thermo_profile.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "index",
                "region",
                "x_si_m",
                f"x_display_{get_unit_symbol('length', unit_preset)}",
                "radius_si_m",
                f"radius_display_{get_unit_symbol('length', unit_preset)}",
                "area_si_m2",
                f"area_display_{get_unit_symbol('area', unit_preset)}",
                "area_ratio",
                "temperature_si_k",
                f"temperature_display_{get_unit_symbol('temperature', unit_preset)}",
                "density_si_kg_m3",
                f"density_display_{get_unit_symbol('density', unit_preset)}",
                "enthalpy_si_j_kg",
                f"enthalpy_display_{get_unit_symbol('specific_energy', unit_preset)}",
                "cp_si_j_kg_k",
                f"cp_display_{get_unit_symbol('specific_heat', unit_preset)}",
                "viscosity_si",
                f"viscosity_display_{get_unit_symbol('viscosity', unit_preset)}",
                "thermal_conductivity_si",
                f"thermal_conductivity_display_{get_unit_symbol('thermal_conductivity', unit_preset)}",
                "prandtl_number",
                "gamma",
                "molecular_weight_si_kg_mol",
                f"molecular_weight_display_{get_unit_symbol('molecular_weight', unit_preset)}",
                "mach_number",
                "velocity_si_m_s",
                f"velocity_display_{get_unit_symbol('velocity', unit_preset)}",
                "reynolds_number",
                "adiabatic_wall_temperature_si_k",
                f"adiabatic_wall_temperature_display_{get_unit_symbol('temperature', unit_preset)}",
                "thermal_boundary_layer_thickness_si_m",
                f"thermal_boundary_layer_thickness_display_{get_unit_symbol('length', unit_preset)}",
                "velocity_boundary_layer_thickness_si_m",
                f"velocity_boundary_layer_thickness_display_{get_unit_symbol('length', unit_preset)}",
                "source",
                "species_mass_fractions",
                "species_mole_fractions",
            ]
        )
        for index, point in enumerate(bundle.thermochemistry_profile):
            writer.writerow(
                [
                    index,
                    point.region,
                    point.x_m,
                    convert_to_display(point.x_m, "length", unit_preset),
                    point.radius_m,
                    convert_to_display(point.radius_m, "length", unit_preset),
                    point.area_m2,
                    convert_to_display(point.area_m2, "area", unit_preset),
                    point.state.area_ratio,
                    point.state.temperature_k,
                    convert_to_display(point.state.temperature_k, "temperature", unit_preset),
                    point.state.density_kg_per_m3,
                    convert_to_display(point.state.density_kg_per_m3, "density", unit_preset),
                    point.state.enthalpy_j_per_kg,
                    convert_to_display(point.state.enthalpy_j_per_kg, "specific_energy", unit_preset),
                    point.state.cp_j_per_kg_k,
                    convert_to_display(point.state.cp_j_per_kg_k, "specific_heat", unit_preset),
                    point.state.viscosity_pa_s,
                    convert_to_display(point.state.viscosity_pa_s, "viscosity", unit_preset),
                    point.state.thermal_conductivity_w_per_m_k,
                    convert_to_display(
                        point.state.thermal_conductivity_w_per_m_k,
                        "thermal_conductivity",
                        unit_preset,
                    ),
                    point.state.prandtl_number,
                    point.state.gamma,
                    point.state.molecular_weight_kg_per_mol,
                    convert_to_display(point.state.molecular_weight_kg_per_mol, "molecular_weight", unit_preset),
                    point.state.mach_number,
                    point.state.velocity_m_per_s,
                    convert_to_display(point.state.velocity_m_per_s, "velocity", unit_preset),
                    point.state.reynolds_number,
                    point.state.adiabatic_wall_temperature_k,
                    convert_to_display(point.state.adiabatic_wall_temperature_k, "temperature", unit_preset),
                    point.state.thermal_boundary_layer_thickness_m,
                    convert_to_display(
                        point.state.thermal_boundary_layer_thickness_m,
                        "length",
                        unit_preset,
                    ),
                    point.state.velocity_boundary_layer_thickness_m,
                    convert_to_display(
                        point.state.velocity_boundary_layer_thickness_m,
                        "length",
                        unit_preset,
                    ),
                    point.state.source,
                    _species_to_string(point.state.species_mass_fractions),
                    _species_to_string(point.state.species_mole_fractions),
                ]
            )

    return summary, contour, thermo_profile


def export_bundle(
    bundle: ExportBundle,
    output_stem: str | Path,
    *,
    unit_preset: UnitPreset = UnitPreset.SI,
) -> dict[str, Path]:
    """Export JSON and CSV representations for a computed bundle."""

    stem = Path(output_stem)
    json_path = export_bundle_to_json(bundle, stem.with_suffix(".json"), unit_preset=unit_preset)
    summary_path, contour_path, thermo_profile_path = export_bundle_to_csv(
        bundle=bundle,
        summary_path=stem.with_name(f"{stem.stem}_summary.csv"),
        contour_path=stem.with_name(f"{stem.stem}_contour.csv"),
        thermo_profile_path=stem.with_name(f"{stem.stem}_thermo_profile.csv"),
        unit_preset=unit_preset,
    )
    return {
        "json": json_path,
        "summary_csv": summary_path,
        "contour_csv": contour_path,
        "thermo_profile_csv": thermo_profile_path,
    }


def _display_entry(value: float | None, quantity: str, unit_preset: UnitPreset) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "value": convert_to_display(value, quantity, unit_preset),
        "unit": get_unit_symbol(quantity, unit_preset),
    }


def _summary_rows(bundle: ExportBundle) -> list[tuple[str, str, float | None, str | None]]:
    return [
        ("meta", "generated_at_utc", None, None),
        ("inputs", "chamber_pressure_pa", bundle.inputs.chamber_pressure_pa, "pressure"),
        ("inputs", "thrust_n", bundle.inputs.thrust_n, "force"),
        ("inputs", "mixture_ratio", bundle.inputs.mixture_ratio, None),
        ("inputs", "expansion_ratio", bundle.inputs.expansion_ratio, None),
        ("inputs", "ambient_pressure_pa", bundle.inputs.ambient_pressure_pa, "pressure"),
        ("inputs", "characteristic_length_m", bundle.inputs.characteristic_length_m, "length"),
        ("inputs", "manual_nozzle_length_m", bundle.inputs.manual_nozzle_length_m, "length"),
        ("thermochemistry", "chamber_temperature_k", bundle.thermochemistry.chamber_temperature_k, "temperature"),
        ("thermochemistry", "c_star_m_s", bundle.thermochemistry.c_star_m_s, "velocity"),
        ("thermochemistry", "isp_vac_s", bundle.thermochemistry.isp_vac_s, "isp"),
        ("thermochemistry", "isp_amb_s", bundle.thermochemistry.isp_amb_s, "isp"),
        ("thermochemistry", "chamber_density_kg_per_m3", bundle.thermochemistry.chamber_density_kg_per_m3, "density"),
        ("geometry", "throat_area_m2", bundle.geometry.throat_area_m2, "area"),
        ("geometry", "throat_radius_m", bundle.geometry.throat_radius_m, "length"),
        ("geometry", "exit_area_m2", bundle.geometry.exit_area_m2, "area"),
        ("geometry", "exit_radius_m", bundle.geometry.exit_radius_m, "length"),
        ("geometry", "mass_flow_kg_per_s", bundle.geometry.mass_flow_kg_per_s, "mass_flow"),
        ("geometry", "chamber_area_m2", bundle.geometry.chamber_area_m2, "area"),
        ("geometry", "chamber_radius_m", bundle.geometry.chamber_radius_m, "length"),
        ("geometry", "chamber_volume_m3", bundle.geometry.chamber_volume_m3, "volume"),
        ("geometry", "chamber_length_m", bundle.geometry.chamber_length_m, "length"),
        ("geometry", "contour_length_m", bundle.geometry.contour_length_m, "length"),
        ("geometry", "current_expansion_ratio", bundle.geometry.current_expansion_ratio, None),
        ("geometry", "optimal_expansion_ratio", bundle.geometry.optimal_expansion_ratio, None),
        ("geometry", "reference_conical_length_m", bundle.geometry.reference_conical_length_m, "length"),
        ("geometry", "current_nozzle_length_m", bundle.geometry.current_nozzle_length_m, "length"),
    ]


def _species_to_string(species: dict[str, float]) -> str:
    return "; ".join(f"{name}={value:.6g}" for name, value in species.items())
