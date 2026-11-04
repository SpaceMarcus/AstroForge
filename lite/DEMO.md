# AstroForge Lite in fünf Minuten vorführen

Ziel: zeigen, wie ein Triebwerksentwurf und sein Versorgungssystem gemeinsam bearbeitet werden. Die Demonstration bleibt bei einem stationären Vorentwurf; sie verspricht keinen vollständigen Triebwerksnachweis.

## Vor der Vorführung

- Browser und Anwendung auf dem tatsächlich eingesetzten Windows-Rechner oder Android-Handy öffnen. Beim privaten Hosting den Zugriff vorher prüfen; der Link ist nicht automatisch für Besucher öffentlich.
- Aktuellen eigenen Entwurf als Datei speichern, dann die Vorlage **AF–01 / Pressure-fed** laden.
- Den Ausgangsfall berechnen und das Ergebnis ansehen. Vorlage: 10 kN, 30 bar, O/F 2,6, Expansion 12.
- Ein Referenzprojekt als JSON-Datei bereithalten. Bei lokalem Windows-Betrieb den Server geöffnet lassen. Für eine Offlinevorführung vorher einen tatsächlichen Offline-Neustart prüfen.

## 0:00–0:45 · Das gesamte Triebwerk

Den Systemplan zeigen: zwei getrennte Versorgungspfade, Injektor, Brennkammer und Glockendüse. Brennstoff und Oxidator sind farblich unterscheidbar.

Erklären: „AstroForge beginnt beim Triebwerksentwurf. Die Komponentenansicht verbindet die Systemebene mit den Details jedes Bauteils.“

## 0:45–1:45 · Eine Section detaillieren

Die Brennstoff-Section öffnen. Die Brennstoffleitung auswählen und ihre **Länge von 1,2 m auf 2,4 m** ändern. Neu berechnen und den Druckverlust sowie den erforderlichen Versorgungsdruck vergleichen.

Ein Bauteil verschieben und erklären, dass der grafische Verlauf die physische Leitungslänge nicht verändert. Zur Systemebene zurückkehren. Auf dem Handy dafür die Bereiche **System**, **Details** und **Ergebnisse** verwenden.

## 1:45–2:45 · Eine Grenze sichtbar machen

Die **RP-1 Versorgung** wählen und den verfügbaren Druck von **55 bar auf 25 bar** setzen. Neu berechnen und die fehlende Druckreserve in der Auswertung zeigen.

Erklären: „Der Entwurf fordert mehr Versorgungsdruck, als hier verfügbar ist. Lite kennzeichnet das. Es erfindet keinen neuen Betriebspunkt.“

Den Druck wieder auf **55 bar** setzen und erneut berechnen. Bei Bedarf die geänderte Leitungslänge wieder auf 1,2 m zurückstellen.

## 2:45–3:45 · Von der Systemebene zur Geometrie

Die Düse auswählen. Die vorläufige 2D-Kontur und die Durchmesser zeigen. Die Expansion von **12 auf 16** ändern, neu berechnen und die geänderte Geometrie ansehen. Darauf hinweisen, dass vorherige Ergebnisse bis zur Neuberechnung als veraltet gelten.

Die Modellhinweise öffnen: Thermochemie aus einem begrenzten CEA-Datenfeld, lokal ausgewertete Druckverluste und eine glatte kubische Glockenapproximation, keine validierte Rao-Kontur. Die CEA-Stoffkarten verwenden feste Reaktantentemperaturen von 298,15 K für RP-1 und 90,18 K für LOX. Eine Änderung der Versorgungstemperatur berechnet die Chemie nicht neu. Detaillierte Kühlung und strukturelle Nachweise sind spätere Ausbaustufen.

## 3:45–4:30 · Das Projekt mitnehmen

**Speichern** wählen und die Projektdatei zeigen. Erläutern, dass dieselbe Datei auf Windows und Android geöffnet werden kann. Wenn das zweite Gerät bereitsteht, die vorher übertragene Referenzdatei dort öffnen und berechnen.

Optional die Stationstabelle als CSV exportieren. Die Datei enthält die berechneten Werte; sie ist kein vollständiger Prüfbericht.

## 4:30–5:00 · Rückmeldung sammeln

Drei konkrete Fragen stellen:

1. Welche Entwurfsentscheidung könnte dieses Werkzeug in Ihrem Alltag unterstützen?
2. Welches Ergebnis fehlt, damit Sie den Vorentwurf sinnvoll bewerten können?
3. Wäre als nächster Schritt detaillierte Kühlung, eine pumpengeförderte Architektur oder ein weiteres Stoffpaar am wertvollsten?

Keine zusätzliche Funktion im Gespräch als bereits verfügbar darstellen. Lite zeigt den durchgängigen Arbeitsablauf; die nächste Erweiterung soll aus einer tatsächlichen Entwurfsaufgabe folgen.

## Falls etwas nicht wie erwartet läuft

Die Vorlage erneut laden und berechnen. Nicht unterstützte Verbindungen oder getrennte Pfade werden in der Auswertung benannt; betroffene Komponenten können von dort geöffnet werden. Bei einem Gerätewechsel ist eine Projektdatei erforderlich, da Autosave nicht zwischen Geräten synchronisiert wird.

Die Browserdateien laufen lokal, aber privater Hosting-Zugriff kann Internet und Anmeldung benötigen. Ein physisches Android-Gerät sollte vor der Veranstaltung separat getestet werden; bisherige mobile Emulation ersetzt diesen Test nicht.
