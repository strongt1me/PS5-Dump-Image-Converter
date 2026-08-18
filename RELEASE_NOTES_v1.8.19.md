# PS5 Dump & Image Converter v1.8.19 – Release Notes

## Zweck dieses Releases

Version **v1.8.19** korrigiert einen Design-spezifischen Kontrastfehler bei der in v1.8.18 fertiggestellten Kartenbild-Darstellung: Im hellen Design wirkte die Quelle-Karte durch das Hintergrundbild unnötig dunkel-gräulich statt hell.

## Ausgangslage

Nach der Rückfrage, ob die in v1.8.18 behobene Beschriftungs-Kasten-Darstellung auch in allen drei Farbdesigns korrekt sei, wurde live in allen drei Designs (Dunkel, Mittel, Hell) geprüft. Dunkel und Mittel waren bereits korrekt. Im hellen Design zeigte sich jedoch: Die Quelle-Karte (eigentlich weiß, `bg_card = #FFFFFF`) wurde mit derselben Deckkraft (50 %) wie in den dunklen Designs mit dem Hintergrundbild gemischt. Da das voreingestellte Hintergrundbild überwiegend dunkel ist, ergab diese Mischung eine spürbar dunkel-gräuliche Karte statt einer hellen – ein Kontrastbruch zum Rest der hellen Oberfläche, der in den dunklen Designs naturgemäß nicht auffällt.

## Änderung

### Design-abhängige Deckkraft für das Kartenbild

Eine neue Konstante `BG_CARD_IMAGE_OPACITY_LIGHT` (18 %) wird ausschließlich im hellen Design für die Kartenbild-Mischung verwendet; Dunkel und Mittel bleiben unverändert bei `BG_CARD_IMAGE_OPACITY` (50 %). Die Auswahl erfolgt zur Laufzeit anhand des aktuell aktiven Designs (`self._current_theme`) in `_blend_bg_image_for_card`. Das betrifft sowohl die Kartenfläche selbst als auch die in v1.8.18 eingeführten Beschriftungs-Bildausschnitte (QUELLE, ZIELFORMAT usw.), da beide dieselbe Blend-Funktion nutzen.

## Bedeutung für Nutzer

Im hellen Design bleibt die Quelle-Karte jetzt überwiegend hell/weiß mit nur einem dezenten Hauch Bildstruktur, statt spürbar dunkel-gräulich zu wirken. Dunkles und mittleres Design zeigen weiterhin dasselbe, bereits abgestimmte Erscheinungsbild wie in v1.8.18.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden.
- GUI-Smoke-Test weiterhin erfolgreich.
- Zusätzliche manuelle Verifikation mit echten Bildschirmaufnahmen einer echten Tkinter-Instanz je Design (Dunkel, Mittel, Hell), aufgenommen gezielt über das Anwendungsfenster (nicht als Vollbildschirm-Screenshot, um keine anderen offenen Fenster zu erfassen): Vor der Änderung war die helle Quelle-Karte deutlich dunkler als die restliche Oberfläche (gemessene Kartenfarbe ca. RGB 108/114/132 statt erwartet nahe Weiß); nach der Änderung liegt die gemessene Kartenfarbe bei ca. RGB 177/181/192, deutlich näher am hellen Design.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.19** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
