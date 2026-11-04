# AstroForge Lite Modellumfang und Rechenkonventionen

Stand: 4. November 2026. Diese Beschreibung gilt für `src/physics.js`. Lite ist ein stationäres Vorentwurfs- und Bilanzwerkzeug mit vorgegebenen Betriebspunktparametern. Ein erfolgreich berechnetes Ergebnis ist kein Nachweis für tatsächlich erreichbare Hardwareleistung.

## Einheiten und Ergebnisbezug

Der Rechenkern verwendet SI-Größen. Eingaben in bar, mm und kW werden mit `1 bar = 100000 Pa`, `1 mm = 0.001 m` und `1 kW = 1000 W` umgerechnet. `g0 = 9.80665 m/s²`. Wirkungsgrade sind Zahlen zwischen 0 und 1, nicht Prozentwerte.

Der Hauptschub ist ein **idealer Zielwert**. Kammerdruck, O/F und Expansion werden vorgegeben; die erforderliche Halsfläche und der Massenstrom werden daraus bestimmt. Pumpendruckerhöhung, Motorleistung, Wellendrehzahl und Zusatzgaszustand sind ebenfalls Vorgaben. Lite löst keinen tatsächlichen gemeinsamen Off-design-Betriebspunkt.

## Haupttriebwerk und CEA-Daten

Die mitgelieferte Tabelle enthält 392 mit dem bestehenden `RocketCEABackend` erzeugte LOX/RP-1-Gleichgewichtszustände. Es wird eine Kammer mit unendlichem Flächenverhältnis im Chemiebackend verwendet. Der einstellbare geometrische Kontraktionswert ist nicht an diese Chemie gekoppelt. Die verwendeten Reactant Cards stehen einschließlich ihrer Temperaturen in `public/thermo.json`: RP-1 298.15 K, LOX 90.18 K. Änderungen der Versorgungstemperatur verändern diese CEA-Rechnung nicht.

