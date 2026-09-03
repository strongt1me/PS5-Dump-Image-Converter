# -*- coding: utf-8 -*-
"""Ruft ``prosperopkg`` auf - das Werkzeug, das PS5-Pakete baut.

Warum ein eigener Prozess und keine eingebundene Bibliothek: Darunter
liegt LibProsperoPkg unter **GPL-3**. Fest dazugelinkt schlaegt die
Lizenz auf das ganze Programm durch. Ueber die Prozessgrenze bleibt die
Trennung sauber - denselben Weg gehen ``mkpfs`` und ``UFS2Tool`` schon.
Einzelheiten stehen in ``ProsperoPkg-2.5/UPSTREAM.md``.

Das Werkzeug meldet sich zeilenweise. Die letzte Zeile traegt das
Ergebnis:

* ``RESULT: READY`` / ``RESULT: NOT_READY`` bei ``inspect``
* ``RESULT: <Pfad>`` bei ``build``

Alles davor ist Fortschritt und gehoert unveraendert ins
Protokollfenster.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from typing import Callable, Iterable

#: Der Ordner des Werkzeugs, relativ zum Programm.
WERKZEUGORDNER = "ProsperoPkg-2.5"

#: Die ausfuehrbare Datei je Plattform.
PROGRAMMNAME = "prosperopkg.exe" if sys.platform == "win32" else "prosperopkg"

#: Unterordner je Plattform - wie bei UFS2Tool.
#:
#: Auf dem Mac entscheidet zusaetzlich der Prozessor: Ein x86_64-Bau
#: laeuft auf Apple Silicon nur ueber Rosetta 2, und ohne Rosetta findet
#: macOS gar keine passende Architektur. Deshalb liegen beide Bauten da.
PLATTFORMORDNER = {
    "win32": "win-x64",
    "linux": "linux-x64",
    "darwin": "osx-x64",
}


def plattformordner() -> str:
    """Der Ordnername des Baus fuer diesen Rechner.

    Dieselbe Unterscheidung wie in
    ``werkzeuge_bereitstellen.ufs2tool_kennung``: Betriebssystem **und**
    Prozessor. Ohne den zweiten Teil bekaeme ein Mac mit M-Prozessor den
    Intel-Bau untergeschoben.

    Returns:
        Der Unterordner, oder der Windows-Bau als letzte Zuflucht.
    """
    maschine = (platform.machine() or "").lower()
    arm = maschine in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "osx-arm64" if arm else "osx-x64"
    return PLATTFORMORDNER.get(sys.platform, "win-x64")

#: Was ``inspect`` als Ergebnis kennt.
BEREIT = "READY"
NICHT_BEREIT = "NOT_READY"


class ProsperoFehler(Exception):
    """Das Werkzeug fehlt, bricht ab oder antwortet unverstaendlich."""


def _suchwurzeln() -> list[str]:
    """Die Stellen, an denen mitgelieferte Ordner liegen koennen.

    Gleiche Reihenfolge wie ``PS5ConverterGUI._mitgeliefert_finden``: im
    entpackten Bundle, neben der Programmdatei, im Arbeitsverzeichnis.
    """
    wurzeln = [getattr(sys, "_MEIPASS", "")]
    try:
        wurzeln.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:  # noqa: BLE001
        pass
    wurzeln.append(os.getcwd())
    wurzeln.append(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    return [w for w in wurzeln if w]


def werkzeug_finden() -> str:
    """Der Pfad zu ``prosperopkg``.

    Returns:
        Der Pfad, oder ein leerer String, wenn das Werkzeug fehlt.
    """
    unterordner = plattformordner()
    for wurzel in _suchwurzeln():
        pfad = os.path.join(wurzel, WERKZEUGORDNER, unterordner, PROGRAMMNAME)
        if os.path.isfile(pfad):
            # Das Ausfuehrungsrecht ueberlebt weder NTFS noch eine ZIP-Datei.
            # Ohne diese Zeile startet der Linux-Bau nicht - derselbe Grund,
            # aus dem werkzeuge_bereitstellen es fuer UFS2Tool setzt.
            if sys.platform != "win32" and not os.access(pfad, os.X_OK):
                try:
                    os.chmod(pfad, os.stat(pfad).st_mode | 0o111)
                except OSError:
                    pass
            return pfad
    return ""


def _laufen_lassen(argumente: list[str],
                   melden: Callable[[str], None] | None = None,
                   zeitgrenze: float = 7200.0) -> tuple[int, list[str]]:
    """Startet das Werkzeug und reicht jede Zeile weiter, sobald sie kommt.

    Args:
        argumente: Was hinter dem Programmnamen steht.
        melden: Bekommt jede Ausgabezeile. ``None`` schweigt.
        zeitgrenze: Nach so vielen Sekunden wird abgebrochen. Zwei Stunden
            sind reichlich: Das Packen rechnet die Kraken-Kompression in
            reinem C#, und die ist bei einem grossen Titel langsam.

    Returns:
        ``(Rueckgabewert, Zeilen)``.
    """
    programm = werkzeug_finden()
    if not programm:
        raise ProsperoFehler(
            "prosperopkg wurde nicht gefunden (erwartet in %s/%s/)."
            % (WERKZEUGORDNER, plattformordner()))

    anlauf: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if sys.platform == "win32":
        # Ohne das blitzt fuer jeden Aufruf ein Fenster auf.
        anlauf["creationflags"] = 0x08000000     # CREATE_NO_WINDOW

    zeilen: list[str] = []
    with subprocess.Popen([programm] + argumente, **anlauf) as lauf:
        try:
            for zeile in lauf.stdout or ():
                sauber = zeile.rstrip("\r\n")
                zeilen.append(sauber)
                if melden is not None:
                    melden(sauber)
            lauf.wait(timeout=zeitgrenze)
        except subprocess.TimeoutExpired:
            lauf.kill()
            raise ProsperoFehler(
                "prosperopkg hat die Zeitgrenze von %.0f s ueberschritten."
                % zeitgrenze) from None
    return (lauf.returncode, zeilen)


def _ergebniszeile(zeilen: Iterable[str]) -> str:
    """Der Wert hinter ``RESULT:``, oder ein leerer String."""
    for zeile in reversed(list(zeilen)):
        if zeile.startswith("RESULT:"):
            return zeile.split(":", 1)[1].strip()
    return ""


#: Was ``read`` als letzte Zeile meldet, wenn die Datei keine PS5-PKG ist.
KEINE_PKG = "NOT_A_PS5_PKG"


def paket_lesen(datei: str,
                melden: Callable[[str], None] | None = None) -> dict:
    """Liest den aeusseren Container einer PS5-PKG-Datei.

    Das eigene Entpackwerk des Programms kommt an PS5-Pakete nicht heran -
    an 31 Dateien gemessen. LibProsperoPkg kann es, und die Bibliothek liegt
    ohnehin bei; bis v1.9.2 bot die Huelle davon nur ``build`` an.

    **Gelesen wird nur der aeussere Container.** Kopf, Content-ID und die
    Eintragstabelle - die eingebettete PFS bleibt verschluesselt, dafuer
    braeuchte es Schluessel, die hier niemand hat. Wer eine Dateiliste des
    Spiels erwartet, bekommt sie also nicht; die Eintraege sind die des
    Pakets (``param.sfo``, ``playgo-chunk.dat``, Bilder), nicht die des
    Spielinhalts.

    Args:
        datei: Die ``.pkg``-Datei.
        melden: Bekommt jede Ausgabezeile, sobald sie anfaellt.

    Returns:
        ``{"ist_pkg": bool, "typ": str, "kopf": {...}, "eintraege": [...],
        "unvollstaendig": int, "zeilen": [str]}``

        ``typ`` ist ``Meta`` (nur Metadaten, ``\\x7FCNT``), ``FullDebug``
        oder ``FullRetail`` (finalisiertes Abbild, ``\\x7FFIH``).
        ``unvollstaendig`` nennt die fehlenden Bytes eines geteilten Satzes,
        sonst 0.

    Raises:
        ProsperoFehler: Das Werkzeug fehlt oder bricht unerwartet ab.
    """
    code, zeilen = _laufen_lassen(["read", "--source", datei], melden,
                                  zeitgrenze=300.0)
    ergebnis = _ergebniszeile(zeilen)

    # Rueckgabewert 3 hat zwei Bedeutungen: "keine PS5-PKG" ist eine
    # Feststellung, kein Fehler - das Programm soll sie anzeigen duerfen,
    # ohne eine Ausnahme zu fangen. Alles andere bleibt ein Fehler.
    if ergebnis == KEINE_PKG:
        return {"ist_pkg": False, "typ": "", "kopf": {}, "eintraege": [],
                "unvollstaendig": 0, "zeilen": zeilen}
    if code != 0:
        raise ProsperoFehler(
            "prosperopkg read endete mit %d: %s"
            % (code, " | ".join(zeilen[-3:])))

    kopf: dict = {}
    eintraege: list = []
    fehlend = 0
    for zeile in zeilen:
        if zeile.startswith("ENTRY\t"):
            teile = zeile.split("\t")
            if len(teile) >= 7:
                eintraege.append({
                    "name": teile[1] if teile[1] != "-" else "",
                    "id": teile[2],
                    "offset": _zahl(teile[3]),
                    "groesse": _zahl(teile[4]),
                    "verschluesselt": teile[5] == "encrypted",
                    "schluesselindex": _zahl(teile[6]),
                })
        elif zeile.startswith("UNVOLLSTAENDIG:"):
            fehlend = _zahl(zeile.split(":", 1)[1].split()[0])
        elif ":" in zeile and not zeile.startswith(("RESULT:", "HINWEIS:")):
            name, _, wert = zeile.partition(":")
            name = name.strip()
            if name:
                kopf[name] = wert.strip()

    return {
        "ist_pkg": True,
        "typ": ergebnis,
        "kopf": kopf,
        "eintraege": eintraege,
        "unvollstaendig": fehlend,
        "zeilen": zeilen,
    }


def _zahl(text: str) -> int:
    """Eine Zahl aus einer Ausgabezeile, oder 0.

    Bewusst nachsichtig: Eine unlesbare Zahl darf die uebrigen Angaben nicht
    mitnehmen - der Kopf ist auch ohne sie brauchbar.
    """
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return 0


def pruefen(quelle: str,
            melden: Callable[[str], None] | None = None) -> dict:
    """Sagt, ob ein Backup als Debug-Paket starten wuerde.

    Args:
        quelle: Der Ordner des Backups (ein entpackter Dump).
        melden: Bekommt jede Ausgabezeile.

    Returns:
        ``{"bereit": bool, "blocker": [(Art, Pfad)], "hinweise": [str],
        "zeilen": [str]}``

    Raises:
        ProsperoFehler: Das Werkzeug fehlt oder bricht ab.
    """
    code, zeilen = _laufen_lassen(["inspect", "--source", quelle], melden,
                                  zeitgrenze=600.0)
    if code != 0:
        raise ProsperoFehler(
            "prosperopkg inspect endete mit %d: %s"
            % (code, " | ".join(zeilen[-3:])))

    blocker = []
    hinweise = []
    for zeile in zeilen:
        if zeile.startswith("BLOCKER:"):
            rest = zeile.split(":", 1)[1].strip()
            teile = rest.split("\t", 1)
            blocker.append((teile[0].strip(),
                            teile[1].strip() if len(teile) > 1 else ""))
        elif zeile.startswith("ISSUE:"):
            hinweise.append(zeile.split(":", 1)[1].strip())
    return {
        "bereit": _ergebniszeile(zeilen) == BEREIT,
        "blocker": blocker,
        "hinweise": hinweise,
        "zeilen": zeilen,
    }


def bauen(quelle: str, zielordner: str,
          melden: Callable[[str], None] | None = None,
          lizenzfrei: bool = True,
          fake_signieren: bool = False,
          schnell: bool = True,
          zeitgrenze: float = 7200.0) -> str:
    """Baut ein installierbares Debug-Paket aus einem Backup-Ordner.

    Fehlende Angaben (Content-ID, Title-ID, Titel, Version) holt sich das
    Werkzeug selbst aus ``sce_sys/param.json`` des Quellordners.

    Args:
        quelle: Der Ordner des Backups.
        zielordner: Wohin die ``.pkg`` geschrieben wird.
        melden: Bekommt jede Ausgabezeile.
        lizenzfrei: Ohne Lizenzsatz bauen; der Einhaengeschluessel wird
            aus Content-ID und Passcode abgeleitet. Das ist der Weg fuer
            ein Debug-Paket, denn ein echter ``rif`` laesst sich am
            Rechner nicht erzeugen.
        fake_signieren: Module beim Bauen fake-signieren.
        schnell: Den teuren Optimal-Parse des Kraken-Encoders abschalten.
            **Vorgabe an**, und zwar aus Messung: Am 29.08.2026 lief
            derselbe 1-GB-Dump mit Vorgabe 134 Minuten ohne Ergebnis und
            mit dieser Option 319 Sekunden durch. Das Paket wird dabei
            etwas groesser; die Einzelheiten stehen in
            ``ProsperoPkg-2.5/UPSTREAM.md``.
        zeitgrenze: Sekunden bis zum Abbruch.

    Returns:
        Der Pfad zur fertigen ``.pkg``.

    Raises:
        ProsperoFehler: Das Werkzeug fehlt, bricht ab oder nennt keinen Pfad.
    """
    argumente = ["build", "--source", quelle, "--out", zielordner]
    if lizenzfrei:
        argumente.append("--license-free")
    if fake_signieren:
        argumente.append("--fake-sign")
    if schnell:
        argumente.append("--schnell")

    code, zeilen = _laufen_lassen(argumente, melden, zeitgrenze)
    if code != 0:
        raise ProsperoFehler(
            "prosperopkg build endete mit %d: %s"
            % (code, " | ".join(zeilen[-3:])))
    pfad = _ergebniszeile(zeilen)
    if not pfad or not os.path.isfile(pfad):
        raise ProsperoFehler(
            "prosperopkg meldete keinen brauchbaren Pfad: %r" % pfad)
    return pfad

def homebrew_bauen(quelle: str, zielordner: str,
                   melden: Callable[[str], None] | None = None,
                   modulname: str = "",
                   schnell: bool = True,
                   zeitgrenze: float = 3600.0) -> str:
    """Packt kompiliertes Homebrew in ein installierbares Debug-Paket.

    Der Unterschied zu :func:`bauen` ist nicht bloss der Einstiegspunkt:

    * :func:`bauen` erwartet einen fertigen Anwendungsbaum - einen
      entpackten Spiel-Dump.
    * Diese Funktion baut den Baum selbst: Das kompilierte Modul wird zu
      ``eboot.bin``, ein vorhandener ``sce_sys``-Ordner kommt mit.

    Und vor allem: Das Ergebnis traegt ``RequiresRif = False``. Ein
    Spiel-Backup scheitert beim Start an der fehlenden Lizenzdatei, die
    sich am Rechner nicht erzeugen laesst - Homebrew braucht sie nicht.
    Am 29.08.2026 gemessen: ein 120-KB-Modul in **1 Sekunde** zu einem
    931-KB-Paket, ``IsLaunchReady`` wahr.

    Args:
        quelle: Der Ordner mit dem kompilierten Modul. Erwartet wird ein
            **rohes ELF**; ``sce_sys/`` ist freiwillig, liefert aber
            Content-ID, Titel und Version, wenn eine ``param.json``
            darin liegt.
        zielordner: Wohin die ``.pkg`` geschrieben wird.
        melden: Bekommt jede Ausgabezeile.
        modulname: Der Dateiname des Moduls. Leer heisst ``eboot.bin``.
        schnell: Wie bei :func:`bauen`.
        zeitgrenze: Sekunden bis zum Abbruch. Eine Stunde genuegt
            reichlich - Homebrew ist um Groessenordnungen kleiner als
            ein Spiel.

    Returns:
        Der Pfad zur fertigen ``.pkg``.

    Raises:
        ProsperoFehler: Das Werkzeug fehlt, bricht ab oder nennt keinen Pfad.
    """
    argumente = ["homebrew", "--source", quelle, "--out", zielordner]
    if modulname:
        argumente += ["--module", modulname]
    if schnell:
        argumente.append("--schnell")

    code, zeilen = _laufen_lassen(argumente, melden, zeitgrenze)
    if code != 0:
        raise ProsperoFehler(
            "prosperopkg homebrew endete mit %d: %s"
            % (code, " | ".join(zeilen[-3:])))
    pfad = _ergebniszeile(zeilen)
    if not pfad or not os.path.isfile(pfad):
        raise ProsperoFehler(
            "prosperopkg meldete keinen brauchbaren Pfad: %r" % pfad)
    return pfad
