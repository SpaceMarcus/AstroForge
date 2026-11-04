# AstroForge 2.0 Lite

Ein lokaler Arbeitsraum für den stationären Vorentwurf eines druckgeförderten LOX/RP-1-Triebwerks. Komponenten, Versorgungspfade und Brennkammer-/Düsengeometrie gehören zum selben Projekt. Die Oberfläche funktioniert im Windows-Browser und passt sich Android-Handys an.

## Starten

**Windows ohne Installation:** `AstroForge-2.0-Lite.exe` aus dem Vorführpaket öffnen. Der Starter bringt seine Laufzeit und alle Web-Dateien mit und öffnet die Oberfläche im Standardbrowser. Die feste lokale Adresse ist `http://127.0.0.1:4174/`; das Starterfenster verwaltet den Server. Bei belegtem Port wird eine alternative Adresse angezeigt, deren Autosave getrennt ist. Die EXE ist noch nicht signiert; eine Abnahme auf einem sauberen Windows-PC steht aus.

**Windows aus dem Quellprojekt:** Node.js installieren, anschließend `Start-AstroForge.cmd` öffnen. Das Skript erstellt die Browserdateien, startet den lokalen Server und öffnet [AstroForge Lite](http://localhost:4173). Das Serverfenster während der Nutzung geöffnet lassen. Ein zusätzliches Paket-Installieren ist nicht erforderlich.

Alternativ im Ordner `lite`:

```powershell
npm test
npm run build
npm start
```

Der Entwicklungsstand wurde mit Node.js 25.9.0 erstellt. Die Anwendung hat keine externen Laufzeitpakete und lädt keine Schriftarten oder Bibliotheken von einem CDN.

**Android:** Die gehostete Browseradresse verwenden. Veröffentlichte private Adresse: [AstroForge 2.0 Lite](https://astroforge-2-lite.marcusmohren.chatgpt.site). Privater Zugriff ist keine öffentliche Kundenfreigabe und kann eine Anmeldung benötigen.

Optional kann ein Handy im selben Netzwerk den lokalen Windows-Server über dessen Netzwerkadresse und Port 4173 öffnen. `localhost` auf dem Handy bezeichnet das Handy, nicht den Windows-Rechner. Installation und Offlinefunktionen sind über eine einfache HTTP-Netzwerkadresse nicht verlässlich verfügbar; dafür HTTPS-Hosting verwenden.

## Der erste Entwurf

1. Die Vorlage **AF–01 / Pressure-fed** öffnet ein Triebwerk mit 10 kN Zielschub, 30 bar Kammerdruck und O/F 2,6.
2. Unter **Triebwerksentwurf** die Ziele bearbeiten. Auf dem Handy zwischen **Bauteile**, **System**, **Details** und **Ergebnisse** wechseln.
3. Komponenten anklicken und ihre Parameter im Inspector ändern. Zum Verschieben am Bauteil ziehen; zum Verbinden zuerst einen Ausgangsport, dann einen Eingangsport anklicken.
4. Die Oxidator- oder Brennstoff-Section öffnen, um deren Teile näher zu bearbeiten. Der Brotkrumenpfad führt zurück zum Gesamtsystem.
5. **Berechnen** ausführen. Die Auswertung zeigt ideale Leistung, vorläufige Geometrie und erforderliche Versorgungsdrücke.
6. Das Projekt mit **Speichern** als JSON-Datei sichern. **Öffnen** übernimmt die Datei auch auf einem anderen Gerät.

Eine neue Komponente wird zunächst unverbunden angelegt. Zum Einfügen in einen Pfad die vorhandene Verbindung im Inspector trennen und beide neuen Verbindungen herstellen. **Rückgängig** stellt Änderungen wieder her. Grafisches Verschieben verändert die physische Leitungslänge nicht.

## Umfang

- Zwei getrennte, unverzweigte Versorgungspfade bis zum Injektor; anschließend eine Kammer und eine Düse.
- Versorgung, Leitung, einfaches Ventil und ideale Messstelle; definierte Verlustannahmen am Injektor.
- Zwei vorgegebene Sections: Oxidator und Brennstoff. Keine beliebig verschachtelte Subsystembibliothek.
- Lokales Autosave, Projektdateien, Undo/Redo sowie CSV- und JSON-Ergebnisexport.
- Berechnung in einem Browser-Worker. Entwurfsänderungen markieren bestehende Ergebnisse als veraltet.

Die stationäre Rechnung ermittelt aus den Entwurfszielen die Massenströme und rechnet anschließend die benötigten Versorgungsdrücke rückwärts aus den Verlusten. Zu wenig verfügbarer Druck macht den Entwurf nicht erfüllbar. Eine Druckreserve bedeutet erforderliche Druckanpassung; sie ist kein automatisch gelöster realer Betriebspunkt.

## Rechenmodelle und Grenzen

| Bereich | Lite-Modell |
|---|---|
| Thermochemie | Interpolation von 392 vorab mit RocketCEA 1.2.3 erzeugten Zuständen; kein laufender CEA-Solver im Browser |
| CEA-Einlasszustände | Feste Reaktantentemperaturen der Stoffkarten: RP-1 298,15 K, LOX 90,18 K |
| Datenbereich | Kammerdruck 10–80 bar, O/F 2,0–3,2, Expansion 4–40 |
| RP-1-Versorgung | Konstante Screeningwerte: Dichte 810 kg/m³, dynamische Viskosität 0,0018 Pa·s; Temperatur 288–303 K |
| LOX-Versorgung | Konstante Screeningwerte: Dichte 1.140 kg/m³, dynamische Viskosität 0,0002 Pa·s; Temperatur 85–95 K |
| Versorgungstemperatur | Vorgegebene isotherme Annahme; keine gelöste Erwärmung und keine Kopplung der editierbaren Versorgungstemperatur an die CEA-Thermochemie |
| Geometrie | Vorläufige Kammer-/Düsenkontur mit glatter kubischer Glockenapproximation; keine validierte Rao-Auslegung |

Lite enthält keinen allgemeinen Netzsolver, keine Pumpen-/Turbinenzyklen, Transienten, reale Off-design-Lösung, Detailkühlung, Struktur- oder Lebensdauernachweise. Die Ergebnisse dienen dem Vorentwurf und sind keine Zertifizierung oder Freigabe zur Fertigung beziehungsweise Erprobung.

## Speicherung und Offline-Nutzung

Autosave bleibt im Browserspeicher dieses Geräts. Browserdaten löschen oder ein anderes Browserprofil verwenden kann diesen Stand entfernen. Eine gespeicherte Projektdatei ist der vorgesehene Weg für Sicherung und Gerätewechsel. Ergebnisexporte beziehen sich auf den berechneten Stand; nach einer Änderung zuerst neu rechnen.

Ein lokaler Offline-Test wurde bestanden: Nach Abschalten des Entwicklungsservers ließ sich die Anwendung aus dem Browsercache neu laden und erneut berechnen. Das belegt nicht automatisch das Offlineverhalten der privaten Hosting-Anmeldung.

Die Anwendung enthält ein Manifest und einen Service Worker. Nach einem vollständigen Laden in einem unterstützten sicheren Kontext können die Anwendungsdateien zwischengespeichert werden. Die Installation über das Browsermenü hängt vom Browser ab. Privates Hosting kann für Anmeldung und Zugriff weiterhin Internet benötigen; die Vorführung daher vor Ort auf dem tatsächlich eingesetzten Gerät prüfen.

Der Browserablauf wurde mit 1.440 × 900 Pixeln und einer mobilen Emulation mit 390 × 844 Pixeln geprüft: Unterversorgung, veraltete Ergebnisse, Fehler bei geschlossenem Ventil, Undo, Section-Navigation sowie Trennen und Wiederverbinden. Dabei wurden keine Konsolenfehler beobachtet. Ein physisches Android-Handy wurde nicht getestet. Für die STE empfiehlt sich die [fünfminütige Vorführung](DEMO.md) mit einem zuvor geladenen und gespeicherten Referenzprojekt.

## Prüfnachweise

31 automatisierte Tests für Rechenkern, Graph-Hilfen, Import, Verlauf und Integration bestanden. Zusätzlich wurden 252 CEA-Zellmittelpunkte gegen direkte Backend-Rechnungen geprüft; größte beobachtete Abweichungen: c* 0,184 %, Cf 0,429 %, Tc 0,464 %, Austrittsdruck 0,650 %. Dies sind Stichprobenwerte, keine globale Fehlergrenze oder experimentelle Validierung. Der Windows-Starter wurde als Python-Programm und als gebündelte EXE im Smoke-Test geprüft. Details in `VALIDATION.md`.
