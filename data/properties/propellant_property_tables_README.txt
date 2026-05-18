Propellant property tables for AstraForge thermal-analysis lookup

Files:
- propellant_property_tables_nist_style.csv: flat CSV table, easiest to edit manually
- propellant_property_tables_nist_style.json: same records plus metadata for programmatic use

Important limitation:
These values were generated with CoolProp HEOS in the execution environment, not by direct automated export from NIST WebBook or REFPROP. Treat the data as NIST-style / REFPROP-style engineering lookup data for software development and predesign, not as a traceable official NIST export.

Fluids included:
1. RP1_SURROGATE_N_DODECANE
   - single-component proxy: n-Dodecane, CAS 112-40-3
   - grid: T = [293.15, 323.15, 373.15, 423.15, 473.15, 523.15, 573.15, 623.15, 653.15] K, p = [20, 50, 100, 150, 200] bar
   - NIST RP-1 surrogate models are actually multi-component; this is only a simple proxy.

2. LOX_OXYGEN
   - Oxygen, CAS 7782-44-7
   - grid: T = [80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 180.0, 200.0] K, p = [3, 10, 30, 60, 100, 150, 200] bar
   - includes phase column; filter for liquid/supercritical states when used as coolant.

Columns:
fluid_id, display_name, role, coolprop_fluid, nist_cas, T_K, p_Pa, p_bar, phase, rho_kg_m3, cp_J_kgK, mu_Pa_s, k_W_mK, h_J_kg, s_J_kgK, Pr, valid, note

Recommended AstraForge use:
- Interpolate rho, cp, mu, k over T,p.
- Keep phase checks active.
- Do not extrapolate far outside the table.
- Later replace this file with direct REFPROP/NIST exports for verification-grade work.
