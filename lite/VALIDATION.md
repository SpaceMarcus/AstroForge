# AstroForge 2.0 Lite Prüfstand

## Erweiterung 2.7 · Dokumentverwaltung und Präsentation

118 bestehende und neue Softwaretests bestanden. Vier neue Tests decken unabhängige Snapshots, Serialisierung, Speicherfehler, Dokumentvergleich, fehlerhafte Archive, Archivkapazität und die Trennung von Datenpräsenz und Validierung ab. Dies erweitert keine physikalische Validierung.

Browser: benannten Stand speichern, Projektname ändern, Änderung vergleichen, wiederherstellen mit automatischer Sicherung, Neuladen mit erhaltenem Archiv, Archiv exportieren und wieder importieren, Statuslink zum Inspector, HTML-Bericht herunterladen. Desktop und 390 × 844 geprüft; mobile Dialogbreite 356 px bei Dokumentbreite 390 px ohne Überlauf. Präsentation blendet Bearbeitung aus; keine Konsolenfehler im geprüften Ablauf.


## Erweiterung 2.6 · Analyse und Teilergebnisse

4. November 2026. **114 automatisierte Tests bestanden.** Neue Tests prüfen Methan/H2/Propan mit nicht unterstützter Kanalkühlung, fehlende Stoffdaten und ungültige Entwurfsparameter sowie die Identität der idealen Kennwerte zwischen Voll- und Teilergebnis. Teilergebnisse ändern weder das Projekt noch den Fehlerstatus und enthalten keine vorgetäuschte Feed-Bilanz.

Browserprüfung: HTP90/Propan als vollständige Druckförder-Auslegung; Methan in der Pumpen-/Kühlvorlage als ausdrücklich unvollständiges Ergebnis mit Bauteillink; RP-1-Kühlnetz mit Druckprofil und Stationsauswahl. Navigation zur Analyse und zurück bei 390 × 844, Dokumentbreite 390 px ohne horizontalen Überlauf. Keine neuen Stoffdaten oder Validitätsbereiche eingeführt.


## Erweiterung 2.2 · Geometriegekoppelte Kanalkühlung

4. November 2026. **82 automatisierte Tests bestanden**. Neue Abdeckung: SI-Bartz-Referenz, quadratischer Laminar-Kanal, Machzahl, Enthalpie-/kinetischer Energieabschluss, Stoffdaten- und Phasengrenzen, Kanalgeometrie, Kammerdruckabhängigkeit, Druckrekonstruktion für hohe Verluste, Wärmeübertragung in den nachgeschalteten Feed-Pfad, Zellrandtemperaturen, Netzverfeinerung, Legacy-Erhalt, Modellwechsel/Undo, Profilbedienung und sichere Ausgabe.

Neue elektrische und Turbinenvorlage: 10 kN Hauptschub, 30 bar, O/F 2,0, L* 0,5 m, 120 Kanäle, 0,75 mm Kanalhöhe und 20 bar Quellen. Diese expliziten Beispielparameter ersetzen keine importierten Entwürfe. Berechnete Werte: Wandmaximum 874,17 K bei vorgegebener Grenze 900 K, Kühlmittelaustritt 610,38 K, Wärmeaufnahme 1223,51 kW, Kanal-Gesamtdruckverlust 11,006 bar. 120 Unterteilungen plus Konturstützstellen ergeben 184 Zellen und 185 Randpunkte; das Profil enthält 369 Datensätze. Die Randpunkte werden zur Maximumsuche, nicht nochmals zur Wärmeintegration verwendet.

Die Prüfung mit 40/120/400 Unterteilungen verändert das Wandmaximum der Beispielvorlage um weniger als 0,003 K. Das belegt numerische Stabilität dieses Beispiels, keine allgemeine Genauigkeit der physikalischen Näherungen. Der Gesamtenthalpie-/Geschwindigkeitsabschluss liegt im geprüften Lauf deutlich unter 0,01 W.

