"""Tests for Rao / TOP nozzle-angle interpolation."""

import math

import pytest

from engine.nozzle_geometry import get_top_nozzle_angles, normalize_top_length_fraction


def test_get_top_nozzle_angles_accepts_k_length_fraction() -> None:
    theta_n_deg, theta_e_deg = get_top_nozzle_angles(35.0, 0.8)

    assert 25.0 < theta_n_deg < 40.0
    assert 5.0 < theta_e_deg < 15.0


def test_get_top_nozzle_angles_accepts_lf_percent_directly() -> None:
    theta_n_from_k, theta_e_from_k = get_top_nozzle_angles(35.0, 0.8)
    theta_n_from_lf, theta_e_from_lf = get_top_nozzle_angles(35.0, 80.0)

    assert math.isclose(theta_n_from_k, theta_n_from_lf, rel_tol=0.0, abs_tol=1.0e-12)
    assert math.isclose(theta_e_from_k, theta_e_from_lf, rel_tol=0.0, abs_tol=1.0e-12)


def test_get_top_nozzle_angles_rejects_low_expansion_ratio() -> None:
    with pytest.raises(ValueError, match="Rao/Huzel-&-Huang chart interpolation is only valid"):
        get_top_nozzle_angles(4.0, 0.8)


def test_get_top_nozzle_angles_rejects_high_expansion_ratio() -> None:
    with pytest.raises(ValueError, match="Rao/Huzel-&-Huang chart interpolation is only valid"):
        get_top_nozzle_angles(55.0, 80.0)


def test_get_top_nozzle_angles_rejects_invalid_length_fraction() -> None:
    with pytest.raises(ValueError, match="Rao/Huzel-&-Huang chart interpolation is only valid"):
        get_top_nozzle_angles(35.0, 0.5)


def test_normalize_top_length_fraction_converts_k_to_lf_percent() -> None:
    assert normalize_top_length_fraction(0.8) == 80.0
    assert normalize_top_length_fraction(80.0) == 80.0
