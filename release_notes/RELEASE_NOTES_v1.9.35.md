# PS5 Dump & Image Converter v1.9.35

Dasselbe Format noch einmal bauen – jetzt in allen Aufgaben 2 bis 6 und
für jedes Abbildformat.

## Was kaputt war

In v1.9.34 war `.exFAT` zu `.exFAT` freigegeben, aber die **Auswahlliste**
bot es nie an. Es gibt zwei Tore:

1. `_get_target_options` baut die Liste im Auswahlfeld – sie warf das
   Selbst-Ziel **immer** hinaus.
2. `_conversion_block_reason` prüft beim Start – dort war es freigegeben.

Gemessen war nur das zweite. Eine Freigabe, die nie in der Liste landet,
ist wertlos.

## Was jetzt gilt

Eine Regel statt einer Liste von Sonderfällen: Quelle und Ziel dürfen
dasselbe Format haben, sobald beim Bauen etwas hineinkommt –
AMPR-EMU-Asset-Pack, **PlayGo-Stub** oder **BACKPORT**. PlayGo zählte
bisher gar nicht mit (`_integration_gewaehlt` kannte nur AMPR und
BACKPORT).

| Format | Quelle und Ziel gleich? |
| --- | --- |
| `.ffpfsc` / `.ffpfs` | mit Asset-Pack, PlayGo oder BACKPORT |
| `.exFAT` | immer – „.exFAT (neu bauen)“ |
| `.ffpkg` | immer – „.ffpkg (neu validieren)“ |

`.exFAT` und `.ffpkg` sind ausgenommen, weil sie ohnehin vollständig
entpackt, neu gebaut und dabei geprüft werden.

Die Tabelle der Einzelfälle aus v1.9.34 ist entfallen – sie wäre bei
jedem neuen Format wieder unvollständig gewesen.

## Der Wächter dazu

`test_beide_tore_sind_sich_einig` geht jede Kombination aus Aufgabe,
Format und Einbau-Zustand durch und verlangt, dass Auswahlliste und
Startprüfung dasselbe sagen. Läuft eines von beiden weg, fällt der Test.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.35.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.35_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.35_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.35.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
