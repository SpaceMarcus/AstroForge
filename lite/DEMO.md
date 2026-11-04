# AstroForge 2.1 Lite in fünf Minuten vorführen

Ziel: einen Triebwerksentwurf über Komponenten bearbeiten und Druck-, Wärme- sowie Wellenleistungsbilanzen gemeinsam beurteilen. Die Cycle-Modelle sind ausdrücklich begrenzte Vorentwurfsmodelle.

## Vor der Vorführung

- Den aktuellen 2.1-Quellstand aus dem GitHub-Repository bauen und lokal starten. Die frühere private 2.0-Site enthält diesen Cycle-Ausbau nicht.
- Windows: `Start-AstroForge.cmd` oder ein nachweislich aktuelles 2.1-EXE-Paket verwenden. Für Android den Node-Server auf Windows starten und im selben Netzwerk über `http://<Windows-Netzwerkadresse>:4173` öffnen. Die EXE auf Port 4174 ist ausschließlich lokal erreichbar.
- Eigenen Arbeitsstand zuerst als Datei sichern. Ein Referenzprojekt als JSON bereithalten. Für die Handyvorführung den Server eingeschaltet lassen; ein HTTP-LAN-Aufruf bietet keine zugesicherte Offlineinstallation.
- Die drei Vorlagen einmal berechnen. Aktuelle Testergebnisse in `VALIDATION.md` prüfen und die Vorführung auf den tatsächlich eingesetzten Geräten durchspielen.

## 0:00–0:45 · Drei Architekturen, ein Arbeitsraum

**Vorlage** öffnen und die drei Einstiege zeigen: **Druckgefördert**, **Pumpen & Kühlung** und **Turbine & Abgasdüse**. Alle beginnen mit demselben idealen Haupttriebwerksziel von 10 kN.

**Pumpen & Kühlung** laden. Die beiden Fluidpfade, Pumpen, gemeinsame Welle und den Kühlblock zeigen. Mechanische Zuordnungen unterscheiden sich farblich von Fluidleitungen.

Erklären: „Die Architektur ist bearbeitbar. Jeder Block hat ein benanntes Modell, Parameter und einen Beitrag zur Bilanz.“

## 0:45–1:45 · Wellenleistung prüfen

Den **Elektrischen Antrieb** auswählen. Seine Drehzahl, den mechanischen Wirkungsgrad und die externe Antriebsleistung zeigen. In der Auswertung Pumpenbedarf, verfügbare Leistung und Drehmoment ansehen.

Die externe Antriebsleistung von **30 kW auf 1 kW** reduzieren und neu berechnen. Das Leistungsdefizit zeigen. Anschließend wieder **30 kW** einstellen und neu rechnen.

Erklären: „Der gewünschte Betriebspunkt braucht eine bestimmte Pumpenleistung. Ein grünes Druckbudget genügt nicht, wenn der Antrieb diese Leistung nicht liefern kann. Eine Leistungsreserve ist wiederum noch kein gelöster Drehzahlgleichgewichtspunkt.“

## 1:45–2:30 · Eine Komponente detaillieren

Die Brennstoff-Section öffnen. Die RP-1-Pumpe auswählen und ihre **Antriebswelle** im Inspector zeigen. Anschließend den Kühlblock wählen und die vorgegebene Wärmeaufnahme, den Druckverlust und cp ansehen. Die berechnete Austrittstemperatur in der Auswertung zeigen.

Erklären: „Dieser Kühlblock bilanziert vorgegebene Wärme. Er dimensioniert noch keine Kanäle und berechnet keine Wandtemperatur. Die Hauptthermochemie bleibt von der eingestellten Versorgungstemperatur getrennt.“

## 2:30–3:45 · Turbine, Abgasdüse und Systemleistung

Die Vorlage **Turbine & Abgasdüse** laden und berechnen. Den getrennten Zweig aus **Treibgasquelle → Turbine → Abgasdüse** sowie die Wellenzuordnung zeigen.

In der Auswertung Turbinenaustrittstemperatur, Turbinenleistung und Zusatzschub betrachten. Die Hauptkennwerte von **Gesamtschub** und **System-Isp** unterscheiden: Letzteres berücksichtigt den zusätzlichen Treibgasmassenstrom.

Erklären: „Der Treibgasstrom ist hier eine vorgegebene Randbedingung. Das zeigt Komponenten- und Leistungszusammenhänge, aber noch keinen vollständig geschlossenen Gasgeneratorzyklus. Chemie und Abzweige dieses Gasgenerators sind nicht gelöst.“

Die Düse auswählen und ihre vorläufige 2D-Kontur zeigen: glatte kubische Glockenapproximation, keine validierte Rao-Kontur.

## 3:45–4:30 · Das System bearbeiten

Eine **Messstelle** hinzufügen. Im Inspector das passende Medium wählen, unter **In Versorgungspfad einsetzen** eine Verbindung auswählen und **In Leitung einsetzen** betätigen. Neu berechnen und den idealen Messwert zeigen.

Alternativ eine Leitung auswählen und ihre physische Länge verändern. Ein grafisches Verschieben verändert diese Länge nicht. **Rückgängig** demonstrieren. Änderungen kennzeichnen vorherige Ergebnisse bis zur Neuberechnung als veraltet.

## 4:30–5:00 · Projekt und nächste Entscheidung

**Speichern** wählen. Die Projektdatei lässt sich auf Windows und Android öffnen; Autosave allein synchronisiert nicht zwischen Geräten. Bei Bedarf ein Ergebnis-JSON exportieren, das auch die Cycle-Auswertung enthält.

Als Rückmeldung fragen: „Welche nächste Entscheidung möchten Sie damit treffen: eine belastbarere Kühlungsauslegung, einen vollständig gekoppelten Cycle oder den Vergleich weiterer Stoffpaare?“

## Modellhinweise auf Nachfrage

- Hauptthermochemie: begrenztes Datenfeld aus 392 RocketCEA-Zuständen; Interpolation innerhalb 10–80 bar, O/F 2–3,2 und Expansion 4–40.
- Die CEA-Stoffkarten verwenden RP-1 bei 298,15 K und LOX bei 90,18 K. Änderungen an Versorgungstemperaturen oder Kühlwärme berechnen diese Chemie nicht neu.
- Pumpen verwenden inkompressible Druckarbeit; Turbine und Abgasdüse konstantes cp und γ. Keine Kennfelder, Starttransienten, Kavitation oder automatische Off-design-Lösung.
- Ergebnisse sind Vorentwurf und Komponenten-Screening, kein thermischer, struktureller oder experimenteller Freigabenachweis.

## Falls etwas nicht wie erwartet läuft

Die gewünschte Vorlage erneut laden und berechnen. Ungültige Verbindungen und fehlende Wellenzuordnungen anhand der Meldungen korrigieren. Für eine Vorführung mit einem Handy die LAN-Verbindung und Windows-Firewall vorab prüfen. Der aktuelle Stand ist keine native Android-App; eine physische Android-Abnahme ist getrennt von Browseremulation durchzuführen.
