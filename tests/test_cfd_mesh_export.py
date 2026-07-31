"""Gmsh gas/channel flowfield export smoke tests."""

from __future__ import annotations

import json

import pytest

from engine.cfd import CfdMeshExportOptions, export_cfd_meshes, find_gmsh_command
from engine.cooling import AxialProfile, ChannelLayout, ChannelShape
from tests.test_step_export import _bundle


@pytest.mark.skipif(find_gmsh_command() is None, reason="Gmsh not installed")
def test_gmsh_exports_tagged_gas_and_channel_meshes(tmp_path) -> None:
    layout = ChannelLayout(
        shape=ChannelShape.RECTANGULAR,
        channel_count=AxialProfile.constant(12.0),
        width_m=AxialProfile.constant(0.002),
        height_m=AxialProfile.constant(0.003),
        hot_wall_thickness_m=AxialProfile.constant(0.001),
        closeout_thickness_m=AxialProfile.constant(0.001),
        helix_angle_deg=AxialProfile.constant(10.0),
    )
    result = export_cfd_meshes(
        _bundle(),
        tmp_path,
        channel_layout=layout,
        options=CfdMeshExportOptions(
            gas_element_size_m=0.02,
            channel_element_size_m=0.0015,
        ),
    )

    assert result.gas_msh.stat().st_size > 1_000
    assert result.gas_vtk.stat().st_size > 1_000
    assert result.channel_msh is not None and result.channel_msh.stat().st_size > 1_000
    assert result.channel_vtk is not None and result.channel_vtk.stat().st_size > 1_000
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["gas_domain"]["physical_groups"]["hot_wall"] == 103
    assert manifest["channel_domain"]["physical_groups"]["coolant_inlet"] == 202
    assert manifest["mesh_quality"]["gas"]["triangle_count"] > 0
    assert manifest["mesh_quality"]["channel"]["tetrahedron_count"] > 0
    assert manifest["mesh_quality"]["channel"]["watertight_volume_boundary"] is True
