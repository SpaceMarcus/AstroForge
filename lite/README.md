# AstroForge 2.2 Lite

Ein lokaler Arbeitsraum für den stationären LOX/RP-1-Triebwerksvorentwurf mit grafisch bearbeitbaren Komponenten. Version 2.2 ergänzt eine geometriegekoppelte Kanalkühlung mit Temperaturprofilen, Wärmestromdichte und Druckverlust. Pumpen, Antriebswellen sowie ein separat vorgegebener Treibgaszweig mit Turbine und Abgasdüse bleiben Teil des Arbeitsraums. Komponenten, Leistung und vorläufige Geometrie gehören zum selben Projekt.

Der Quellcode wird im GitHub-Repository geführt. Die aktuelle private [AstroForge-Site](https://astroforge-2-lite.marcusmohren.chatgpt.site) dient zum Testen auf Windows und Android und wird bei abgeschlossenen Weiterentwicklungen mit aktualisiert. Die Anmeldung mit dem berechtigten ChatGPT-Konto ist erforderlich. Den sichtbaren Versionsstand und die Neuerungen findest du im Kopfbereich beziehungsweise unter Hilfe.

## Starten

**Windows-Paket:** Sofern ein zum aktuellen Branch gehörendes 2.2-Paket vorliegt, die enthaltene AstroForge-Lite-EXE öffnen. Der Starter bringt seine Laufzeit und Web-Dateien mit und öffnet den Standardbrowser. Die feste lokale Adresse ist `http://127.0.0.1:4174/`; bei belegtem Port wird eine alternative Adresse angezeigt, deren Autosave getrennt ist. Dieser Server ist nur auf dem Windows-Rechner erreichbar. Ein älteres 2.0-Paket erhält die neuen Funktionen nicht automatisch. Paket- und Prüfnachweise stehen in `VALIDATION.md`.

**Windows aus dem Quellprojekt:** Node.js installieren, anschließend `Start-AstroForge.cmd` öffnen. Das Skript erstellt die Browserdateien, startet den lokalen Server und öffnet [AstroForge Lite](http://localhost:4173). Das Serverfenster während der Nutzung geöffnet lassen. Ein zusätzliches Paket-Installieren ist nicht erforderlich.

Alternativ im Ordner `lite`:

```powershell
npm test
npm run build
npm start
```

Der Entwicklungsstand wurde mit Node.js 25.9.0 erstellt. Die Anwendung hat keine externen Laufzeitpakete und lädt keine Schriftarten oder Bibliotheken von einem CDN.

**Android:** Die [AstroForge-Site](https://astroforge-2-lite.marcusmohren.chatgpt.site) im Browser öffnen und anmelden.

**Alternativ im lokalen Netzwerk:** Den Node-Server mit `npm run build` und `npm start` auf Windows starten. Das Handy mit demselben Netzwerk verbinden und im Browser `http://<Windows-Netzwerkadresse>:4173` öffnen, beispielsweise mit der IPv4-Adresse des WLAN-Adapters aus `ipconfig`. Der Windows-Firewallzugriff für diesen lokalen Server muss im verwendeten Netzwerk erlaubt sein. `localhost` auf dem Handy bezeichnet das Handy, nicht den Windows-Rechner. Die EXE auf Port 4174 ist dafür nicht geeignet, weil sie nur an die lokale Loopback-Adresse bindet.

Android verwendet die responsive Browseroberfläche, keine native APK. Installation und Service-Worker-Offlinefunktionen sind über eine einfache HTTP-Netzwerkadresse nicht verfügbar; die Vorführung über diesen Weg benötigt den laufenden Windows-Server. GitHub stellt den Quellcode bereit und ist hier kein automatisch eingerichtetes HTTPS-App-Hosting.

## Der erste Entwurf

1. Über **Vorlage** eine der drei Architekturen wählen. Alle starten mit 10 kN idealem Hauptschub und 30 bar Kammerdruck. Die Kühlungs-Vorlagen verwenden O/F 2,0, L* 0,5 m und 0,75 mm Kanalhöhe; neue einzeln hinzugefügte Kühlmäntel starten mit 2 mm Höhe.
2. Unter **Triebwerksentwurf** die Ziele bearbeiten. Auf dem Handy zwischen **Bauteile**, **System**, **Details** und **Ergebnisse** wechseln.
3. Komponenten anklicken und ihre Parameter im Inspector ändern. Zum Verschieben am Bauteil ziehen; zum Verbinden zuerst einen Ausgangsport, dann einen Eingangsport anklicken.
4. Die Oxidator- oder Brennstoff-Section öffnen, um deren Teile näher zu bearbeiten. Der Brotkrumenpfad führt zurück zum Gesamtsystem.
5. **Berechnen** ausführen. Die Auswertung zeigt ideale Leistung, vorläufige Geometrie und erforderliche Versorgungsdrücke.
6. Das Projekt mit **Speichern** als JSON-Datei sichern. **Öffnen** übernimmt die Datei auch auf einem anderen Gerät.

Eine neue Fluidkomponente wird zunächst unverbunden angelegt. Im Inspector unter **In Versorgungspfad einsetzen** die passende Verbindung wählen und **In Leitung einsetzen** betätigen. Alternativ die vorhandene Verbindung trennen und beide neuen Verbindungen über die Ports herstellen. Pumpen und Turbinen erhalten zusätzlich im Feld **Antriebswelle** eine vorhandene Welle. Die mechanische Zuordnung ist keine Fluidleitung. **Rückgängig** stellt Änderungen wieder her. Grafisches Verschieben verändert die physische Leitungslänge nicht.

## Die drei Vorlagen

| Vorlage | Enthaltene Modelle |
|---|---|
| AF–01 / Pressure-fed | Zwei druckgeförderte Versorgungspfade mit Injektor, Kammer und Glockendüse |
| AF–02 / Electric + Regen | Zwei Pumpen, gemeinsamer externer Wellenantrieb und ein geometriegekoppelter Kühlmantel |
| AF–03 / Turbine drive | Pumpen, Welle, Kühlmantel sowie separate Treibgasquelle, Turbine und Abgasdüse |

Die dritte Vorlage ist kein vollständig geschlossener Gasgeneratorzyklus: Der Treibgaszustand und sein zusätzlicher Massenstrom werden separat vorgegeben. Das System-Isp berücksichtigt diesen zusätzlichen Verbrauch.

## Umfang

- Zwei getrennte, unverzweigte Versorgungspfade bis zum Injektor; anschließend eine Kammer und eine Düse.
- Versorgung, Leitung, einfaches Ventil und ideale Messstelle; definierte Verlustannahmen am Injektor.
- Pumpen mit vorgegebener Druckerhöhung und Wellenzuordnung; Antrieb mit Leistung, Wirkungsgrad und Drehzahl.
- Ein regenerativer Kühlmantel mit rechteckigen Kanälen entlang der Kammer-/Düsenkontur; berechnete Wärmeaufnahme, Wandtemperaturen und Druckverlust.
- Temperatur-, Wärmestrom- und statisches Kühlmitteldruckprofil mit Stationsauswahl und eigenem CSV-Export. Ältere Wärmebilanzblöcke bleiben beim Import erhalten.
- Ein separater, unverzweigter Treibgaszweig von einer Gasquelle über eine Turbine zu einer Abgasdüse.
- Zwei vorgegebene Sections: Oxidator und Brennstoff. Keine beliebig verschachtelte Subsystembibliothek.
- Lokales Autosave, Projektdateien, Undo/Redo sowie CSV- und JSON-Ergebnisexport.
- Berechnung in einem Browser-Worker. Entwurfsänderungen markieren bestehende Ergebnisse als veraltet.

Die stationäre Rechnung ermittelt aus den Entwurfszielen die Hauptmassenströme und rechnet die benötigten Versorgungsdrücke aus Verlusten und Pumpendruckerhöhungen rückwärts. Zusätzlich wird der Pumpenleistungsbedarf je Welle gegen Turbinenleistung und externen Antrieb geprüft. Zu wenig Druck oder Wellenleistung macht den Zielentwurf nicht erfüllbar. Reserven bedeuten notwendige Anpassung; weder ein realer Betriebspunkt noch ein Drehzahlgleichgewicht werden automatisch gelöst.

Die Hauptkennwerte bleiben die idealen Werte des Haupttriebwerks. Bei vorhandenem Treibgaszweig ergänzt die Cycle-Auswertung **Gesamtschub** und **System-Isp** aus Haupttriebwerk, Abgasdüse und gesamtem Massenverbrauch. Diese Größen dürfen nicht mit dem Haupttriebwerks-Isp verwechselt werden.

## Rechenmodelle und Grenzen

| Bereich | Lite-Modell |
|---|---|
| Thermochemie | Interpolation von 392 vorab mit RocketCEA 1.2.3 erzeugten Zuständen; kein laufender CEA-Solver im Browser |
| CEA-Einlasszustände | Feste Reaktantentemperaturen der Stoffkarten: RP-1 298,15 K, LOX 90,18 K |
| Datenbereich | Kammerdruck 10–80 bar, O/F 2,0–3,2, Expansion 4–40 |
| RP-1-Versorgung ohne Kanalmodell | Konstante Screeningwerte: Dichte 810 kg/m³, dynamische Viskosität 0,0018 Pa·s; Temperatur 288–303 K |
| LOX-Versorgung | Konstante Screeningwerte: Dichte 1.140 kg/m³, dynamische Viskosität 0,0002 Pa·s; Temperatur 85–95 K |
| Versorgungstemperatur | Außerhalb der Kühlung isotherm; Wärmeaufnahme im Kühlmantel verändert den Brennstoffzustand, jedoch nicht die CEA-Verbrennungschemie |
| Pumpe | Inkompressible Druckarbeit mit vorgegebener Druckerhöhung und Wirkungsgrad; keine Kennlinie oder Kavitation |
| Welle | Pumpenbedarf gegen Turbinenleistung nach mechanischem Wirkungsgrad plus externe, bereits an der Welle verfügbare Leistung; Drehmoment aus vorgegebener Drehzahl |
| Kanalkühlung | Stationäres 1D-Gegenstrommodell, Bartz-Gasseite mit eingefrorenen CEA-Kammertransportwerten, Wandwärmeleitung und Kanalströmung mit Rippenwirkung |
| Brennstoff mit Kanalmodell | Temperatur-/druckabhängiges n-Dodecan als RP-1-Ersatzstoff im gesamten Brennstoffpfad; CoolProp-Tabelle 288–633 K / 1–200 bar, ausschließlich gültige einphasige Tabellenzellen |
| Älterer Kühlblock | Vorgegebener Wärmestrom, Druckverlust und cp bleiben erhalten; explizite Umstellung im Inspector aktiviert Kanalparameter |
| Turbine | Idealgas-Expansion bei konstantem cp und γ sowie vorgegebenen Ein-/Austrittsdrücken und Wirkungsgrad |
| Abgasdüse | Zusätzlicher Impuls- und Druckschub aus dem separaten Treibgasstrom; keine optimierte Kontur oder Ablösung |
| Geometrie | Vorläufige Kammer-/Düsenkontur mit glatter kubischer Glockenapproximation; keine validierte Rao-Auslegung |

Lite enthält keinen allgemeinen Netzsolver, keinen vollständigen Gasgenerator-/Expander-/Staged-Combustion-Abschluss, keine Transienten, reale Off-design-Lösung, Strahlung, axiale Wandleitung, Siedung, Verkokung, Struktur- oder Lebensdauernachweise. Der angezeigte Abstand zur Wandgrenze vergleicht die Modelltemperatur mit einer vom Nutzer eingegebenen Grenze; er ist keine geprüfte Werkstoffzulässigkeit. n-Dodecan ist kein qualifiziertes RP-1-Gemischmodell. Die Ergebnisse dienen dem Vorentwurf und sind keine Zertifizierung oder Freigabe zur Fertigung beziehungsweise Erprobung.

## Kühlkanäle bearbeiten

In **Pumpen & Kühlung** den Kühlmantel auswählen. Kanalanzahl, -höhe, Umfangsteilungsanteil, Wanddicke, Wärmeleitfähigkeit und Rauheit bearbeiten. Kanalbreite und Länge folgen der bestehenden Kammer-/Düsenkontur; der Massenstrom kommt aus dem Brennstoffpfad. Wärmeaufnahme und Druckverlust werden im Kanalmodus berechnet, nicht eingegeben.

Nach **Berechnen** über **Temperaturprofil & Kanalwerte** die heiße und kalte Wand sowie das Kühlmittel entlang der Achse betrachten. Zwischen Temperatur, Wärmestromdichte und statischem Kühlmitteldruck wechseln. Eine Station auswählen und bei Bedarf die Kanaldaten als CSV exportieren. Die Kurven laufen in Gasströmungsrichtung; das Kühlmittel strömt vom Düsenaustritt zurück zur Kammer. Eine Überschreitung der eingegebenen Wandgrenze bleibt als Warnstatus sichtbar. Außerhalb der Stoffdaten oder bei fehlender Konvergenz gibt es kein gültiges Ergebnis.

Alte Projekte behalten ihren aufgeprägten Wärmebilanzblock. **Auf Kühlkanäle umstellen** ersetzt dessen Parameter ausdrücklich; die Änderung ist rückgängig machbar. Es ist höchstens ein Kanalmodell je Projekt erlaubt.

## Speicherung und Offline-Nutzung

Autosave bleibt im Browserspeicher dieses Geräts. Browserdaten löschen oder ein anderes Browserprofil verwenden kann diesen Stand entfernen. Eine gespeicherte Projektdatei ist der vorgesehene Weg für Sicherung und Gerätewechsel. Ergebnisexporte beziehen sich auf den berechneten Stand; nach einer Änderung zuerst neu rechnen.

Die Anwendung enthält ein Manifest und einen Service Worker. Nach einem vollständigen Laden in einem unterstützten sicheren Kontext können Anwendungsdateien zwischengespeichert werden. Browserinstallation und Offlineverhalten hängen vom Zugriffsweg ab. Der Android-LAN-Zugriff über HTTP benötigt weiterhin den laufenden Server. Den tatsächlich verwendeten Vorführweg daher vor Ort prüfen.

Der bisherige 2.0-Stand wurde auf Desktop und in mobiler Browseremulation sowie lokal offline geprüft. Diese Nachweise sind nicht automatisch eine Abnahme aller neuen 2.2-Cycle-Funktionen. Ein physisches Android-Handy wurde bisher nicht getestet. Aktuelle Prüfstände stehen in `VALIDATION.md`; der [Vorführablauf](DEMO.md) erklärt die neuen Komponentenmodelle.

## Prüfnachweise

Automatisierte Tests laufen mit `npm test`. Den tatsächlichen Umfang und Status der numerischen, Browser- und Paketprüfungen dokumentiert `VALIDATION.md`. CEA-Vergleichsstichproben sind keine globale Fehlergrenze oder experimentelle Validierung; der zusätzliche Cycle-Umfang benötigt eigene Nachweise.
