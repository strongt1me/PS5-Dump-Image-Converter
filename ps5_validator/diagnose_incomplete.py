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

def diagnose_incomplete_extraction(dump_path: str) -> str:
    """Analysiert einen unvollständig extrahierten PS5-Dump und gibt Tipps."""
    import os
    from pathlib import Path
    
    dump_root = Path(dump_path)
    
    critical = [
        "eboot.bin",
        "sce_sys/param.json",
        "sce_sys/pfs-version.dat",
    ]
    
    missing = []
    for f in critical:
        if not (dump_root / f).exists():
            missing.append(f)
    
    msg = f"""
============================================================
[DIAGNOSE] Unvollständiger PS5-Dump erkannt
============================================================

Kritische Dateien fehlen: {', '.join(missing) if missing else 'keine'}

Vermutet Ursache:
- Die .ffpfsc-Datei wurde nicht vollständig zu einem Game Dump extrahiert
- Dies ist normalerweise ein Zeichen für eine beschädigte oder
  inkompatible .ffpfsc-Datei

Empfohlene Lösungen:
1. SHA256-Prüfsumme der .ffpfsc-Datei vergleichen
   - Download überprüfen oder erneut laden
2. MkPFS-Version aktualisieren
   - Neuere Version unterstützt möglicherweise neuere Dump-Formate
3. Dump-Prozess erneut starten
   - Mit ausreichend freiem Speicherplatz (>150% der Dump-Größe)
4. Auf beschädigte Festplatte prüfen (CHKDSK/fsck)
5. PS5 Dump neu erstellen mit aktueller Methode

Weitere Infos:
- mkpfs: https://github.com/PSBrew/MkPFS
- PS5-exfat-builder: https://github.com/PSBrew/ps5-exfat-builder
============================================================
"""
    
    return msg

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        dump_path = sys.argv[1]
        print(diagnose_incomplete_extraction(dump_path))
    else:
        print(__doc__)
