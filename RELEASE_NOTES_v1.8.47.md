# PS5 Dump & Image Converter v1.8.47 – Release Notes

## Zweck dieses Releases

Zwei Dinge. Die Auswahl **KOMPRESSION (PFS)** war wirkungslos – gepackt wurde immer mit einer fest hinterlegten Stufe, egal was eingestellt war. Und die Anwendung läuft ab dieser Version auch unter **Linux**.

---

## Die Kompressionsstufe wirkt jetzt

Das Feld **KOMPRESSION (PFS)** bietet vier Stufen an: 1 (Schnellste), 3 (Schnell), 6 (Ausgewogen), 9 (Maximal). Am Ergebnis änderte sich nichts – alle vier erzeugten dieselbe Datei.

### Ursache 1: Die Stufe erreichte die Engine nie

Jeder Packlauf holt seine Stufe aus dem Aufgabenprofil. Dieses Profil setzte den Wert immer fest aus einer Tabelle im Programm:

| Aufgabe | fest hinterlegte Stufe |
| --- | --- |
| 1 – Dump-Ordner konvertieren | 9 |
| 3 und 6 – exFAT / AIO | 8 |
| 4 – ffpkg konvertieren | 7 |

Die Einstellung aus der Oberfläche wurde dabei nicht gelesen. Sie wurde zwar gespeichert und beim nächsten Start wieder angezeigt, kam aber nie bei der Engine an.

### Ursache 2: Die Größenvorhersage log passend dazu

Die geschätzte Zielgröße neben dem Quellfeld (`4,3 GB → ~2,1 GB`) rechnete sehr wohl mit der gewählten Stufe – nur mit dem falschen Verfahren. Sie komprimierte eine Stichprobe mit **zstd**, während die Engine mit **zlib** arbeitet. Die angekündigte Größe änderte sich also beim Umstellen, die fertige Datei nie.

Genau dieser Widerspruch fällt beim Benutzen auf: Das Programm verspricht eine Wirkung, die es nicht liefert.

### Nachgemessen

Gleiche Quelle, Aufgabe 1, `.ffpfsc` als Ziel:

| Eingestellt | vorher an die Engine | vorher | nachher an die Engine | nachher |
| --- | --- | --- | --- | --- |
| 1 | `--compression-level 9` | 1.310.720 B | `--compression-level 1` | **1.769.472 B** |
| 3 | `--compression-level 9` | 1.310.720 B | `--compression-level 3` | 1.310.720 B |
| 6 | `--compression-level 9` | 1.310.720 B | `--compression-level 6` | 1.310.720 B |
| 9 | `--compression-level 9` | 1.310.720 B | `--compression-level 9` | 1.310.720 B |

Dass die Stufen 3, 6 und 9 bei dieser kleinen Testquelle gleich ausfallen, liegt an der 64-KiB-Blockausrichtung des Containers – die Unterschiede sind kleiner als ein Block. Bei echten Titeln wirken sie sich aus.

### Ursache 3: Die Anzeige blieb stehen

Beim Test der fertigen Anwendung fiel eine dritte Stelle auf. Selbst nachdem die Stufe beim Packen ankam, änderte sich die angezeigte Zielgröße beim Umstellen nicht: Die Schätzung entstand ausschließlich beim Wechsel der **Quelle**. Wer nur die Stufe wechselte, sah weiterhin den Wert der vorherigen Stufe.

Sie rechnet sich jetzt sofort neu, sobald die Auswahl wechselt – im Hintergrund, damit die Stichprobe von bis zu 32 MB die Oberfläche nicht anhält. Die Quellgröße wird dabei nicht erneut ermittelt; sie ändert sich durch einen Stufenwechsel nicht, und ein erneuter Durchlauf über einen mehrere Gigabyte großen Dump würde jedes Mal Sekunden kosten.

### Zwei Anmerkungen für später

- `--compression-level` der Engine ist eine **zlib**-Stufe (0–9), keine zstd-Stufe. Die Benennung im Quelltext (`zstd_level`) führt in die Irre und wurde wegen der Vielzahl der Fundstellen bewusst nicht umbenannt.
- Die Worker-Berechnung nahm die Stufe schon immer als Eingabe entgegen und skaliert die Anzahl damit. Der Entwurf war also von Beginn an auf einen veränderlichen Wert ausgelegt; es fehlte allein die Verbindung zur Oberfläche.

Der Startwert stand außerdem auf Stufe 7 – eine Stufe, die das Auswahlfeld gar nicht anbietet. Er steht jetzt auf 6, passend zur Voreinstellung „Ausgewogen".

---

## Die Anwendung läuft jetzt unter Linux

`./Build_Linux.sh` erzeugt eine einzelne, eigenständige Programmdatei unter `dist/`. `./Install_Linux.sh` legt sie mit Symbol ins Anwendungsmenü; `--entfernen` nimmt das zurück. Beides läuft unterhalb von `~/.local`, ohne `sudo` und ohne Eingriff ins System.