Browserabläufe bei 1440 × 900 und 390 × 844:

- Bestehendes 2.1-Projekt bleibt beim Laden im alten Wärmebilanzmodell berechenbar.
- Kühlkanal-Inspector direkt über Brennkammer geöffnet; neue Vorlage berechnet.
- Kanalhöhe auf 2 mm erhöht: Wandtemperaturwarnung im Arbeitsraum und Profil. Auf 0,6 mm reduziert: höherer erforderlicher Quelldruck und erkannte Unterversorgung. Damit ist der Rückweg ins Feed-Budget sichtbar geprüft.
- Ungültige Kanalhöhe 0 bleibt markiert und blockiert die Rechnung; Graph und Ergebnisse werden als veraltet behandelt.
- Temperatur-/Wärmestrom-/Druckansicht und Stationsauswahl bedient; geöffnete Stationstabelle bleibt nach Auswahl geöffnet.
- Finaler CSV-Download: 369 Zeilen, davon 184 Zellen und 185 Randpunkte, mit statischem Druckbezug, Gas-/Kühlmittelmodell und Energieresiduum.
- Finale Diagramme ohne horizontales Dokument-Überlaufen auf 390 Pixeln; keine Browser-Konsolenfehler.
- Server beendet, Anwendung aus Cache neu geladen und Kanalkühlung erneut berechnet: identische Kennwerte (874 K, 11,01 bar, 610,4 K).

Windows-Paket mit finalem Webstand neu gebaut und EXE-Smoke-Test bestanden. Physisches Android-Gerät und sauberer Windows-PC weiterhin nicht abgenommen. Das Paket heißt `AstroForge-Lite-2.2-Cooling-Windows.zip`; GitHub enthält den Quellstand. Der alte private Webauftritt bleibt unverändert.

Modellgrenzen: n-Dodecan als RP-1-Ersatz, feste CEA-Gasrandbedingungen mit frozen-Transportdaten, stationäres einphasiges 1D-Modell. Kein chemisch-thermischer Kreislaufschluss, keine Strahlung, Verkokung, Siedung, Festigkeit oder Lebensdauer. Wandtemperaturgrenze ist eine Nutzervorgabe, keine zertifizierte Werkstoffzulässigkeit. Quellen und Gleichungen: MODELS.md.

---

## Erweiterung 2.1 · Cycle-Komponenten

4. November 2026. **54 automatisierte Tests bestanden**, einschließlich der bisherigen Regressionstests. Neue Prüfungen betreffen Pumpendruckarbeit, Wellenbedarf/Drehmoment, unabhängige Wellen, Wärmebilanz, Treibgasverbrauch, Turbinenleistung, Abgas-Druckschub, fehlende Zuordnungen und negative Druckbudgets. Vorlagen-Roundtrip, mechanische Ergebnisinvalidierung, HTML-Escaping und Darstellung von Leistungsdefiziten wurden ebenfalls geprüft.

Browserprüfung bei 1440 × 900 und 390 × 844:

- Alte druckgeförderte Projektdatei lädt und berechnet weiterhin.
- Elektrische Vorlage: Pumpenbedarf 16,71 kW, 30 kW Antrieb; Kühlmittel 293,15 → 313,64 K bei aufgeprägten 50 kW.
- Antrieb auf 5 kW geändert: 11,71 kW Defizit in der Auswertung, Warnstatus im Arbeitsraum. Heruntergeladenes CSV enthält `insufficient_drive`.
- Turbinenvorlage: 86,94 kW Turbinenleistung, 83,46 kW nach mechanischem Wirkungsgrad, 87,25 N Zusatzschub. System-Isp 248,3 s berücksichtigt den zusätzlichen Gasstrom; Haupt-Isp bleibt 255,4 s.
- Auf Handygröße Messstelle hinzugefügt und per „In Leitung einsetzen“ eingebunden; anschließende Rechnung erfolgreich.
- Wellenzuordnung der Turbine entfernt: Berechnung mit konkretem Fehler abgewiesen. Zuordnung wiederhergestellt: Rechnung erfolgreich.
- Kein horizontales Dokument-Überlaufen bei 390 Pixeln; keine Browser-Konsolenfehler in diesen Abläufen.
- Lokalen Server beendet: Anwendung aus Browsercache neu geladen und Turbinenvorlage inklusive Cycle-Auswertung erneut erfolgreich berechnet.

