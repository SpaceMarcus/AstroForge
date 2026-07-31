"""STEP B-Rep export through the locally installed FreeCAD engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from engine.cooling import ChannelLayout, ChannelShape
from engine.models import ExportBundle
from engine.station_mesh import EngineStationMesh, build_engine_station_mesh


@dataclass(frozen=True, slots=True)
class StepExportOptions:
    """Objects and channel representation written to the STEP package."""

    include_hot_gas_volume: bool = True
    include_liner: bool = True
    include_channel_fluid: bool = True
    full_channel_pattern: bool = True
    cut_channels_from_liner: bool = True
    max_channel_sections: int = 48
    export_stl: bool = True
    step_schema: str = "AP214"


@dataclass(frozen=True, slots=True)
class StepExportResult:
    assembly_step: Path
    hot_gas_step: Path | None
    liner_step: Path | None
    channel_fluid_step: Path | None
    assembly_stl: Path | None
    manifest_json: Path
    freecad_command: Path
    channel_representation: str
    actual_step_schema: str


def find_freecad_command() -> Path | None:
    """Find FreeCADCmd without requiring a Python CAD wheel."""

    executable = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    if executable:
        return Path(executable)
    candidates = (
        Path.home()
        / "AppData/Local/Programs/FreeCAD/FreeCAD_1.1.1-Windows-x86_64-py311/FreeCADCmd.exe",
        Path("C:/Program Files/FreeCAD 1.0/bin/FreeCADCmd.exe"),
        Path("C:/Program Files/FreeCAD 0.21/bin/FreeCADCmd.exe"),
    )
    return next((candidate for candidate in candidates if candidate.exists()), None)


def export_step_geometry(
    bundle: ExportBundle,
    output_directory: str | Path,
    *,
    channel_layout: ChannelLayout | None = None,
    options: StepExportOptions | None = None,
    freecad_command: str | Path | None = None,
) -> StepExportResult:
    """Export named gas, liner and cooling-channel B-Reps to STEP."""

    if len(bundle.contour) < 2:
        raise ValueError("STEP export requires a committed engine contour.")
    options = options or StepExportOptions()
    command = (
        Path(freecad_command)
        if freecad_command is not None
        else find_freecad_command()
    )
    if command is None or not command.exists():
        raise RuntimeError(
            "FreeCADCmd was not found. Install FreeCAD or provide freecad_command."
        )
    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    mesh = build_engine_station_mesh(bundle.contour)
    job = _build_step_job(bundle, mesh, output_dir, channel_layout, options)
    worker = Path(__file__).with_name("freecad_step_worker.py")
    with tempfile.TemporaryDirectory(prefix="astraforge-step-") as temporary:
        job_path = Path(temporary) / "step_job.json"
        job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
        completed = subprocess.run(
            [str(command), str(worker), str(job_path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"FreeCAD STEP export failed: {details}")
    expected = {
        "assembly": output_dir / "astraforge_thrust_chamber_assembly.step",
        "gas": output_dir / "astraforge_hot_gas_volume.step",
        "liner": output_dir / "astraforge_cooled_liner.step",
        "channels": output_dir / "astraforge_cooling_channel_fluid.step",
        "assembly_stl": output_dir / "astraforge_thrust_chamber_assembly.stl",
    }
    if not expected["assembly"].exists():
        raise RuntimeError("FreeCAD completed without writing the STEP assembly.")
    actual_schema = _detect_step_schema(expected["assembly"])
    manifest_path = output_dir / "astraforge_step_manifest.json"
    channel_representation = job["channel_representation"]
    manifest = {
        "format": "STEP",
        "requested_schema": options.step_schema,
        "actual_schema": actual_schema,
        "coordinate_system": "right-handed Cartesian; engine axis +X; SI metres",
        "source_generated_at_utc": bundle.generated_at_utc,
        "objects": {
            "assembly": str(expected["assembly"].name),
            "hot_gas_volume": (
                str(expected["gas"].name) if expected["gas"].exists() else None
            ),
            "cooled_liner": (
                str(expected["liner"].name) if expected["liner"].exists() else None
            ),
            "cooling_channel_fluid": (
                str(expected["channels"].name)
                if expected["channels"].exists()
                else None
            ),
            "assembly_stl": (
                str(expected["assembly_stl"].name)
                if expected["assembly_stl"].exists()
                else None
            ),
        },
        "channel_representation": channel_representation,
        "options": asdict(options),
        "notes": job["notes"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return StepExportResult(
        assembly_step=expected["assembly"],
        hot_gas_step=expected["gas"] if expected["gas"].exists() else None,
        liner_step=expected["liner"] if expected["liner"].exists() else None,
        channel_fluid_step=(
            expected["channels"] if expected["channels"].exists() else None
        ),
        assembly_stl=(
            expected["assembly_stl"] if expected["assembly_stl"].exists() else None
        ),
        manifest_json=manifest_path,
        freecad_command=command,
        channel_representation=channel_representation,
        actual_step_schema=actual_schema,
    )


def _build_step_job(
    bundle: ExportBundle,
    mesh: EngineStationMesh,
    output_dir: Path,
    layout: ChannelLayout | None,
    options: StepExportOptions,
) -> dict[str, object]:
    contour = [
        {"x_m": point.x_m, "radius_m": point.radius_m}
        for point in bundle.contour
    ]
    liner_thickness = bundle.inputs.wall_thickness_m or 0.0015
    outer_profile: list[dict[str, float]] = []
    channel_sections: list[dict[str, object]] = []
    channel_count = 0
    constant_count = True
    rotation_rad = 0.0
    previous_station = None
    previous_section = None
    counts: list[int] = []
    if options.max_channel_sections < 2:
        raise ValueError("STEP channel loft requires at least two section stations.")
    selected_channel_indices = _selected_channel_station_indices(
        mesh,
        options.max_channel_sections,
    )

    for station in mesh.stations:
        if layout is None:
            radial_build = liner_thickness
            outer_profile.append(
                {
                    "x_m": station.x_m,
                    "radius_m": station.inner_radius_m + radial_build,
                }
            )
            continue
        section = layout.section_at(station.s_m)
        counts.append(section.channel_count)
        radial_extent = _section_radial_extent_m(section.cross_section)
        radial_build = (
            section.hot_wall_thickness_m
            + radial_extent
            + section.closeout_thickness_m
        )
        outer_profile.append(
            {
                "x_m": station.x_m,
                "radius_m": station.inner_radius_m + radial_build,
            }
        )
        if previous_station is not None and previous_section is not None:
            ds = station.s_m - previous_station.s_m
            mean_radius = 0.5 * (
                station.inner_radius_m
                + previous_station.inner_radius_m
                + section.hot_wall_thickness_m
                + previous_section.hot_wall_thickness_m
                + 0.5
                * (
                    radial_extent
                    + _section_radial_extent_m(previous_section.cross_section)
                )
            )
            mean_helix = 0.5 * (
                section.helix_angle_deg + previous_section.helix_angle_deg
            )
            rotation_rad += (
                math.tan(math.radians(mean_helix)) * ds / max(mean_radius, 1.0e-9)
            )
        if station.index in selected_channel_indices:
            polygon = _section_polygon_m(section.cross_section)
            channel_sections.append(
                {
                    "station_id": station.station_id,
                    "points_xyz_m": _transform_section_polygon(
                        mesh,
                        station.index,
                        polygon,
                        rotation_rad,
                        section.hot_wall_thickness_m,
                        section.helix_angle_deg,
                    ),
                }
            )
        previous_station = station
        previous_section = section

    if counts:
        channel_count = counts[0]
        constant_count = len(set(counts)) == 1
    full_pattern = (
        layout is not None
        and options.include_channel_fluid
        and options.full_channel_pattern
        and constant_count
    )
    representation = (
        f"full circumferential pattern ({channel_count} channels)"
        if full_pattern
        else "single representative channel"
        if layout is not None and options.include_channel_fluid
        else "not exported"
    )
    notes: list[str] = []
    if layout is not None and options.full_channel_pattern and not constant_count:
        notes.append(
            "Variable channel count cannot form one continuous patterned solid; "
            "a representative channel was exported."
        )
    notes.append(
        "Channel sections follow the canonical geometry and helix path; "
        "manifold/collector solids are not yet included."
    )
    return {
        "output_directory": str(output_dir.resolve()),
        "contour": contour,
        "outer_profile": outer_profile,
        "channel_sections": channel_sections,
        "channel_count": channel_count,
        "full_channel_pattern": full_pattern,
        "channel_representation": representation,
        "include_hot_gas_volume": options.include_hot_gas_volume,
        "include_liner": options.include_liner,
        "include_channel_fluid": options.include_channel_fluid and layout is not None,
        "cut_channels_from_liner": (
            options.cut_channels_from_liner and full_pattern
        ),
        "step_schema": options.step_schema,
        "export_stl": options.export_stl,
        "notes": notes,
    }


def _section_radial_extent_m(section) -> float:
    if section.height_m is not None:
        return section.height_m
    if section.diameter_m is not None:
        return section.diameter_m
    if section.polygon_points_m:
        return max(point[1] for point in section.polygon_points_m) - min(
            point[1] for point in section.polygon_points_m
        )
    raise ValueError("Channel section has no radial extent.")


def _selected_channel_station_indices(
    mesh: EngineStationMesh,
    maximum: int,
) -> set[int]:
    station_count = len(mesh.stations)
    if station_count <= maximum:
        return set(range(station_count))
    indices = {
        round(index * (station_count - 1) / (maximum - 1))
        for index in range(maximum)
    }
    throat_index = min(
        range(station_count),
        key=lambda index: mesh.stations[index].area_m2,
    )
    indices.add(throat_index)
    return indices


def _section_polygon_m(section) -> tuple[tuple[float, float], ...]:
    shape = section.shape
    if shape in {ChannelShape.RECTANGULAR, ChannelShape.ROUNDED_RECTANGULAR}:
        width, height = section._width_height()
        if shape is ChannelShape.ROUNDED_RECTANGULAR and section.corner_radius_m > 0.0:
            return _rounded_rectangle_points(
                width,
                height,
                section.corner_radius_m,
            )
        return (
            (-0.5 * width, 0.0),
            (0.5 * width, 0.0),
            (0.5 * width, height),
            (-0.5 * width, height),
        )
    if shape is ChannelShape.TRAPEZOIDAL:
        top, bottom, height = section._trapezoid_dimensions()
        return (
            (-0.5 * bottom, 0.0),
            (0.5 * bottom, 0.0),
            (0.5 * top, height),
            (-0.5 * top, height),
        )
    if shape is ChannelShape.CIRCULAR:
        diameter = section._diameter()
        radius = 0.5 * diameter
        return tuple(
            (
                radius * math.cos(angle),
                radius + radius * math.sin(angle),
            )
            for angle in _angles(32)
        )
    if shape is ChannelShape.SEMICIRCULAR:
        diameter = section._diameter()
        radius = 0.5 * diameter
        return (
            (-radius, 0.0),
            *tuple(
                (
                    radius * math.cos(angle),
                    radius * math.sin(angle),
                )
                for angle in [math.pi - index * math.pi / 16.0 for index in range(17)]
            ),
        )
    if shape is ChannelShape.RACETRACK:
        width, height = section._width_height()
        radius = 0.5 * height
        straight = 0.5 * (width - height)
        points = []
        for index in range(17):
            angle = -0.5 * math.pi + index * math.pi / 16.0
            points.append(
                (straight + radius * math.cos(angle), radius + radius * math.sin(angle))
            )
        for index in range(17):
            angle = 0.5 * math.pi + index * math.pi / 16.0
            points.append(
                (-straight + radius * math.cos(angle), radius + radius * math.sin(angle))
            )
        return tuple(points)
    if shape is ChannelShape.CUSTOM_POLYGON:
        points = section.polygon_points_m
        minimum_v = min(point[1] for point in points)
        center_u = 0.5 * (
            min(point[0] for point in points) + max(point[0] for point in points)
        )
        return tuple((u - center_u, v - minimum_v) for u, v in points)
    raise ValueError(f"Unsupported channel shape: {shape}")


def _rounded_rectangle_points(
    width: float,
    height: float,
    radius: float,
) -> tuple[tuple[float, float], ...]:
    points = []
    centers = (
        (0.5 * width - radius, radius, -0.5 * math.pi),
        (0.5 * width - radius, height - radius, 0.0),
        (-0.5 * width + radius, height - radius, 0.5 * math.pi),
        (-0.5 * width + radius, radius, math.pi),
    )
    for center_u, center_v, start in centers:
        for index in range(5):
            angle = start + index * 0.5 * math.pi / 4.0
            points.append(
                (
                    center_u + radius * math.cos(angle),
                    center_v + radius * math.sin(angle),
                )
            )
    return tuple(points)


def _angles(count: int) -> tuple[float, ...]:
    return tuple(2.0 * math.pi * index / count for index in range(count))


def _transform_section_polygon(
    mesh: EngineStationMesh,
    station_index: int,
    polygon: tuple[tuple[float, float], ...],
    rotation_rad: float,
    hot_wall_thickness_m: float,
    helix_angle_deg: float,
) -> list[list[float]]:
    station = mesh.stations[station_index]
    left = mesh.stations[max(0, station_index - 1)]
    right = mesh.stations[min(len(mesh.stations) - 1, station_index + 1)]
    dx = right.x_m - left.x_m
    dr = right.inner_radius_m - left.inner_radius_m
    magnitude = math.hypot(dx, dr)
    tangent_x = dx / magnitude
    tangent_r = dr / magnitude
    cos_theta = math.cos(rotation_rad)
    sin_theta = math.sin(rotation_rad)
    radial = (0.0, cos_theta, sin_theta)
    circumferential = (0.0, -sin_theta, cos_theta)
    normal = (-tangent_r, tangent_x * cos_theta, tangent_x * sin_theta)
    helix_angle = math.radians(helix_angle_deg)
    path_tangent = _normalize(
        (
            math.cos(helix_angle) * tangent_x,
            math.cos(helix_angle) * tangent_r * cos_theta
            + math.sin(helix_angle) * circumferential[1],
            math.cos(helix_angle) * tangent_r * sin_theta
            + math.sin(helix_angle) * circumferential[2],
        )
    )
    width_axis = _normalize(_cross(path_tangent, normal))
    base = (
        station.x_m + hot_wall_thickness_m * normal[0],
        station.inner_radius_m * radial[1] + hot_wall_thickness_m * normal[1],
        station.inner_radius_m * radial[2] + hot_wall_thickness_m * normal[2],
    )
    return [
        [
            base[0] + u * width_axis[0] + v * normal[0],
            base[1] + u * width_axis[1] + v * normal[1],
            base[2] + u * width_axis[2] + v * normal[2],
        ]
        for u, v in polygon
    ]


def _cross(first, second):
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _normalize(vector):
    magnitude = math.sqrt(sum(component**2 for component in vector))
    if magnitude <= 0.0:
        raise ValueError("Cannot normalize a zero CAD direction vector.")
    return tuple(component / magnitude for component in vector)


def _detect_step_schema(path: Path) -> str:
    header = path.read_text(encoding="utf-8", errors="ignore")[:4_096].upper()
    if "10303 242" in header or "AP242" in header:
        return "AP242"
    if "10303 214" in header or "AUTOMOTIVE_DESIGN" in header:
        return "AP214"
    if "10303 203" in header or "CONFIG_CONTROL_DESIGN" in header:
        return "AP203"
    return "unknown"
