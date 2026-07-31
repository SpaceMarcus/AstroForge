"""Tests for parsing RPA console benchmark output."""

from __future__ import annotations

from pathlib import Path

from engine.rpa_benchmark import (
    RPABenchmarkResult,
    parse_rpa_console_output,
    write_rpa_benchmark_json,
)


RPA_OUTPUT = """
Case name:
                    SSME

Theoretical chamber performance

Parameter                       Sea Level Opt Expans     Vacuum       Unit
Characteristic velocity            0.0000  2323.8666     0.0000        m/s
Specific impulse (by mass)      3723.0730  4388.1463  4544.2797     N-s/kg
Specific impulse (by weight)     379.6478   447.4664   463.3876          s
Thrust coefficient                 1.6021     1.8883     1.9555

Estimated delivered performance

Parameter                       Sea Level Opt Expans     Vacuum       Unit
Characteristic velocity            0.0000  2316.2853     0.0000        m/s
Specific impulse (by mass)      3606.8462  4271.9195  4428.0528     N-s/kg
Specific impulse (by weight)     367.7960   435.6146   451.5357          s
Thrust coefficient                 1.5572     1.8443     1.9117
WARNING: reference warning
"""


def test_parse_rpa_console_output_extracts_ideal_and_delivered_tables() -> None:
    result = parse_rpa_console_output(RPA_OUTPUT, input_file="SSME.cfg")

    assert result.case_name == "SSME"
    assert result.ideal.characteristic_velocity_m_per_s == 2323.8666
    assert result.ideal.isp_vacuum_s == 463.3876
    assert result.ideal.cf_sea_level == 1.6021
    assert result.delivered is not None
    assert result.delivered.characteristic_velocity_m_per_s == 2316.2853
    assert result.delivered.isp_vacuum_s == 451.5357
    assert result.delivered.cf_vacuum == 1.9117
    assert result.warnings == ("WARNING: reference warning",)


def test_write_rpa_benchmark_json_is_structured(tmp_path: Path) -> None:
    result: RPABenchmarkResult = parse_rpa_console_output(
        RPA_OUTPUT,
        input_file="SSME.cfg",
    )

    path = write_rpa_benchmark_json([result], tmp_path / "reference.json")
    text = path.read_text(encoding="utf-8")

    assert path.exists()
    assert '"format": "astraforge-rpa-benchmark"' in text
    assert '"case_name": "SSME"' in text
    assert '"isp_vacuum_s": 451.5357' in text
