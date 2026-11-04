## 2.4.0 — Cooling-Netz und Abzweige

- Eigene Cooling-Section mit Brennstoff aus dem Feed-System oder separater RP-1-Kühlversorgung.
- Abzweig, Verengung und Verbraucher mit Massenstrom- und Druckvorgabe; Kühlmittel kann nach dem Mantel zum Injektor und zu weiteren Verbrauchern abfließen.
- Manifold-Position als axialer Slider mit lokalem ε. Direkt angeschlossene Kühlstrecken übernehmen die zugehörige Eintritts-/Austrittsgrenze.
- Mehrere nicht überlappende Kühlstrecken mit getrennten Massenströmen und Gleich-/Gegenstrom.
- Leitungstooltip mit erforderlichem Druckbudget, Knotendruck und zusätzlichem Zweig-Druckabgleich.
- Neue Vorlagen „Kühlung & Abzweige“ und „Separate Kühlversorgung“.

Teilströme sind vorgegeben, keine selbsttätig berechnete passive Stromaufteilung. Preburner und Film sind Verbraucherrandbedingungen ohne Verbrennungs-/Filmwirkung. Zusammenführungen, Rückführkreise und überlappende Kühlmäntel werden abgewiesen. Bestehende Serienprojekte behalten ihren Rechenweg.

## 2.3.0 — Engine section and edge-based feedlines

- Engine section with contour, elongated jacket, axial coverage sliders and co-/counterflow.
- Turn and manifold components with explicit reference diameter and local hydraulic K loss.
- Feedline arrows replace line blocks in new workspace templates; selectable panels expose inputs and steady-state outputs.
- Explicit, reversible legacy line migration; imported cooling defaults preserve full counterflow coverage.
- Partial coverage is explicitly limited to the cooled region. Gasgenerator chemistry, gas-pipe losses, multiple cooling passes and branched networks remain outside this version.

# AstroForge Lite 2.2 · Regenerative Cooling Preview

Regenerative Kühlung wird jetzt aus Kanalgeometrie und Kammer-/Düsenkontur berechnet. Brennstoffmassenstrom und Eintrittszustand stammen aus dem Feed-System; berechneter Druckverlust und Kühlmittelaustritt wirken auf den Versorgungspfad zurück.

- Rechteckkanäle mit variabler Breite entlang des Umfangs, Rippenwirkung, Wanddicke und Wärmeleitfähigkeit.
- Bartz-Gasseite, Wandwärmeleitung, Kanal-Konvektion und Reibungs-/Beschleunigungsdruckanteile.
- Temperatur-, Wärmestrom- und Druckprofile, lokale Stationswerte und CSV-Export.
- Temperaturgrenzen, ungültige Phasen/Geometrien und Nichtkonvergenz werden sichtbar behandelt.
- Alte Wärmebilanzprojekte bleiben unverändert; explizites Upgrade im Inspector und Undo.
- Neue Electric-/Turbine-Vorlagen mit dokumentierten Kanalparametern.

82 automatisierte Tests, Desktop-/Handy-Viewport und Windows-EXE-Smoke-Test bestanden. Numerische Netzverfeinerung und Energieabschluss sind dokumentiert. Physisches Android-Gerät und sauberer Windows-PC stehen noch aus.

Windows: ZIP entpacken, `AstroForge-2.0-Lite.exe` starten. Anleitung, Beispiele, Modellbeschreibung und Screenshots liegen bei. Die EXE ist unsigniert. Android verwendet die responsive Browseranwendung über den Node-Server im gleichen Netzwerk; keine APK.

Vorentwurfsmodell: n-Dodecan ist ein RP-1-Ersatzstoff; CEA bleibt feste Gasrandbedingung ohne Rückkopplung der Brennstoffenthalpie in die Chemie. Kein Strahlungs-, Siede-, Verkokungs-, Festigkeits- oder Lebensdauernachweis. Die frühere private Site wurde nicht aktualisiert.
