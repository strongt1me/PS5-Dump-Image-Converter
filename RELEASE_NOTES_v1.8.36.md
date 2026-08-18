# PS5 Dump & Image Converter v1.8.36 – Release Notes

## Zweck dieses Releases

Die letzte Lücke der `param.json`-Reparatur schließen. Seit v1.8.33 kommt die Titel-ID zuverlässig aus `sce_sys/nptitle.dat`; Titel und Content-ID blieben leer, weil sie in **keiner** lokalen Datei eines Dumps stehen. Beide lassen sich jetzt auf Wunsch online nachschlagen.

---

## Warum überhaupt online

Vorab geprüft, was lokal vorhanden ist:

| Quelle | Titel-ID | Titel | Content-ID |
| --- | --- | --- | --- |
| `sce_sys/param.json` | ja | ja | ja |
| `sce_sys/nptitle.dat` | **ja** (32/32 Backups) | nein | nein |
| `eboot.bin` | nein | nein | nein (33 MB vollständig durchsucht) |
| `npbind.dat` | nein | nein | nein |
| Ordnername | manchmal (10/32) | nein | nein |

Ist die `param.json` das defekte Stück, bleibt für Titel und Content-ID nur eine externe Quelle.

---

## Der Ablauf

1. `param.json` fehlt oder ist unlesbar → das Programm fragt wie bisher, ob eine Ersatzdatei entstehen soll.
2. Bei Ja folgt eine **zweite, eigene Frage**: „Titel online nachschlagen?" Sie steht auf **Nein** voreingestellt und nennt ausdrücklich, was gesendet wird – die Titel-ID, sonst nichts – und an wen.
3. Bei Ja wird `https://prosperopatches.com/<TitelID>` abgerufen (Zeitlimit 8 s), Titel und Content-ID werden ausgelesen.
4. Die Ersatzdatei entsteht mit allem, was zusammengekommen ist.

Der Titel landet dabei unter `localizedParameters` → `en-US` → `titleName`, also genau dort, wo die Konsole und dieses Programm ihn suchen. Ein Feld `titleName` auf oberster Ebene würde nirgends gelesen.

### Die drei Auflagen

| Auflage | Umsetzung |
| --- | --- |
| Lokale Werte haben Vorrang | Der Nachschlag läuft nur im Reparaturfall – also nur, wenn lokal nichts lesbar ist |
| Sauberer Rückfall ohne Netz | Jede Ausnahme wird gefangen, das Ergebnis ist dann leer; die Reparatur läuft weiter |
| Eigene Frage, Standard Nein | `default_yes=False`; der Dialog belegt „Nein" vor |

---

## Messung an echten Backups (16.08.2026)

| Dump | Titel-ID | Content-ID | Titel |
| --- | --- | --- | --- |
| Arcade Zone | PPSA19015 | ✔ | ✔ |
| Crazy Chicken Shooter | PPSA03117 | ✔ | ✔ |
| Teardown | PPSA15246 | ✔ | ✔ |
| Double Dragon Revive | PPSA23000 | ✔ | ✔ |
| Dirt 5 | PPSA01552 | ✔ | ✔ |
| Alan Wake Remastered | PPSA01925 | ✔ | ✔ |
| Fallout 4 | PPSA09016 | ✔ | ✔ |
| Instant Sports Plus | PPSA04319 | ✔ | ✘ |

**Content-ID 8/8 exakt, Titel 7/8.** Die Abweichung ist eine Umbenennung zwischen Regionen: lokal „Instant Sports Plus", online „Instant Sports Paradise". Die Content-ID stimmte auch dort.

---

## Behobener Fehler

**Das Fenster *Spiel-Info* zeigte den Titel mit vorangestellter Titel-ID.** Die Patch-Seite liefert im Seitenkopf inzwischen `PPSA19015: Arcade Game Zone` statt `Arcade Game Zone`. Der Titel wurde von dort ungefiltert übernommen, sodass die Kennung im Fenster mit erschien – betroffen war nur der Fall, dass der Titel online geholt wurde, also gerade bei defekter `param.json`. Das Präfix wird jetzt abgetrennt, ebenso ein angehängter Seitenname.

Zum Zeitpunkt der ersten Messung (15.08.) trug die Seite dieses Präfix noch nicht.

---

## Prüfung

| Prüfung | Umfang | Ergebnis |
| --- | --- | --- |
| Neue Tests `test_titel_online.py` | 34 | grün |
| Gesamte Testsuite | 413 | grün (2 übersprungen) |
| Echter Ablauf an einer Arbeitskopie | 14 Punkte | 14/14 |

Der Ablauftest arbeitete auf einer Kopie von `sce_sys` unter `E:\Test` mit absichtlich zerstörter `param.json` und deckte alle drei Auflagen ab: Ablehnung des Nachschlags (Ersatzdatei nur mit Titel-ID), Zustimmung (Titel und Content-ID exakt übernommen) und simulierter Netzausfall (Reparatur läuft trotzdem durch). Zusätzlich bestätigt: Es werden genau zwei getrennte Fragen gestellt, und die zweite ist auf „Nein" voreingestellt.

Die Testattrappen für `_ask_yesno_threadsafe` verneinen die Nachschlag-Frage grundsätzlich – die Testsuite greift nie ins Netz.

---

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `ps5_validator/utils/titel_online.py` | **neu** – Adressbildung und Auswertung des Seitenkopfs (ohne Netzbezug) |
| `ps5_validator/utils/param_manifest.py` | `create_default_param` nimmt jetzt einen Titel entgegen |
| `PS5ImageConverter_Pro_FINAL_revised.py` | Abruf, zweite Rückfrage, Präfix-Korrektur im Info-Fenster |
| `ps5_validator/utils/i18n.py` | 4 neue Schlüssel, deutsch und englisch |
| `test_titel_online.py` | **neu** – 34 Tests |
| `test_exfat_folder_build.py`, `test_param_json_recovery.py`, `test_all_quality_new.py` | Testattrappen auf die neue Signatur nachgezogen |
