# AstroForge Lite Modellumfang und Rechenkonventionen

Stand: 4. November 2026. Diese Beschreibung gilt für Lite 2.2, `src/physics.js` und `src/cooling.js`. Lite ist ein stationäres Vorentwurfs- und Bilanzwerkzeug mit vorgegebenen Betriebspunktparametern. Ein erfolgreich berechnetes Ergebnis ist kein Nachweis für tatsächlich erreichbare Hardwareleistung.

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

Die dargestellte Kontur besitzt glatte kubische Übergänge und eine Glockenlänge von 80 % einer geometrischen 15°-Kegelreferenz. Das ist eine **Visualisierungsnäherung**, keine Rao-/MoC-Konstruktion und keine Fertigungskontur. Das Kanalmodell verwendet genau diese diskretisierte Kontur für thermisches Screening. Daraus folgt weder eine validierte Düsenkontur noch ein Festigkeitsnachweis. Der eingegebene Halskrümmungsfaktor ist eine Bartz-Modellannahme; er rekonstruiert die kubische Kontur nicht.

## Versorgungspfade

Genau ein Brennstoffpfad und ein Oxidatorpfad führen ohne Verzweigung zum Injektor. Leitungen, Ventile, Messstellen, Pumpen und höchstens ein geometriegekoppelter Brennstoff-Kühlmantel sowie ältere Wärmebilanzblöcke können in Reihe angeordnet werden. Sections ändern die physische Bilanz nicht.

Ohne Kanalmodell gelten konstante Screeningwerte:

| Medium | Dichte | Dynamische Viskosität | Zulässige Eingangs-Temperatur |
|---|---|---|---|
| RP-1 | 810 kg/m³ | 0.0018 Pa·s | 288–303 K |
| LOX | 1140 kg/m³ | 0.0002 Pa·s | 85–95 K |

Dies sind ausdrücklich konstante Annahmen, keine aktuelle Stoffdatenbankabfrage und keine temperaturabhängigen RP-1-Surrogatdaten. Ohne Kanalmodell bleiben Dichte und Viskosität nach Erwärmung im alten Wärmebilanzblock unverändert. Sobald ein Kanalmodell vorhanden ist, verwendet der gesamte Brennstoffpfad die unten beschriebenen temperatur- und druckabhängigen n-Dodecan-Ersatzstoffwerte. LOX bleibt konstant. Eine Phasenänderung, chemische Zersetzung oder lokale Kavitation wird nicht berechnet.

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

## Geometriegekoppelte Kanalkühlung

Neue Kühlmäntel verwenden `mode: channels`. Höchstens ein solcher Block ist je Projekt erlaubt. Der gesamte Hauptbrennstoffstrom fließt vom Düsenaustritt zurück zur Kammer. Kontur und Halsfläche stammen aus demselben Haupttriebwerksentwurf. Es gibt keine zusätzliche Kühlmassenstromvorgabe und keinen berechneten Bypass.

### Stoffwerte und feste Gasrandbedingung

`public/cooling-data.json` enthält getrennte Gastransport- und Kühlmitteldaten. Gastransport wird über pc und O/F bilinear interpoliert. Für Bartz und die lokale Strömungsnäherung werden **frozen-Kammer-cp, -Prandtlzahl und -gamma** verwendet; die Viskosität stammt ebenfalls aus CEA. `gamma = cp/(cp-R)` basiert auf der Kammer-Molmasse. Diese Werte bleiben entlang der Kontur konstant. Kammer-Tc, c* und pc sind feste CEA-/Entwurfsrandbedingungen. Der berechnete Wärmeentzug reduziert die Gasenthalpie nicht; die aufgeheizte Brennstoffenthalpie wird nicht in eine neue Verbrennungsrechnung zurückgeführt.