Statische Anwendung neu gebaut. Windows-EXE mit diesen Webdateien neu gebündelt; EXE-Smoke-Test erfolgreich. Das aktuelle Paket heißt `AstroForge-Lite-2.1-Cycle-Windows.zip`. Physisches Android-Gerät und sauberer Windows-PC bleiben ausstehend. Der frühere private Webauftritt wurde nicht aktualisiert; GitHub enthält den aktuellen Quellstand.

Diese Erweiterung ist ein Komponenten-Screening. Vorgegebene Pumpendruckerhöhung, Wärmeeintrag und Treibgasrandbedingungen schließen keinen vollständigen Triebwerkszyklus. Quellen, Gleichungen und Grenzen: `MODELS.md`.

---

## Historischer Prüfstand 2.0

4. November 2026. Diese Datei beschreibt tatsächlich ausgeführte Prüfungen und verbleibende Grenzen.

## Automatisiert

- `npm test`: 31 Tests bestanden. Rechenkern, Graph-Hilfsfunktionen, Speicherformat, Historie und Integration.
- `npm run build`: statische Browseranwendung gebaut; keine externen Laufzeitpakete.
- 392 thermochemische Stützstellen aus RocketCEA 1.2.3. Reproduzierbare Erzeugung mit `tools/generate_thermo.py` im bestehenden Python-Repository.
- 252 Zellmittelpunkte zusätzlich direkt mit CEA berechnet. Maximal beobachtete relative Interpolationsabweichungen: c* 0,184 %, Cf 0,429 %, Tc 0,464 %, Austrittsdruck 0,650 %. Keine globale Fehlergrenze und kein Versuchsnachweis.
- Thermochemie bei festen Reaktantentemperaturen; der Datenbereich wird strikt begrenzt. Abweichende Versorgungstemperaturen verändern keine CEA-Eingangszustände.
- Unabhängige laminare Druckverlustreferenz, Massenerhaltung, monotone Leitungsverluste und Unterversorgungsprüfung.
- Fehlerfälle: unverbundene/zyklische/verzweigte Graphen, falsches Medium, geschlossene Ventile, nicht endliche Werte, ungültige Stofftemperaturen und Chemie außerhalb der Tabelle.
- Import: Formatversion, Größe, IDs, reservierte Objekt-IDs, Verbindungsgültigkeit und numerische Struktur.
- Stations-/Section-Zuordnung, Layoutunabhängigkeit und Ergebnisinvalidierung geprüft.
- Windows-Starter: Python- und EXE-Smoke-Test erfolgreich; fünf gebündelte Webressourcen, Dateipfadbegrenzung, gesperrte Verzeichnislisten und Verhalten bei belegtem Port geprüft.

## Im Browser bedient

Desktop-Ansicht bei 1440 × 900 und mobile Ansicht bei 390 × 844 im In-App-Browser:

