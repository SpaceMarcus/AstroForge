"""FreeCAD-owned worker process for AstraForge STEP construction."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import FreeCAD
import Mesh
import Part

_M_TO_FREECAD_MM = 1_000.0


def _revolved_volume(profile):
    points = [
        FreeCAD.Vector(
            _M_TO_FREECAD_MM * row["x_m"],
            _M_TO_FREECAD_MM * row["radius_m"],
            0.0,
        )
        for row in profile
    ]
    points.extend(
        [
            FreeCAD.Vector(_M_TO_FREECAD_MM * profile[-1]["x_m"], 0.0, 0.0),
            FreeCAD.Vector(_M_TO_FREECAD_MM * profile[0]["x_m"], 0.0, 0.0),
            points[0],
        ]
    )
    wire = Part.makePolygon(points)
    return Part.Face(wire).revolve(
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(1.0, 0.0, 0.0),
        360.0,
    )


def _revolved_liner(inner, outer):
    points = [
        FreeCAD.Vector(
            _M_TO_FREECAD_MM * row["x_m"],
            _M_TO_FREECAD_MM * row["radius_m"],
            0.0,
        )
        for row in inner
    ]
    points.extend(
        FreeCAD.Vector(
            _M_TO_FREECAD_MM * row["x_m"],
            _M_TO_FREECAD_MM * row["radius_m"],
            0.0,
        )
        for row in reversed(outer)
    )
    points.append(points[0])
    return Part.Face(Part.makePolygon(points)).revolve(
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(1.0, 0.0, 0.0),
        360.0,
    )


def _loft_channel(sections):
    wires = []
    for section in sections:
        points = [
            FreeCAD.Vector(
                _M_TO_FREECAD_MM * point[0],
                _M_TO_FREECAD_MM * point[1],
                _M_TO_FREECAD_MM * point[2],
            )
            for point in section["points_xyz_m"]
        ]
        points.append(points[0])
        wires.append(Part.makePolygon(points))
    return Part.makeLoft(wires, True, False)


def _set_step_preferences(schema):
    scheme = "AP242DIS" if schema.upper().startswith("AP242") else schema.upper()
    step_preferences = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/Part/STEP"
    )
    step_preferences.SetString("Scheme", scheme)
    import_preferences = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/Import"
    )
    import_preferences.SetBool("ExpandCompound", False)


def main():
    job_path = Path(sys.argv[-1])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    output = Path(job["output_directory"])
    output.mkdir(parents=True, exist_ok=True)
    _set_step_preferences(job.get("step_schema", "AP242"))
    document = FreeCAD.newDocument("AstraForge_STEP_Assembly")
    export_objects = []
    gas_object = None
    liner_object = None
    channels_object = None

    if job["include_hot_gas_volume"]:
        gas_object = document.addObject("Part::Feature", "HotGasFluidVolume")
        gas_object.Label = "AstraForge Hot Gas Fluid Volume"
        gas_object.Shape = _revolved_volume(job["contour"])
        export_objects.append(gas_object)

    channel_shape = None
    if job["include_channel_fluid"] and job["channel_sections"]:
        representative = _loft_channel(job["channel_sections"])
        if job["full_channel_pattern"]:
            copies = []
            count = int(job["channel_count"])
            for index in range(count):
                copy = representative.copy()
                copy.rotate(
                    FreeCAD.Vector(0.0, 0.0, 0.0),
                    FreeCAD.Vector(1.0, 0.0, 0.0),
                    360.0 * index / count,
                )
                copies.append(copy)
            channel_shape = Part.makeCompound(copies)
        else:
            channel_shape = representative
        channels_object = document.addObject(
            "Part::Feature",
            "CoolingChannelFluid",
        )
        channels_object.Label = "AstraForge Cooling Channel Fluid"
        channels_object.Shape = channel_shape
        export_objects.append(channels_object)

    if job["include_liner"]:
        liner_shape = _revolved_liner(job["contour"], job["outer_profile"])
        if job["cut_channels_from_liner"] and channel_shape is not None:
            liner_shape = liner_shape.cut(channel_shape)
        liner_object = document.addObject("Part::Feature", "CooledLiner")
        liner_object.Label = "AstraForge Cooled Liner"
        liner_object.Shape = liner_shape
        export_objects.append(liner_object)

    document.recompute()
    Part.export(
        export_objects,
        str(output / "astraforge_thrust_chamber_assembly.step"),
    )
    if gas_object is not None:
        Part.export([gas_object], str(output / "astraforge_hot_gas_volume.step"))
    if liner_object is not None:
        Part.export([liner_object], str(output / "astraforge_cooled_liner.step"))
    if channels_object is not None:
        Part.export(
            [channels_object],
            str(output / "astraforge_cooling_channel_fluid.step"),
        )
    if job.get("export_stl", False):
        Mesh.export(
            export_objects,
            str(output / "astraforge_thrust_chamber_assembly.stl"),
        )
    FreeCAD.closeDocument(document.Name)


# FreeCADCmd executes a passed script in its console namespace, where
# ``__name__`` is not consistently ``"__main__"`` across releases.
main()