Das Kühlmittel ist **CoolProp 8.0.0 / HEOS n-Dodecan**, ein einzelner RP-1-Ersatzstoff, kein qualifiziertes RP-1-Gemisch und kein offizieller NIST-/REFPROP-Export. Dichte, cp, Viskosität, Wärmeleitfähigkeit und spezifische Enthalpie werden über T und p bilinear interpoliert. Tabellenumfang: **288–633 K, 1–200 bar**. Nur Zellen mit gültigen flüssigen beziehungsweise dichten `supercritical_liquid`-Eckzuständen werden verwendet. Gas-/ungültige Zustände sind nullmarkiert und werden nicht überbrückt; Extrapolation ist gesperrt. Der rechteckige Zahlenbereich bedeutet deshalb nicht, dass jede T/p-Kombination zulässig ist. Quellen und Vergleichsstichproben stehen im Datensatz.

### Geometrie, Wärme und Druck

Der eingegebene Anteil der Umfangsteilung bestimmt die lokale Breite der rechteckigen Kanäle. Höhe, Wanddicke und Kanalanzahl sind konstant. Der Wärmeübergang berücksichtigt die effektiv benetzte Fläche einschließlich gerader Rippen mit `eta_fin = tanh(mh)/(mh)`.

Die lokale Machzahl folgt aus dem Flächen-Mach-Verhältnis mit konstantem frozen-gamma, unter- beziehungsweise überschallschnell vor beziehungsweise nach dem Hals. Die Gas-Recoverytemperatur verwendet den Faktor `Pr^(1/3)`. Der gasseitige Bartz-Ansatz enthält lokale Fläche, Halskrümmung und eine iterativ bestimmte Wandtemperaturkorrektur. Das Wandmodell nutzt ebene radiale Wärmeleitung mit konstanter eingegebener Wärmeleitfähigkeit:

```
q = h_g * (T_recovery - T_wall_hot)
q = (T_wall_hot - T_coolant) / (wall_thickness/k_wall + 1/(h_coolant*area_factor))
T_wall_cold = T_wall_hot - q*wall_thickness/k_wall
Q_segment = q * hot_surface_segment
```

Kühlmittelseitig werden Rechteckkanalkorrelationen für laminare Darcy-Reibung und Nusseltzahl sowie Haaland/Gnielinski für turbulente Strömung verwendet. Zwischen Re 2300 und 4000 wird interpoliert und gewarnt. Re über 5 Millionen oder Pr außerhalb 0,5–2000 erzeugt einen Korrelationshinweis; relative Rauheit über 0,05 wird abgewiesen.

Das Modell marschiert entgegen der Gasrichtung. Pro Segment werden Zustand, Wandtemperatur, Wärmeaufnahme und Druck gekoppelt iteriert. Energie enthält Enthalpie **und kinetische Energie**:

```
Q_total = mdot * (h_out - h_in + (v_out² - v_in²)/2)
p_static_out = p_static_in - friction_loss - acceleration_term
```

Darcy-Reibung und ein längenverteilter örtlicher Verlust K tragen zum Druckverlust bei. Die variable Kanalfläche kann örtliche statische Druckrückgewinnung erzeugen. Gesamt-Eintrittsdruck wird iterativ in statischen Druck umgerechnet; am Austritt wird der dynamische Anteil wieder addiert. **Stationsprofil und Kanaltabelle zeigen statischen Kühlmitteldruck.** Blockeintritt, -austritt und Δp in der Feed-Bilanz sind Gesamtdruckbudgets am Zielbetriebspunkt.

Die vorgegebene Zahl axialer Segmente wird um alle ursprünglichen Konturstützstellen ergänzt; deshalb kann die ausgegebene Stationszahl größer sein. Das Profil enthält Segmentmitten und zusätzliche Randzustände einschließlich des Düsenaustritts, damit Wandtemperaturspitzen an den Rändern erfasst werden. Randzustände tragen keinen zusätzlichen Segmentwärmestrom bei. Alle Stationen sind in Gasströmungsrichtung sortiert. Segmentiteration: höchstens 100 Schritte, Toleranzen 1e-6 K und 1e-7 bar; Wandtemperatur-Bisektion: 60 Schritte. Das äußere Brennstoff-Druckbudget iteriert höchstens 60-mal mit 50-%-Dämpfung und 1e-5 bar Toleranz. Verletzte Stoffdatengrenzen oder fehlende Konvergenz liefern kein gültiges Ergebnis.

