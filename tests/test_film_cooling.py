"""Equation and marching tests for gaseous and liquid film cooling."""

from __future__ import annotations

import math

import pytest

from engine.cooling import (
    FilmCoolingInputs,
    FilmCoolingSlot,
    FilmPhase,
    gaseous_film_mixing_fraction,
    gaseous_film_mixing_weights,
    march_film_cooling,
)
from engine.models import NozzlePoint
from engine.station_mesh import build_engine_station_mesh


def _mesh() -> object:
    return build_engine_station_mesh(
        [
            NozzlePoint(x_m=0.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
            NozzlePoint(x_m=0.5, radius_m=0.1, area_m2=math.pi * 0.1**2),
            NozzlePoint(x_m=1.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
        ]
    )


def test_rpa_gaseous_film_mixing_law_and_weights() -> None:
    fraction = gaseous_film_mixing_fraction(
        0.01,
        turbulent_mixing_coefficient=0.001,
        surface_layer_mass_flow_kg_per_s=1.0,
        film_mass_flow_kg_per_s=0.1,
        surface_layer_thickness_m=0.005,
    )

    assert fraction == pytest.approx(1.0 - math.exp(-0.04))
    weights = gaseous_film_mixing_weights(
        fraction,
        surface_layer_mass_flow_kg_per_s=1.0,
        film_mass_flow_kg_per_s=0.1,
    )
    assert (
        weights.k_surface_from_surface + weights.k_surface_from_film
    ) == pytest.approx(1.0)
    assert weights.k_film_from_surface + weights.k_film_from_film == pytest.approx(1.0)


def test_gaseous_film_shields_convection_at_injection_and_mixes_downstream() -> None:
    slot = FilmCoolingSlot(
        slot_id="gas-film",
        s_m=0.0,
        circuit_id="film",
        mass_flow_kg_per_s=0.1,
        slot_height_m=0.0005,
        injection_angle_deg=20.0,
        liquid=False,
    )
    inputs = FilmCoolingInputs(
        slot=slot,
        injection_temperature_k=300.0,
        coolant_cp_j_per_kg_k=2_000.0,
        coolant_viscosity_pa_s=1.0e-5,
        surface_layer_mass_flow_kg_per_s=1.0,
        surface_layer_thickness_m=0.02,
    )

    result = march_film_cooling(
        _mesh(),
        inputs,
        convective_heat_flux_w_per_m2=1.0e6,
        radiation_heat_flux_w_per_m2=1.0e5,
    )

    assert result.stations[0].wall_heat_flux_w_per_m2 == pytest.approx(1.0e5)
    assert result.stations[-1].mixing_fraction > result.stations[0].mixing_fraction
    assert result.stations[-1].wall_heat_flux_w_per_m2 > 1.0e5
    assert result.stations[-1].wall_heat_flux_w_per_m2 < 1.1e6


def test_liquid_film_heats_then_vaporizes_by_energy_balance() -> None:
    slot = FilmCoolingSlot(
        slot_id="liquid-film",
        s_m=0.0,
        circuit_id="film",
        mass_flow_kg_per_s=0.01,
        slot_height_m=0.0005,
        injection_angle_deg=20.0,
        liquid=True,
    )
    inputs = FilmCoolingInputs(
        slot=slot,
        injection_temperature_k=300.0,
        coolant_cp_j_per_kg_k=1_000.0,
        coolant_viscosity_pa_s=1.0e-3,
        surface_layer_mass_flow_kg_per_s=1.0,
        surface_layer_thickness_m=0.02,
        vaporization_temperature_k=310.0,
        latent_heat_j_per_kg=10_000.0,
    )

    result = march_film_cooling(
        _mesh(),
        inputs,
        convective_heat_flux_w_per_m2=1.0e6,
        radiation_heat_flux_w_per_m2=2.0e4,
    )

    assert result.total_heat_absorbed_by_film_w == pytest.approx(200.0)
    assert result.liquid_depletion_s_m == pytest.approx(0.5)
    assert result.stations[1].phase is FilmPhase.GASEOUS_MIXING
    assert result.stations[1].liquid_mass_flow_kg_per_s == 0.0
    assert result.stations[1].gaseous_film_mass_flow_kg_per_s == pytest.approx(0.01)
    assert result.stations[0].wall_heat_flux_w_per_m2 == pytest.approx(2.0e4)
