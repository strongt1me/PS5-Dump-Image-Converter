# PS5 Dump & Image Converter v1.8.31 – Release Notes

## Zweck dieses Releases

Zwei Lücken bei unvollständigen und falsch gebauten Quellen sind geschlossen:

1. Ein Dump-Ordner ohne `eboot.bin` oder `sce_sys/param.json` ließ sich anstandslos verpacken – das Ergebnis war formal gültig und auf der Konsole unbrauchbar. Jetzt warnt das Programm vor dem Start, und Aufgabe 8 erkennt es auch am fertigen Container.
2. Ein falsch verschachteltes `.ffpfsc` war mit den vorhandenen Mitteln nicht von einem korrekten zu unterscheiden. Jetzt schon – ohne die Datei zu entpacken.

## Änderungen im Einzelnen

### 1. Warnung vor dem Start

`_run_preflight_checks()` prüfte bisher nur Rahmenbedingungen: Quelle vorhanden, Pfadlängen, freier Speicher, OSFMount. Der Inhalt des Dumps blieb ungesehen.

Neu meldet `_missing_critical_dump_files()` fehlende Pflichtdateien, sobald die Quelle ein Ordner ist. Die Meldung erscheint als Warnung im bestehenden Preflight-Dialog und landet im Abschlussbericht – bewusst **kein Abbruch**, damit sich auch Teilordner bewusst packen lassen.

Aufgabe 8 ist ausgenommen: Der Validator meldet fehlende Dateien ohnehin ausführlich, eine zweite Meldung wäre doppelt.

Die Engine hätte dafür eine eigene Prüfung (`validate_input(require_game_files=True)` verlangt `sce_sys/param.json` mit gültiger `titleId` und `eboot.bin`), sie ist aber opt-in über `--require-game-files`. Der Schalter bleibt bewusst ungesetzt: Er würde abbrechen statt zu warnen.

### 2. Pflichtdateien auch im Container

`FfpfsValidator._check_critical_files()` prüft die Namensliste der innersten Ebene gegen dieselbe Liste. Fehlt etwas, steht es als `critical_missing` im Ergebnis und der Status ist **FAILED** – genau wie bei der Ordnerprüfung.

Beide Seiten holen die Liste aus `dump_validator.CRITICAL_FILES` (`eboot.bin`, `sce_sys/param.json`, `sce_sys/pfs-version.dat`). Ein eigener Test hält fest, dass Preflight und Validator dieselbe Liste verwenden, und ein zweiter, dass derselbe Inhalt als Ordner und als Container zum selben Urteil führt.

### 3. Verschachtelungsprüfung ohne Entpacken

Ein korrektes `.ffpfsc` ist zweistufig: außen der Container, darin genau ein rohes PFS-Image mit den Spieldateien. Fehlt beim inneren Image `--raw`, legt mkpfs von sich aus ein **exFAT-Abbild** dazwischen. `mkpfs tree` und `inspect` zeigen den Unterschied nicht – beide listen nur die äußere Ebene, dort steht in beiden Fällen genau ein Eintrag mit demselben Namen.

`FfpfsValidator._check_nesting()` prüft jetzt drei Ebenen:

| Ebene | Erwartung | sonst |
| --- | --- | --- |
| außen | genau ein Eintrag (das innere Abbild) | `flach aufgebaut` → WARNING |
| innen | ein PFS-Image | FAILED |
| innerste | die Spieldateien | ein Eintrag, der selbst ein Abbild ist → FAILED |

Erkannt wird am Inhalt, nicht am Namen: exFAT-Signatur `EXFAT   ` bei Offset 0x03, PFS-Magic oder Abbild-Endung.

**Der Aufwand war der Grund, warum das bisher unterblieb – zu Unrecht.** Vollständiges Entpacken wäre unverhältnismäßig, ist aber nicht nötig: `open_inner_file_view()` aus der mitgelieferten mkpfs-Engine liefert eine seekbare Sicht, die nur die angefassten Blöcke entpackt. Gebraucht werden Kopf, Inode-Tabelle und Verzeichnisblöcke der inneren Ebene. **Gemessen an einer 392-MB-Datei: 757 KB in 25 Zugriffen, 9 ms** – der Aufwand hängt an der Zahl der Einträge, nicht an den Nutzdaten.

Damit die Engine auch in der EXE erreichbar ist, entpackt Aufgabe 8 sie bei Bedarf und legt sie auf den Importpfad; eigenständig findet der Validator den `MkPFS-*`-Ordner selbst. Fehlt sie ganz, steht „nicht geprüft" im Protokoll statt eines Fehlers.

### 4. Neue Zeilen im Protokoll

| Zeile | Bedeutung |
| --- | --- |
| `nesting` | `in Ordnung`, `falsch verschachtelt (…)` oder `flach aufgebaut (…)` |
| `inner_files` / `inner_dirs` | Dateien und Ordner auf der innersten Ebene |
| `outer_files` | Einträge im äußeren Container (normal: 1) |
| `critical_files` | `vollstaendig` oder `unvollstaendig (n fehlen)` |

## Bedeutung für Nutzer

- Ein unbemerkt unvollständig kopiertes Backup fällt vor der Konvertierung auf, nicht erst auf der Konsole.
- Fertige Container lassen sich nachträglich darauf prüfen, ohne den Ursprungsordner zu haben.
- Falsch gebaute Container werden als solche erkannt statt als „geprüft und in Ordnung" durchgewunken.

## Verifikation

- Vier eigens gebaute Container (klein und 392 MB, je korrekt und ohne `--raw`): korrekte → OK mit 4 bzw. 93 Dateien auf der innersten Ebene, defekte → FAILED mit Nennung des exFAT-Abbilds. `mkpfs tree` liefert für beide weiterhin identische Ausgaben.
- Zusätzlich geprüft: unkomprimierte `.ffpfs`-Variante (OK) und ein rohes inneres Image (WARNING, `flach aufgebaut`).
- Container aus einem Ordner ohne `eboot.bin`: FAILED mit `critical_missing=['eboot.bin']`; derselbe Ordner direkt geprüft ebenfalls FAILED.
- Preflight an vollständigem und unvollständigem Ordner geprüft; Aufgabe 8 löst keine doppelte Warnung aus.
- Der Weg durch Aufgabe 8 wurde direkt ausgeführt (`_mode_dump_validator` liefert True bzw. False, Protokoll nennt den Grund).
- Neue Testdateien: `test_validator_nesting.py` (6 Tests, darunter ein Lesebudget von 8 MB) und `test_incomplete_dump.py` (8 Tests). Gesamt **54/54**; `test_build_ready.py` zusätzlich 8/8.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.31** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.31.sha256`

Neu im Projekt: `test_validator_nesting.py`, `test_incomplete_dump.py`.