`wallMarginK = eingegebene Wandgrenze - maximale heiße Wandtemperatur`. Eine negative Marge ergibt einen Warnstatus bei weiterhin auswertbarem Rechenergebnis. Sie bezeichnet ausschließlich einen Vergleich mit der **vom Nutzer gesetzten Temperaturgrenze**, keine geprüfte Werkstoffzulässigkeit.

Nicht enthalten sind Strahlung, axiale Wandleitung, Siedung/Zweiphasigkeit, Verkokung/Pyrolyse, thermische Spannungen, Ermüdung oder Lebensdauer. Auch bei eingehaltenem Temperaturlimit bleiben diese offenen Nachweise bestehen. Die Gasrandbedingung, Chemie und Hauptmassenströme werden durch die Kühlrechnung nicht neu gelöst.

## Älterer regenerativer Wärmebilanzblock

Importierte Projekte ohne Kanalmodus behalten ihre Parameter. Die explizite Umstellung im Inspector ersetzt sie durch Kanalparameter und ist rückgängig machbar. Der ältere Block nimmt einen vorgegebenen Wärmestrom und Druckverlust auf:

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
| Älterer Kühlblock Q / Druckverlust / cp | 0–5000 kW / 0–100 bar / 100–10000 J/(kg K) |
| Kanalanzahl / Höhe / Teilungsanteil | 12–500 ganzzahlig / 0.2–10 mm / 0.1–0.9 |
| Kanalwanddicke / Wärmeleitfähigkeit | 0.2–5 mm / 5–500 W/(m K) |
| Kanalrauheit / örtlicher Verlust K | 0–0.1 mm / 0–50; zusätzlich Rauheit/Dh ≤ 0.05 |
| Eingegebene Wandgrenze / axiale Segmentvorgabe | 400–2000 K / 40–400 ganzzahlig |
| Halskrümmungsradius / Halsradius | 0.2–5 |
| Wellendrehzahl / Wirkungsgrad / Motorleistung | 100–200000 rpm / 0.05–1 / 0–10000 kW |
| Treibgas p / T / Massenstrom | 0.1–200 bar / 200–2000 K / 0.001–10 kg/s |
| Treibgas cp / gamma | 500–10000 J/(kg K) / 1.05–1.67 |
| Turbinenaustrittsdruck / Wirkungsgrad | 0.01–200 bar / 0.05–1 |
| Abgas-Austrittsdruck / Wirkungsgrad | 0.001–200 bar / 0.05–1 |

Zusätzlich muss `p_gas_source > p_turbine_out > p_exhaust_exit` gelten. Der Turbinen-Austrittsgesamtdruck muss oberhalb des Umgebungsdrucks liegen. Fehlende Wellenzuordnungen, isolierte Wellen, unvollständige Zusatzgaswege und Fluidverbindungen an Wellen werden abgewiesen.

## Verifikation und verbleibende Grenzen

Die Tests prüfen Referenzwerte, Erhaltung der Massenströme, eine unabhängige laminare Druckverlustlösung, Pumpenarbeit, Turbinenenthalpie, Wellenzuordnung, Drehmoment, Wärmebilanz, Zusatzgasverbrauch und Druckschub. Ungültige Zustände werden gesondert getestet. Kanaltests ergänzen Wärme-/Druckbilanzen, Stoffdatengrenzen, thermische Sensitivitäten und Netzdiskretisierung; UI-/Migrationstests prüfen Darstellung und den Erhalt alter Projekte. Aktueller tatsächlicher Prüfstatus: `VALIDATION.md`. Diese Prüfungen ersetzen keine experimentellen Nachweise.

