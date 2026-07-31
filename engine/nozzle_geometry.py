"""TOP / Rao nozzle-angle helpers for preliminary bell-nozzle design."""

from __future__ import annotations

from functools import lru_cache
import math

TOP_NOZZLE_SOURCE = "Rao / Huzel & Huang chart interpolation via pygasflow"
TOP_NOZZLE_REPORT_METHOD = "Digitized Rao/Huzel-&-Huang TOP nozzle chart interpolation"
TOP_NOZZLE_VALIDITY_RANGE = "60% <= Lf <= 100%, 5 <= Ae/At <= 50"
TOP_NOZZLE_LIMITATION = "Preliminary design approximation; not a full MoC or CFD-optimized contour"

_VALIDITY_MESSAGE = (
    "Rao/Huzel-&-Huang chart interpolation is only valid in this range: "
    "60 <= Lf <= 100 and 5 <= Ae/At <= 50."
)


@lru_cache(maxsize=1)
def _get_rao_interpolator():
    """Create and cache the pygasflow Rao interpolator on first use."""

    try:
        from pygasflow.nozzles.rao_parabola_angles import Rao_Parabola_Angles
    except ImportError as exc:
        raise RuntimeError(
            "pygasflow is required for Rao/TOP nozzle-angle interpolation."
        ) from exc
    try:
        return Rao_Parabola_Angles()
    except Exception as exc:
        raise RuntimeError(
            "Rao/TOP nozzle-angle interpolation could not be initialized from pygasflow."
        ) from exc


def normalize_top_length_fraction(length_fraction: float) -> float:
    """Normalize a bell-length input to Lf percent for Rao/TOP chart lookup.

    Accepts either:
    - K in the range 0.6 to 1.0
    - Lf in the range 60 to 100

    The returned value is always Lf in percent.
    """

    if not math.isfinite(length_fraction):
        raise ValueError(f"{_VALIDITY_MESSAGE} Received a non-finite length fraction.")
    if 0.6 <= length_fraction <= 1.0:
        return length_fraction * 100.0
    if 60.0 <= length_fraction <= 100.0:
        return length_fraction
    raise ValueError(
        f"{_VALIDITY_MESSAGE} Received length_fraction={length_fraction:.6g}."
    )


def get_top_nozzle_angles(
    expansion_ratio: float,
    length_fraction: float,
) -> tuple[float, float]:
    """Return empirical Rao/TOP bell angles in degrees for preliminary design.

    These angles are obtained from digitized Rao / Huzel & Huang chart
    interpolation via pygasflow. They are not closed-form analytical results.
    """

    if not math.isfinite(expansion_ratio):
        raise ValueError(f"{_VALIDITY_MESSAGE} Received a non-finite expansion ratio.")
    if not 5.0 <= expansion_ratio <= 50.0:
        raise ValueError(
            f"{_VALIDITY_MESSAGE} Received expansion_ratio={expansion_ratio:.6g}."
        )

    length_fraction_percent = normalize_top_length_fraction(length_fraction)
    rao = _get_rao_interpolator()
    theta_n_deg, theta_e_deg = rao.angles_from_Lf_Ar(length_fraction_percent, expansion_ratio)
    return float(theta_n_deg), float(theta_e_deg)


def get_top_nozzle_report_metadata() -> dict[str, str]:
    """Return report metadata for the Rao/TOP interpolation method."""

    return {
        "method": TOP_NOZZLE_REPORT_METHOD,
        "validity_range": TOP_NOZZLE_VALIDITY_RANGE,
        "limitation": TOP_NOZZLE_LIMITATION,
    }


def compute_divergence_efficiency(exit_angle_deg: float | None) -> float | None:
    """Return the conical cosine divergence factor from the exit half-angle.

    This is RPA equation 16 and is exact only for the one-dimensional correction
    of a conical nozzle.  Bell nozzles should use
    :func:`compute_bell_divergence_efficiency`.
    """

    if exit_angle_deg is None or not math.isfinite(exit_angle_deg):
        return None
    return 0.5 * (1.0 + math.cos(math.radians(exit_angle_deg)))


def compute_bell_divergence_efficiency(
    *,
    expansion_ratio: float,
    length_fraction: float,
    average_isentropic_exponent: float,
) -> float:
    """Return the empirical bell-nozzle divergence factor from RPA equation 20.

    ``length_fraction`` accepts either the nondimensional range 0.4-1.0 or the
    corresponding percentage range 40-100.  Values of the average isentropic
    exponent outside the documented 1.1-1.25 range are conservatively clipped
    to the nearest validity boundary.
    """

    if not math.isfinite(expansion_ratio) or expansion_ratio <= 1.0:
        raise ValueError("Bell divergence efficiency requires Ae/At > 1.")
    if not math.isfinite(length_fraction):
        raise ValueError("Bell length fraction must be finite.")
    if length_fraction > 1.0:
        length_fraction /= 100.0
    if not 0.4 <= length_fraction <= 1.0:
        raise ValueError(
            "RPA bell divergence equation 20 requires a length fraction from 0.4 to 1.0."
        )
    if (
        not math.isfinite(average_isentropic_exponent)
        or average_isentropic_exponent <= 1.0
    ):
        raise ValueError(
            "Bell divergence efficiency requires an average isentropic exponent above 1."
        )
    average_isentropic_exponent = max(
        1.1,
        min(1.25, average_isentropic_exponent),
    )

    relative_exit_radius = math.sqrt(expansion_ratio)
    relative_origin_radius = 1.0 + (
        (relative_exit_radius - 1.0) / length_fraction
    )
    coefficient_b = 1.52 * (
        math.exp(-30.0 * (average_isentropic_exponent - 1.0)) + 0.1
    )
    exponent_n = (
        1.45 * relative_origin_radius**0.25
        - 0.005 * relative_origin_radius
    )
    numerator = math.exp(
        exponent_n * (1.0 - relative_exit_radius / relative_origin_radius)
    ) - 1.0
    denominator = math.exp(exponent_n) - 1.0
    efficiency = 1.0 - coefficient_b * numerator / denominator
    return max(0.0, min(1.0, efficiency))
