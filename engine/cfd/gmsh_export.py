"""Gmsh flowfield export with stable CFD boundary names and manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess

from engine.cad import StepExportOptions, export_step_geometry
from engine.cooling import ChannelLayout
from engine.models import ExportBundle


@dataclass(frozen=True, slots=True)
class CfdMeshExportOptions:
    gas_element_size_m: float = 0.003
    channel_element_size_m: float = 0.0005
    mesh_channel: bool = True
    channel_inlet_at_nozzle_exit: bool = True
    optimize_channel_tetrahedra: bool = True


@dataclass(frozen=True, slots=True)
class CfdMeshExportResult:
    gas_msh: Path
    gas_vtk: Path
    channel_msh: Path | None
    channel_vtk: Path | None
    manifest_json: Path
    gas_geo: Path
    channel_geo: Path | None
    gmsh_command: Path


def find_gmsh_command() -> Path | None:
    executable = shutil.which("gmsh")
    if executable:
        return Path(executable)
    candidates = (
        Path.home()
        / "AppData/Local/Programs/Gmsh/gmsh-4.15.2-Windows64/gmsh.exe",
        Path("C:/Program Files/gmsh/gmsh.exe"),
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def export_cfd_meshes(
    bundle: ExportBundle,
    output_directory: str | Path,
    *,
    channel_layout: ChannelLayout | None = None,
    options: CfdMeshExportOptions | None = None,
    gmsh_command: str | Path | None = None,
) -> CfdMeshExportResult:
    """Write axisymmetric gas and representative 3-D channel flowfield meshes."""

    if len(bundle.contour) < 2:
        raise ValueError("CFD mesh export requires a committed engine contour.")
    options = options or CfdMeshExportOptions()
    _positive(options.gas_element_size_m, "Gas element size")
    _positive(options.channel_element_size_m, "Channel element size")
    command = (
        Path(gmsh_command) if gmsh_command is not None else find_gmsh_command()
    )
    if command is None or not command.exists():
        raise RuntimeError("Gmsh executable was not found.")
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    gas_geo = output / "gas_flowfield_2d.geo"
    gas_msh = output / "gas_flowfield_2d.msh"
    gas_vtk = output / "gas_flowfield_2d.vtk"
    gas_geo.write_text(
        _gas_geo_source(bundle, options.gas_element_size_m),
        encoding="utf-8",
    )
    _run_gmsh(command, gas_geo, dimension=2, output=gas_msh, format_name="msh41")
    _run_gmsh(command, gas_geo, dimension=2, output=gas_vtk, format_name="vtk")

    channel_msh = None
    channel_vtk = None
    channel_geo = None
    channel_step = None
    if options.mesh_channel:
        if channel_layout is None:
            raise ValueError("Channel CFD mesh export requires a channel layout.")
        cad_dir = output / "channel_cad_source"
        cad_result = export_step_geometry(
            bundle,
            cad_dir,
            channel_layout=channel_layout,
            options=StepExportOptions(
                include_hot_gas_volume=False,
                include_liner=False,
                include_channel_fluid=True,
                full_channel_pattern=False,
                cut_channels_from_liner=False,
                export_stl=False,
                max_channel_sections=32,
            ),
        )
        channel_step = cad_result.channel_fluid_step
        if channel_step is None:
            raise RuntimeError("Representative channel STEP source was not written.")
        channel_geo = output / "coolant_channel_3d.geo"
        channel_msh = output / "coolant_channel_3d.msh"
        channel_vtk = output / "coolant_channel_3d.vtk"
        x_min = min(point.x_m for point in bundle.contour)
        x_max = max(point.x_m for point in bundle.contour)
        channel_geo.write_text(
            _channel_geo_source(
                channel_step,
                x_min,
                x_max,
                options.channel_element_size_m,
                options.channel_inlet_at_nozzle_exit,
            ),
            encoding="utf-8",
        )
        extra = ["-optimize_netgen"] if options.optimize_channel_tetrahedra else []
        _run_gmsh(
            command,
            channel_geo,
            dimension=3,
            output=channel_msh,
            format_name="msh41",
            extra_arguments=extra,
        )
        _run_gmsh(
            command,
            channel_geo,
            dimension=3,
            output=channel_vtk,
            format_name="vtk",
        )

    checks = {
        "gas": _mesh_check(command, gas_msh),
        "channel": _mesh_check(command, channel_msh) if channel_msh else None,
    }
    quality = {
        "gas": _vtk_quality(gas_vtk),
        "channel": _vtk_quality(channel_vtk) if channel_vtk else None,
    }
    manifest_path = output / "astraforge_cfd_mesh_manifest.json"
    manifest = {
        "format": {
            "primary": "Gmsh MSH 4.1",
            "inspection": "legacy VTK",
        },
        "coordinate_system": "right-handed Cartesian; engine axis +X; SI metres",
        "source_generated_at_utc": bundle.generated_at_utc,
        "gas_domain": {
            "dimension": 2,
            "axisymmetric": True,
            "mesh": gas_msh.name,
            "vtk": gas_vtk.name,
            "geometry_source": gas_geo.name,
            "physical_groups": {
                "gas_flowfield": 100,
                "gas_inlet": 101,
                "axis": 102,
                "hot_wall": 103,
                "nozzle_exit": 104,
                "throat": 105,
            },
        },
        "channel_domain": (
            {
                "dimension": 3,
                "representation": "single representative channel",
                "mesh": channel_msh.name,
                "vtk": channel_vtk.name,
                "geometry_source": channel_geo.name,
                "cad_source": str(channel_step.relative_to(output)),
                "physical_groups": {
                    "coolant_volume": 200,
                    "channel_walls": 201,
                    "coolant_inlet": 202,
                    "coolant_outlet": 203,
                },
                "inlet_location": (
                    "nozzle exit"
                    if options.channel_inlet_at_nozzle_exit
                    else "injector/chamber"
                ),
            }
            if channel_msh is not None
            else None
        ),
        "options": asdict(options),
        "gmsh_checks": checks,
        "mesh_quality": quality,
        "notes": [
            "The gas mesh is an axisymmetric meridional flowfield.",
            "The channel mesh is a representative full 3-D helical coolant volume.",
            "Channel walls are grouped separately from inlet and outlet faces.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return CfdMeshExportResult(
        gas_msh=gas_msh,
        gas_vtk=gas_vtk,
        channel_msh=channel_msh,
        channel_vtk=channel_vtk,
        manifest_json=manifest_path,
        gas_geo=gas_geo,
        channel_geo=channel_geo,
        gmsh_command=command,
    )


def _gas_geo_source(bundle: ExportBundle, element_size_m: float) -> str:
    contour = bundle.contour
    lines = [
        'SetFactory("OpenCASCADE");',
        f"Mesh.CharacteristicLengthMin = {0.35 * element_size_m:.16g};",
        f"Mesh.CharacteristicLengthMax = {element_size_m:.16g};",
    ]
    # Axis points use tags 1 and 2; wall points start at 10.
    lines.append(
        f"Point(1) = {{{contour[0].x_m:.16g}, 0, 0, {element_size_m:.16g}}};"
    )
    lines.append(
        f"Point(2) = {{{contour[-1].x_m:.16g}, 0, 0, {element_size_m:.16g}}};"
    )
    wall_tags = []
    for index, point in enumerate(contour, start=10):
        wall_tags.append(index)
        lines.append(
            f"Point({index}) = {{{point.x_m:.16g}, {point.radius_m:.16g}, 0, {element_size_m:.16g}}};"
        )
    lines.extend(
        [
            "Line(1) = {1, 2};",
            f"Line(2) = {{2, {wall_tags[-1]}}};",
            f"Spline(3) = {{{', '.join(map(str, reversed(wall_tags)))}}};",
            f"Line(4) = {{{wall_tags[0]}, 1}};",
            "Curve Loop(10) = {1, 2, 3, 4};",
            "Plane Surface(20) = {10};",
            'Physical Surface("gas_flowfield", 100) = {20};',
            'Physical Curve("gas_inlet", 101) = {4};',
            'Physical Curve("axis", 102) = {1};',
            'Physical Curve("hot_wall", 103) = {3};',
            'Physical Curve("nozzle_exit", 104) = {2};',
        ]
    )
    throat_tag = wall_tags[
        min(range(len(contour)), key=lambda index: contour[index].area_m2)
    ]
    lines.append(f'Physical Point("throat", 105) = {{{throat_tag}}};')
    lines.extend(
        [
            "Mesh.Algorithm = 6;",
            "Mesh 2;",
        ]
    )
    return "\n".join(lines) + "\n"


def _channel_geo_source(
    step_path: Path,
    x_min_m: float,
    x_max_m: float,
    element_size_m: float,
    inlet_at_exit: bool,
) -> str:
    path = step_path.resolve().as_posix()
    tolerance = max(2.5 * element_size_m, 1.0e-6)
    inlet_x = x_max_m if inlet_at_exit else x_min_m
    outlet_x = x_min_m if inlet_at_exit else x_max_m
    domain_extent = max(
        abs(x_min_m),
        abs(x_max_m),
        1.0,
    )
    return f'''SetFactory("OpenCASCADE");
Geometry.OCCTargetUnit = "M";
Merge "{path}";
Mesh.CharacteristicLengthMin = {0.35 * element_size_m:.16g};
Mesh.CharacteristicLengthMax = {element_size_m:.16g};
volumes[] = Volume{{:}};
all_surfaces[] = CombinedBoundary{{ Volume{{volumes[]}}; }};
inlet_surfaces[] = Surface In BoundingBox {{{inlet_x - tolerance:.16g}, {-domain_extent:.16g}, {-domain_extent:.16g}, {inlet_x + tolerance:.16g}, {domain_extent:.16g}, {domain_extent:.16g}}};
outlet_surfaces[] = Surface In BoundingBox {{{outlet_x - tolerance:.16g}, {-domain_extent:.16g}, {-domain_extent:.16g}, {outlet_x + tolerance:.16g}, {domain_extent:.16g}, {domain_extent:.16g}}};
wall_surfaces[] = all_surfaces[];
wall_surfaces[] -= inlet_surfaces[];
wall_surfaces[] -= outlet_surfaces[];
Physical Volume("coolant_volume", 200) = {{volumes[]}};
Physical Surface("channel_walls", 201) = {{wall_surfaces[]}};
Physical Surface("coolant_inlet", 202) = {{inlet_surfaces[]}};
Physical Surface("coolant_outlet", 203) = {{outlet_surfaces[]}};
Mesh.Algorithm3D = 10;
Mesh 3;
'''


def _run_gmsh(
    command: Path,
    source: Path,
    *,
    dimension: int,
    output: Path,
    format_name: str,
    extra_arguments: list[str] | None = None,
) -> None:
    arguments = [
        str(command),
        str(source),
        f"-{dimension}",
        "-format",
        format_name,
        "-o",
        str(output),
        "-v",
        "2",
        *(extra_arguments or []),
    ]
    completed = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0 or not output.exists():
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Gmsh mesh generation failed: {details}")


def _mesh_check(command: Path, mesh: Path) -> dict[str, object]:
    completed = subprocess.run(
        [str(command), str(mesh), "-check", "-v", "3"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return {
        "passed": completed.returncode == 0 and "Error" not in output,
        "warning_count": output.count("Warning"),
        "summary": output[-4_000:],
        "size_bytes": mesh.stat().st_size,
    }


def _vtk_quality(path: Path) -> dict[str, object]:
    """Return geometry-only quality metrics from an ASCII legacy VTK mesh."""

    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    points_index = next(
        index for index, line in enumerate(lines) if line.startswith("POINTS ")
    )
    point_count = int(lines[points_index].split()[1])
    coordinate_tokens: list[str] = []
    cursor = points_index + 1
    while len(coordinate_tokens) < 3 * point_count:
        coordinate_tokens.extend(lines[cursor].split())
        cursor += 1
    coordinates = [float(value) for value in coordinate_tokens[: 3 * point_count]]
    points = [
        tuple(coordinates[index : index + 3])
        for index in range(0, len(coordinates), 3)
    ]

    cells_index = next(
        index for index, line in enumerate(lines) if line.startswith("CELLS ")
    )
    cell_count = int(lines[cells_index].split()[1])
    cell_tokens: list[str] = []
    cursor = cells_index + 1
    while cursor < len(lines) and not lines[cursor].startswith("CELL_TYPES "):
        cell_tokens.extend(lines[cursor].split())
        cursor += 1
    cells = []
    token_index = 0
    for _ in range(cell_count):
        node_count = int(cell_tokens[token_index])
        token_index += 1
        cells.append(
            tuple(
                int(value)
                for value in cell_tokens[token_index : token_index + node_count]
            )
        )
        token_index += node_count
    type_count = int(lines[cursor].split()[1])
    type_tokens: list[str] = []
    cursor += 1
    while len(type_tokens) < type_count:
        type_tokens.extend(lines[cursor].split())
        cursor += 1
    cell_types = [int(value) for value in type_tokens[:type_count]]

    triangle_areas: list[float] = []
    tetra_volumes: list[float] = []
    edge_aspect_ratios: list[float] = []
    tetra_faces: dict[tuple[int, int, int], int] = {}
    for cell, cell_type in zip(cells, cell_types):
        if cell_type == 5 and len(cell) == 3:
            triangle_areas.append(_triangle_area(*(points[index] for index in cell)))
            edge_aspect_ratios.append(
                _edge_aspect_ratio(tuple(points[index] for index in cell))
            )
        elif cell_type == 10 and len(cell) == 4:
            tetra_volumes.append(_tetra_volume(*(points[index] for index in cell)))
            edge_aspect_ratios.append(
                _edge_aspect_ratio(tuple(points[index] for index in cell))
            )
            for face in (
                (cell[0], cell[1], cell[2]),
                (cell[0], cell[1], cell[3]),
                (cell[0], cell[2], cell[3]),
                (cell[1], cell[2], cell[3]),
            ):
                key = tuple(sorted(face))
                tetra_faces[key] = tetra_faces.get(key, 0) + 1
    watertight = None
    if tetra_faces:
        boundary_faces = [face for face, count in tetra_faces.items() if count == 1]
        boundary_edges: dict[tuple[int, int], int] = {}
        for face in boundary_faces:
            for edge in (
                (face[0], face[1]),
                (face[1], face[2]),
                (face[2], face[0]),
            ):
                key = tuple(sorted(edge))
                boundary_edges[key] = boundary_edges.get(key, 0) + 1
        watertight = all(count == 2 for count in boundary_edges.values())
    return {
        "point_count": point_count,
        "cell_count": cell_count,
        "triangle_count": len(triangle_areas),
        "tetrahedron_count": len(tetra_volumes),
        "minimum_triangle_area_m2": min(triangle_areas) if triangle_areas else None,
        "maximum_triangle_area_m2": max(triangle_areas) if triangle_areas else None,
        "minimum_tetrahedron_volume_m3": min(tetra_volumes) if tetra_volumes else None,
        "maximum_tetrahedron_volume_m3": max(tetra_volumes) if tetra_volumes else None,
        "minimum_edge_aspect_ratio": (
            min(edge_aspect_ratios) if edge_aspect_ratios else None
        ),
        "maximum_edge_aspect_ratio": (
            max(edge_aspect_ratios) if edge_aspect_ratios else None
        ),
        "watertight_volume_boundary": watertight,
    }


def _triangle_area(first, second, third) -> float:
    cross = _cross(_subtract(second, first), _subtract(third, first))
    return 0.5 * math.sqrt(sum(component**2 for component in cross))


def _tetra_volume(first, second, third, fourth) -> float:
    first_edge = _subtract(second, first)
    second_edge = _subtract(third, first)
    third_edge = _subtract(fourth, first)
    cross = _cross(second_edge, third_edge)
    return abs(sum(a * b for a, b in zip(first_edge, cross))) / 6.0


def _edge_aspect_ratio(points) -> float:
    lengths = [
        math.dist(first, second)
        for index, first in enumerate(points)
        for second in points[index + 1 :]
    ]
    return max(lengths) / max(min(lengths), 1.0e-30)


def _subtract(first, second):
    return tuple(a - b for a, b in zip(first, second))


def _cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and greater than zero.")
