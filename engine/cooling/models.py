"""Geometry-first cooling models for variable regenerative and film cooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Iterable


class InterpolationMode(str, Enum):
    """How a stationwise scalar profile is evaluated."""

    STEP = "step"
    LINEAR = "linear"


class ChannelShape(str, Enum):
    """Supported coolant-channel cross-section families."""

    RECTANGULAR = "rectangular"
    TRAPEZOIDAL = "trapezoidal"
    ROUNDED_RECTANGULAR = "rounded-rectangular"
    SEMICIRCULAR = "semicircular"
    CIRCULAR = "circular"
    RACETRACK = "racetrack"
    CUSTOM_POLYGON = "custom-polygon"


class CoolingMechanism(str, Enum):
    """Cooling mechanisms assignable to an axial segment."""

    REGENERATIVE_CHANNELS = "regenerative-channels"
    ANNULUS = "annulus"
    TUBULAR_WALL = "tubular-wall"
    COAXIAL_SHELL = "coaxial-shell"
    RADIATION = "radiation"
    FILM = "film"
    ABLATIVE = "ablative"
    UNCOOLED = "uncooled"


@dataclass(frozen=True, slots=True)
class AxialKeyframe:
    """One value at a hot-wall arc-length coordinate."""

    s_m: float
    value: float

    def __post_init__(self) -> None:
        _require_finite_nonnegative(self.s_m, "Keyframe arc length")
        if not math.isfinite(self.value):
            raise ValueError("Keyframe value must be finite.")


@dataclass(frozen=True, slots=True)
class AxialProfile:
    """Piecewise step or linear scalar profile along the engine wall."""

    keyframes: tuple[AxialKeyframe, ...]
    interpolation: InterpolationMode = InterpolationMode.LINEAR
    minimum_value: float | None = None
    maximum_value: float | None = None

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise ValueError("An axial profile requires at least one keyframe.")
        coordinates = [keyframe.s_m for keyframe in self.keyframes]
        if coordinates != sorted(coordinates) or len(set(coordinates)) != len(coordinates):
            raise ValueError("Axial-profile keyframes must have unique increasing coordinates.")
        for keyframe in self.keyframes:
            if self.minimum_value is not None and keyframe.value < self.minimum_value:
                raise ValueError(
                    f"Axial-profile value {keyframe.value:g} is below "
                    f"{self.minimum_value:g}."
                )
            if self.maximum_value is not None and keyframe.value > self.maximum_value:
                raise ValueError(
                    f"Axial-profile value {keyframe.value:g} is above "
                    f"{self.maximum_value:g}."
                )

    @classmethod
    def constant(
        cls,
        value: float,
        *,
        s_start_m: float = 0.0,
        minimum_value: float | None = None,
        maximum_value: float | None = None,
    ) -> "AxialProfile":
        return cls(
            keyframes=(AxialKeyframe(s_start_m, value),),
            minimum_value=minimum_value,
            maximum_value=maximum_value,
        )

    def evaluate(self, s_m: float) -> float:
        """Evaluate with constant extrapolation beyond the end keyframes."""

        _require_finite_nonnegative(s_m, "Evaluation arc length")
        if s_m <= self.keyframes[0].s_m:
            return self.keyframes[0].value
        if s_m >= self.keyframes[-1].s_m:
            return self.keyframes[-1].value
        for left, right in zip(self.keyframes, self.keyframes[1:]):
            if left.s_m <= s_m <= right.s_m:
                if self.interpolation is InterpolationMode.STEP:
                    return left.value
                fraction = (s_m - left.s_m) / (right.s_m - left.s_m)
                return left.value + fraction * (right.value - left.value)
        return self.keyframes[-1].value


@dataclass(frozen=True, slots=True)
class ChannelCrossSection:
    """Nominal local coolant-channel cross section."""

    shape: ChannelShape
    width_m: float | None = None
    height_m: float | None = None
    top_width_m: float | None = None
    bottom_width_m: float | None = None
    diameter_m: float | None = None
    corner_radius_m: float = 0.0
    polygon_points_m: tuple[tuple[float, float], ...] = ()

    def area_m2(self) -> float:
        """Return local fluid area."""

        if self.shape is ChannelShape.RECTANGULAR:
            width, height = self._width_height()
            return width * height
        if self.shape is ChannelShape.TRAPEZOIDAL:
            top, bottom, height = self._trapezoid_dimensions()
            return 0.5 * (top + bottom) * height
        if self.shape is ChannelShape.ROUNDED_RECTANGULAR:
            width, height = self._width_height()
            radius = self._validated_corner_radius(width, height)
            return width * height - (4.0 - math.pi) * radius**2
        if self.shape is ChannelShape.SEMICIRCULAR:
            radius = 0.5 * self._diameter()
            return 0.5 * math.pi * radius**2
        if self.shape is ChannelShape.CIRCULAR:
            radius = 0.5 * self._diameter()
            return math.pi * radius**2
        if self.shape is ChannelShape.RACETRACK:
            width, height = self._width_height()
            if width < height:
                raise ValueError("Racetrack width must be at least its height.")
            radius = 0.5 * height
            return (width - height) * height + math.pi * radius**2
        if self.shape is ChannelShape.CUSTOM_POLYGON:
            area, _perimeter = self._polygon_geometry()
            return area
        raise ValueError(f"Unsupported channel shape: {self.shape}")

    def wetted_perimeter_m(self) -> float:
        """Return the full local coolant wetted perimeter."""

        if self.shape is ChannelShape.RECTANGULAR:
            width, height = self._width_height()
            return 2.0 * (width + height)
        if self.shape is ChannelShape.TRAPEZOIDAL:
            top, bottom, height = self._trapezoid_dimensions()
            side = math.hypot(height, 0.5 * abs(top - bottom))
            return top + bottom + 2.0 * side
        if self.shape is ChannelShape.ROUNDED_RECTANGULAR:
            width, height = self._width_height()
            radius = self._validated_corner_radius(width, height)
            return 2.0 * (width + height) - 8.0 * radius + 2.0 * math.pi * radius
        if self.shape is ChannelShape.SEMICIRCULAR:
            diameter = self._diameter()
            radius = 0.5 * diameter
            return math.pi * radius + diameter
        if self.shape is ChannelShape.CIRCULAR:
            return math.pi * self._diameter()
        if self.shape is ChannelShape.RACETRACK:
            width, height = self._width_height()
            if width < height:
                raise ValueError("Racetrack width must be at least its height.")
            return 2.0 * (width - height) + math.pi * height
        if self.shape is ChannelShape.CUSTOM_POLYGON:
            _area, perimeter = self._polygon_geometry()
            return perimeter
        raise ValueError(f"Unsupported channel shape: {self.shape}")

    def hydraulic_diameter_m(self) -> float:
        """Return ``4 A/P`` for the local section."""

        return 4.0 * self.area_m2() / self.wetted_perimeter_m()

    def _width_height(self) -> tuple[float, float]:
        width = _required_positive(self.width_m, "Channel width")
        height = _required_positive(self.height_m, "Channel height")
        return width, height

    def _trapezoid_dimensions(self) -> tuple[float, float, float]:
        top = _required_positive(self.top_width_m, "Trapezoid top width")
        bottom = _required_positive(self.bottom_width_m, "Trapezoid bottom width")
        height = _required_positive(self.height_m, "Trapezoid height")
        return top, bottom, height

    def _diameter(self) -> float:
        return _required_positive(self.diameter_m, "Channel diameter")

    def _validated_corner_radius(self, width: float, height: float) -> float:
        _require_finite_nonnegative(self.corner_radius_m, "Channel corner radius")
        if self.corner_radius_m > 0.5 * min(width, height):
            raise ValueError("Channel corner radius exceeds half the minimum dimension.")
        return self.corner_radius_m

    def _polygon_geometry(self) -> tuple[float, float]:
        points = self.polygon_points_m
        if len(points) < 3:
            raise ValueError("A custom channel polygon requires at least three points.")
        twice_area = 0.0
        perimeter = 0.0
        for first, second in zip(points, points[1:] + points[:1]):
            x1, y1 = first
            x2, y2 = second
            if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
                raise ValueError("Custom channel polygon coordinates must be finite.")
            twice_area += x1 * y2 - x2 * y1
            perimeter += math.hypot(x2 - x1, y2 - y1)
        area = 0.5 * abs(twice_area)
        if area <= 0.0 or perimeter <= 0.0:
            raise ValueError("Custom channel polygon must enclose positive area.")
        return area, perimeter


@dataclass(frozen=True, slots=True)
class CoolantCircuit:
    """One connected coolant flow path."""

    circuit_id: str
    coolant_id: str
    mass_flow_kg_per_s: float
    inlet_temperature_k: float
    inlet_pressure_pa: float
    opposite_hot_gas_flow: bool = True

    def __post_init__(self) -> None:
        if not self.circuit_id.strip():
            raise ValueError("Coolant circuit ID must not be empty.")
        if not self.coolant_id.strip():
            raise ValueError("Coolant ID must not be empty.")
        _require_positive(self.mass_flow_kg_per_s, "Coolant mass flow")
        _require_positive(self.inlet_temperature_k, "Coolant inlet temperature")
        _require_positive(self.inlet_pressure_pa, "Coolant inlet pressure")


@dataclass(frozen=True, slots=True)
class CoolingSegment:
    """Axial range with one or more active cooling mechanisms."""

    segment_id: str
    s_start_m: float
    s_end_m: float
    mechanisms: tuple[CoolingMechanism, ...]
    circuit_id: str | None = None

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("Cooling segment ID must not be empty.")
        _require_finite_nonnegative(self.s_start_m, "Cooling segment start")
        _require_finite_nonnegative(self.s_end_m, "Cooling segment end")
        if self.s_end_m <= self.s_start_m:
            raise ValueError("Cooling segment end must be downstream of its start.")
        if not self.mechanisms:
            raise ValueError("Cooling segment requires at least one mechanism.")
        needs_circuit = any(
            mechanism
            in {
                CoolingMechanism.REGENERATIVE_CHANNELS,
                CoolingMechanism.ANNULUS,
                CoolingMechanism.TUBULAR_WALL,
                CoolingMechanism.COAXIAL_SHELL,
                CoolingMechanism.FILM,
            }
            for mechanism in self.mechanisms
        )
        if needs_circuit and not (self.circuit_id or "").strip():
            raise ValueError("Active coolant mechanisms require a coolant circuit ID.")

    def contains(self, s_m: float, *, include_end: bool = False) -> bool:
        return self.s_start_m <= s_m <= self.s_end_m if include_end else self.s_start_m <= s_m < self.s_end_m


@dataclass(frozen=True, slots=True)
class FilmCoolingSlot:
    """One circumferential or partial-circumference film injection feature."""

    slot_id: str
    s_m: float
    circuit_id: str
    mass_flow_kg_per_s: float
    slot_height_m: float
    injection_angle_deg: float
    circumference_fraction: float = 1.0
    liquid: bool = False

    def __post_init__(self) -> None:
        if not self.slot_id.strip() or not self.circuit_id.strip():
            raise ValueError("Film slot and circuit IDs must not be empty.")
        _require_finite_nonnegative(self.s_m, "Film-slot location")
        _require_positive(self.mass_flow_kg_per_s, "Film mass flow")
        _require_positive(self.slot_height_m, "Film-slot height")
        if not math.isfinite(self.injection_angle_deg) or not -90.0 <= self.injection_angle_deg <= 90.0:
            raise ValueError("Film injection angle must be between -90 and 90 degrees.")
        if not math.isfinite(self.circumference_fraction) or not 0.0 < self.circumference_fraction <= 1.0:
            raise ValueError("Film circumference fraction must be in the range (0, 1].")


@dataclass(frozen=True, slots=True)
class ChannelSectionState:
    """Resolved channel and wall geometry at one engine station."""

    s_m: float
    channel_count: int
    cross_section: ChannelCrossSection
    rib_width_m: float
    hot_wall_thickness_m: float
    closeout_thickness_m: float
    roughness_m: float
    helix_angle_deg: float
    single_channel_area_m2: float
    total_flow_area_m2: float
    single_channel_wetted_perimeter_m: float
    total_wetted_perimeter_m: float
    hot_wall_width_per_channel_m: float
    total_hot_wall_width_m: float
    hydraulic_diameter_m: float
    helical_length_multiplier: float


@dataclass(frozen=True, slots=True)
class ChannelLayout:
    """Stationwise-variable regenerative channel geometry."""

    shape: ChannelShape
    channel_count: AxialProfile
    width_m: AxialProfile | None = None
    height_m: AxialProfile | None = None
    top_width_m: AxialProfile | None = None
    bottom_width_m: AxialProfile | None = None
    diameter_m: AxialProfile | None = None
    corner_radius_m: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(0.0, minimum_value=0.0)
    )
    rib_width_m: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(0.001, minimum_value=0.0)
    )
    hot_wall_thickness_m: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(0.001, minimum_value=1.0e-6)
    )
    closeout_thickness_m: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(0.002, minimum_value=0.0)
    )
    roughness_m: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(5.0e-6, minimum_value=0.0)
    )
    helix_angle_deg: AxialProfile = field(
        default_factory=lambda: AxialProfile.constant(
            0.0,
            minimum_value=-80.0,
            maximum_value=80.0,
        )
    )
    polygon_points_m: tuple[tuple[float, float], ...] = ()

    def section_at(self, s_m: float) -> ChannelSectionState:
        """Resolve one local section for thermal, CAD and mesh consumers."""

        count_value = self.channel_count.evaluate(s_m)
        channel_count = int(round(count_value))
        if channel_count < 1 or not math.isclose(count_value, channel_count, abs_tol=1.0e-6):
            raise ValueError("Channel count profile must evaluate to a positive integer.")
        section = ChannelCrossSection(
            shape=self.shape,
            width_m=_evaluate_optional(self.width_m, s_m),
            height_m=_evaluate_optional(self.height_m, s_m),
            top_width_m=_evaluate_optional(self.top_width_m, s_m),
            bottom_width_m=_evaluate_optional(self.bottom_width_m, s_m),
            diameter_m=_evaluate_optional(self.diameter_m, s_m),
            corner_radius_m=self.corner_radius_m.evaluate(s_m),
            polygon_points_m=self.polygon_points_m,
        )
        single_area = section.area_m2()
        wetted_perimeter = section.wetted_perimeter_m()
        hot_wall_width = _hot_wall_width_m(section)
        helix_angle = self.helix_angle_deg.evaluate(s_m)
        cosine = math.cos(math.radians(helix_angle))
        if cosine <= 0.0:
            raise ValueError("Helix angle produces an invalid axial projection.")
        return ChannelSectionState(
            s_m=s_m,
            channel_count=channel_count,
            cross_section=section,
            rib_width_m=self.rib_width_m.evaluate(s_m),
            hot_wall_thickness_m=self.hot_wall_thickness_m.evaluate(s_m),
            closeout_thickness_m=self.closeout_thickness_m.evaluate(s_m),
            roughness_m=self.roughness_m.evaluate(s_m),
            helix_angle_deg=helix_angle,
            single_channel_area_m2=single_area,
            total_flow_area_m2=channel_count * single_area,
            single_channel_wetted_perimeter_m=wetted_perimeter,
            total_wetted_perimeter_m=channel_count * wetted_perimeter,
            hot_wall_width_per_channel_m=hot_wall_width,
            total_hot_wall_width_m=channel_count * hot_wall_width,
            hydraulic_diameter_m=section.hydraulic_diameter_m(),
            helical_length_multiplier=1.0 / cosine,
        )


def validate_cooling_layout(
    *,
    circuits: Iterable[CoolantCircuit],
    segments: Iterable[CoolingSegment],
    film_slots: Iterable[FilmCoolingSlot] = (),
    contour_length_m: float,
) -> tuple[CoolantCircuit, ...]:
    """Validate IDs, ranges and coolant references for a complete layout."""

    _require_positive(contour_length_m, "Contour length")
    circuit_tuple = tuple(circuits)
    segment_tuple = tuple(segments)
    slot_tuple = tuple(film_slots)
    circuit_ids = [circuit.circuit_id for circuit in circuit_tuple]
    if len(circuit_ids) != len(set(circuit_ids)):
        raise ValueError("Coolant circuit IDs must be unique.")
    segment_ids = [segment.segment_id for segment in segment_tuple]
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError("Cooling segment IDs must be unique.")
    known_circuits = set(circuit_ids)
    for segment in segment_tuple:
        if segment.s_end_m > contour_length_m:
            raise ValueError(
                f"Cooling segment {segment.segment_id!r} exceeds the contour length."
            )
        if segment.circuit_id is not None and segment.circuit_id not in known_circuits:
            raise ValueError(
                f"Cooling segment {segment.segment_id!r} references unknown circuit "
                f"{segment.circuit_id!r}."
            )
    slot_ids: set[str] = set()
    for slot in slot_tuple:
        if slot.slot_id in slot_ids:
            raise ValueError("Film-slot IDs must be unique.")
        slot_ids.add(slot.slot_id)
        if slot.s_m > contour_length_m:
            raise ValueError(f"Film slot {slot.slot_id!r} lies outside the contour.")
        if slot.circuit_id not in known_circuits:
            raise ValueError(
                f"Film slot {slot.slot_id!r} references unknown circuit "
                f"{slot.circuit_id!r}."
            )
    return circuit_tuple


def _evaluate_optional(profile: AxialProfile | None, s_m: float) -> float | None:
    return None if profile is None else profile.evaluate(s_m)


def _hot_wall_width_m(section: ChannelCrossSection) -> float:
    """Return the projected channel width adjacent to the combustion wall.

    For trapezoids, ``bottom_width_m`` is defined as the hot-wall width.  For a
    custom polygon, the local x-span is used.  The same convention is consumed
    by thermal, structural, CAD and CFD exporters.
    """

    if section.shape is ChannelShape.TRAPEZOIDAL:
        return _required_positive(section.bottom_width_m, "Trapezoid bottom width")
    if section.shape in {
        ChannelShape.RECTANGULAR,
        ChannelShape.ROUNDED_RECTANGULAR,
        ChannelShape.RACETRACK,
    }:
        return _required_positive(section.width_m, "Channel width")
    if section.shape in {ChannelShape.CIRCULAR, ChannelShape.SEMICIRCULAR}:
        return _required_positive(section.diameter_m, "Channel diameter")
    if section.shape is ChannelShape.CUSTOM_POLYGON:
        coordinates = [point[0] for point in section.polygon_points_m]
        if len(coordinates) < 3:
            raise ValueError("A custom channel polygon requires at least three points.")
        return _required_positive(max(coordinates) - min(coordinates), "Polygon hot-wall width")
    raise ValueError(f"Unsupported channel shape: {section.shape}")


def _required_positive(value: float | None, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} is required for this channel shape.")
    _require_positive(value, label)
    return value


def _require_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and greater than zero.")


def _require_finite_nonnegative(value: float, label: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and non-negative.")
