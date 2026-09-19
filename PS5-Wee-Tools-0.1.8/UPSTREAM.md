# PS5 Wee Tools – mitgeliefertes Fremdwerkzeug

Grundlage ist **PS5 Wee Tools 0.1.8** von andy-man
(`https://github.com/andy-man/ps5-wee-tools`), lizenziert unter **GPL-3.0**.
Der vollständige Lizenztext liegt als `LICENSE` daneben.

Stand: Zweig `main`, Commit `4232c2e810f0d2602cd71fb448d379fa32960fe7`
(18.09.2026). Das ist Tag `v0.1.8` (`2b9b8c5`) plus die ungarische
Übersetzung `i18n/hu.json`. Quellarchiv `ps5-wee-tools-main.zip`, SHA-256
`a24367a9476dc78c7afd4ef0eca5822ad0c865f936f10504a65c0f32ce361d8f`.

## Unverändert

Alle 42 Dateien sind byte-gleich mit dem Quellarchiv. `herkunft.json` nennt
die Prüfsumme jeder Datei; `test_wee_tools.py` hält den Ordner dagegen. Hinzu
kommen nur diese Datei und `herkunft.json`.

## Was es ist

Ein Textmenü für den **NOR-Flash (SFlash) der Konsole** – nicht für
Spiel-Dumps: Konsolendaten aus einem NOR-Dump lesen (Modell, SKU, Region,
Seriennummern, Firmware, MAC), Merker umschalten, Partitionen zerlegen und
zusammensetzen, 2BLS-Dateien, UART-Terminal, EMC-Fehlerlog und der
SPIway-Flasher (Teensy 2.0), der den NOR **auch beschreibt**. Ein falsch
beschriebener NOR kann die Konsole unbrauchbar machen. Einzige
Fremdabhängigkeit ist `pyserial` (BSD-3-Clause).

## Wie das Programm es einbindet

- Knopf **PS5 Wee Tools (NOR)** unter WEITERE TOOLS. Er fragt vorher nach und
  startet das Werkzeug als **eigenen Prozess** in einem eigenen
  Konsolenfenster (interner Modus `--ps5-wee-tools`, siehe
  `ps5_validator/utils/wee_tools.py`). Der Code des Werkzeugs wird nicht in
  das Programm übernommen.
- Beim Start wird dieser Ordner nach `PS5 Wee Tools/programm/` neben dem
  Programm gespiegelt; eine vorhandene `config.ini` bleibt stehen. Das
  Werkzeug läuft von dort. Arbeitsverzeichnis ist `PS5 Wee Tools/` – dort
  landen gelesene NOR-Dumps (`dump_*.bin`) und UART-Protokolle (`uart_*.txt`).

Drei Anpassungen geschehen zur Laufzeit im eigenen Prozess, nicht im Code:

1. **`sys.frozen` aus.** wee-tools sucht `config.ini` und `i18n/` unter
   `ROOT_PATH`; im gebauten Programm wäre das der Ordner neben der
   Programmdatei, wo keine Sprachdateien liegen – jede Übersetzung fiele still
   weg. Ohne `frozen` ist `ROOT_PATH` der Ordner der Kopie.
2. **`quit()`/`exit()`** werden bereitgestellt, falls sie fehlen (im
   gebauten Programm legt sie das `site`-Modul nicht an; „Beenden“ im
   Hauptmenü ruft `quit()`).
3. **Eigene Paketnamen getrennt.** `tools`, `utils`, `lang` und `data` werden
   vor dem Start aus dem Modulspeicher genommen, und die Kopie steht vorn im
   Suchpfad – im Projektordner liegt ein eigenes `tools/`.

## Gemessene Eigenheiten (nur Wissen)

- Der Merker-Umschalter schreibt ohne Sicherung direkt in die Dump-Datei.
- `getPartitionsInfo` vergleicht `f.read(1)` (bytes) mit `0x00` (Zahl) und
  liest dadurch immer die Tabelle aus MBR2, auch bei aktivem Slot A.

## Aktualisieren

Ordner durch die neue Fassung ersetzen (neuer Ordnername mit Fassung),
`herkunft.json` neu erzeugen, `wee_tools.ORDNER` und die drei `.spec` anpassen
und `test_wee_tools.py` laufen lassen: Er hält die Importe des Werkzeugs gegen
die `hiddenimports` aller drei `.spec` – ein neuer Import, der dort fehlt,
würde sonst erst im gebauten Programm auffallen.
