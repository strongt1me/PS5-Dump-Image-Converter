# PS5 Dump & Image Converter v1.8.49 – Release Notes

## Zweck dieses Releases

Ein kleiner Eingriff mit einer klaren Begründung – und ein Fund in der Testabdeckung, der mehr wert ist als der Eingriff selbst.

---

## Nur Bibliotheken wandern in das Spiel

Beim Backport wurde bisher der **komplette** mitgelieferte Ordner in den Dump kopiert. Der Satz für Firmware 7 enthält aber nicht nur Bibliotheken:

| Datei | Größe | Was es ist |
| --- | --- | --- |
| `libSceAgc.sprx`, `libSceAgcDriver.sprx`, `libSceNpAuth.sprx`, `libSceNpAuthAuthorizedAppDialog.sprx`, `libSceSaveData.native.sprx` | 25–321 KB | echte Ersatzbibliotheken (SELF) |
| `FW7` | 0 Bytes | Markierung, benennt den Satz |
| `ps5-backpork.elf` | 116 KB | Payload von PS5 BACKPORK KITCHEN, keine Bibliothek |

**Übernommen werden jetzt nur `.sprx` und `.prx`** – plus die leere Markierung `FW<n>`, weil sie nichts kostet und später verrät, welcher Satz im Ordner liegt.

### Warum die `.elf` überhaupt dort lag

`Backport_Fakelibs/` ist eine wortgleiche Kopie der Sätze aus PS5 BACKPORK KITCHEN 2.3.1, und dessen `Form1.vb` kopiert ungefiltert:

```vb
CopyRelative(fakelibfolder, fakelibingame)
```

Das Programm tat also dasselbe wie die Referenz. ShadowMount+ hängt den Ordner nach `common/lib`, wo Bibliotheken **nach Namen** geladen werden, wenn ein Spiel sie anfordert – nach `ps5-backpork.elf` fragt keines. Der `ps5-exfat-builder` beschreibt seinen Auswahldialog passend dazu mit „containing .sprx/.prx files".

### Warum die Datei verzichtbar ist

Ein früherer Test verlangte sie ausdrücklich und nannte sie „den Starter". Der Name war eine Deutung, kein Beleg. Untersucht: ET_DYN, enthält die Zeichenketten `backpork` und `kernel` – der Payload des Werkzeugs. Entscheidend ist aber der Satz selbst:

**In FW4, FW5 und FW6 fehlt sie.** Wäre sie zum Backporten nötig, wären diese drei Sätze unbrauchbar.

Der Test heißt jetzt `test_fw7_satz_enthaelt_die_elf_noch_auf_der_platte` und hält beides fest: Die Datei bleibt im mitgelieferten Satz, wandert aber nicht mehr in das Spiel. Sollte ein zurückportiertes Spiel je ohne sie zicken, ist das die erste Stelle, an der man nachsieht.

### Nachvollziehbar im Protokoll

> `[INFO] 1 Datei(en) aus dem Bibliothekssatz übersprungen (keine .sprx/.prx): ps5-backpork.elf`

Nur FW7 verliert etwas; die übrigen Sätze sind unverändert (FW4 und FW5 je 4 Dateien, FW6 acht, FW7 sechs statt sieben).

---

## Der Nebenfund: Tests lasen die Einstellungsdatei des Nutzers

`test_ampr_restore.py` fiel plötzlich vierfach um und meldete „no_backup" statt „restored". Die Ursache lag nicht im Programm: `_fakelib_ordnername()` liest die gespeicherte Wahl, und in der Konfiguration stand `fakelib2`. Der Test legte seine Sicherung in `fakelib` an und suchte sie in `fakelib2`.

Die Abhängigkeit bestand schon vorher – sie fiel nur nie auf, weil der Ordnername festverdrahtet war. **Ein Test darf nicht davon abhängen, was der Nutzer eingestellt hat.** Sein Prüfling bekommt jetzt einen festgelegten Ordner.

Bei der Gelegenheit prüft er den Ablauf in **beiden** Ordnern, samt der Zusicherung, dass bei gewähltem `fakelib2` ein daneben liegendes `fakelib` unangetastet bleibt.

Ergänzend abgesichert: `_fakelib_ordnername()` übersteht eine fehlende `_load_setting`. Tests bauen die Instanz über `__new__` ohne `__init__`; die `AttributeError` wurde von Aufrufern als „keine Sicherung vorhanden" gedeutet – ein Fehler, der nach einem Programmfehler aussah.

---

## Tests

**47 Testdateien grün.** `test_backport.py` prüft 79 Fälle, `test_ampr_restore.py` sieben statt fünf.

---

## Linux-Fassung

Gebaut und geprüft unter **Ubuntu 26.04 (WSL), Python 3.14.4, PyInstaller 6.22.1** – 107,8 MB, eine einzelne Programmdatei ohne Installation.

Unter Linux entfällt die UAC-Hürde, die den Kommandozeilenmodus unter Windows nicht-interaktiv unprüfbar macht. Deshalb sind die End-to-End-Nachweise dort geführt:

| Prüfung | Ergebnis |
| --- | --- |
| `--cli --help` | exit 0 |
| Aufgabe 8 an einem echten Dump | exit 0, BESTANDEN |
| Aufgabe 1: Ordner → `.ffpfsc` | exit 0 in 18 s, 156.762.112 Bytes |
| Rundlauf `.ffpfsc` → Ordner | **bitgleich**, 63 Dateien |
| `.ffpkg` unter Linux | sauber abgelehnt, exit 1 |

Die Ablehnung nennt den Grund beim Namen, statt von fehlenden Rechten zu sprechen:

> `Das Erzeugen eines UFS2-.ffpkg braucht UFS2Tool, und das gibt es nur unter Windows.`

Zwei Beobachtungen am Rande: Der Bau zieht die Version selbsttätig aus `APP_VERSION`, ein Nachtragen in den Linux-Dateien ist also nicht nötig. Und die erzeugte `.ffpfsc` ist **auf das Byte so groß wie unter Windows** – dieselbe Quelle, dieselbe Stufe 9, dasselbe Ergebnis.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.49.exe` | Windows, 99,19 MiB |
| `dist\PS5_Dump_Image_Converter_v1.8.49_linux_x86_64` | Linux x86-64, 107,8 MB |
| `SOURCE_FILE_MANIFEST_v1.8.49.sha256` | Prüfsummen aller Quelldateien |