Oberfläche, alle acht Aufgaben in ihren nativen Wegen, Kommandozeilenmodus, Übertragung zur PS5 und die Werkzeugfenster arbeiten dort wie unter Windows.

### Was unter Linux nicht geht

| Bereich | Grund |
| --- | --- |
| `.ffpkg` lesen und bauen | Läuft über UFS2Tool und den Dokan-Treiber – reine Windows-Software |
| OSFMount-Ersatzwege | OSFMount gibt es nur für Windows |

Diese Wege melden das jetzt ausdrücklich. Vorher kam an derselben Stelle „Administratorrechte fehlen" – unter Linux irreführend, denn dort ist nicht das Recht das Problem, sondern dass es das Werkzeug nicht gibt. Die nativen MkPFS- und exFAT-Wege sind vollständig vorhanden.

### Weitere Unterschiede

| Bereich | Verhalten unter Linux |
| --- | --- |
| Erhöhte Rechte | Für den normalen Betrieb nicht nötig; das Programm startet als normaler Benutzer |
| Einstellungen | `~/.config/PS5ImageConverterPro/` statt `%APPDATA%`; die Registry-Registrierung entfällt, die MIT-Lizenz liegt als Datei bei |
| Schriftart | Die Oberfläche ist auf *Segoe UI* ausgelegt. Fehlt sie, wird über fontconfig die erste vorhandene aus *Ubuntu*, *Cantarell*, *Noto Sans*, *DejaVu Sans*, *Liberation Sans* gewählt |
| Dateien öffnen | Handbuch, Lizenzen und Zielordner über `xdg-open`; „im Dateimanager zeigen" über D-Bus (Nautilus, Dolphin, Nemo, Thunar) |
| Herunterfahren nach Abschluss | `systemctl poweroff`, ersatzweise `shutdown -h now` – bisher meldete das Programm „nur unter Windows unterstützt" |
| FileZilla, OSFMount, Dokan installieren | Nur unter Windows. FileZilla wird gefunden, wenn es über die Paketverwaltung installiert ist |
| Virenscanner-Ausnahmen, Zertifikat | Entfallen ersatzlos |

Alle betriebssystemabhängigen Stellen liegen in **`ps5_validator/utils/plattform.py`**.

### Zur Weitergabe

Eine Linux-Programmdatei ist an Architektur und C-Bibliothek des Systems gebunden, auf dem sie entstanden ist – anders als die EXE lässt sie sich nicht beliebig weiterreichen. Die mitgelieferte Datei entstand auf Ubuntu 26.04 und setzt glibc 2.42 voraus. Auf älteren Systemen `./Build_Linux.sh` dort ausführen; das Skript prüft die Voraussetzungen und nennt den passenden Installationsbefehl, wenn Tcl/Tk fehlt.

---

## Auch unter Windows behoben

- Beim Backport wurde `libc.prx` nicht mehr erkannt, sobald der Pfad aus PS5-Metadaten oder einer FTP-Liste stammte statt aus dem Dateisystem. Der Patch wurde dann stillschweigend übersprungen. Dateinamen werden jetzt an beiden Pfadtrennzeichen erkannt.
- Ein Test las die Ausgabe der Engine ohne Kodierungsangabe ein. Windows wählte dafür die Codepage der Konsole, an der die Fortschrittsanzeige scheiterte – der Testlauf brach mit einem Folgefehler ab, der die eigentliche Meldung verdeckte.

---

## Tests

**47 Testdateien grün unter Windows, dieselben 47 unter Linux.** `test_build_ready.py` zusätzlich als Build-Freigabe.

Neu ist `test_kompressionsstufe.py` (18 Prüfungen): Jede angebotene Stufe muss beim Packlauf ankommen, ein unsinniger Wert darf nichts verbiegen, und die Größenvorhersage muss mit demselben Verfahren rechnen, das auch packt.

Drei Tests prüfen bewusst plattformabhängiges Verhalten und überspringen sich auf dem jeweils anderen System – etwa der Vergleich zweier Pfade, die sich nur in der Groß-/Kleinschreibung unterscheiden: Windows sieht darin denselben Ordner, Linux zwei verschiedene.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.47.exe` | Ausführbares Programm für Windows |
| `dist/PS5_Dump_Image_Converter_v1.8.47_linux_x86_64` | Ausführbares Programm für Linux |
| `Build_Linux.sh` | Buildskript für Linux |
| `Install_Linux.sh` | Menüeintrag anlegen/entfernen |
| `PS5ImageConverter_Pro_linux.spec` | PyInstaller-Konfiguration für Linux |
| `ps5_validator/utils/plattform.py` | Betriebssystem-Abstraktion |
| `SOURCE_FILE_MANIFEST_v1.8.47.sha256` | Prüfsummen aller Quelldateien |
