# PS5 Dump & Image Converter v1.7.89 – Release Notes

## Zweck dieses Korrekturrelease

Version **v1.7.89** ersetzt den bislang allein verwendeten FFPKG-`makefs`-Erstellungsweg durch einen strikt validierten Kandidatenablauf. Anlass war ein echter UFS2-Prüffehler nach einem scheinbar erfolgreichen Build: Ein Rückgabecode von `0` allein ist keine ausreichende Annahme für eine strukturell gültige FFPKG-Datei.

Der Builder erzeugt daher zuerst einen Kandidaten mit UFS2Tool `newfs -D` und übernimmt eine Zieldatei erst dann atomar, wenn sowohl `info` als auch das schreibgeschützte `fsck_ufs -fn` erfolgreich sind. Dies folgt den dokumentierten UFS2Tool-orientierten Abläufen der verglichenen Referenzprojekte.[1] [2] [3]

## FFPKG-Erstellungsreihenfolge

| Priorität | Kandidatenprofil | Übergabekriterium |
|---:|---|---|
| 1 | `newfs -O 2 -b 65536 -f 65536 -S 512 -m 0 -i 262144 -D` | `info` und `fsck_ufs -fn` erfolgreich |
| 2 | `newfs -O 2 -b 32768 -f 4096 -S 512 -m 0 -i 131072 -D` | `info` und `fsck_ufs -fn` erfolgreich |
| 3 | Bestehender expliziter `makefs`-Pfad | `info` und `fsck_ufs -fn` erfolgreich |

Jeder abgewiesene Kandidat wird gelöscht. Die finale Zieldatei entsteht ausschließlich durch atomare Übernahme eines bereits validierten Zwischenstands.

## Abnahmenachweis

| Prüfung | Ergebnis |
|---|---|
| Repräsentativer Grenzfall | 191 Dateien und 648.398.581 Byte |
| Native UFS2-Prüfung | `info` und `fsck_ufs -fn` erfolgreich |
| Round-Trip | Extraktion erfolgreich |
| Inhaltsvergleich | SHA-256-Manifest: 0 fehlende, 0 zusätzliche, 0 abweichende Dateien |
| Regressionen | FFPKG-Unit-, Integrations-, Qualitäts- und Build-Readiness-Tests erfolgreich |

Die vollständigen maschinenlesbaren Werte stehen in [`FFPKG_VERIFICATION_v1.7.89.json`](FFPKG_VERIFICATION_v1.7.89.json).

## Pflichtbestandteile des vollständigen Quellrelease

Das Quellarchiv enthält den vollständigen Quellstand einschließlich der wiederhergestellten bzw. erforderlichen Bestandteile `.github/`, `MkPFS-0.0.9/`, `helloworld/` und `extract_icon.py`. Die von `Build_EXE.ps1` aufgerufene `extract_icon.py` wurde bytegenau wiederhergestellt und synchronisiert `app_icon.ico` aus dem im Hauptprogramm eingebetteten Base64-Icon. Der optionale Ordner `helloworld/` ist leer, weil weder der beigefügte Originalbestand noch das v1.7.87-Referenzarchiv darin Dateien enthielten.

Zusätzlich stellt der Releaseordner die Prüfsumme des Quellarchivs, den maschinenlesbaren FFPKG-Nachweis, diese Release-Notiz, `extract_icon.py`, einen Release-Manifest und einen SHA-256-Manifest der Quelldateien eigenständig bereit.

## Unveränderte Bereiche

Die gesperrten `.ffpfsc`-/MkPFS-Pfade und die ProgressEngine-Indizes wurden durch dieses Release nicht verändert.

## Referenzen

[1]: https://github.com/SvenGDK/UFS2Tool "SvenGDK UFS2Tool"
[2]: https://github.com/kerrdec97/ps5-exfat-builder "kerrdec97 ps5-exfat-builder"
[3]: https://github.com/sinajet/PSFFPKG "sinajet PSFFPKG"
