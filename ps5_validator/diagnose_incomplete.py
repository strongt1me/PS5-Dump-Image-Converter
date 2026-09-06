#!/usr/bin/env python3
"""
Diagnose-Hilfe für unvollständig extrahierte PS5 Dumps

Wenn eine .ffpfsc-Datei nicht vollständig entpackt wird, fehlen kritische Dateien
wie eboot.bin, sce_sys/param.json und sce_sys/pfs-version.dat.

Häufige Ursachen:
1. Beschädigte .ffpfsc-Datei (beschädigter Download oder korrupter Sektor)
2. Inkompatible MkPFS-Version (unterschiedliche Dateiformate)
3. Unvollständige Extraktions-Prozess (unterbrochen oder Fehler)
4. Zu wenig Speicherplatz bei der Extraktions-Phase
5. Permissions-Fehler während der Extraktion

Lösungen:
- Die .ffpfsc-Datei mit checksum validieren (SHA256)
- Ein frisches Dump mit neuerer MkPFS-Version erstellen
- Den Dump-Prozess erneut starten
- Genug freien Speicherplatz bereitstellen
"""

#: Die Bausteine des Berichts. Wie in den Helfermodulen unter
#: ``ps5_validator/utils`` trägt dieses Modul seine Sätze nur als Vorgabe -
#: die Oberfläche reicht über ``texte`` die übersetzte Fassung herein.
#:
#: Bei der großen Übersetzung (v1.8.12) wurde dieser Bericht ausdrücklich
#: ausgenommen, weil er als "technisch, geringer Wert" galt. Am 06.09.2026
#: wurde nachverfolgt, wohin er geht: ``_append_to_log`` und damit in das
#: sichtbare Protokollfeld des Hauptfensters, bei jedem gescheiterten
#: Validatorlauf mit fehlenden Pflichtdateien. Er ist also genau das, was
#: der Anwender im Fehlerfall zu lesen bekommt.
MELDUNGEN = {
    "kopfzeile": "[DIAGNOSE] Unvollständiger PS5-Dump erkannt",
    "fehlende": "Kritische Dateien fehlen: {dateien}",
    "keine": "keine",
    "ursache": (
        "Vermutete Ursache:\n"
        "- Die .ffpfsc-Datei wurde nicht vollständig zu einem Game Dump "
        "extrahiert\n"
        "- Das ist normalerweise ein Zeichen für eine beschädigte oder "
        "unpassende .ffpfsc-Datei"
    ),
    "loesungen": (
        "Empfohlene Lösungen:\n"
        "1. SHA256-Prüfsumme der .ffpfsc-Datei vergleichen\n"
        "   - Download überprüfen oder erneut laden\n"
        "2. MkPFS-Version aktualisieren\n"
        "   - Eine neuere Fassung kennt möglicherweise neuere Dump-Formate\n"
        "3. Den Entpackvorgang erneut starten\n"
        "   - Mit ausreichend freiem Speicherplatz (>150 % der Dump-Größe)\n"
        "4. Auf einen Fehler des Datenträgers prüfen (CHKDSK/fsck)\n"
        "5. Den PS5-Dump neu erstellen"
    ),
    "weitere_infos": "Weitere Infos:",
}

#: Die kritischen Dateien - dieselbe Liste, die auch der Validator führt.
KRITISCHE_DATEIEN = (
    "eboot.bin",
    "sce_sys/param.json",
    "sce_sys/pfs-version.dat",
)

_TRENNLINIE = "=" * 60


def diagnose_incomplete_extraction(dump_path: str,
                                   texte: "dict | None" = None) -> str:
    """Analysiert einen unvollständig extrahierten PS5-Dump und gibt Tipps.

    Args:
        dump_path: Der Ordner, in dem der Dump liegen sollte.
        texte: Vorlagen je Kennung; fehlt eine, gilt die aus
            :data:`MELDUNGEN`. So kann die Oberfläche übersetzen, ohne dass
            dieses Modul ``i18n`` kennt.

    Returns:
        Der fertige Bericht.
    """
    from pathlib import Path

    def _satz(kennung: str, **werte) -> str:
        vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
        try:
            return vorlage.format(**werte)
        except (KeyError, IndexError, ValueError):
            # Eine unbrauchbare Vorlage darf den Bericht nicht sprengen -
            # dann lieber der eingebaute Satz.
            return MELDUNGEN[kennung].format(**werte)

    dump_root = Path(dump_path)
    missing = [f for f in KRITISCHE_DATEIEN if not (dump_root / f).exists()]

    return "\n".join((
        "",
        _TRENNLINIE,
        _satz("kopfzeile"),
        _TRENNLINIE,
        "",
        _satz("fehlende",
              dateien=", ".join(missing) if missing else _satz("keine")),
        "",
        _satz("ursache"),
        "",
        _satz("loesungen"),
        "",
        _satz("weitere_infos"),
        "- mkpfs: https://github.com/PSBrew/MkPFS",
        "- PS5-exfat-builder (kerrdec97): https://github.com/PSBrew/ps5-exfat-builder",
        _TRENNLINIE,
        "",
    ))

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        dump_path = sys.argv[1]
        print(diagnose_incomplete_extraction(dump_path))
    else:
        print(__doc__)
