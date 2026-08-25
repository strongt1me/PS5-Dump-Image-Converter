## Was ist neu

**Die Oberfläche lässt sich auf eine Farbsehschwäche einstellen.**

Rund sechs von hundert Männern können Rot und Grün nicht zuverlässig
unterscheiden. Für sie sahen Erfolg, Warnung und Fehler bisher ähnlich aus —
im hellen Design waren Warnung und Fehler praktisch nicht auseinanderzuhalten.

* **Neue Auswahl in den Einstellungen:** Keine · Deuteranopie (Grünschwäche,
  am häufigsten) · Protanopie (Rotschwäche) · Tritanopie (Blauschwäche) ·
  Achromatopsie (kein Farbsehen).
* **Wirkt sofort**, ohne Neustart.
* **Geändert werden nur die Farben, die eine Bedeutung tragen** — Erfolg,
  Warnung, Fehler. Hintergründe, Schrift und das gewählte Design bleiben, wie
  sie sind.

Der Gedanke dahinter ist nicht „andere Farben“, sondern eine andere Richtung:
Rot gegen Grün ist genau die Achse, die bei den häufigen Formen ausfällt. Blau
gegen Gelb bleibt erhalten — Erfolg wird deshalb türkis statt grün. Dazu kommt
Helligkeit als zweites Merkmal, das auch dort trägt, wo gar keine Farbe
wahrgenommen wird.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.97.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.97_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.97_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.97_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.97.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1503 Tests grün. Die Farbwahl ist nicht geschätzt, sondern gerechnet: Für jede
der zwölf Kombinationen aus Design und Farbschwäche wird der Abstand zwischen
den bedeutungstragenden Farben gemessen — zuvor lagen neun davon unter der
Schwelle, jetzt keine mehr. Ein Test prüft zusätzlich, dass der frühere Zustand
durchfallen würde; sonst wäre die Messung wertlos.

Bei **Achromatopsie** bleibt eine Grenze, die keine Farbwahl aufhebt: Dort
zählt nur Helligkeit, und vier gleichzeitig lesbare Stufen gibt der verfügbare
Bereich nicht her. Wo das zutrifft, trägt Text die Aussage — im Protokoll,
beim Verbindungsstatus und in der Bauform-Anzeige steht sie ohnehin
ausgeschrieben.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.96...v1.8.97
