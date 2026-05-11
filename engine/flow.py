"""Central flow-case plausibility helpers for nozzle activation and UI state."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from enum import Enum
import math

from engine.models import InputParameters

DEFAULT_PLAUSIBILITY_GAMMA = 1.20


class FlowCase(str, Enum):
    """First-order nozzle-flow cases used by the MVP."""

    SUBSONIC = "subsonic"
    CHOKED_SUPERSONIC = "choked-supersonic"


@dataclass(slots=True)
class FlowCaseAssessment:
    """Shared classification result used by the GUI and geometry pipeline."""

    flow_case: FlowCase
    gamma_used: float
    gamma_source: str
    critical_back_pressure_ratio: float
    current_back_pressure_ratio: float
    nozzle_geometry_enabled: bool
    title: str
    message: str


def critical_back_pressure_ratio(gamma: float) -> float:
    """Return the ideal-gas critical back-pressure ratio pa/pc for choking."""

    if not math.isfinite(gamma) or gamma <= 1.0:
        gamma = DEFAULT_PLAUSIBILITY_GAMMA
    return (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))


def classify_flow_case(
    chamber_pressure_pa: float,
    back_pressure_pa: float,
    *,
    gamma: float | None = None,
) -> FlowCaseAssessment:
    """Classify the current nozzle case as unchoked/subsonic or choked/supersonic."""

    gamma_used = gamma if gamma is not None and math.isfinite(gamma) and gamma > 1.0 else DEFAULT_PLAUSIBILITY_GAMMA
    gamma_source = "thermochemistry" if gamma is not None and math.isfinite(gamma) and gamma > 1.0 else "default"
    critical_ratio = critical_back_pressure_ratio(gamma_used)
    current_ratio = float("inf")
    if chamber_pressure_pa > 0.0 and math.isfinite(chamber_pressure_pa):
        current_ratio = back_pressure_pa / chamber_pressure_pa

    is_subsonic = (
        not math.isfinite(chamber_pressure_pa)
        or chamber_pressure_pa <= 0.0
        or not math.isfinite(back_pressure_pa)
        or back_pressure_pa < 0.0
        or current_ratio >= critical_ratio
    )
    if is_subsonic:
        return FlowCaseAssessment(
            flow_case=FlowCase.SUBSONIC,
            gamma_used=gamma_used,
            gamma_source=gamma_source,
            critical_back_pressure_ratio=critical_ratio,
            current_back_pressure_ratio=current_ratio,
            nozzle_geometry_enabled=False,
            title="Subsonic / unchoked plausibility case",
            message=(
                "Back pressure is at or above the critical ratio, so AstraForge keeps the MVP "
                "geometry throat-only and disables the divergent nozzle controls."
            ),
        )

    return FlowCaseAssessment(
        flow_case=FlowCase.CHOKED_SUPERSONIC,
        gamma_used=gamma_used,
        gamma_source=gamma_source,
        critical_back_pressure_ratio=critical_ratio,
        current_back_pressure_ratio=current_ratio,
        nozzle_geometry_enabled=True,
        title="Choked / supersonic CD-nozzle case",
        message=(
            "Back pressure is below the critical ratio, so divergent nozzle geometry remains active "
            "for the current MVP design path."
        ),
    )


def classify_input_flow_case(
    inputs: InputParameters,
    *,
    gamma: float | None = None,
) -> FlowCaseAssessment:
    """Convenience wrapper for classifying an InputParameters instance."""

    return classify_flow_case(
        chamber_pressure_pa=inputs.chamber_pressure_pa,
        back_pressure_pa=inputs.ambient_pressure_pa,
        gamma=gamma,
    )


def adapt_inputs_for_flow_case(
    inputs: InputParameters,
    assessment: FlowCaseAssessment,
) -> InputParameters:
    """Return geometry-safe inputs for the currently classified flow case."""

    if assessment.flow_case is not FlowCase.SUBSONIC:
        return inputs
    return replace(
        inputs,
        expansion_ratio=1.0,
        manual_nozzle_length_m=None,
    )
