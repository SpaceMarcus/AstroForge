# Logikprüfung · AstroForge Lite

Stand: 2026-11-04. Geprüft wurden Originaltopologie gegenüber intern expandierten Feedlines, Solverwahl, Kühlstreckenauswahl, Massenbilanz, Druckbudgets, Stoffauswahl und Exportkonsistenz. Dies ist eine Software-Konsistenzprüfung, keine experimentelle Validierung der physikalischen Modelle.

## Behobene Befunde

1. **Manifold-Grenzen gingen im seriellen Solver verloren.** Normale Feedline-Pfeile werden intern zu Leitungsknoten. Dadurch erkannte die Kühlung den direkt angeschlossenen Manifold nicht mehr. Der Solver erhält jetzt die Originaltopologie separat. Regression: Manifold bei 75 % ergibt auch in der Rechnung Kühlende 75 % statt 100 %.
2. **Mehrere serielle Kühlstrecken wurden trotz getrennter Wandbereiche abgewiesen.** Projekte mit mehreren Kanalstrecken verwenden jetzt den vorhandenen Mehrstrecken-Netzsolver. Überlappungen werden vor dem thermischen Rechnen ausdrücklich abgewiesen, damit kein Folgefehler durch doppelte Erwärmung die Ursache verdeckt.
3. **Unbekannte Kühlungsmodi wurden in verzweigten Projekten still als Wärmebilanz behandelt.** Beide Rechenwege weisen unbekannte Modi jetzt ab.
4. **Manifold-Auswahl zeigte bei mehreren Kühlmänteln den ersten Mantel.** Die Geometrieansicht wählt nun zuerst den direkt ausgewählten, danach den angeschlossenen Kühlmantel. Bei mehreren direkt verbundenen Mänteln bleibt eine deterministische erste Auswahl; jeder Mantel kann separat ausgewählt werden.
5. **Fiktive Referenzleitungen konnten die Hauptauslegung eines realen Netzes begrenzen.** Die Referenz für Thermochemie/Geometrie verwendet nun große ideale Leitungen. Die realen Durchmesser und Druckverluste werden ausschließlich im tatsächlichen Netz bewertet.
6. **Treibstoffauswahl darf keine stillen RP-1-Ersatzrechnungen auslösen.** Jede neue Kombination benötigt ihr eigenes gekennzeichnetes CEA-Datenfeld und beide Fluidmodelle. Fehlende/falsche Daten werden abgewiesen. Bestehende Projekte ohne Stoffauswahl behalten LOX/RP-1.
7. **Neue Fluidzustände benötigen zusammenpassende Grenzen.** Eintrittstemperatur, verfügbarer Quelldruck und erforderlicher statischer Druck werden gegen die jeweiligen Screeninggrenzen geprüft. Bei konstanten Fluiddaten darf ein Wärmebilanzblock den Temperaturbereich nicht verlassen. Kühlkanäle sind nur für ausdrücklich unterstützte Stoffkombinationen mit passender Tabelle zulässig.

8. **Sections beeinflussten die Zulässigkeit desselben Fluidnetzes unterschiedlich.** Beide Solver prüfen nur noch gültige Gruppennamen. Die Anzeigegruppe ändert weder Medium noch Rechenwerte; der Ergebnisfingerabdruck berücksichtigt sie nicht mehr.

## Modellvertrag und verbleibende Grenzen

- Injektor und Verbraucher geben die Teilströme vor. Rückwärts summierte Massenbedarfe und zusätzliche Zweig-Drosselverluste sind ein Auslegungsbudget, kein automatisch gelöster passiver Betriebspunkt.
- Source-Druckreserve bedeutet nötige Druckanpassung oder verfügbare Reserve; sie wird nicht automatisch in einen anderen Massenstrom umgesetzt.
- Neue konstante Fluidmodelle sind eng begrenzte Screeningwerte. Die minimale Druckgrenze orientiert sich am oberen Temperaturende, nicht an einer vollständigen lokalen Phasenrechnung. NPSH, Kavitation, Sieden und Zweiphasenströmung sind nicht nachgewiesen.
- Preburner und Film bleiben Massenstrom-/Druckrandbedingungen. Keine Preburner-Chemie, Filmwärmeabschirmung oder daraus abgeleiteter Zusatzschub.
- Stofftemperaturen im Feed ändern die vorab berechnete CEA-Reaktantenenthalpie nicht. Kanalwärme wird nicht erneut in die Verbrennungschemie zurückgekoppelt.
- Zusammenführungen, Rückführschleifen und überlappende Kühlflächen bleiben abgewiesen. Nicht gekühlte Wandbereiche werden nicht thermisch freigegeben.
- Ein Manifold mit mehreren angeschlossenen Mänteln wählt in der Geometrieansicht zunächst einen davon; die Einzelselektion entscheidet über die aktive Strecke.
- Sections sind reine Anzeigegruppen. Die physikalische Medienzuordnung bleibt eine eigene Bauteileigenschaft.

## Prüfnachweise

Regressionen in `tests/network.test.js` prüfen Manifold-Grenzen, zwei serielle und zwei parallele Teilstrecken, Massen-/Energieabschluss, Verengungen und Modusvalidierung. `tests/propellant-physics.test.js` prüft alle ausgewählten Kombinationen, Datenidentität, Methan-Abzweige samt unabhängiger hydraulischer Vergleichsrechnung und unzulässige Stoffzustände. Der abschließende Gesamtstatus steht in `VALIDATION.md`.


Abschließender automatisierter Lauf dieses Audits: **111/111 Tests bestanden**. Alle elf Kombinationen lösen den begrenzten Druckförder-Referenzpunkt mit ihren eigenen Daten. Ethanol-Kühltests für LOX, N₂O und HTP 90 % verwenden getrennte Gasrandbedingungen und 4 kg/s durch die hintere Konturhälfte; Energieresiduen jeweils unter 0.005 W. Die Tests liefern keinen Vergleich mit experimentellen Triebwerksdaten. Browser- und Veröffentlichungsprüfung erfolgen im Hauptarbeitsgang.
