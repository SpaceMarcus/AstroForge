"""Tests for the canonical variable cooling-channel geometry."""

from __future__ import annotations

import math

import pytest

from engine.cooling import (
    AxialKeyframe,
    AxialProfile,
    ChannelCrossSection,
    ChannelLayout,
    ChannelShape,
    CoolantCircuit,
    CoolingMechanism,
    CoolingSegment,
    FilmCoolingSlot,
    InterpolationMode,
)
from engine.cooling.models import validate_cooling_layout
from engine.models import NozzlePoint
from engine.station_mesh import build_engine_station_mesh


def test_axial_profile_supports_linear_and_step_variation() -> None:
    linear = AxialProfile(
        (AxialKeyframe(0.0, 1.0), AxialKeyframe(1.0, 3.0))
    )
    step = AxialProfile(
        (AxialKeyframe(0.0, 10.0), AxialKeyframe(1.0, 20.0)),
        interpolation=InterpolationMode.STEP,
    )

    assert linear.evaluate(0.25) == pytest.approx(1.5)
    assert linear.evaluate(2.0) == 3.0
    assert step.evaluate(0.75) == 10.0


@pytest.mark.parametrize(
    ("section", "expected_area"),
    [
        (
            ChannelCrossSection(
                ChannelShape.RECTANGULAR,
                width_m=0.002,
                height_m=0.003,
            ),
            6.0e-6,
        ),
        (
            ChannelCrossSection(
                ChannelShape.TRAPEZOIDAL,
                top_width_m=0.0015,
                bottom_width_m=0.0025,
                height_m=0.003,
            ),
            6.0e-6,
        ),
        (
            ChannelCrossSection(
                ChannelShape.CIRCULAR,
                diameter_m=0.002,
            ),
            math.pi * 1.0e-6,
        ),
        (
            ChannelCrossSection(
                ChannelShape.RACETRACK,
                width_m=0.004,
                height_m=0.002,
            ),
            4.0e-6 + math.pi * 1.0e-6,
        ),
    ],
)
def test_channel_cross_sections_have_expected_area(
    section: ChannelCrossSection,
    expected_area: float,
) -> None:
    assert section.area_m2() == pytest.approx(expected_area)
    assert section.wetted_perimeter_m() > 0.0
    assert section.hydraulic_diameter_m() > 0.0


def test_custom_polygon_geometry() -> None:
    section = ChannelCrossSection(
        ChannelShape.CUSTOM_POLYGON,
        polygon_points_m=((0.0, 0.0), (0.002, 0.0), (0.002, 0.003), (0.0, 0.003)),
    )

    assert section.area_m2() == pytest.approx(6.0e-6)
    assert section.wetted_perimeter_m() == pytest.approx(0.010)


def test_variable_channel_layout_resolves_helix_and_total_flow_area() -> None:
    layout = ChannelLayout(
        shape=ChannelShape.ROUNDED_RECTANGULAR,
        channel_count=AxialProfile(
            (AxialKeyframe(0.0, 80.0), AxialKeyframe(1.0, 100.0)),
            interpolation=InterpolationMode.STEP,
        ),
        width_m=AxialProfile(
            (AxialKeyframe(0.0, 0.002), AxialKeyframe(1.0, 0.0015))
        ),
        height_m=AxialProfile(
            (AxialKeyframe(0.0, 0.003), AxialKeyframe(1.0, 0.002))
        ),
        corner_radius_m=AxialProfile.constant(0.0003, minimum_value=0.0),
        helix_angle_deg=AxialProfile(
            (AxialKeyframe(0.0, 0.0), AxialKeyframe(1.0, 30.0)),
            minimum_value=-80.0,
            maximum_value=80.0,
        ),
    )

    section = layout.section_at(0.5)

    assert section.channel_count == 80
    assert section.total_flow_area_m2 == pytest.approx(
        section.channel_count * section.single_channel_area_m2
    )
    assert section.helix_angle_deg == pytest.approx(15.0)
    assert section.helical_length_multiplier == pytest.approx(
        1.0 / math.cos(math.radians(15.0))
    )


def test_cooling_layout_validates_circuits_segments_and_film_slots() -> None:
    circuit = CoolantCircuit(
        circuit_id="fuel-main",
        coolant_id="RP-1",
        mass_flow_kg_per_s=2.0,
        inlet_temperature_k=290.0,
        inlet_pressure_pa=12.0e6,
    )
    segment = CoolingSegment(
        segment_id="regen-1",
        s_start_m=0.0,
        s_end_m=1.2,
        mechanisms=(
            CoolingMechanism.REGENERATIVE_CHANNELS,
            CoolingMechanism.FILM,
        ),
        circuit_id="fuel-main",
    )
    slot = FilmCoolingSlot(
        slot_id="film-1",
        s_m=0.4,
        circuit_id="fuel-main",
        mass_flow_kg_per_s=0.05,
        slot_height_m=0.0005,
        injection_angle_deg=25.0,
    )

    validated = validate_cooling_layout(
        circuits=[circuit],
        segments=[segment],
        film_slots=[slot],
        contour_length_m=1.5,
    )

    assert validated == (circuit,)


def test_engine_station_mesh_has_stable_ids_and_geometry() -> None:
    contour = [
        NozzlePoint(x_m=-0.2, radius_m=0.10, area_m2=math.pi * 0.10**2),
        NozzlePoint(x_m=0.0, radius_m=0.05, area_m2=math.pi * 0.05**2),
        NozzlePoint(x_m=0.3, radius_m=0.15, area_m2=math.pi * 0.15**2),
    ]

    mesh = build_engine_station_mesh(contour)

    assert [station.station_id for station in mesh.stations] == [
        "STA-00000",
        "STA-00001",
        "STA-00002",
    ]
    assert mesh.stations[1].region == "throat"
    assert mesh.contour_length_m > 0.5
    assert mesh.nearest_to_s(mesh.stations[1].s_m).station_id == "STA-00001"
