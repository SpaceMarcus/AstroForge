"""Integration smoke test for the local FreeCAD STEP exporter."""

from __future__ import annotations

import math

import pytest

from engine.cad import (
    StepExportOptions,
    export_step_geometry,
    find_freecad_command,
)
from engine.cooling import AxialProfile, ChannelLayout, ChannelShape
from engine.models import (
    ChemistryMode,
    ExportBundle,
    GeometryResult,
    InputParameters,
    NozzlePoint,
    ThermochemistryResult,
)


def _bundle() -> ExportBundle:
    inputs = InputParameters(
        fuel="RP-1",
        oxidizer="LOX",
        chamber_pressure_pa=7.0e6,
        thrust_n=100_000.0,
        mixture_ratio=2.6,
        expansion_ratio=4.0,
        ambient_pressure_pa=101_325.0,
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        wall_thickness_m=0.001,
    )
    thermo = ThermochemistryResult(
        chemistry_mode=ChemistryMode.EQUILIBRIUM,
        propellant_description="test",
        chamber_temperature_k=3_500.0,
        c_star_m_s=1_750.0,
        isp_vac_s=300.0,
    )
    geometry = GeometryResult(
        throat_area_m2=math.pi * 0.05**2,
        throat_radius_m=0.05,
        exit_area_m2=math.pi * 0.10**2,
        exit_radius_m=0.10,
        mass_flow_kg_per_s=10.0,
    )
    contour = [
        NozzlePoint(x_m=0.0, radius_m=0.08, area_m2=math.pi * 0.08**2),
        NozzlePoint(x_m=0.1, radius_m=0.05, area_m2=math.pi * 0.05**2),
        NozzlePoint(x_m=0.3, radius_m=0.10, area_m2=math.pi * 0.10**2),
    ]
    return ExportBundle(inputs, thermo, geometry, contour)


@pytest.mark.skipif(find_freecad_command() is None, reason="FreeCADCmd not installed")
def test_freecad_exports_named_step_parts(tmp_path) -> None:
    layout = ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(12.0),
        width_m=AxialProfile.constant(0.002),
        height_m=AxialProfile.constant(0.003),
        hot_wall_thickness_m=AxialProfile.constant(0.001),
        closeout_thickness_m=AxialProfile.constant(0.001),
        helix_angle_deg=AxialProfile.constant(15.0),
    )

    result = export_step_geometry(
        _bundle(),
        tmp_path,
        channel_layout=layout,
        options=StepExportOptions(
            full_channel_pattern=False,
            cut_channels_from_liner=False,
        ),
    )

    assert result.assembly_step.read_text(
        encoding="utf-8",
        errors="ignore",
    ).startswith("ISO-10303-21")
    assert result.actual_step_schema == "AP214"
    assert result.hot_gas_step is not None and result.hot_gas_step.stat().st_size > 1_000
    assert result.liner_step is not None and result.liner_step.stat().st_size > 1_000
    assert (
        result.channel_fluid_step is not None
        and result.channel_fluid_step.stat().st_size > 1_000
    )
    assert result.assembly_stl is not None and result.assembly_stl.stat().st_size > 1_000
    assert result.manifest_json.exists()
