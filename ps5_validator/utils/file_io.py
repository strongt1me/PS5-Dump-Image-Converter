"""
PS5 Dump Validator – File I/O Utilities
Hilfsfunktionen für Dateizugriff, Grössen-Formatierung und Cache.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Callable, NamedTuple


CACHE_FILENAME = ".ps5val_cache.json"


def _weiterreichen(fehler: OSError) -> None:
    raise fehler


def get_all_files(root: str | Path) -> list[Path]:
    """Alle Dateien in einem Verzeichnis rekursiv auflisten.

    Raises:
        OSError: Ein Ordner darin ist nicht lesbar. ``os.walk`` uebergeht
            solche Ordner sonst still - bis zum 24.09.2026 pruefte die
            Dump-Pruefung dann nur einen Teil, und das Ergebnis konnte
            trotzdem "bestanden" lauten (Durchsicht, U4-2). Der Aufrufer
            faengt den Fehler ab: "Verzeichnis nicht lesbar".
    """
    root = Path(root)
    files: list[Path] = []
    for dirpath, _, filenames in os.walk(root, onerror=_weiterreichen):
        for fn in filenames:
            files.append(Path(dirpath) / fn)
    return sorted(files)


class Groesse(NamedTuple):
    """Ergebnis von :func:`groesse_summieren`."""

    summe: int            #: Bytes aller gezaehlten Dateien
    dateien: int          #: Zahl der gezaehlten Dateien
    fehler: int           #: Eintraege und Ordner, die nicht lesbar waren (nicht in ``summe``)
    abgebrochen: bool     #: ``abbruch`` lieferte ``True`` - ``summe`` ist, was bis dahin gezaehlt war
    verknuepfungen: int = 0                   #: gefundene Verknuepfungen (Symlinks), NTFS-Verbindungen (Junctions) und andere Reparsepunkte
    beispiele: "tuple[str, ...]" = ()         #: die ersten davon (:data:`VERKNUEPFUNG_BEISPIELE`), Pfad unter dem Ordner mit ``/``


#: So viele Verknuepfungen nennt :class:`Groesse` mit Namen; gezaehlt werden alle.
VERKNUEPFUNG_BEISPIELE = 3

#: Das Windows-Merkmal "Reparsepunkt" (``st_file_attributes``): Verknuepfung, Junction, aber auch OneDrive-Platzhalter und Dateien der
#: Datendeduplizierung. Dump Forge lehnt jeden Reparsepunkt im Spielordner ab (``scan.rs``: ``is_symlink() || is_reparse_point``).
REPARSEPUNKT = stat.FILE_ATTRIBUTE_REPARSE_POINT


def _ist_reparsepunkt(eintrag: "os.DirEntry[str]") -> bool:
    """Trägt der Eintrag selbst (nicht sein Ziel) das Merkmal Reparsepunkt? Nur unter Windows gibt es ``st_file_attributes``.

    ``DirEntry.stat(follow_symlinks=False)`` kommt unter Windows aus den Verzeichnisdaten, ohne weiteren Aufruf je Eintrag.
    """
    try:
        return bool(getattr(eintrag.stat(follow_symlinks=False), "st_file_attributes", 0) & REPARSEPUNKT)
    except OSError:
        return False


def groesse_summieren(ordner: str | Path, *, beobachter: Callable[[int, int], None] | None = None,
                      abbruch: Callable[[], bool] | None = None, verbindungen_folgen: bool = False,
                      genau: bool = False) -> Groesse:
    """Die Summe der Dateigroessen unter ``ordner`` - mit ``os.scandir`` statt ``os.walk`` und ``getsize`` je Datei.

    ``DirEntry.stat()`` liefert die Groesse unter Windows aus den Verzeichnisdaten, ohne einen weiteren Aufruf je Datei; die
    fruehere Zaehlung (``os.walk`` und ``os.path.getsize`` fuer jede Datei) brauchte fuer Ghost of Yotei (84.218 Dateien,
    150,75 GB) 348 s, ``scandir`` zaehlt dieselben Dateien und Bytes in rund 14 s (gemessen 19.11.2026). Am 12.09.2026 stand an
    einer USB-exFAT-Platte mit 17.000 Dateien einmal eine halbe Stunde.

    Args:
        beobachter: bekommt nach jeder gezaehlten Datei ``(summe, dateien)`` - der Aufrufer drosselt selbst.
        abbruch: wird je Verzeichnis gefragt; ``True`` beendet das Zaehlen sofort (``abgebrochen``).
        verbindungen_folgen: ``True`` folgt NTFS-Verbindungen (Junctions) wie ``os.walk`` es tat, ``False`` zaehlt sie nicht.
            Verknuepfungen (Symlinks) auf Ordner werden nie verfolgt. Beide stehen in ``Groesse.verknuepfungen`` (mit den ersten
            Namen in ``beispiele``), auch wenn ihnen gefolgt wird, dazu jeder andere Reparsepunkt unter Windows (OneDrive-Platzhalter,
            Datendeduplizierung): Dump Forge lehnt einen Ordner mit einem davon ab ("symlink (not followed)", gemessen 19.11.2026), und
            Seite 7 sagt das, bevor der Anwender STARTEN waehlt. Eine Verknuepfung auf eine Datei wird wie bisher mit der Groesse ihres
            Ziels gezaehlt und ebenfalls vermerkt; ein Reparsepunkt, der keine Verknuepfung ist, zaehlt mit seiner Groesse und wird vermerkt.
        genau: ``True`` fragt die Groesse je Datei mit ``os.stat`` ab (ein Aufruf je Datei, wie frueher). ``DirEntry.stat()`` gibt
            unter Windows die Groesse aus dem Verzeichniseintrag, und der bleibt bei einer Datei, die gerade geschrieben wird, auf dem
            alten Stand (gemessen 19.11.2026: 0 Bytes bei einem offenen Schreiber, ``os.stat`` 4 bis 400 MB). Wer ein Ziel waehrend
            des Kopierens abfragt (Fortschritt), braucht ``genau``; fuer einen ruhenden Ordner (Quelle) genuegt die schnelle Zaehlung.

    Fehler werden nicht geworfen, sondern gezaehlt (``fehler``): Der Aufrufer entscheidet, ob eine Teilsumme taugt. Ein Eintrag, der
    zwischen Auflisten und Abfragen verschwindet (``FileNotFoundError``: geloescht, oder ein Symlink ohne Ziel), ist kein Fehler -
    ``os.walk`` und ``getsize`` liessen ihn ebenfalls aus. Der Wurzelordner selbst muss da sein. Eine Ausnahme aus ``beobachter`` oder
    ``abbruch`` geht unveraendert an den Aufrufer (sie zaehlt nicht als Verzeichnisfehler).
    """
    summe = dateien = fehler = verknuepft = 0
    beispiele: list[str] = []
    wurzel = str(ordner)
    stapel = [wurzel]

    def vermerken(pfad_der_verknuepfung: str) -> None:
        nonlocal verknuepft
        verknuepft += 1
        if len(beispiele) < VERKNUEPFUNG_BEISPIELE:
            beispiele.append(os.path.relpath(pfad_der_verknuepfung, wurzel).replace(os.sep, "/"))

    def ergebnis(abgebrochen: bool) -> Groesse:
        return Groesse(summe, dateien, fehler, abgebrochen, verknuepft, tuple(beispiele))

    while stapel:
        if abbruch is not None and abbruch():
            return ergebnis(True)
        pfad = stapel.pop()
        try:
            verzeichnis = os.scandir(pfad)
        except FileNotFoundError:
            if pfad == wurzel:
                fehler += 1                                # die Wurzel fehlt: das ist ein Fehler (nichts zu zaehlen waere eine falsche 0)
            continue
        except OSError:
            fehler += 1
            continue
        # Nur das Lesen des Verzeichnisses und die Abfrage eines Eintrags stehen unter ``except OSError``: ``beobachter`` und ``abbruch``
        # sind Rueckrufe des Aufrufers - ein ``OSError`` aus ihnen ist kein Verzeichnisfehler und darf nicht als einer gezaehlt werden
        # (er liess sonst den Rest des Ordners still aus; Gegenlese 19.11.2026).
        with verzeichnis as eintraege:
            while True:
                try:
                    eintrag = next(eintraege)
                except StopIteration:
                    break
                except FileNotFoundError:
                    if pfad == wurzel:
                        fehler += 1
                    break
                except OSError:
                    fehler += 1                            # das Verzeichnis liess sich nicht zu Ende lesen: der Rest fehlt
                    break
                try:
                    if eintrag.is_dir(follow_symlinks=False):
                        pruefen = getattr(eintrag, "is_junction", None)   # DirEntry.is_junction gibt es ab Python 3.12
                        ist_verbindung = pruefen is not None and pruefen()
                        if ist_verbindung or _ist_reparsepunkt(eintrag):
                            vermerken(eintrag.path)
                        if verbindungen_folgen or not ist_verbindung:
                            stapel.append(eintrag.path)    # ein anderer Reparsepunkt (OneDrive-Ordner) wird wie bisher gelesen
                        continue
                    if eintrag.is_symlink():
                        vermerken(eintrag.path)
                        if eintrag.is_dir():
                            continue                       # eine Verknuepfung auf einen Ordner: wie ``os.walk``, nicht gezaehlt
                    elif _ist_reparsepunkt(eintrag):
                        vermerken(eintrag.path)            # z. B. ein OneDrive-Platzhalter: zaehlt mit, wird aber vermerkt
                    summe += (os.stat(eintrag.path) if genau else eintrag.stat()).st_size
                except FileNotFoundError:
                    continue                               # verschwunden oder Symlink ohne Ziel: nichts zu zaehlen, kein Fehler
                except OSError:
                    fehler += 1
                    continue
                dateien += 1
                if beobachter is not None:
                    beobachter(summe, dateien)
                if abbruch is not None and dateien % 512 == 0 and abbruch():
                    return ergebnis(True)                  # auch in einem Ordner mit zehntausenden Dateien
    return ergebnis(False)


def fmt_bytes(n: int) -> str:
    """Bytes in lesbare Grösse umwandeln."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def load_cache(cache_path: str | Path) -> dict[str, Any]:
    """Hash-Cache aus JSON-Datei laden."""
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache_path: str | Path, data: dict[str, Any]) -> None:
    """Hash-Cache in JSON-Datei speichern."""
    try:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def get_cache_path(root: str | Path) -> Path:
    """Cache-Pfad für ein Verzeichnis oder eine Datei bestimmen."""
    root = Path(root)
    if root.is_dir():
        return root / CACHE_FILENAME
    return root.parent / CACHE_FILENAME


def write_json_report(output_path: str | Path, data: dict[str, Any]) -> None:
    """JSON-Bericht in Datei schreiben."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
