# PS5 Dump & Image Converter v1.8.18 – Release Notes

## Zweck dieses Releases

Version **v1.8.18** rundet das in v1.8.16/v1.8.17 eingeführte Hintergrundbild ab: Die Beschriftungen (QUELLE, ZIELFORMAT usw.) zeigen keinen störenden, farblich unpassenden Kasten mehr, das Hintergrundbild in der Quelle-Karte läuft nahtlos in einem Stück durch, und ein beim Start sichtbares Wackeln der Karte ist behoben. Zusätzlich wurde ein Fenster-Anzeigefehler im Param-/Manifest-Editor korrigiert.

## Ausgangslage

Nach der Rückmeldung, dass das Hintergrundbild zwar sichtbar sei, die Beschriftungen aber weiterhin einen sichtbaren, nicht zum Bild passenden Kasten zeigten, wurde entschieden, den Text direkt auf einen passenden Bildausschnitt zu setzen statt auf eine einfarbige Fläche. Der erste Umsetzungsversuch maß die reine Textgröße jeder Beschriftung, indem das Bild kurz entfernt und danach wieder gesetzt wurde – genau dieses Entfernen/Setzen löste jedoch selbst eine Größenänderung der Karte aus, was wiederum eine erneute Neuzeichnung anstieß. Das Ergebnis war eine Endlosschleife mit sichtbarem Wackeln der Karte und dauerhaft hoher CPU-Last, bestätigt durch einen Testlauf, der nach rund 3:49 Minuten bereits 221 Sekunden CPU-Zeit verbraucht hatte.

## Änderung

### Beschriftungen ohne Kasten

Jede der fünf statischen Beschriftungen (QUELLE, ZIELFORMAT, KOMPRESSION/WORKER, ZIELORDNER, TEMP-ORDNER) bekommt jetzt über Tkinters `compound="center"` den zu ihrer Position innerhalb der Karte passenden Ausschnitt des Hintergrundbilds als eigenes Bild, auf dem der normale, weiterhin über Sprachumschaltung aktualisierbare Text liegt. Die dynamische Format-Hinweiszeile (deren Text sich je nach erkanntem Quelltyp ändert) bleibt bewusst unverändert – dort würde ein Bild-Umbau unverhältnismäßig komplex.

### Endlosschleife beim Neuzeichnen behoben

Die reine Textgröße jeder Beschriftung wird jetzt nur einmal pro Text gemessen und zwischengespeichert; nur ein tatsächlicher Sprachwechsel löst eine Neumessung aus. Bei einer reinen Fenstergrößenänderung wird ausschließlich der bereits bekannte Bildausschnitt neu zugeschnitten, nie die Textgröße neu gemessen – damit kann das Setzen des Bildes keine neue Größenänderung und damit keine neue Neuzeichnung mehr auslösen.

### Param-/Manifest-Editor korrekt dimensioniert

Das Bearbeitungsfenster für `param.json`/`manifest.json` war mit 720×560 Pixeln zu klein für seinen tatsächlichen Inhalt (Tabelle mit 14 Zeilen plus mehrere Knopfreihen), wodurch die untersten Knöpfe erst nach manuellem Maximieren sichtbar wurden. Das Fenster ist jetzt auf 780×720 Pixel vergrößert und hat eine Mindestgröße von 700×640 Pixeln.

## Bedeutung für Nutzer

Die Beschriftungen fügen sich jetzt optisch nahtlos in das Hintergrundbild ein, ohne störenden Kasten und ohne sichtbares Wackeln beim Programmstart. Der Param-/Manifest-Editor zeigt von Anfang an alle Knöpfe, ohne dass das Fenster erst vergrößert werden muss.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden.
- GUI-Smoke-Test bestätigt: läuft wieder in wenigen Sekunden durch (vorher durch die Endlosschleife über zwei Minuten hängend), alle Hintergrundbild-Prüfungen weiterhin erfolgreich.
- Zusätzliche manuelle Verifikation mit echten Bildschirmaufnahmen einer echten Tkinter-Instanz und einem auffälligen Diagonalstreifen-Testbild: Die Beschriftungen zeigen keinen Kasten mehr, das Streifenmuster läuft nahtlos durch Karte und Beschriftungen, und zwei zeitlich versetzte Aufnahmen derselben Fensterinstanz zeigen keine Größen- oder Positionsänderung mehr (kein Wackeln).
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.18** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
