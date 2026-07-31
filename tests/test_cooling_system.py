"""Tests for multiple regenerative circuits and axial cooling segments."""

from __future__ import annotations

import math

import pytest

from engine.cooling import (
    AxialProfile,
    ChannelLayout,
    ChannelShape,
    CoolantCircuit,
    CoolingMechanism,
    CoolingSegment,
    RegenerativeCircuitPath,
    march_cooling_system,
)
from engine.models import NozzlePoint
from engine.station_mesh import build_engine_station_mesh


def _mesh():
    return build_engine_station_mesh(
        [
            NozzlePoint(x_m=0.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
            NozzlePoint(x_m=0.5, radius_m=0.1, area_m2=math.pi * 0.1**2),
            NozzlePoint(x_m=1.0, radius_m=0.1, area_m2=math.pi * 0.1**2),
        ]
    )


def _layout() -> ChannelLayout:
    return ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(100.0),
        width_m=AxialProfile.constant(0.002),
        height_m=AxialProfile.constant(0.003),
    )


def _path(path_id: str, start: float, end: float, fraction: float = 1.0):
    circuit = CoolantCircuit(
        circuit_id=f"circuit-{path_id}",
        coolant_id="water",
        mass_flow_kg_per_s=1.0,
        inlet_temperature_k=300.0,
        inlet_pressure_pa=20.0e6,
        opposite_hot_gas_flow=False,
    )
    segment = CoolingSegment(
        segment_id=f"segment-{path_id}",
        s_start_m=start,
        s_end_m=end,
        mechanisms=(CoolingMechanism.REGENERATIVE_CHANNELS,),
        circuit_id=circuit.circuit_id,
    )
    return RegenerativeCircuitPath(
        path_id=path_id,
        circuit=circuit,
        segment=segment,
        layout=_layout(),
        heat_load_fraction=fraction,
    )


def test_two_axial_circuits_cover_disjoint_segments() -> None:
    result = march_cooling_system(
        _mesh(),
        (_path("upstream", 0.0, 0.5), _path("downstream", 0.5, 1.0)),
        hot_wall_heat_flux_w_per_m2=1.0e5,
    )

    assert len(result.path_results) == 2
    assert result.total_coolant_mass_flow_kg_per_s == pytest.approx(2.0)
    assert result.result_for_path("upstream").stations[-1].station.s_m == pytest.approx(0.5)
    assert result.result_for_path("downstream").stations[0].station.s_m == pytest.approx(0.5)
    assert result.total_heat_added_w == pytest.approx(1.0e5 * 2.0 * math.pi * 0.1)


def test_parallel_circuits_can_split_but_not_overassign_heat_load() -> None:
    split = march_cooling_system(
        _mesh(),
        (_path("a", 0.0, 1.0, 0.4), _path("b", 0.0, 1.0, 0.6)),
        hot_wall_heat_flux_w_per_m2=1.0e5,
    )
    assert split.total_heat_added_w == pytest.approx(1.0e5 * 2.0 * math.pi * 0.1)

    with pytest.raises(ValueError, match="more than 100%"):
        march_cooling_system(
            _mesh(),
            (_path("a", 0.0, 1.0, 0.6), _path("b", 0.0, 1.0, 0.6)),
            hot_wall_heat_flux_w_per_m2=1.0e5,
        )
