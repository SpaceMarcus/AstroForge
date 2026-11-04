# AstroForge 2.0 Lite Prüfstand

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
