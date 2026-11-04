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