CEA ist ein Gleichgewichtsprogramm zur Berechnung thermochemischer Zustände und theoretischer Raketenleistung. Lite verwendet vorab berechnete Zustände, keinen laufenden CEA-Solver im Browser. [NASA CEA Dokumentation](https://nasa.github.io/cea/)

Interpolation: `c*`, Vakuum-`Cf` und Kammertemperatur werden trilinear interpoliert. Für den Düsen-Austrittsdruck wird `log(pe/pc)` linear über Kammerdruck, O/F und `log(epsilon)` interpoliert. Extrapolation wird abgewiesen.

Die folgenden Beziehungen verbinden idealen Schub, Massenstrom und spezifischen Impuls:

```
Cf = Cf_vac - (pa / pc) * epsilon
At = F_main / (Cf * pc)
mdot_main = pc * At / cstar
Isp_main = Cf * cstar / g0
mdot_fuel = mdot_main / (1 + OF)
mdot_ox = mdot_main - mdot_fuel
```

Die allgemeine Schubdefinition enthält Impuls- und Druckschub. Spezifischer Impuls bezieht sich auf den zugehörigen gesamten Massenverbrauch. [NASA Specific Impulse](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/)

Verbrennungs-, Reibungs- und Divergenzverluste sind hier nicht enthalten. Bei Überexpansion erscheint ein Hinweis; eine Strömungsablösung wird nicht gelöst.

## Geometrie

Hals-/Austritts-/Kammerradius folgen aus Flächenverhältnissen. Im Lite-Modell ist `L_chamber = Lstar / contractionRatio`; L* bezieht sich damit ausdrücklich auf das zylindrische Kammervolumen. Konvergentes Volumen wird diesem L*-Ansatz nicht zusätzlich zugerechnet.

Die dargestellte Kontur besitzt glatte kubische Übergänge und eine Glockenlänge von 80 % einer geometrischen 15°-Kegelreferenz. Das ist eine **Visualisierungsnäherung**, keine Rao-/MoC-Konstruktion und keine Fertigungskontur. Aus der Darstellung werden keine Wärme- oder Festigkeitsnachweise abgeleitet.

## Versorgungspfade

Genau ein Brennstoffpfad und ein Oxidatorpfad führen ohne Verzweigung zum Injektor. Leitungen, Ventile, Messstellen, Pumpen und ein oder mehrere Brennstoff-Wärmebilanzblöcke können in Reihe angeordnet werden. Sections ändern die physische Bilanz nicht.

Konstante Screeningwerte:

| Medium | Dichte | Dynamische Viskosität | Zulässige Eingangs-Temperatur |
|---|---|---|---|
| RP-1 | 810 kg/m³ | 0.0018 Pa·s | 288–303 K |
| LOX | 1140 kg/m³ | 0.0002 Pa·s | 85–95 K |

Dies sind ausdrücklich konstante Annahmen, keine aktuelle Stoffdatenbankabfrage und keine temperaturabhängigen RP-1-Surrogatdaten. Nach Erwärmung im Wärmebilanzblock bleiben Dichte und Viskosität unverändert. Eine Phasenänderung, chemische Zersetzung oder lokale Kavitation wird nicht berechnet.

Leitungen verwenden Darcy–Weisbach mit `v = mdot/(rho*A)` und `Re = rho*v*D/mu`. Für `Re < 2300` gilt `f = 64/Re`; oberhalb 4000 wird die Haaland-Näherung verwendet. Dazwischen wird linear über Re interpoliert und eine Warnung ausgegeben. Der örtliche Verlust ist `K*rho*v²/2`. Ventile verwenden den Querschnitt der vorangehenden Leitung, bei fehlendem Vorgänger den der ersten Leitung im Pfad. Relative Rauheit ist auf höchstens 0.05 begrenzt; Geschwindigkeit über 100 m/s wird als außerhalb des Lite-Screenings abgewiesen.

Die rückwärtige Bilanz lautet schematisch:

```
p_required_source = pc + injector_loss + sum(passive_losses) - sum(pump_rises)
pressure_margin = p_available_source - p_required_source
```

Angezeigte Pfaddrücke sind **erforderliche Gesamtdruckbudgets**, keine gelösten lokalen statischen Istdrücke. Höhenunterschiede fehlen. Ein zu geringer verfügbarer Druck wird als Defizit ausgewiesen. Überschuss bedeutet Reserve beziehungsweise notwendigen zusätzlichen Druckabbau. Nicht positive rückwärts berechnete Drücke werden abgewiesen, statt physikalisch unmögliche Eintrittszustände auszugeben.

## Pumpen und Wellen

Die Pumpe überträgt inkompressible Druckarbeit. Ihr fester Druckanstieg wird durch keine Drehzahlkennlinie bestimmt:

```
P_hydraulic = mdot * delta_p / rho
P_pump_shaft = P_hydraulic / eta_pump
```

Der DOE-Sourcebook erläutert den Zusammenhang von Fluidarbeit, Förderstrom/Förderhöhe und Pumpen-/Antriebswirkungsgrad sowie die Notwendigkeit einer Betrachtung des gesamten Pumpensystems. Die Formeln oben sind die hier implementierte SI-Energiebilanz. [DOE Pumping System Sourcebook](https://www.energy.gov/sites/default/files/2014/05/f16/pump.pdf)

Mechanische Zuordnung erfolgt über die Wellen-ID, nicht über Fluidverbindungen. Für jede Welle:

```
P_required = sum(assigned_pump_shaft_power)
P_available = P_motor_delivered + eta_shaft * sum(assigned_turbine_power)
P_balance = P_available - P_required
omega = rpm * 2*pi / 60
torque_required = P_required / omega
torque_available = P_available / omega
```

Motorleistung wird bereits **an der Welle** angegeben; der mechanische Wirkungsgrad wirkt auf die Turbinenleistung. Ein positiver Saldo bedeutet Leistungsreserve, keinen automatisch stationär geschlossenen Drehmomentzustand. Ein Defizit macht den vorgegebenen Zielbetriebspunkt nicht erfüllbar. Pumpenerwärmung, NPSH, Kavitation, Lager, Kennfelder und Rotordynamik fehlen.

## Regenerativer Wärmebilanzblock

Dieser Block nimmt einen vorgegebenen Wärmestrom und Druckverlust auf:

```
T_out = T_in + Q / (mdot * cp)
```

Die Rechnung ist eine Ein-/Austritts-Energiebilanz mit konstantem cp. Sie berechnet weder die tatsächlich übertragbare Wärme noch Wandtemperatur, Kühlkanalgeometrie oder eine thermische Marge. Die Wärmequelle ist extern aufgeprägt; dieselbe Energie wird nicht automatisch aus der CEA-Brennkammer oder Hauptdüse abgezogen. Temperaturen über 650 K werden als außerhalb dieses Screeningumfangs abgewiesen; diese Grenze ist **keine Material- oder Betriebssicherheitsgrenze**.

## Separates Treibgas, Turbine und Abgasdüse

Optional ist genau ein getrennter Pfad `Treibgasquelle → Turbine → Abgasdüse` erlaubt. Der Gaszustand wird vom Nutzer vorgegeben. Es handelt sich nicht um Gasgeneratorchemie oder einen berechneten Treibstoffabzweig aus den Hauptpfaden.

Für kalorisch ideales Gas mit konstantem cp und gamma, Gesamtdruck/Temperatur am Turbineneintritt und Gesamt-Austrittsdruck:

```
a = (gamma - 1) / gamma
delta_T_turbine = eta_turbine * T_in * (1 - (p_out/p_in)^a)
T_out = T_in - delta_T_turbine
P_turbine = mdot_aux * cp * delta_T_turbine
```

Diese spezifische Arbeit folgt aus dem idealisierten Turbinen-Enthalpieabfall mit isentropem Wirkungsgrad. [NASA Power Turbine Thermodynamics](https://www.grc.nasa.gov/www/k-12/airplane/powtrbth.html)

Die nachgeschaltete Abgasdüse verwendet die Turbinen-Austrittsgesamttemperatur und einen vorgegebenen statischen Austrittsdruck:

```
delta_T_nozzle = eta_nozzle * T_total * (1 - (p_exit/p_total)^a)
v_exit = sqrt(2 * cp * delta_T_nozzle)
T_exit = T_total - delta_T_nozzle
R = cp * (gamma - 1) / gamma
rho_exit = p_exit / (R * T_exit)
A_exit = mdot_aux / (rho_exit * v_exit)
F_aux = mdot_aux * v_exit + (p_exit - p_ambient) * A_exit
```

Der Geschwindigkeitsansatz stammt aus der idealisierten Düsen-Energiegleichung. Lite dimensioniert die Austrittsfläche anschließend aus Kontinuität; eine feste Hardwaregeometrie wird nicht iteriert. [NASA Turbine Nozzle Performance](https://www.grc.nasa.gov/WWW/K-12/airplane/nozzleh.html)

Zusatzschub wird axial gleichgerichtet angenommen. Überexpandierte Abgasströmung wird markiert; Ablösung und Seitenkräfte fehlen. Der Zusatzgasverbrauch wird einmal hinzugezählt:

```
F_system = F_main + F_aux
mdot_system = mdot_main + mdot_aux
Isp_system = F_system / (mdot_system * g0)
```

Haupt-Isp und System-Isp bleiben getrennte Ergebnisse. Elektrischer Energiebedarf wird dadurch nicht in eine äquivalente Treibstoffmasse umgerechnet.

## Zulässige Eingabebereiche

Diese Grenzen definieren den Software-/Screeningumfang, keine Hardwarezulassung.

| Eingabe | Bereich |
|---|---|
| Hauptschub / pc / O/F / Expansion | 100–100000 N / 10–80 bar / 2–3.2 / 4–40 |
| Umgebungsdruck / L* / Kontraktion | 0–1.2 bar / 0.2–3 m / 1.5–8 |
| Verfügbarer Versorgungsdruck | 2–200 bar |
| Leitungslänge / Innendurchmesser | 0–100 m / 1–200 mm |
| Absolute Rauheit | 0 bis min(1 mm, D/20) |
| Örtlicher Verlust K / Injektorverlust je Seite | 0–10000 / 0–100 bar |
| Pumpendruckanstieg / Wirkungsgrad | 0.01–150 bar / 0.05–1 |
| Kühlblock Q / Druckverlust / cp | 0–5000 kW / 0–100 bar / 100–10000 J/(kg K) |
| Wellendrehzahl / Wirkungsgrad / Motorleistung | 100–200000 rpm / 0.05–1 / 0–10000 kW |
| Treibgas p / T / Massenstrom | 0.1–200 bar / 200–2000 K / 0.001–10 kg/s |
| Treibgas cp / gamma | 500–10000 J/(kg K) / 1.05–1.67 |
| Turbinenaustrittsdruck / Wirkungsgrad | 0.01–200 bar / 0.05–1 |
| Abgas-Austrittsdruck / Wirkungsgrad | 0.001–200 bar / 0.05–1 |

Zusätzlich muss `p_gas_source > p_turbine_out > p_exhaust_exit` gelten. Der Turbinen-Austrittsgesamtdruck muss oberhalb des Umgebungsdrucks liegen. Fehlende Wellenzuordnungen, isolierte Wellen, unvollständige Zusatzgaswege und Fluidverbindungen an Wellen werden abgewiesen.

## Verifikation und verbleibende Grenzen

Die Tests prüfen Referenzwerte, Erhaltung der Massenströme, eine unabhängige laminare Druckverlustlösung, Pumpenarbeit, Turbinenenthalpie, Wellenzuordnung, Drehmoment, Wärmebilanz, Zusatzgasverbrauch und Druckschub. Ungültige Zustände werden gesondert getestet. Diese Prüfungen ersetzen keine experimentellen Nachweise.

Der Datengenerator prüft alle 252 Zellmittelpunkte gegen zusätzliche direkte CEA-Aufrufe. Größte relative Abweichungen dieser Stichprobe: c* 0.184 %, Cf 0.429 %, Tc 0.464 %, pe 0.650 %. Die Daten enthalten die genauer gespeicherten Werte und die verwendete Backend-Version. Das sind **Stichprobenabweichungen**, keine mathematisch garantierten globalen Fehlergrenzen.

Die erweiterten Module ergeben Komponenten- und Leistungsbudgets. Sie bilden keinen vollständig gekoppelten Gasgenerator-, Expander- oder Staged-Combustion-Cycle ab.