- Standardprojekt lädt und rechnet: 10 kN idealer Zielschub, rund 255,4 s Isp, 3,993 kg/s Gesamtmassenstrom.
- LOX-Versorgungsdruck auf 20 bar geändert: Unterversorgung erkannt; Zielbetriebspunkt wird nicht still verändert.
- Undo und erneute Rechnung stellen den gültigen Entwurf wieder her.
- Oxidator-Section geöffnet; Ventil ausgewählt und geschlossen; Rechnung liefert konkrete Komponentenfehlermeldung.
- Verbindung im Inspector getrennt und über Ausgangs-/Eingangsports wieder verbunden.
- Leitung auf der Zeichenfläche verschoben und per Undo zurückgesetzt; reine Layoutänderung lässt Ergebnisse aktuell.
- Messstelle hinzugefügt: offene Anschlüsse verhindern die Berechnung; Undo entfernt die Messstelle und stellt den berechenbaren Graphen wieder her.
- Projektdatei auf Handygröße heruntergeladen, über Dateiauswahl wieder geöffnet und neu berechnet.
- Ungültiger Kammerdruck bleibt beim Komponentenwechsel erhalten und verhindert eine Rechnung mit alten Eingaben.
- Mobile Ergebnisse und Detailfelder ohne horizontales Dokument-Überlaufen.
- Keine Anwendungsfehler/-warnungen in der Online-Browserkonsole während der geprüften Abläufe.
- Lokaler Offline-Test: Server auf Port 4173 beendet, dessen Nichterreichbarkeit separat geprüft; Browser lädt Anwendung aus Cache neu und rechnet erfolgreich.

## Lieferung und noch nicht geprüft

Die Browserversion wurde über Sites privat veröffentlicht. Ihr Zugang erfordert das berechtigte ChatGPT-Konto; die Hosting-Anmeldung wurde nicht für den Nutzer übernommen. Die eigentliche Anwendung wurde lokal geprüft. Öffentliche Kundenfreigabe wurde nicht eingerichtet.

Physische Android-Hardware, installierte Android-PWA, unterschiedliche Android-Browser und ein sauberer Windows-PC wurden nicht abgenommen. Die Windows-EXE ist nicht signiert; ihr sichtbares Starterfenster wurde nicht automatisiert bedient. Auf dem Zielgerät vor der STE einmal starten, Projektdatei laden und den Demoablauf durchführen.

## Bewusste Abweichungen vom früheren MVP-Entwurf

- Browserfähige begrenzte CEA-Interpolation statt eines laufenden Python-/CEA-Dienstes auf jedem Gerät.
- Konstante, sichtbar dokumentierte Fluid-Screeningwerte statt vollständiger zustandsabhängiger Tabellen. Keine Phasen-/Kavitationsrechnung.
- Glatte kubische Konturdarstellung statt Wiederverwendung des vollständigen Rao-/CAD-Pfads. Keine Fertigungsgeometrie.
- Zwei vorgegebene Sections mit abgeleiteten Grenzverbindungen statt frei benennbarer, beliebig verschachtelter Subsysteme.
- Projekt speichert den Entwurf; nach Import neu rechnen. Ergebnis-JSON ist ein separater Export mit Eingabestand und Herkunft.

Diese Entscheidungen ermöglichen einen eigenständigen Windows-/Android-Vorführprototyp. Sie sind in UI und Anleitung benannt und dürfen nicht als vollständige Umsetzung aller langfristigen Fachmodelle verkauft werden.


## 2.3 engine section and feedlines — 2026-11-04

Added solver regressions for co-/counterflow inlet locations, partial profile endpoints, energy conservation, legacy full-coverage defaults, invalid interval/direction rejection, fitting K losses, edge hydraulic losses, JSON persistence, and reversible/idempotent migration including custom diameters. Ideal gas arrows use turbine exit / chamber inlet states rather than nozzle exhaust states.

Browser verification: desktop 1280×720 and responsive viewport 390×844. Legacy-line conversion, cooling coverage and flow direction, manifold insertion before the jacket, recomputation, and feedline length editing exercised through the UI. Document width at 390 px remained 390 px. No browser error logs observed. Responsive viewport testing is not a physical Android-device test. Partial coverage does not validate uncooled wall regions; manifold and turn are lumped serial loss elements, not a branched or multipass solver.


## 2.4 Cooling-Netz — 2026-11-04

98 automatisierte Tests bestanden. Neue Prüfungen: Kühlmantel → Abzweig → Injektor und Preburnerbedarf, Massenabschluss, Kanalenergieresiduum < 0.01 W, separate Kühlversorgung, zwei entgegengesetzt durchströmte nicht überlappende Kühlstrecken mit gemeinsamem Manifold sowie unabhängiger analytischer K-Verlust einer Verengung. Ungültige Engpassgeometrie, Nullbedarf, Schleifen/Zusammenführungen, Gas-Leitungsverluste und falsches Wellenmedium werden abgewiesen.

