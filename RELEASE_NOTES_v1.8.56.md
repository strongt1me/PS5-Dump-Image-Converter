# PS5 Dump & Image Converter v1.8.56 – Release Notes

## Zweck dieses Releases

Das Programm hat die Prüfung, die mkpfs nach jedem Packen von sich aus durchführt, an **sechs Stellen abgeschaltet** — unsichtbar und nicht abwählbar. Diese Version gibt sie frei und stellt die Wahl in die Hauptzeile.

Gefunden wurde das beim Abgleich mit der offiziellen Anleitung, nicht durch einen Fehlerbericht.

---

## Der Abgleich, der es zutage gebracht hat

In [PS5 SDK usw/README.md:259](PS5%20SDK%20usw/README.md:259) steht die dokumentierte Vorlage zum Packen:

```bash
mkpfs pack folder --verify --no-compress --no-adjust-output-file-extension --version PS5 --inode-bits 32 …
mkpfs pack file   --verify --version PS5 --inode-bits 32 …
```

Das Referenzprogramm `ps5-exfat-builder` hält sich in [ui/tab_pfs.py:972](PS5%20SDK%20usw/ps5-exfat-builder-4.0.2/ps5-exfat-builder-4.0.2/ui/tab_pfs.py:972) daran — mit dem ausdrücklichen Kommentar *„Exact flags per ShadowMount+ README"* — und lässt die Prüfung laufen.

Unser Programm schickte stattdessen in **jedem** Packaufruf `--no-verify-structure`. In mkpfs ist diese Strukturprüfung voreingestellt; der Schalter schaltet sie ab. `--verify` kam ohnehin nie vor. Damit lief nach dem Packen **keine** der beiden Prüfungen von mkpfs.

---

## Was neu ist

Rechts neben den Worker-Threads steht jetzt ein drittes Feld:

| Stufe | Was an mkpfs geht | Bedeutung |
| --- | --- | --- |
| Aus | `--no-verify-structure` | wie bisher — keine Prüfung |
| **Schnell** *(Vorgabe)* | *nichts* | mkpfs prüft die Struktur, wie voreingestellt |
| Vollständig | `--verify` | Struktur **plus** vollständiger Rücklauf |

Dass „Schnell" gar keinen Schalter schickt, ist der Kern der Sache: Es ist mkpfs' eigene Voreinstellung, die bisher aktiv unterdrückt wurde.

### Warum eine Klappliste und nicht zwei Kästchen

Die beiden Schalter sind nicht gleichrangig, sondern **geordnet**: `--verify` schließt die Strukturprüfung ein. Zwei unabhängige Haken hätten den Zustand „vollständig ohne Struktur" erlaubt, den es nicht gibt. Die Liste kennt ihn nicht, speichert einen einzigen Wert und steht optisch neben dem Kompressionsfeld, dem sie entspricht.

Gespeichert wird die sprachunabhängige Kennung (`aus` / `schnell` / `voll`) unter `mkpfs_verify` — nicht der übersetzte Text, sonst wäre die Wahl nach einem Sprachwechsel verloren. Ein Hinweis beim Überfahren nennt die Bedeutung und erwähnt, dass Aufgabe 8 ein fertiges Abbild jederzeit auch nachträglich prüft.

**Die Laufzeit ist nicht gemessen.** „Schnell" kostet nach jedem Packen etwas; wie viel, zeigt erst ein echter Lauf.

---

## Nebenher vereinheitlicht

Die vier `pack file`-Aufrufe drückten die Kompression auf drei verschiedene Arten aus — einer gar nicht, im Vertrauen auf `default=True` in [MkPFS-0.0.9/mkpfs/cli.py:752](MkPFS-0.0.9/mkpfs/cli.py:752). Das Ergebnis war überall dasselbe, aber nur so lange, wie diese Vorgabe steht. Jetzt nennt jeder Aufruf die Kompression ausdrücklich.

---

## Was dabei über das Packen klar wurde

Die Anleitung nennt **kein** `--raw`. Mit dem mitgelieferten mkpfs 0.0.9 wäre das falsch — dort steht in [cli.py:1480](MkPFS-0.0.9/mkpfs/cli.py:1480):

> Default: wrap the folder in an exFAT and compress it into the .ffpfsc in one pass […] Use `--raw` to pack the folder directly as PFS.

Ohne `--raw` liefert `pack folder` also bereits ein fertiges `.ffpfsc`, das die zweite Stufe nochmals einpackt — der dreifach verschachtelte Aufbau, der einmal ein echter Fehler war. Das Referenzprogramm braucht `--raw` nicht, weil es mkpfs **0.0.7** bündelt.

**Die Anleitung ist damit nicht falsch, sondern an eine ältere Fassung gebunden.** Wer sie wörtlich auf 0.0.9 anwendet, bekommt stillschweigend ein kaputtes Abbild. Eine Prüfung verlangt deshalb für jeden `pack folder`-Aufruf sowohl `--raw` als auch `--no-compress`.

Nicht nachprüfbar blieb das Verhalten von 0.0.7 selbst: Diese Fassung liegt dem Referenzprogramm nicht im Quelltext bei.

---

## Tests

**806 Prüfungen, 0 Fehlschläge.** Neu: sechs zur Prüfstufe, drei zu den Kompressionsschaltern.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.56.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.56_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.56.sha256` | Prüfsummen aller Quelldateien |
