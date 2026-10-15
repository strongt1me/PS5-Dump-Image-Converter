## Die neue Asset-Pack-Methode lief nur mit installiertem Python

Wer v1.9.8 als fertige Programmdatei benutzte und *Asset-Pack* wählte, bekam
sofort einen Abbruch. Zwei Gründe, beide behoben:

- Das Packwerkzeug suchte ein **Python auf dem Rechner**. Auf einem Rechner
  ohne Python-Installation gab es keines.
- Die Kompressionsbibliothek **LZ4 lag gar nicht in der Programmdatei**. Sie
  wird nur zur Laufzeit nachgeladen und fiel deshalb beim Bündeln durch.

Das Programm ruft für den Packvorgang jetzt **sich selbst** auf, statt nach
einem fremden Python zu suchen — derselbe Weg, den der PS4-Paketwandler schon
geht. Alles Nötige steckt in der Programmdatei. Es muss nichts
nachinstalliert werden.

Nachgezogen wurde außerdem, was beim Prüfen der Bündelung auffiel: sechs
weitere Module, die nur zur Laufzeit geladen werden und deshalb ebenfalls
gefehlt hätten.

## Die Fassungsliste zeigt nur noch, was zur Methode passt

Nicht jede AMPR-Fassung kann gepackte Bänder lesen. Stand *Asset-Pack*
eingestellt und daneben eine Fassung, die das nicht beherrscht, entstand ein
Spielordner, den der Emulator auf der Konsole nicht öffnen konnte — ohne dass
vorher jemand widersprochen hätte.

Jetzt richtet sich die Liste nach der Methode:

| Methode | Auswählbare Fassungen |
| --- | --- |
| Normal | alle außer `test-pack` und `test-debug-pack` |
| Asset-Pack | nur `test-pack` und `test-debug-pack` |

Die beiden pack-fähigen Fassungen tauchen in der Normal-Liste nicht mehr auf.
Sie gehören dort nicht hin.

## Fortschritt: kein Flackern, und beim Packen bewegt sich etwas

**Beim Anlegen der Arbeitskopie** flackerte die Anzeige. Grund war die
Größenangabe unter dem Balken: Sie wurde im selben Takt neu gezeichnet wie der
Balken, und jedes Neuzeichnen der Beschriftung zog das ganze Feld mit. Sie hat
jetzt einen eigenen, ruhigeren Takt.

**Beim Packen selbst** stand der Balken still. Das Packwerkzeug meldet
durchaus seinen Fortschritt, die Zeilen landeten aber nur im Protokoll. Sie
steuern jetzt den Balken.

Während der **abschließenden Prüfung** — die keine Prozentzahlen liefert,
sondern jeden Block gegen die Quelle rechnet — läuft eine Uhr mit, damit
sichtbar bleibt, dass etwas geschieht und das Programm nicht hängt.

## Ein Asset-Pack lässt sich wieder herausnehmen

Aufgabe 7 (AMPR EMU Manager) hat einen neuen Knopf. Er entfernt aus einem
Spielordner:

- das Manifest `ampr_assets.index`,
- die Laufzeitdatei `ampr_assets.runtime`,
- alle Bänder `ampr_assets-*.pak`.

Die Spieldateien bleiben unangetastet — sie lagen ohnehin einzeln daneben, das
Pack legt sich nur zusätzlich darüber. Damit lässt sich ein Backup mit
Asset-Pack in eines ohne verwandeln, ohne es aus dem Dump neu zu erstellen.

Über die Kommandozeile heißt die Aktion `--ampr-action ampr_pack_remove`.

## Die Firmware-Auswahl war bei kleinem Fenster abgeschnitten

Die Einbauzeile hat mit der Methodenliste ein sechstes Bedienelement bekommen
und passte damit nicht mehr in die Karte: Bei der kleinsten Fensterbreite
ragte die **BACKPORT-Firmware elf Pixel über den Rand** hinaus und war weder
zu sehen noch anzuklicken.

Die Methodenliste ist jetzt so breit wie ihr längster Eintrag statt zwei
Zeichen breiter. Die Zeile bleibt drin.

Eine Nebenwirkung bleibt und ist bewusst so: Die Einbauzeile rückt erst ab
rund 1930 px Fensterbreite neben die Prüfstufe statt wie bisher ab 1780 px.
Darunter steht sie in einer eigenen Zeile.

---

### Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.9.exe` | Windows 64-bit |
| `PS5_Dump_Image_Converter_v1.9.9_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.9.9.sha256` | Prüfsummen der Quelldateien |

Beide Programmdateien laufen eigenständig; es muss nichts nachinstalliert
werden.
