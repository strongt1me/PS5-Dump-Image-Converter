# PS5 Dump & Image Converter v1.8.54 – Release Notes

## Zweck dieses Releases

Zwei Fehler aus v1.8.53. Einer war sofort sichtbar, der andere fiel erst beim Aufräumen der Testreihe auf – und war der ernstere von beiden.

---

## 1. Aufgabe 8 verurteilte einen Dump, den sie selbst repariert hatte

Gemeldet an einem echten Backup. Im Protokoll standen diese drei Zeilen direkt untereinander:

```text
[Info] sce_sys/param.json wurde neu erstellt (Titel-ID: PPSA06328).
[param.json] Prüfung bestanden – keine Beanstandungen.
[ERGEBNIS] FEHLGESCHLAGEN: FAILED
```

`sce_sys/param.json` steht in `CRITICAL_FILES`. Fehlt sie, lautet das Urteil FAILED – und es fiel, **bevor** die Datei angelegt wurde. Der Ordner war in dem Moment, in dem das rote Fehlerfenster erschien, vollständig. Nachgemessen an derselben Quelle: `STATUS: OK`, 1166 Dateien, 0 Fehler.

**Die Behandlung läuft jetzt vor dem Durchlauf.** Das kostet nichts: `pruefe_datei()` liest eine einzelne kleine Datei. Der teure Teil – SHA-256 über den ganzen Ordner – läuft danach genau einmal, und sein Ergebnis beschreibt den Stand, den der Ordner am Ende wirklich hat. Ein zweiter Durchlauf zur Korrektur des Urteils wäre bei einem 100-GB-Backup nicht bezahlbar.

Lehnt der Nutzer ab, meldet die Prüfung die fehlende Datei weiterhin – dann zu Recht.

---

## 2. Die Rückfrage stand auf Ja, obwohl ein Ja ins Netz greift

Der schwerwiegendere Fund, und er kam nicht aus einer Fehlermeldung, sondern aus einem Test, der seit v1.8.53 rot stand.

Bis v1.8.52 hatte der Online-Nachschlag eine **eigene** Frage mit `default_yes=False`. Die Begründung stand im Quelltext: Die Titel-ID geht an eine fremde Seite, ein versehentliches Enter darf das nicht auslösen. v1.8.53 legte beide Fragen zu einer zusammen – und die verbliebene benutzte die Vorgabe `default_yes=True`. Seitdem löste Enter das Anlegen **und** den Netzabruf zugleich aus.

Jetzt gilt: Führt ein Ja zu einem Netzabruf, ist der vorbelegte Knopf **Nein**. Geschieht alles lokal – keine Titel-ID erkannt oder Nachschlag abgeschaltet –, bleibt es bei **Ja**.

### Warum der Test das fast nicht bemerkt hätte

Er suchte die Zeichenkette `default_yes=False` im Quelltext. Diese Prüfung schlug nur deshalb an, weil die Zeile ganz verschwand. Wäre sie an eine andere Stelle gerutscht, hätte der Test weiter grün gemeldet. Er misst jetzt die **tatsächliche Vorbelegung**, indem er `_offer_create_param_json` einmal mit und einmal ohne erlaubten Nachschlag aufruft und mitschreibt, womit gefragt wird.

---

## Kleinere Berichtigungen

- **„Die Konvertierung ist fehlgeschlagen … z. B. mkpfs Exit-Code oder Disk-Full-Meldung"** erschien auch bei Aufgabe 8 und der Inspektion. Beide wandeln nichts um, sie lesen; einen mkpfs-Schritt gibt es dort nicht. Sie melden jetzt „Beanstandungen gefunden".
- **Diese Fehlermeldungen waren als einzige noch fest auf Deutsch verdrahtet**, samt Fenstertitel „Fehler". Im englischen Programm stand hier deutscher Text. Vier neue Schlüssel in `i18n.py`.

---

## Die Testreihe ist wieder vollständig grün

v1.8.53 ging mit **sieben roten Tests** heraus. Sie sind aufgearbeitet:

| Befund | Art |
| --- | --- |
| Vorbelegung der Rückfrage | **echter Fehler**, siehe oben |
| `create_default_param` schreibt jetzt ein vollständiges Dokument | Erwartung veraltet (das war der Fix in v1.8.53) |
| Titel kommt zuerst aus dem Trophäen-Container | Erwartung veraltet |
| eine Rückfrage statt zweier | Erwartung veraltet |
| zwei Vorlagen mit knapper `param.json` | bestehen seit v1.8.51 die inhaltliche Prüfung nicht |
| Attrappe ohne `root`-Attribut | Folge derselben Vorlage |

**Nebenbefund:** Drei Testdateien griffen seit v1.8.53 bei jedem Lauf wirklich ins Netz. Ihre Attrappe erkannte die Online-Frage an `default_yes=False`; nach dem Zusammenlegen traf das nicht mehr zu, und der Nachschlag lief mit. Jetzt ausdrücklich abgeschaltet.

**Dazu ein Fenstertest, der nur in der vollen Reihe brach:** `tkinter` merkt sich die erste Wurzel als `_default_root` und behält sie, auch wenn sie längst zerstört ist. `ImageTk.PhotoImage` ohne `master` baut sein Bild dann im alten Interpreter, während das Label im neuen entsteht – Tk meldet `image "pyimage269" doesn't exist`. Allein lief die Datei durch, hinter anderen Fenstertests nicht.

Stand jetzt: **772 Tests, 0 Fehlschläge**, 3 übersprungen.

---

## Das Release Gate ist entfernt

Auf Wunsch entfernt: `.github/skills/release-test/` mit seinen drei Skripten und dem Statusstand, dazu `.github/skills/full-test/scripts/dispatcher.py`, der nichts anderes tat, als genau diese Skripte aufzurufen. Von `.github/` bleibt der macOS-Workflow.

Zur Einordnung, warum das Gate den Fehler nicht gefangen hat: Es prüfte Syntax, `test_build_ready.py` und `test_all_quality.py` – die übrigen 47 Testdateien sah es nie. Deshalb konnte v1.8.53 mit sieben roten Tests herausgehen, ohne dass es mucksste. Die Absicherung ist jetzt der vollständige Durchlauf über alle Testdateien.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.54.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.54_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.54.sha256` | Prüfsummen aller Quelldateien |
