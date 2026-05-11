"""Preset helpers for saved AstraForge engine configurations."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from engine.io.export import _to_serializable
from engine.models import (
    BellContourVariant,
    ChemistryMode,
    InputParameters,
    ManufacturingMode,
    ManufacturingRoute,
    NozzleContourMethod,
    OFSweepMetric,
    WallThicknessMode,
)
from engine.project_state import ProjectManagementData, ProjectMode
from engine.unit_system import UnitPreset

PRESET_FORMAT = "astraforge-engine-preset"
PRESET_VERSION = 1


def preset_to_dict(
    inputs: InputParameters,
    *,
    of_sweep_metric: OFSweepMetric = OFSweepMetric.ISP_VAC,
    selected_mixture_ratio: float | None = None,
    unit_preset: UnitPreset = UnitPreset.SI_CAD,
    project_mode: ProjectMode = ProjectMode.SANDBOX,
    system_engineering_enabled: bool = False,
    project_management: ProjectManagementData | None = None,
) -> dict[str, Any]:
    """Convert the current engine preset into a JSON-serializable dictionary."""

    project_management = project_management or ProjectManagementData()
    return {
        "format": PRESET_FORMAT,
        "version": PRESET_VERSION,
        "inputs": _to_serializable(inputs),
        "ui_state": {
            "of_sweep_metric": of_sweep_metric.value,
            "selected_mixture_ratio": selected_mixture_ratio,
            "unit_preset": unit_preset.value,
            "project_mode": project_mode.value,
            "system_engineering_enabled": bool(system_engineering_enabled),
            "project_management": asdict(project_management),
        },
    }


def export_engine_preset(
    inputs: InputParameters,
    target_path: str | Path,
    *,
    of_sweep_metric: OFSweepMetric = OFSweepMetric.ISP_VAC,
    selected_mixture_ratio: float | None = None,
    unit_preset: UnitPreset = UnitPreset.SI_CAD,
    project_mode: ProjectMode = ProjectMode.SANDBOX,
    system_engineering_enabled: bool = False,
    project_management: ProjectManagementData | None = None,
) -> Path:
    """Write an AstraForge engine preset to disk."""

    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            preset_to_dict(
                inputs,
                of_sweep_metric=of_sweep_metric,
                selected_mixture_ratio=selected_mixture_ratio,
                unit_preset=unit_preset,
                project_mode=project_mode,
                system_engineering_enabled=system_engineering_enabled,
                project_management=project_management,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def load_engine_preset(target_path: str | Path) -> tuple[InputParameters, dict[str, Any]]:
    """Read an AstraForge engine preset from disk."""

    path = Path(target_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("format") != PRESET_FORMAT:
        raise ValueError("The selected file is not an AstraForge engine preset.")
    if payload.get("version") != PRESET_VERSION:
        raise ValueError(
            f"Unsupported AstraForge preset version: {payload.get('version')!r}."
        )

    raw_inputs = payload.get("inputs")
    if not isinstance(raw_inputs, dict):
        raise ValueError("The preset does not contain a valid inputs block.")

    inputs = InputParameters(
        fuel=str(raw_inputs.get("fuel", "")).strip(),
        oxidizer=str(raw_inputs.get("oxidizer", "")).strip(),
        chamber_pressure_pa=_required_float(raw_inputs, "chamber_pressure_pa"),
        thrust_n=_required_float(raw_inputs, "thrust_n"),
        mixture_ratio=_required_float(raw_inputs, "mixture_ratio"),
        expansion_ratio=_required_float(raw_inputs, "expansion_ratio"),
        ambient_pressure_pa=_required_float(raw_inputs, "ambient_pressure_pa"),
        contraction_ratio=_optional_float(raw_inputs, "contraction_ratio"),
        characteristic_length_m=_optional_float(raw_inputs, "characteristic_length_m"),
        chemistry_mode=ChemistryMode(
            raw_inputs.get("chemistry_mode", ChemistryMode.EQUILIBRIUM.value)
        ),
        contour_method=NozzleContourMethod(
            raw_inputs.get("contour_method", NozzleContourMethod.BELL.value)
        ),
        bell_variant=BellContourVariant(
            raw_inputs.get("bell_variant", BellContourVariant.PARABOLA.value)
        ),
        manual_nozzle_length_m=_optional_float(raw_inputs, "manual_nozzle_length_m"),
        throat_upstream_radius_m=_optional_float(raw_inputs, "throat_upstream_radius_m"),
        throat_downstream_radius_m=_optional_float(raw_inputs, "throat_downstream_radius_m"),
        convergent_half_angle_deg=float(raw_inputs.get("convergent_half_angle_deg", 45.0)),
        chamber_corner_radius_m=_optional_float(raw_inputs, "chamber_corner_radius_m"),
        manufacturing_mode=ManufacturingMode(
            raw_inputs.get("manufacturing_mode", ManufacturingMode.TRADITIONAL.value)
        ),
        manufacturing_route=ManufacturingRoute(
            raw_inputs.get(
                "manufacturing_route",
                ManufacturingRoute.MILLED_CHANNELS_CLOSEOUT.value,
            )
        ),
        liner_material=str(raw_inputs.get("liner_material", "CuCrZr")).strip() or "CuCrZr",
        liner_coating_enabled=bool(raw_inputs.get("liner_coating_enabled", False)),
        liner_coating=_optional_string(raw_inputs, "liner_coating"),
        wall_thickness_mode=WallThicknessMode(
            raw_inputs.get("wall_thickness_mode", WallThicknessMode.CONSTANT.value)
        ),
        wall_thickness_m=_optional_float(raw_inputs, "wall_thickness_m")
        if "wall_thickness_m" in raw_inputs
        else 0.0015,
    )

    raw_ui_state = payload.get("ui_state", {})
    if not isinstance(raw_ui_state, dict):
        raw_ui_state = {}

    of_metric_raw = raw_ui_state.get("of_sweep_metric", OFSweepMetric.ISP_VAC.value)
    try:
        of_sweep_metric = OFSweepMetric(of_metric_raw)
    except ValueError:
        of_sweep_metric = OFSweepMetric.ISP_VAC

    unit_preset_raw = raw_ui_state.get("unit_preset", UnitPreset.SI_CAD.value)
    try:
        unit_preset = UnitPreset(unit_preset_raw)
    except ValueError:
        unit_preset = UnitPreset.SI_CAD

    project_mode_raw = raw_ui_state.get("project_mode", ProjectMode.SANDBOX.value)
    try:
        project_mode = ProjectMode(project_mode_raw)
    except ValueError:
        project_mode = ProjectMode.SANDBOX

    raw_project_management = raw_ui_state.get("project_management", {})
    if not isinstance(raw_project_management, dict):
        raw_project_management = {}
    project_management = ProjectManagementData(
        allow_initial_design_editing_after_run=bool(
            raw_project_management.get("allow_initial_design_editing_after_run", False)
        ),
        mission_objectives=_optional_string(raw_project_management, "mission_objectives") or "",
        requirements=_optional_string(raw_project_management, "requirements") or "",
        constraints=_optional_string(raw_project_management, "constraints") or "",
        budgets=_optional_string(raw_project_management, "budgets") or "",
        thrust_requirement=_optional_string(raw_project_management, "thrust_requirement") or "",
        pressure_requirement=_optional_string(raw_project_management, "pressure_requirement") or "",
        throttling_requirement=_optional_string(raw_project_management, "throttling_requirement") or "",
        max_length=_optional_string(raw_project_management, "max_length") or "",
        wall_temperature_constraint=_optional_string(raw_project_management, "wall_temperature_constraint") or "",
        manufacturing_constraint=_optional_string(raw_project_management, "manufacturing_constraint") or "",
        mass_budget=_optional_string(raw_project_management, "mass_budget") or "",
    )

    return inputs, {
        "of_sweep_metric": of_sweep_metric,
        "selected_mixture_ratio": _optional_float(raw_ui_state, "selected_mixture_ratio"),
        "unit_preset": unit_preset,
        "project_mode": project_mode,
        "system_engineering_enabled": bool(raw_ui_state.get("system_engineering_enabled", False))
        and project_mode is ProjectMode.GUIDED,
        "project_management": project_management,
    }


def _required_float(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if value is None:
        raise ValueError(f"The preset is missing the required field '{key}'.")
    return float(value)


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    return float(value)


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    string_value = str(value).strip()
    return string_value or None