Der Datengenerator prüft alle 252 Zellmittelpunkte gegen zusätzliche direkte CEA-Aufrufe. Größte relative Abweichungen dieser Stichprobe: c* 0.184 %, Cf 0.429 %, Tc 0.464 %, pe 0.650 %. Die Daten enthalten die genauer gespeicherten Werte und die verwendete Backend-Version. Das sind **Stichprobenabweichungen**, keine mathematisch garantierten globalen Fehlergrenzen.

Die erweiterten Module ergeben Komponenten- und Leistungsbudgets. Sie bilden keinen vollständig gekoppelten Gasgenerator-, Expander- oder Staged-Combustion-Cycle ab.


## 2.4: Verzweigte Kühl- und Versorgungsnetze

Das neue Netzmodell löst gerichtete Bäume mit genau einem Zulauf je Bauteil. Injektorbedarf stammt aus der Hauptauslegung; zusätzliche Verbraucher geben Massenstrom und benötigten Eintrittsgesamtdruck vor. Die rückwärts summierten Teilströme erfüllen die Massenbilanz. Temperaturen werden vorwärts transportiert, Kanalwärme und Verluste lokal berechnet. Erforderliche Druckbudgets werden rückwärts aufgestellt und mit zustandsabhängigen Stoffwerten iteriert (Druckresiduum < 1e-5 bar, höchstens 100 Iterationen).

Am Abzweig wird der größte erforderliche Zweigdruck angesetzt. Die Differenz zu jedem anderen Zweig erscheint als zusätzlich notwendiger Drosselverlust. Dieser Verlust ist keine vorhandene Komponente und keine gelöste passive Stromaufteilung. Ohne passenden Druckabgleich sind die vorgeschriebenen Teilströme nicht als selbsttätiger Betriebspunkt nachgewiesen. Leitungseintrittsdruck im Tooltip bezeichnet den Zustand nach diesem hypothetischen Abgleich; der vorgelagerte Knotendruck wird separat angezeigt.

Verengungen verwenden Δp = K ρ v²/2 mit Geschwindigkeit im Engpass. K wird vorgegeben, nicht aus dem Durchmesserverhältnis geschätzt. Der Zulaufdurchmesser darf nicht kleiner als der Engpass sein. Branch- und Manifold-K beziehen sich auf den gesamten Einlassstrom und den angegebenen Bezugsdurchmesser; Einzellasten der Verteilkanäle werden nicht separat aufgelöst.

Separate Kühlversorgung verwendet denselben n-Dodecan-Ersatzstoff wie der Hauptbrennstoff. Eine direkte Manifold-Verbindung setzt den entsprechenden Kühlstreckenendpunkt auf seine axiale Position. Angezeigt wird ε = A(x)/At einschließlich „vor/nach Hals“, da ε allein die axiale Lage nicht eindeutig bestimmt. Nicht überlappende Teilstrecken können gleichzeitig gegen- und gleichsinnig durchströmt werden. Nicht gekühlte Wandbereiche werden thermisch nicht nachgewiesen.

Verbraucher können als Preburner, Film oder sonstiger Auslass bezeichnet werden. Sie entnehmen Masse; es gibt keine Preburner-Chemie, Filmwärmeabschirmung oder Verbraucherschub. Der zusätzliche Massenverbrauch reduziert den ausgewiesenen System-Isp. Die bestehende vorgegebene Treibgasversorgung ist weiterhin unabhängig, keine thermochemische Kopplung zum Preburner-Verbraucher. Mischknoten, Rückführschleifen und überlappende Kühlflächen werden abgewiesen.


## 2.5: Stoffauswahl und Gültigkeit

Elf fest definierte Paare statt beliebiger ungeprüfter Kombinationen:

