# RPA Reference Benchmarks

`rpa_2_3_2_reference.json` contains structured console results generated from
the locally installed RPA 2.3.2 Standard edition. The source cases are the
unmodified RPA examples named in each record.

The benchmark runner:

1. invokes `rpac.exe` with the source configuration
2. parses ideal and estimated-delivered performance tables
3. supports normal tables and tables containing an additional flow-separation
   column
4. preserves RPA warnings
5. writes deterministic JSON without machine-specific timestamps

## Same-Input LOX/RP-1 Check

The built-in AstraForge example was exported to RPA configuration format and
successfully evaluated by `rpac.exe`. This tests the same chamber pressure,
mixture ratio, expansion ratio, contraction ratio, thrust, ambient pressure
and propellant names in both programs.

| Metric | AstraForge | RPA 2.3.2 | Relative difference |
|---|---:|---:|---:|
| Ideal c* [m/s] | 1794.9516 | 1793.1837 | +0.099% |
| Ideal vacuum Isp [s] | 343.7606 | 343.2807 | +0.140% |
| Delivered c* [m/s] | 1771.3048 | 1765.4390 | +0.332% |
| Delivered vacuum Isp [s] | 332.6134 | 330.1906 | +0.734% |

These differences are inside the initial parity target. Differences are
expected because AstraForge uses RocketCEA thermodynamic data while RPA uses
its bundled database and its own equilibrium solver.

## Interpretation

- A small difference is not automatically an AstraForge defect.
- Every benchmark must distinguish equation differences from database
  differences.
- Delivered-performance comparisons must record all enabled correction
  factors.
- Thermal and cycle benchmarks will use their own tolerances and reference
  outputs rather than reusing performance tolerances.
