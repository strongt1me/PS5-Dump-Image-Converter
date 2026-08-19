# PS5 Dump & Image Converter v1.8.59 – Release Notes

## Zweck dieses Releases

Die Erstinstallation auf dem Mac verlangte bisher Handarbeit in den Systemeinstellungen. Das war unnötig — das Nötige lag längst im Projekt, kam nur nie beim Nutzer an.

Dazu die Schriftgröße auf dem Mac, jetzt gemessen statt geschätzt.

---

## 1. Die Erstinstallation auf dem Mac

### Was schiefging

`Install_macOS.sh` entfernt die Quarantäne-Markierung seit jeher:

```bash
xattr -dr com.apple.quarantine "$ZIEL" 2>/dev/null
```

Das Abbild wurde aber so gebaut:

```bash
hdiutil create -srcfolder "$BUENDEL" …
```

`$BUENDEL` ist allein die `.app`. **Der Installer lag im Repository, nicht im `.dmg`.** Wer die App von Hand herauszog — der naheliegende Weg —, behielt die Markierung, und macOS blockierte den Start.

### Was jetzt im Abbild liegt

| Datei | Zweck |
| --- | --- |
| `PS5 Dump & Image Converter.app` | das Programm |
| `Erste Installation.command` | Doppelklick: kopiert und entfernt die Markierung |
| `Applications` (Verknüpfung) | für alle, die lieber ziehen |

Nötig ist das **einmal pro heruntergeladener Fassung**, nicht bei jedem Start. Die Markierung setzt macOS beim Herunterladen; ist sie einmal weg, bleibt sie weg.

**Was ich nicht versprechen kann:** Ob macOS die `.command`-Datei aus einem unsignierten Abbild ohne Rückfrage ausführt, ließ sich von Windows aus nicht prüfen. Möglicherweise ist dabei noch ein „Öffnen"-Klick nötig — dann immerhin einer statt des Umwegs über die Systemeinstellungen.

### Ganz ohne Nutzeraktion geht es nicht

Der Warndialog von macOS ist keine Fehlfunktion, sondern Gatekeeper. Er verschwindet nur durch **Notarisierung** bei Apple, und die verlangt ein Entwicklerkonto (99 $/Jahr) samt Signaturzertifikat. Das ist eine Entscheidung des Projektinhabers, keine technische Frage.

---

## 2. App Translocation — der stille Befund

Im Protokoll vom 19.08.2026 stand der mkpfs-Pfad so:

```text
/private/var/folders/2k/…/T/AppTranslocation/7997DEE9-…/d/PS5 Dump & Image Converter.app/…
```

**`AppTranslocation`**: Solange die Markierung dranhängt, führt macOS das Programm nicht von seinem eigentlichen Ort aus, sondern aus einer zufällig benannten, schreibgeschützten Kopie. Es läuft — aber Einstellungen und Protokolle liegen in einem Ordner, den das System beim Beenden wegräumt.

Das erklärt vermutlich einiges, was vorher unerklärlich wirkte. Das Programm erkennt den Zustand jetzt beim Start, sagt es in einem Hinweisfenster mit der Lösung, und führt ihn im Diagnosebericht als eigene Zeile.

---

## 3. Schrift auf dem Mac: gemessen statt geschätzt

Der Diagnosebericht lieferte die Zahlen:

| | Rechnung | Ergebnis |
| --- | --- | --- |
| Windows | 9 pt × `tk scaling` 1,6683 | **15,0 px** |
| macOS mit 1,35 | 9 pt × `tk scaling` 1,3499 | **12,1 px** |

Der Schätzwert 1,35 war um ein Fünftel zu klein. Der Faktor steht jetzt auf **1,65** — 14,8 px, praktisch gleichauf mit Windows. Über `macos_font_scaling` in der Einstellungsdatei weiterhin ohne neuen Bau änderbar.

---

## 4. Der Diagnosebericht sagt jetzt, was gezeichnet wurde

Bisher stand dort `Hintergrundbild: (1424, 752)`. Nachgesehen: **das ist die Größe der Bilddatei** `bg_19_ray-burst.png`. Die Zeile sagte also nur, welches Bild geladen ist — nicht, ob die Anpassung an das Fenster funktioniert.

Neu:

```text
Hintergrundbild (gezeichnet): …x…
Inhaltsflaeche (gezeichnet):  …x…
Seitenleiste (gezeichnet):    …x…
zuletzt angepasst auf:        (…, …)
```

Damit ist beim nächsten Bericht entscheidbar, ob die Bildanpassung stehenbleibt — die bisherige Zeile konnte das nicht.

---

## 5. Ein falsches Anführungszeichen in einer Meldung

Alle **2600** sichtbaren Texte durchgezählt. Eine Fundstelle, in einem Dialogfenster:

```text
Neben dem Ordner existiert bereits „{name}". Bitte einen anderen Namen wählen.
                                          ↑ typografisch geöffnet, gerade geschlossen
```

Berichtigt. Eine Prüfung wacht künftig darüber und kennt beide Sprachen: Deutsch öffnet mit `„` und schließt mit `“`, Englisch öffnet mit `“` und schließt mit `”`; ein gerades `"` daneben ist fast immer ein Versehen.

---

## Tests

**826 Prüfungen, 0 Fehlschläge.** Neu: fünf zur Translokation und zum Installer im Abbild, zwei zu den Anführungszeichen.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.59.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.59_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.59_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.59_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.59.sha256` | Prüfsummen aller Quelldateien |
