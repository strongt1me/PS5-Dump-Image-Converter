# PS5 Dump & Image Converter v1.7.90 – Release Notes

## Zweck dieses Patch-Releases

Version **v1.7.90** behebt den weiterhin gemeldeten FFPKG-Fehler, bei dem UFS2Tool eine Datei auf dem ausgewählten Zielvolume erzeugte, die anschließend eine ungültige Cylinder-Group-Struktur aufwies. Der Fix verändert ausschließlich den FFPKG-Pfad. Die gesperrten `.ffpfsc`-/MkPFS- und exFAT-Erstellungswege bleiben unverändert.

Zusätzlich ist die Bearbeitung bestehender `.ffpkg`-Quellen im Aufgabe-7-Workflow wieder konsistent: Änderungen an einer `.ffpkg` werden erneut als validierte UFS2-`.ffpkg` ausgegeben und nicht mehr als abweichender Containerpfad behandelt.

| Abschnitt | Verhalten ab v1.7.90 |
| --- | --- |
| Kandidaterstellung | Ausschließlich im ausgewählten Temp-Staging, nicht direkt auf dem Zielvolume. |
| Staging-Abnahme | Native UFS2Tool-Prüfung: `info` und schreibgeschütztes `fsck_ufs -fn`. |
| Zielvolume-Transfer | Kopie in eine eindeutige Transferdatei, SHA-256-Vergleich mit dem Staging-Kandidaten und zweiter nativer UFS2-Check. |
| Finale Übernahme | Nur eine doppelt validierte Transferdatei wird atomar auf den endgültigen `.ffpkg`-Namen umbenannt. |
| Fehlerdiagnostik | Bericht enthält Kandidatenhistorie, Profile, Rückgabecodes, Validierungen, Pfade und Hashwerte. |

## Abnahmenachweis

Die Projekttestsuite bestand mit **25 erfolgreichen Tests**. Der reale 191-Dateien-/648.398.581-Byte-Regressionsfall wurde vollständig über den neuen Produktionspfad geprüft. Zusätzlich wurde die offizielle UFS2Tool-v4.1-Windows-Executable über einen getrennten Staging- und Zielvolume-Pfad geprüft. Dort bestanden Kandidaterstellung, SHA-256-Transfervergleich, erneute UFS2-Abnahme und atomare Übernahme.

Zusätzlich wurde der opt-in-Integrationspfad unter Windows nach der Rückverdrahtung von Aufgabe 7 erneut geprüft. Erfolgreich verifiziert wurden:

- `RUN_FFPKG_INTEGRATION=1 python -m unittest -v test_ffpkg_production_integration.py`
- `RUN_FFPKG_648MB_INTEGRATION=1 python -m unittest -v test_ffpkg_production_integration.py`

Beide Läufe bestanden mit produktivem UFS2-Builder. Damit sind sowohl der allgemeine Staging-/Transfer-/Validierungspfad als auch der 648-MB-Regressionsfall und der Aufgabe-7-`.ffpkg`-Repackpfad abgesichert.

Der maschinenlesbare Nachweis steht in [`FFPKG_VERIFICATION_v1.7.90.json`](FFPKG_VERIFICATION_v1.7.90.json).

## Vollständigkeit des Release

Das vollständige Quellarchiv enthält den gesamten Projektbestand inklusive `.github/`, `MkPFS-0.0.9/`, `helloworld/`, `extract_icon.py`, Changelog, Release Notes, FFPKG-Abnahmenachweis und vollständigem Quellhashmanifest. Die Pflichtdateien liegen zusätzlich eigenständig im Releaseordner vor.
