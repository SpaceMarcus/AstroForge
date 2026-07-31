"""Delivered-performance losses and operating maps for preliminary design.

The equations in this module follow the correction-factor structure documented
for RPA 2.3:

    zeta_c = zeta_r
    zeta_n = zeta_f * zeta_d * zeta_z
    c*_d = zeta_c * c*
    Cf_vac,d = zeta_n * Cf_vac

For non-vacuum operation the ambient-pressure term is subtracted after the
vacuum momentum correction.  This keeps the pressure-thrust term explicit and
avoids applying a nozzle momentum efficiency to ambient back pressure.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from engine.models import ExportBundle, NozzleContourMethod, NozzlePoint
from engine.nozzle_geometry import (
    compute_bell_divergence_efficiency,
    compute_divergence_efficiency,
)

STANDARD_GRAVITY_M_PER_S2 = 9.80665
SEA_LEVEL_PRESSURE_PA = 101_325.0


@dataclass(frozen=True, slots=True)
class DeliveredPerformanceAssumptions:
    """User-selectable correction assumptions for a preliminary assessment."""

    combustion_efficiency: float | None = None
    friction_efficiency: float = 0.99
    divergence_efficiency: float | None = None
    condensed_mass_fraction: float = 0.0
    condensed_specific_heat_j_per_kg_k: float = 0.0
    exit_velocity_m_per_s: float | None = None
    wall_shear_stress_pa: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class PerformanceLossBreakdown:
    """Resolved correction factors and their provenance."""

    combustion_efficiency: float
    finite_rate_geometry_loss_fraction: float
    finite_rate_pressure_loss_fraction: float
    friction_efficiency: float
    divergence_efficiency: float
    multiphase_efficiency: float
    nozzle_efficiency: float
    total_isp_efficiency: float
    combustion_source: str
    friction_source: str
    divergence_source: str


@dataclass(frozen=True, slots=True)
class DeliveredPerformanceResult:
    """Ideal and delivered performance at one ambient pressure and throttle."""

    ambient_pressure_pa: float
    throttle_fraction: float
    chamber_pressure_pa: float
    ideal_c_star_m_per_s: float
    delivered_c_star_m_per_s: float
    ideal_cf_vac: float
    delivered_cf_vac: float
    ideal_cf_ambient: float
    delivered_cf_ambient: float
    ideal_isp_vac_s: float
    delivered_isp_vac_s: float
    ideal_isp_ambient_s: float
    delivered_isp_ambient_s: float
    mass_flow_kg_per_s: float
    ideal_thrust_n: float
    delivered_thrust_n: float
    separation_risk: bool
    losses: PerformanceLossBreakdown


@dataclass(frozen=True, slots=True)
class PerformanceMapPoint:
    """Single altitude/throttle point for plotting and export."""

    altitude_m: float
    ambient_pressure_pa: float
    throttle_fraction: float
    result: DeliveredPerformanceResult


def estimate_finite_rate_combustion_efficiency(
    *,
    chamber_pressure_pa: float,
    throat_radius_m: float,
    exit_radius_m: float,
    oxidizer: str,
    fuel: str,
) -> tuple[float, float, float, str]:
    """Estimate the RPA finite-rate chamber factor from equations 10-12.

    The propellant-specific geometry term is available only for the three
    empirical families tabulated in the RPA report.  Unknown pairs retain the
    pressure term and are reported explicitly instead of silently borrowing a
    coefficient from another propellant.
    """

    _require_positive_finite(chamber_pressure_pa, "Chamber pressure")
    _require_positive_finite(throat_radius_m, "Throat radius")
    _require_positive_finite(exit_radius_m, "Exit radius")
    if exit_radius_m < throat_radius_m:
        raise ValueError("Exit radius must not be smaller than throat radius.")

    coefficients = _kinetics_coefficients(oxidizer, fuel)
    geometry_loss = 0.0
    family_name = "unavailable for this propellant pair"
    if coefficients is not None:
        h0_m, exponent_a, exponent_b, family_name = coefficients
        geometry_loss = (
            (h0_m / throat_radius_m) ** exponent_a
            * (SEA_LEVEL_PRESSURE_PA / chamber_pressure_pa) ** exponent_b
            * math.log10(exit_radius_m / throat_radius_m)
        )
        geometry_loss = _clamp(geometry_loss, 0.0, 0.25)

    pressure_loss = max(
        0.0,
        (2.1 - math.log(chamber_pressure_pa / 2.0e6)) / 100.0,
    )
    pressure_loss = _clamp(pressure_loss, 0.0, 0.25)
    efficiency = (1.0 - geometry_loss) * (1.0 - pressure_loss)
    source = (
        f"RPA finite-rate estimate ({family_name}; equations 10-12)"
        if coefficients is not None
        else "RPA pressure-only finite-rate estimate (equations 10 and 12)"
    )
    return efficiency, geometry_loss, pressure_loss, source


def compute_multiphase_efficiency(
    *,
    condensed_mass_fraction: float,
    condensed_specific_heat_j_per_kg_k: float,
    exit_velocity_m_per_s: float,
    chamber_temperature_k: float,
    exit_temperature_k: float,
) -> float:
    """Return the multi-phase correction factor from RPA equations 21-23."""

    if not 0.0 <= condensed_mass_fraction < 1.0:
        raise ValueError("Condensed mass fraction must be in the range [0, 1).")
    if condensed_mass_fraction == 0.0:
        return 1.0
    _require_nonnegative_finite(
        condensed_specific_heat_j_per_kg_k,
        "Condensed-phase specific heat",
    )
    _require_positive_finite(exit_velocity_m_per_s, "Exit velocity")
    _require_positive_finite(chamber_temperature_k, "Chamber temperature")
    _require_positive_finite(exit_temperature_k, "Exit temperature")

    temperature_term = chamber_temperature_k - exit_temperature_k * (
        1.0 + math.log(chamber_temperature_k / exit_temperature_k)
    )
    velocity_efficiency = 1.0 - (
        condensed_mass_fraction
        * condensed_specific_heat_j_per_kg_k
        * temperature_term
        / exit_velocity_m_per_s**2
    )
    temperature_efficiency = 1.0 - 0.5 * condensed_mass_fraction
    return _clamp(
        0.2 * velocity_efficiency + 0.8 * temperature_efficiency,
        0.0,
        1.0,
    )


def compute_wall_shear_friction_efficiency(
    *,
    contour: list[NozzlePoint] | tuple[NozzlePoint, ...],
    wall_shear_stress_pa: tuple[float, ...] | list[float],
    ideal_thrust_coefficient: float,
    throat_area_m2: float,
    chamber_stagnation_pressure_pa: float,
) -> tuple[float, float]:
    """Integrate RPA equation 15 over a known wall-shear distribution.

    The supplied stress values must use the same stations as the committed
    contour.  Trapezoidal integration is performed in axial coordinate with
    the local wall-angle cosine kept explicit as written in the RPA relation.
    The returned pair is ``(efficiency, loss_fraction)``.
    """

    if len(contour) < 2:
        raise ValueError("Wall-shear integration requires at least two contour points.")
    if len(wall_shear_stress_pa) != len(contour):
        raise ValueError("Wall-shear station count must equal the contour point count.")
    _require_positive_finite(ideal_thrust_coefficient, "Ideal thrust coefficient")
    _require_positive_finite(throat_area_m2, "Throat area")
    _require_positive_finite(
        chamber_stagnation_pressure_pa,
        "Chamber stagnation pressure",
    )
    if any(
        not math.isfinite(stress) or stress < 0.0
        for stress in wall_shear_stress_pa
    ):
        raise ValueError("Wall-shear stresses must be finite and non-negative.")

    integral = 0.0
    for index, (left, right) in enumerate(zip(contour, contour[1:])):
        dx = right.x_m - left.x_m
        if dx < 0.0:
            raise ValueError("Contour x coordinates must be non-decreasing.")
        if dx == 0.0:
            continue
        left_angle = _local_contour_angle_rad(contour, index)
        right_angle = _local_contour_angle_rad(contour, index + 1)
        left_integrand = (
            wall_shear_stress_pa[index]
            * left.radius_m
            * math.cos(left_angle)
        )
        right_integrand = (
            wall_shear_stress_pa[index + 1]
            * right.radius_m
            * math.cos(right_angle)
        )
        integral += 0.5 * (left_integrand + right_integrand) * dx

    loss_fraction = (
        2.0
        * math.pi
        * integral
        / (
            ideal_thrust_coefficient
            * throat_area_m2
            * chamber_stagnation_pressure_pa
        )
    )
    loss_fraction = _clamp(loss_fraction, 0.0, 1.0)
    return 1.0 - loss_fraction, loss_fraction


def resolve_loss_breakdown(
    bundle: ExportBundle,
    assumptions: DeliveredPerformanceAssumptions | None = None,
) -> PerformanceLossBreakdown:
    """Resolve all correction factors for a committed design bundle."""

    assumptions = assumptions or DeliveredPerformanceAssumptions()
    if assumptions.combustion_efficiency is None:
        (
            combustion_efficiency,
            geometry_loss,
            pressure_loss,
            combustion_source,
        ) = estimate_finite_rate_combustion_efficiency(
            chamber_pressure_pa=bundle.inputs.chamber_pressure_pa,
            throat_radius_m=bundle.geometry.throat_radius_m,
            exit_radius_m=bundle.geometry.exit_radius_m,
            oxidizer=bundle.inputs.oxidizer,
            fuel=bundle.inputs.fuel,
        )
    else:
        combustion_efficiency = _validated_efficiency(
            assumptions.combustion_efficiency,
            "Combustion efficiency",
        )
        geometry_loss = 0.0
        pressure_loss = 0.0
        combustion_source = "User-specified c* efficiency"

    if assumptions.wall_shear_stress_pa is not None:
        ideal_cf = bundle.thermochemistry.cf_vac
        if ideal_cf is None:
            ideal_cf = (
                bundle.thermochemistry.isp_vac_s
                * STANDARD_GRAVITY_M_PER_S2
                / bundle.thermochemistry.c_star_m_s
            )
        friction_efficiency, _friction_loss = (
            compute_wall_shear_friction_efficiency(
                contour=bundle.contour,
                wall_shear_stress_pa=assumptions.wall_shear_stress_pa,
                ideal_thrust_coefficient=ideal_cf,
                throat_area_m2=bundle.geometry.throat_area_m2,
                chamber_stagnation_pressure_pa=bundle.inputs.chamber_pressure_pa,
            )
        )
        friction_source = "Integrated wall shear (RPA equation 15)"
    else:
        friction_efficiency = _validated_efficiency(
            assumptions.friction_efficiency,
            "Friction efficiency",
        )
        friction_source = "User-specified friction efficiency"

    if assumptions.divergence_efficiency is not None:
        divergence_efficiency = _validated_efficiency(
            assumptions.divergence_efficiency,
            "Divergence efficiency",
        )
        divergence_source = "User-specified divergence efficiency"
    elif bundle.inputs.contour_method is NozzleContourMethod.CONICAL:
        divergence_efficiency = compute_divergence_efficiency(
            bundle.geometry.bell_exit_angle_deg
        )
        if divergence_efficiency is None:
            divergence_efficiency = 1.0
        divergence_source = "Conical cosine correction (RPA equation 16)"
    else:
        length_fraction = bundle.geometry.top_nozzle_length_fraction_percent
        if length_fraction is None:
            length_fraction = bundle.inputs.bell_length_fraction_percent or 80.0
        average_k = bundle.thermochemistry.gamma or 1.20
        divergence_efficiency = compute_bell_divergence_efficiency(
            expansion_ratio=bundle.inputs.expansion_ratio,
            length_fraction=length_fraction,
            average_isentropic_exponent=average_k,
        )
        divergence_source = "Bell-nozzle empirical correction (RPA equation 20)"

    multiphase_efficiency = 1.0
    if assumptions.condensed_mass_fraction > 0.0:
        exit_state = bundle.thermochemistry.station_states.get("exit")
        exit_velocity = assumptions.exit_velocity_m_per_s
        if exit_velocity is None and exit_state is not None:
            exit_velocity = exit_state.velocity_m_per_s
        if exit_velocity is None:
            exit_velocity = bundle.thermochemistry.isp_vac_s * STANDARD_GRAVITY_M_PER_S2
        exit_temperature = bundle.thermochemistry.exit_temperature_k
        if exit_temperature is None and exit_state is not None:
            exit_temperature = exit_state.temperature_k
        if exit_temperature is None:
            raise ValueError(
                "Exit temperature is required when multi-phase losses are enabled."
            )
        multiphase_efficiency = compute_multiphase_efficiency(
            condensed_mass_fraction=assumptions.condensed_mass_fraction,
            condensed_specific_heat_j_per_kg_k=(
                assumptions.condensed_specific_heat_j_per_kg_k
            ),
            exit_velocity_m_per_s=exit_velocity,
            chamber_temperature_k=bundle.thermochemistry.chamber_temperature_k,
            exit_temperature_k=exit_temperature,
        )

    nozzle_efficiency = (
        friction_efficiency * divergence_efficiency * multiphase_efficiency
    )
    return PerformanceLossBreakdown(
        combustion_efficiency=combustion_efficiency,
        finite_rate_geometry_loss_fraction=geometry_loss,
        finite_rate_pressure_loss_fraction=pressure_loss,
        friction_efficiency=friction_efficiency,
        divergence_efficiency=divergence_efficiency,
        multiphase_efficiency=multiphase_efficiency,
        nozzle_efficiency=nozzle_efficiency,
        total_isp_efficiency=combustion_efficiency * nozzle_efficiency,
        combustion_source=combustion_source,
        friction_source=friction_source,
        divergence_source=divergence_source,
    )


def evaluate_delivered_performance(
    bundle: ExportBundle,
    *,
    ambient_pressure_pa: float | None = None,
    throttle_fraction: float = 1.0,
    assumptions: DeliveredPerformanceAssumptions | None = None,
) -> DeliveredPerformanceResult:
    """Evaluate delivered performance at one ambient pressure and throttle.

    Chamber pressure is scaled linearly with mass-flow throttle.  Thermochemical
    properties are held at the committed design state, making this a fast
    preliminary map rather than a replacement for a pressure-by-pressure CEA
    recomputation.
    """

    if ambient_pressure_pa is None:
        ambient_pressure_pa = bundle.inputs.ambient_pressure_pa
    _require_nonnegative_finite(ambient_pressure_pa, "Ambient pressure")
    if not math.isfinite(throttle_fraction) or not 0.0 < throttle_fraction <= 1.0:
        raise ValueError("Throttle fraction must be in the range (0, 1].")

    losses = resolve_loss_breakdown(bundle, assumptions)
    chamber_pressure_pa = bundle.inputs.chamber_pressure_pa * throttle_fraction
    throat_area_m2 = bundle.geometry.throat_area_m2
    expansion_ratio = bundle.geometry.exit_area_m2 / throat_area_m2
    ideal_c_star = bundle.thermochemistry.c_star_m_s
    ideal_cf_vac = bundle.thermochemistry.cf_vac
    if ideal_cf_vac is None:
        ideal_cf_vac = (
            bundle.thermochemistry.isp_vac_s
            * STANDARD_GRAVITY_M_PER_S2
            / ideal_c_star
        )

    ideal_cf_ambient = ideal_cf_vac - (
        expansion_ratio * ambient_pressure_pa / chamber_pressure_pa
    )
    delivered_cf_vac = losses.nozzle_efficiency * ideal_cf_vac
    delivered_cf_ambient = delivered_cf_vac - (
        expansion_ratio * ambient_pressure_pa / chamber_pressure_pa
    )
    delivered_c_star = losses.combustion_efficiency * ideal_c_star
    ideal_isp_ambient = ideal_cf_ambient * ideal_c_star / STANDARD_GRAVITY_M_PER_S2
    delivered_isp_vac = (
        delivered_cf_vac * delivered_c_star / STANDARD_GRAVITY_M_PER_S2
    )
    delivered_isp_ambient = (
        delivered_cf_ambient * delivered_c_star / STANDARD_GRAVITY_M_PER_S2
    )
    mass_flow = chamber_pressure_pa * throat_area_m2 / delivered_c_star
    ideal_thrust = ideal_cf_ambient * chamber_pressure_pa * throat_area_m2
    delivered_thrust = (
        delivered_cf_ambient * chamber_pressure_pa * throat_area_m2
    )

    exit_state = bundle.thermochemistry.station_states.get("exit")
    exit_mach = exit_state.mach_number if exit_state is not None else None
    exit_pressure = bundle.thermochemistry.exit_pressure_pa
    separation_risk = schmucker_separation_risk(
        ambient_pressure_pa=ambient_pressure_pa,
        wall_pressure_pa=exit_pressure,
        mach_number=exit_mach,
    )

    return DeliveredPerformanceResult(
        ambient_pressure_pa=ambient_pressure_pa,
        throttle_fraction=throttle_fraction,
        chamber_pressure_pa=chamber_pressure_pa,
        ideal_c_star_m_per_s=ideal_c_star,
        delivered_c_star_m_per_s=delivered_c_star,
        ideal_cf_vac=ideal_cf_vac,
        delivered_cf_vac=delivered_cf_vac,
        ideal_cf_ambient=ideal_cf_ambient,
        delivered_cf_ambient=delivered_cf_ambient,
        ideal_isp_vac_s=bundle.thermochemistry.isp_vac_s,
        delivered_isp_vac_s=delivered_isp_vac,
        ideal_isp_ambient_s=ideal_isp_ambient,
        delivered_isp_ambient_s=delivered_isp_ambient,
        mass_flow_kg_per_s=mass_flow,
        ideal_thrust_n=ideal_thrust,
        delivered_thrust_n=delivered_thrust,
        separation_risk=separation_risk,
        losses=losses,
    )


def build_performance_map(
    bundle: ExportBundle,
    *,
    altitudes_m: tuple[float, ...] | list[float],
    throttle_fractions: tuple[float, ...] | list[float] = (1.0,),
    assumptions: DeliveredPerformanceAssumptions | None = None,
) -> list[PerformanceMapPoint]:
    """Build a deterministic altitude/throttle performance map."""

    points: list[PerformanceMapPoint] = []
    for throttle_fraction in throttle_fractions:
        for altitude_m in altitudes_m:
            ambient_pressure_pa = standard_atmosphere_pressure_pa(altitude_m)
            points.append(
                PerformanceMapPoint(
                    altitude_m=float(altitude_m),
                    ambient_pressure_pa=ambient_pressure_pa,
                    throttle_fraction=float(throttle_fraction),
                    result=evaluate_delivered_performance(
                        bundle,
                        ambient_pressure_pa=ambient_pressure_pa,
                        throttle_fraction=float(throttle_fraction),
                        assumptions=assumptions,
                    ),
                )
            )
    return points


def standard_atmosphere_pressure_pa(altitude_m: float) -> float:
    """Return 1976-standard-atmosphere pressure through 84.852 km."""

    if not math.isfinite(altitude_m) or altitude_m < 0.0 or altitude_m > 84_852.0:
        raise ValueError("Altitude must be between 0 and 84,852 m.")

    geopotential_m = 6_356_766.0 * altitude_m / (6_356_766.0 + altitude_m)
    layer_bases_m = (0.0, 11_000.0, 20_000.0, 32_000.0, 47_000.0, 51_000.0, 71_000.0)
    lapse_rates_k_per_m = (-0.0065, 0.0, 0.0010, 0.0028, 0.0, -0.0028, -0.0020)
    base_temperatures_k = (288.15, 216.65, 216.65, 228.65, 270.65, 270.65, 214.65)
    base_pressures_pa = (
        101_325.0,
        22_632.06,
        5_474.889,
        868.0187,
        110.9063,
        66.93887,
        3.956420,
    )
    gas_constant_air = 287.05287
    gravity = 9.80665

    layer_index = len(layer_bases_m) - 1
    for index in range(len(layer_bases_m) - 1):
        if geopotential_m < layer_bases_m[index + 1]:
            layer_index = index
            break
    delta_height = geopotential_m - layer_bases_m[layer_index]
    lapse_rate = lapse_rates_k_per_m[layer_index]
    base_temperature = base_temperatures_k[layer_index]
    base_pressure = base_pressures_pa[layer_index]
    if lapse_rate == 0.0:
        return base_pressure * math.exp(
            -gravity * delta_height / (gas_constant_air * base_temperature)
        )
    local_temperature = base_temperature + lapse_rate * delta_height
    return base_pressure * (
        base_temperature / local_temperature
    ) ** (gravity / (gas_constant_air * lapse_rate))


def schmucker_separation_pressure_ratio(mach_number: float) -> float:
    """Return pi/pa from the Schmucker criterion used by RPA (equation 39)."""

    if not math.isfinite(mach_number) or mach_number <= 1.0 / 1.88:
        raise ValueError("Mach number is outside the Schmucker criterion range.")
    return (1.88 * mach_number - 1.0) ** -0.64


def schmucker_separation_risk(
    *,
    ambient_pressure_pa: float,
    wall_pressure_pa: float | None,
    mach_number: float | None,
) -> bool:
    """Return whether an operating point crosses the Schmucker criterion."""

    if (
        ambient_pressure_pa <= 0.0
        or wall_pressure_pa is None
        or wall_pressure_pa <= 0.0
        or mach_number is None
    ):
        return False
    try:
        limiting_ratio = schmucker_separation_pressure_ratio(mach_number)
    except ValueError:
        return False
    return wall_pressure_pa / ambient_pressure_pa <= limiting_ratio


def _kinetics_coefficients(
    oxidizer: str,
    fuel: str,
) -> tuple[float, float, float, str] | None:
    oxidizer_key = _normalized_propellant(oxidizer)
    fuel_key = _normalized_propellant(fuel)
    oxygen = any(token in oxidizer_key for token in ("LOX", "O2", "OXYGEN"))
    if oxygen and any(token in fuel_key for token in ("LH2", "H2", "HYDROGEN")):
        return 1.3e-3, 0.4, 1.0, "O2 + H2"
    if oxygen and any(token in fuel_key for token in ("RP1", "KEROSENE", "KEROSINE")):
        return 6.7e-4, 0.35, 0.8, "O2 + kerosene"
    nitrogen_tetroxide = any(
        token in oxidizer_key for token in ("N2O4", "NTO", "AT")
    )
    if nitrogen_tetroxide and "UDMH" in fuel_key:
        return 5.3e-6, 0.25, 0.5, "N2O4 + UDMH"
    return None


def _normalized_propellant(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _validated_efficiency(value: float, label: str) -> float:
    if not math.isfinite(value) or not 0.0 < value <= 1.0:
        raise ValueError(f"{label} must be in the range (0, 1].")
    return value


def _require_positive_finite(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and greater than zero.")


def _require_nonnegative_finite(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and non-negative.")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _local_contour_angle_rad(
    contour: list[NozzlePoint] | tuple[NozzlePoint, ...],
    index: int,
) -> float:
    left = contour[max(index - 1, 0)]
    right = contour[min(index + 1, len(contour) - 1)]
    return math.atan2(right.radius_m - left.radius_m, right.x_m - left.x_m)
