"""Geometry helper functions and first-order engine sizing."""

from __future__ import annotations

import math

from engine.models import GeometryResult, InputParameters, ThermochemistryResult


class GeometrySizingError(ValueError):
    """Raised when geometry sizing cannot be completed from the available data."""


def circle_area_from_radius(radius_m: float) -> float:
    """Return cross-sectional area for a positive radius."""

    if radius_m <= 0.0:
        raise ValueError("Radius must be greater than zero.")
    return math.pi * radius_m**2


def radius_from_circle_area(area_m2: float) -> float:
    """Return radius for a positive circular area."""

    if area_m2 <= 0.0:
        raise ValueError("Area must be greater than zero.")
    return math.sqrt(area_m2 / math.pi)


def area_ratio_from_radii(exit_radius_m: float, throat_radius_m: float) -> float:
    """Return Ae/At for positive exit and throat radii."""

    exit_area = circle_area_from_radius(exit_radius_m)
    throat_area = circle_area_from_radius(throat_radius_m)
    return exit_area / throat_area


def select_reference_thrust_coefficient(
    thermo: ThermochemistryResult,
    ambient_pressure_pa: float,
) -> float:
    """Select the thrust coefficient used to back out throat area from thrust."""

    if ambient_pressure_pa > 0.0 and thermo.cf_amb is not None:
        return thermo.cf_amb
    if thermo.cf_vac is not None:
        return thermo.cf_vac
    raise GeometrySizingError(
        "No usable thrust coefficient is available to size the geometry."
    )


def throat_area_from_thrust(thrust_n: float, chamber_pressure_pa: float, cf: float) -> float:
    """Return throat area from thrust, chamber pressure and thrust coefficient."""

    if thrust_n <= 0.0:
        raise GeometrySizingError("Thrust must be greater than 0 N.")
    if chamber_pressure_pa <= 0.0:
        raise GeometrySizingError("Pc must be greater than 0 Pa.")
    if cf <= 0.0:
        raise GeometrySizingError("Cf must be greater than 0.")
    return thrust_n / (cf * chamber_pressure_pa)


def mass_flow_from_throat_area(
    throat_area_m2: float,
    chamber_pressure_pa: float,
    c_star_m_s: float,
) -> float:
    """Return propellant mass flow from c* and throat area."""

    if throat_area_m2 <= 0.0:
        raise GeometrySizingError("At must be greater than 0 m^2.")
    if c_star_m_s <= 0.0:
        raise GeometrySizingError("c* must be greater than 0 m/s.")
    return chamber_pressure_pa * throat_area_m2 / c_star_m_s


def size_engine_geometry(
    inputs: InputParameters,
    thermo: ThermochemistryResult,
) -> GeometryResult:
    """Derive first-order chamber and nozzle geometry from validated inputs."""

    cf_reference = select_reference_thrust_coefficient(
        thermo=thermo,
        ambient_pressure_pa=inputs.ambient_pressure_pa,
    )
    throat_area_m2 = throat_area_from_thrust(
        thrust_n=inputs.thrust_n,
        chamber_pressure_pa=inputs.chamber_pressure_pa,
        cf=cf_reference,
    )
    throat_radius_m = radius_from_circle_area(throat_area_m2)
    exit_area_m2 = throat_area_m2 * inputs.expansion_ratio
    exit_radius_m = radius_from_circle_area(exit_area_m2)
    mass_flow_kg_per_s = mass_flow_from_throat_area(
        throat_area_m2=throat_area_m2,
        chamber_pressure_pa=inputs.chamber_pressure_pa,
        c_star_m_s=thermo.c_star_m_s,
    )

    chamber_area_m2: float | None = None
    chamber_radius_m: float | None = None
    chamber_volume_m3: float | None = None
    chamber_length_m: float | None = None

    if inputs.contraction_ratio is not None:
        chamber_area_m2 = throat_area_m2 * inputs.contraction_ratio
        chamber_radius_m = radius_from_circle_area(chamber_area_m2)

    if inputs.characteristic_length_m is not None:
        chamber_volume_m3 = inputs.characteristic_length_m * throat_area_m2
        if chamber_area_m2 is not None:
            chamber_length_m = chamber_volume_m3 / chamber_area_m2

    return GeometryResult(
        throat_area_m2=throat_area_m2,
        throat_radius_m=throat_radius_m,
        exit_area_m2=exit_area_m2,
        exit_radius_m=exit_radius_m,
        mass_flow_kg_per_s=mass_flow_kg_per_s,
        chamber_area_m2=chamber_area_m2,
        chamber_radius_m=chamber_radius_m,
        chamber_volume_m3=chamber_volume_m3,
        chamber_length_m=chamber_length_m,
        current_expansion_ratio=inputs.expansion_ratio,
        optimal_expansion_ratio=thermo.optimal_expansion_ratio,
    )
