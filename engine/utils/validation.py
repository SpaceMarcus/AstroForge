"""Validation helpers for engine design inputs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.models import (
    BellContourVariant,
    ChemistryMode,
    InputParameters,
    ManufacturingMode,
    ManufacturingRoute,
    NozzleContourMethod,
    WallThicknessMode,
)


@dataclass(slots=True)
class InputValidationError(ValueError):
    """Collect multiple user-facing validation messages in one exception."""

    messages: list[str]

    def __str__(self) -> str:
        return "\n".join(self.messages)


def _is_finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0.0


def validate_input_parameters(inputs: InputParameters) -> list[str]:
    """Return a list of validation messages for the provided input set."""

    errors: list[str] = []

    if not inputs.fuel.strip():
        errors.append("Fuel must not be empty.")
    if not inputs.oxidizer.strip():
        errors.append("Oxidizer must not be empty.")

    if not _is_finite_positive(inputs.chamber_pressure_pa):
        errors.append("Pc must be greater than 0 Pa.")
    if not _is_finite_positive(inputs.thrust_n):
        errors.append("Thrust must be greater than 0 N.")
    if not _is_finite_positive(inputs.mixture_ratio):
        errors.append("MR must be greater than 0.")
    if not _is_finite_positive(inputs.expansion_ratio):
        errors.append("Expansion ratio eps must be greater than 0.")
    if not math.isfinite(inputs.ambient_pressure_pa) or inputs.ambient_pressure_pa < 0.0:
        errors.append("Pa must be finite and at least 0 Pa.")

    if (
        math.isfinite(inputs.chamber_pressure_pa)
        and math.isfinite(inputs.ambient_pressure_pa)
        and inputs.chamber_pressure_pa <= inputs.ambient_pressure_pa
    ):
        errors.append("Pc must be greater than Pa to define a valid nozzle case.")

    if inputs.contraction_ratio is not None:
        if not _is_finite_positive(inputs.contraction_ratio):
            errors.append("Ac/At must be greater than 0 when it is provided.")
        elif inputs.contraction_ratio <= 1.0:
            errors.append("Ac/At must be greater than 1 when it is provided.")

    if inputs.characteristic_length_m is not None and not _is_finite_positive(
        inputs.characteristic_length_m
    ):
        errors.append("L* must be greater than 0 m when it is provided.")

    if not isinstance(inputs.chemistry_mode, ChemistryMode):
        errors.append("Chemistry mode is invalid.")
    if not isinstance(inputs.contour_method, NozzleContourMethod):
        errors.append("Nozzle contour method is invalid.")
    if not isinstance(inputs.bell_variant, BellContourVariant):
        errors.append("Bell contour subtype is invalid.")

    if inputs.contour_method is NozzleContourMethod.AEROSPIKE:
        errors.append("Aerospike is reserved for a future AstraForge release and is not available yet.")

    if inputs.contour_method is NozzleContourMethod.BELL and inputs.bell_variant is not BellContourVariant.PARABOLA:
        errors.append(
            "Bell subtypes TIC and TOC are visible in the UI but are not numerically implemented yet."
        )

    if inputs.manual_nozzle_length_m is not None and not _is_finite_positive(inputs.manual_nozzle_length_m):
        errors.append("Manual nozzle length L must be greater than 0 m when it is provided.")

    if not math.isfinite(inputs.convergent_half_angle_deg) or not (1.0 <= inputs.convergent_half_angle_deg < 90.0):
        errors.append("Convergent half-angle must stay between 1 and 90 deg.")

    if not isinstance(inputs.manufacturing_mode, ManufacturingMode):
        errors.append("Manufacturing mode is invalid.")
    if not isinstance(inputs.manufacturing_route, ManufacturingRoute):
        errors.append("Manufacturing route is invalid.")
    if not isinstance(inputs.wall_thickness_mode, WallThicknessMode):
        errors.append("Wall-thickness mode is invalid.")
    if inputs.closeout_enabled:
        if inputs.closeout_thickness_m is None or not _is_finite_positive(inputs.closeout_thickness_m):
            errors.append("Closeout thickness must be greater than 0 m when closeout is enabled.")
        if inputs.closeout_material is None or not inputs.closeout_material.strip():
            errors.append("Closeout material must be selected when closeout is enabled.")
    if inputs.wall_thickness_mode is WallThicknessMode.CONSTANT:
        if inputs.wall_thickness_m is None or not _is_finite_positive(inputs.wall_thickness_m):
            errors.append(
                "The hot-gas-to-coolant separating wall thickness must be greater than 0 m in constant mode."
            )
    elif inputs.wall_thickness_m is not None and not _is_finite_positive(inputs.wall_thickness_m):
        errors.append("Wall thickness must be greater than 0 m when it is provided.")

    return errors


def ensure_valid_input(inputs: InputParameters) -> None:
    """Raise InputValidationError when the input set is not valid."""

    errors = validate_input_parameters(inputs)
    if errors:
        raise InputValidationError(errors)