| Oxidator | Brennstoffe | Start-O/F / Datenbereich |
|---|---|---|
| LOX | RP-1, Methan, Wasserstoff, Ethanol, Propan | 2.6 / 2–3.2; 3.2 / 2.5–4; 5.5 / 4–7; 1.6 / 1.2–2; 2.8 / 2–3.5 |
| N2O | RP-1, Ethanol, Propan | 6 / 4–8; 4.5 / 3–6; 6.5 / 4–9 |
| HTP 90 Gew.-% | RP-1, Ethanol, Propan | 7 / 5–9; 5 / 3.5–6.5; 7.5 / 5–10 |

Startwerte sind Bedienvorgaben, keine optimierten Betriebspunkte. Kammerdruck bleibt 10–80 bar, Expansion 4–40. Jeder neue Datensatz stammt aus direkten RocketCEA-Aufrufen mit den dokumentierten Reaktantenkarten. Alle Zellmittelpunkte wurden zusätzlich direkt gerechnet; die Metadaten enthalten größte beobachtete Interpolationsabweichungen je Ergebnisgröße. Diese Stichproben sind weder globale Fehlergrenzen noch experimentelle Modellvalidierung. Karten und deren Temperaturen bleiben feste Thermochemierandbedingungen; die Versorgungstemperatur verändert sie nicht.

Flüssige Feed-Screeningwerte: CoolProp HEOS bei 70 bar und Nominaltemperatur (Methan 110 K, Wasserstoff 20 K, Ethanol 293.15 K, Propan 230 K, LOX 90 K, N2O 250 K). Dichte und Viskosität werden außerhalb der Kanalkühlung konstant verwendet. N2O-Viskosität kommt mangels CoolProp-Transportmodell aus RocketProps 0.1.9 als gesättigte Flüssigkeitsviskosität bei 250 K. Die konservative Mindestdruckgrenze entspricht dem Sättigungsdruck am oberen Ende des jeweiligen engen Temperaturfensters. Unterschreitungen im erforderlichen statischen Druckbudget werden abgewiesen. Dies ersetzt keine NPSH-, Kavitation-, Zweiphasen- oder Selbstbedrückungsrechnung.

HTP ist ausdrücklich 90 Gew.-% H2O2 und 10 Gew.-% Wasser. Feed-Screening verwendet 1390 kg/m³ und 1.26 mPa·s bei 20 °C aus dem Evonik-Aeronautikdatenblatt, begrenzt auf 288–303 K. Es wird keine HTP-Zersetzung, Katalysatorreaktion oder HTP-Kanalkühlung modelliert. Propan ist im Modell unterkühlte Flüssigkeit um 230 K, kein Raumtemperatur-LPG-Gemisch.

Kanalkühlung ist für RP-1 (n-Dodecan-Ersatzstoff) und reines Ethanol freigegeben. Die Gastransportdaten passen zum gewählten Oxidator/Brennstoffpaar. Ethanol verwendet CoolProp-Werte bis 500 K mit ungültigen Phasenzellen ausdrücklich gesperrt; RP-1 behält die bestehende Ersatzstofftabelle. Methan-, Wasserstoff- und Propan-Kanäle werden abgewiesen, bis passende kryogene/überkritische Kühlmodelle vorliegen. Ein vorhandener Kühlmantel wird beim Stoffwechsel nicht still entfernt oder in ein anderes Modell umgestellt.

Quellen: [RocketCEA-Reaktantenkarten](https://rocketcea.readthedocs.io/en/latest/propellants.html), [CoolProp-Fluide und Modellreferenzen](https://coolprop.org/fluid_properties/index.html), [RocketProps N2O](https://rocketprops.readthedocs.io/en/latest/n2o_prop.html), [Evonik HTP für Raumfahrtanwendungen](https://active-oxygens.evonik.com/zh/attachment/140277?rev=9a24167032bd618d7f7ff672a62fa152).

Reproduktion: Python-Abhängigkeiten in `tools/requirements-data.txt`, Generator `tools/generate_propellants.py`. Die Browseranwendung bleibt ohne Python- oder Paketinstallation nutzbar; sie lädt die vorberechneten Tabellen lokal.