Browserprüfung bei 1280×720 und 390×844: neue Vorlagen berechnet, Cooling-Section geöffnet, Manifold per Slider verschoben (99.9 % / ε 11.99), gebundene Streckengrenze geprüft. Abzweigleitung zeigt 0.200 kg/s, 581.7 K, erforderliche 25 bar nach Druckabgleich, 36 bar am Knoten und 11 bar zusätzlichen Drosselbedarf. Gesamter Massenabschluss im Beispiel 0 kg/s; Hauptbedarf 4.143 kg/s plus 0.200 kg/s Verbraucher. Kein horizontaler Dokumentüberlauf bei 390 px, keine Browserfehler. SVG-Leitungsauswahl zusätzlich per Tastatur geprüft. Physisches Android-Gerät und neue Windows-EXE wurden für 2.4 nicht geprüft bzw. gebaut.

Die Prüfung belegt Rechen- und Bedienkonsistenz des Bedarfsmodells, keinen experimentell validierten Betriebspunkt. Film und Preburner sind ausschließlich Verbraucherrandbedingungen. Serienprojekte bleiben auf dem bisherigen Solver; verzweigte Projekte verwenden das neue Druckbudgetmodell.


## 2.5 Stoffauswahl und Logikprüfung — 2026-11-04

111/111 automatisierte Tests bestanden. Nach Ergänzung der Stoffquellen-Metadaten zusätzlich alle fünf Stoffphysiktests bestanden. Alle elf Kombinationen werden am stationären Testpunkt gerechnet; Stoffwechsel, JSON-Persistenz, Legacy-Default und Undo werden separat geprüft. Fehlende oder falsch zugeordnete Tabellen werden abgewiesen.

Regressionsnachweise: Manifold-Grenze bleibt bei Feedline-Expansion bei 75 %; mehrere getrennte serielle Mäntel; passende Mantelauswahl am Manifold; ungültige Kühlmodi; Anzeigegruppen ohne Einfluss auf Physik und Ergebnisgültigkeit. Methan-Abzweig stimmt mit einer unabhängigen Ventil-K-Rechnung überein. Ethanol-Kanäle mit LOX, N2O und HTP90 (separate 4 kg/s, halbe Kontur) schließen jeweils die Energie auf <0.005 W ab, ohne eine RP-1-Kühltabelle zu übergeben.

Der neue Generator prüft alle CEA-Zellmittelpunkte mit separaten direkten Backendaufrufen und dokumentiert die Abweichungen pro Größe. Größte beobachtete relative Abweichung unter den neuen Gittern: 3.47 % (N2O/Ethanol); dies ist kein globales Fehlerlimit. Ethanol-Gastransport- und Kühlmittelinterpolation besitzen eigene Stichprobenmetadaten. Keine experimentelle Validierung.

Browser: Desktop 1280×720 und Handy-Viewport 390×844. HTP90/Propan berechnet (30 bar, O/F 7.5), nach Reload Auswahl/O/F-Grenzen erhalten; Methanwahl und Berechnung über mobile Details/Ergebnisse bedient. Bei 390 px kein horizontaler Dokumentüberlauf. Propanwechsel an einem vorhandenen Kanalmantel liefert die ausdrückliche Nichtverfügbarkeitsmeldung; Undo stellt LOX/RP-1 wieder her. Keine Browserfehler beobachtet. Physisches Androidgerät und neues Windows-EXE-Paket wurden nicht geprüft bzw. gebaut.

Der Logik-Agent-Bericht steht in LOGIC-AUDIT.md. Die neue Datenbasis erweitert Thermochemie und begrenzte Flüssigkeits-Screenings, nicht die Anzahl vollständig validierter Engine-Cycles.
