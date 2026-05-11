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
    """Return a preliminary divergence-efficiency factor from the exit wall angle.

    The returned factor is a compact pre-design cosine-loss approximation that
    can be used for preview-level thrust adjustments. It is not a replacement
    for full nozzle-flow optimization.
    """

    if exit_angle_deg is None or not math.isfinite(exit_angle_deg):
        return None
    return 0.5 * (1.0 + math.cos(math.radians(exit_angle_deg)))
