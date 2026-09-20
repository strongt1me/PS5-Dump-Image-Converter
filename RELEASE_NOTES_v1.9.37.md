# PS5 Dump & Image Converter v1.9.37

Der Knopf „Asset-Pack bauen“ aus v1.9.36 ist jetzt auch auf der
Kommandozeile erreichbar. Dazu eine Korrektur an einer Größenangabe, die
eine Messung nicht überlebt hat.

## Neu: `--ampr-action ampr_assetpack`

In v1.9.36 gab es den Knopf nur im Fenster. `--ampr-action` kannte die
Aktion nicht, und der Hilfetext daneben behauptete weiterhin, Aufgabe 7
baue keine Asset-Pack-Bänder.

```
--ampr-action ampr_assetpack --ampr-variant test-pack
```

Die Schreibweise aus der Klappliste geht auch in einem Stück:
`--ampr-version "0.4.2.1 test-pack"`.

Angegeben werden **muss** eine pack-fähige Fassung – `test-pack` oder
`test-debug-pack`. Fehlt sie oder taugt sie nicht, bricht der Aufruf ab,
bevor irgendetwas entsteht. Im Fenster meldet das ein Hinweisfenster; auf
der Kommandozeile sitzt niemand davor, der eine Meldung nach einer halben
Stunde Packen noch liest.

Gepackte Originaldateien entfernt Aufgabe 7 weiterhin nicht – in keinem der
beiden Wege.

## ShadowMount+ 1.7: sechs neue Einstellungen im Editor

Der ShadowMount+-Konfigurationseditor bot sechs Einstellungen aus 1.7 noch
nicht an. Nachgetragen, mit den Voreinstellungen von 1.7:

| Einstellung | Vorgabe |
| --- | --- |
| `api_enabled` | `1` |
| `nested_pfs_index_cache` | `0` |
| `fan_target_temperature` | `system` |
| `auto_remove_missing_games` | `0` |
| `auto_remove_games_with_dlc` | `0` |
| `auto_remove_missing_delay_seconds` | `300` |

Die drei `auto_remove_*` bleiben auf **aus**: Ein abgezogener USB-Stick ist
kein Löschauftrag.

Eine vorhandene `config.ini` war nie in Gefahr – der Editor gibt Unbekanntes
unverändert weiter. Nachgemessen an einer echten 1.7-Konfiguration: alle 39
Einträge samt Werten und Kommentaren erhalten. Die Liste greift nur, wenn auf
der Konsole noch keine Datei liegt.

Nebenbei gegen 1.7 nachgeprüft: Die vier Schnittstellen-Endpunkte, die das
Programm liest, und alle Felder, die es daraus nimmt, gibt es unverändert.
Und die Abbilder, die das Programm baut, erfüllen die Bedingung für den
schnellen exFAT-Pfad von 1.7 bereits – 512-Byte-Sektoren und
64-KiB-Zuordnungseinheiten.

## Korrektur: Ein Asset-Pack macht das Abbild nicht zwangsläufig größer

Die Texte zu v1.9.36 sagten, ein nachgerüstetes Asset-Pack mache das Backup
„größer, nicht kleiner“. An einem echten Abbild gemessen stimmt das so
nicht:

| | vorher | nachher |
| --- | --- | --- |
| Abbilddatei | 364.904.448 B | 275.972.096 B |
| Dateien darin | 63 | 71 |
| **Inhalt** | 260.935.330 B | 271.961.880 B |

Der **Inhalt** wächst um 4,2 % – die Originale bleiben, die Bänder kommen
dazu. Die **Datei** wurde trotzdem 24 % kleiner: Das Ausgangsabbild hatte
28,5 % Verschnitt, und der eingebaute exFAT-Schreiber arbeitet ohne freie
Zuordnungseinheiten.

Verlässlich ist damit nur die Aussage über den Inhalt. Wie sich die
Dateigröße ändert, entscheidet die Quelle. Handbuch und Changelog sind
berichtigt.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.37.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.37_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.37_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.37.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
