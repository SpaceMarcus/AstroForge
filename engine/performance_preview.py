"""Compact performance-preview helpers for Current Design."""

from __future__ import annotations

from dataclasses import dataclass

from engine.geometry.sizing import select_reference_thrust_coefficient
from engine.models import ExportBundle, InputParameters


def eta_cstar_band(eta_cstar_design: float) -> str:
    """Return a compact UI band name for the current combustion-efficiency assumption."""

    if eta_cstar_design > 1.0:
        return "invalid"
    if eta_cstar_design > 0.98:
        return "success"
    if eta_cstar_design >= 0.95:
        return "normal"
    return "warning"


@dataclass(slots=True)
class PerformancePreviewResult:
    """Compact performance-preview values derived after a Current Design run."""

    c_star_theoretical_m_s: float | None
    eta_cstar_design: float
    c_star_design_m_s: float | None
    chamber_pressure_pa: float | None
    throat_area_m2: float | None
    throat_diameter_m: float | None
    cf_design: float | None
    isp_vac_s: float | None
    isp_sl_s: float | None
    mass_flow_kg_per_s: float | None
    thrust_estimate_n: float | None
    thrust_deviation_percent: float | None
    expansion_ratio: float | None

    @property
    def thrust_deviation_exceeds_threshold(self) -> bool:
        """Return whether the previewed thrust deviates significantly from the target."""

        return (
            self.thrust_deviation_percent is not None
            and abs(self.thrust_deviation_percent) > 5.0
        )


def compute_performance_preview(
    inputs: InputParameters,
    bundle: ExportBundle,
    eta_cstar_design: float,
) -> PerformancePreviewResult:
    """Build a compact Current Design preview from the latest calculated bundle."""

    c_star_theoretical_m_s = (
        bundle.thermochemistry.c_star_m_s
        if bundle.thermochemistry.c_star_m_s > 0.0
        else None
    )
    c_star_design_m_s = None
    if c_star_theoretical_m_s is not None and eta_cstar_design > 0.0:
        c_star_design_m_s = eta_cstar_design * c_star_theoretical_m_s

    chamber_pressure_pa = (
        inputs.chamber_pressure_pa if inputs.chamber_pressure_pa > 0.0 else None
    )
    throat_area_m2 = (
        bundle.geometry.throat_area_m2 if bundle.geometry.throat_area_m2 > 0.0 else None
    )
    throat_diameter_m = None
    if bundle.geometry.throat_radius_m > 0.0:
        throat_diameter_m = 2.0 * bundle.geometry.throat_radius_m

    try:
        cf_design = select_reference_thrust_coefficient(
            bundle.thermochemistry,
            inputs.ambient_pressure_pa,
        )
    except ValueError:
        cf_design = None

    mass_flow_kg_per_s = None
    if (
        chamber_pressure_pa is not None
        and throat_area_m2 is not None
        and c_star_design_m_s is not None
        and c_star_design_m_s > 0.0
    ):
        mass_flow_kg_per_s = chamber_pressure_pa * throat_area_m2 / c_star_design_m_s

    thrust_estimate_n = None
    if (
        cf_design is not None
        and chamber_pressure_pa is not None
        and throat_area_m2 is not None
    ):
        # In the compact pre-design preview we let c* efficiency act as a direct
        # delivered-performance loss on the force estimate, while geometry stays fixed.
        thrust_estimate_n = eta_cstar_design * cf_design * chamber_pressure_pa * throat_area_m2

    thrust_deviation_percent = None
    if (
        thrust_estimate_n is not None
        and inputs.thrust_n > 0.0
    ):
        thrust_deviation_percent = (
            (thrust_estimate_n - inputs.thrust_n) / inputs.thrust_n
        ) * 100.0

    return PerformancePreviewResult(
        c_star_theoretical_m_s=c_star_theoretical_m_s,
        eta_cstar_design=eta_cstar_design,
        c_star_design_m_s=c_star_design_m_s,
        chamber_pressure_pa=chamber_pressure_pa,
        throat_area_m2=throat_area_m2,
        throat_diameter_m=throat_diameter_m,
        cf_design=cf_design,
        isp_vac_s=bundle.thermochemistry.isp_vac_s,
        isp_sl_s=bundle.thermochemistry.isp_amb_s,
        mass_flow_kg_per_s=mass_flow_kg_per_s,
        thrust_estimate_n=thrust_estimate_n,
        thrust_deviation_percent=thrust_deviation_percent,
        expansion_ratio=bundle.geometry.current_expansion_ratio,
    )
