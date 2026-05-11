"""Tests for the lightweight nozzle-preview helper."""

from engine.models import BellContourVariant, NozzleContourMethod
from engine.nozzle_preview import build_nozzle_preview


def test_preview_uses_manual_length_when_provided() -> None:
    preview = build_nozzle_preview(
        throat_radius_m=0.05,
        expansion_ratio=16.0,
        downstream_radius_ratio=0.382,
        contour_method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_length_m=0.4,
    )

    assert preview.uses_manual_length is True
    assert preview.length_m == 0.4
    assert preview.start_x_m > 0.0
    assert preview.start_radius_m > preview.throat_radius_m
    assert preview.angle_source == "Rao / Huzel & Huang chart interpolation via pygasflow"
    assert preview.length_fraction_percent is not None


def test_preview_builds_from_throat_to_exit_without_manual_length() -> None:
    preview = build_nozzle_preview(
        throat_radius_m=None,
        expansion_ratio=9.0,
        downstream_radius_ratio=0.382,
        contour_method=NozzleContourMethod.CONICAL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_length_m=None,
    )

    assert preview.uses_normalized_throat is True
    assert preview.points[0][0] == 0.0
    assert preview.points[0][1] == preview.throat_radius_m
    assert preview.points[-1][0] == preview.length_m
    assert preview.points[-1][1] == preview.exit_radius_m


def test_top_preview_accepts_length_fraction_input() -> None:
    preview = build_nozzle_preview(
        throat_radius_m=0.05,
        expansion_ratio=25.0,
        downstream_radius_ratio=0.382,
        contour_method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_length_m=None,
        length_fraction_input=90.0,
    )

    assert preview.length_fraction_percent == 90.0
    assert preview.length_m > preview.start_x_m


def test_top_preview_inflow_angle_tracks_downstream_throat_radius() -> None:
    baseline_preview = build_nozzle_preview(
        throat_radius_m=0.05,
        expansion_ratio=35.0,
        downstream_radius_ratio=0.382,
        contour_method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_length_m=None,
    )
    larger_radius_preview = build_nozzle_preview(
        throat_radius_m=0.05,
        expansion_ratio=35.0,
        downstream_radius_ratio=0.70,
        contour_method=NozzleContourMethod.BELL,
        bell_variant=BellContourVariant.PARABOLA,
        manual_length_m=None,
    )

    assert larger_radius_preview.inflow_angle_deg > baseline_preview.inflow_angle_deg
