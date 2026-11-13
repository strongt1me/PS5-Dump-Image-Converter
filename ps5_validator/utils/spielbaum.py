# -*- coding: utf-8 -*-
"""Lesebaum: die Dateien eines Spiels als Liste mit Lesefunktion - ohne sie vorher irgendwohin zu entpacken.

Erste Etappe von "Strom ohne Zwischenordner" (Stufe 3 nach dem Vorbild von Dump Forge, 13.11.2026). Bis dahin entpackt jeder
Weg, der eine ``.exfat`` umbaut, das ganze Spiel in einen Ordner auf dem Ziellaufwerk (151 GB geschrieben, 4-faches Lesen) und
baut daraus das Ergebnis. Ein Lesebaum kennt nur, **was** im Spiel liegt (Pfad, Groesse) und **wie** man es liest; wer ihn
benutzt, braucht keinen Ordner mehr.

Vier Arten:

* :class:`PfsBaum` - ein ``.ffpfs``/``.ffpfsc`` (flach oder mit innerem exFAT/PFS), die PFSC-Bloecke werden erst beim Lesen entpackt.
* :class:`OrdnerBaum` - ein Ordner auf der Platte (wie bisher).
* :class:`ExfatBaum` - eine ``.exfat``-Datei, gelesen mit dem eingebetteten Leser von MkPFS. Jeder Faden bekommt seinen eigenen
  Dateigriff und Leser (der Leser merkt sich nur eine Stelle in der Datei und darf nicht von zwei Faeden zugleich benutzt werden).
* :class:`UeberlagerBaum` - ein Baum, dessen Dateien durch die eines zweiten ersetzt, ergaenzt oder entfernt sind. So bleiben die
  wenigen Dateien, die der Einbau veraendert (Backport, Fake-Signatur, DLC EMU, AMPR-Bibliothek), in einem kleinen Ordner, und
  der Rest kommt weiter aus der Quelle.

Alle drei liefern ``dateien()`` als Liste von :class:`BaumDatei` in fester Reihenfolge (nach Pfad) und ``stempel()``, womit sich
vor dem Ersetzen der Quelle pruefen laesst, ob sie waehrenddessen geaendert wurde (SourceStamp bei Forge).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

#: Wie gross ein Stueck ist, das ``lesen`` in einem Zug liefert (hoechstens).
LESE_STUECK = 4 * 1024 * 1024


class BaumFehler(RuntimeError):
    """Ein Lesebaum laesst sich nicht aufbauen oder eine Datei darin nicht lesen."""


@dataclass(frozen=True)
class BaumDatei:
    """Eine Datei im Spiel: Pfad (mit ``/``, ohne fuehrenden Schraegstrich), Groesse und wie man sie liest."""

    rel: str
    groesse: int
    _leser: Callable[[int], Iterator[bytes]]

    def lesen(self, stueck: int = LESE_STUECK) -> Iterator[bytes]:
        """Die Bytes der Datei in Stuecken zu hoechstens ``stueck`` Bytes. Ihre Summe ist genau ``groesse``."""
        gelesen = 0
        for daten in self._leser(max(1, int(stueck))):
            gelesen += len(daten)
            if gelesen > self.groesse:
                raise BaumFehler("%s ist waehrend des Lesens gewachsen" % self.rel)
            yield daten
        if gelesen < self.groesse:
            raise BaumFehler("%s ist kuerzer als gemeldet (%d von %d Bytes)" % (self.rel, gelesen, self.groesse))


class _Baum:
    """Gemeinsames: ``dateien``, ``suchen``, Schliessen."""

    def dateien(self) -> list[BaumDatei]:
        raise NotImplementedError

    def stempel(self) -> tuple:
        raise NotImplementedError

    def suchen(self) -> dict[str, BaumDatei]:
        """Alle Dateien nach Pfad."""
        return {d.rel: d for d in self.dateien()}

    def schliessen(self) -> None:
        """Gibt Dateigriffe frei. Mehrfaches Rufen schadet nicht."""

    def __enter__(self) -> "_Baum":
        return self

    def __exit__(self, *_a: Any) -> None:
        self.schliessen()


class OrdnerBaum(_Baum):
    """Die regulaeren Dateien eines Ordners. Verweise (Symlinks) und Sonderdateien zaehlen nicht, werden aber gemerkt."""

    def __init__(self, wurzel: str, ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.wurzel = os.path.abspath(wurzel)
        if not os.path.isdir(self.wurzel):
            raise BaumFehler("kein Ordner: %s" % self.wurzel)
        self._ignoriert = ignoriert
        self.uebersprungen: list[str] = []
        self._dateien: "list[BaumDatei] | None" = None
        self._stempel_oeffnen: "tuple | None" = None

    def _leser_fuer(self, voll: str) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            with open(voll, "rb") as fh:
                while True:
                    daten = fh.read(stueck)
                    if not daten:
                        return
                    yield daten
        return lesen

    def dateien(self) -> list[BaumDatei]:
        if self._dateien is not None:
            return self._dateien
        gefunden: list[BaumDatei] = []
        self.uebersprungen = []
        for ordner, unter, namen in os.walk(self.wurzel):
            unter.sort()
            for name in sorted(namen):
                voll = os.path.join(ordner, name)
                rel = os.path.relpath(voll, self.wurzel).replace(os.sep, "/")
                if self._ignoriert is not None and any(self._ignoriert(t) for t in rel.split("/")):
                    continue
                if os.path.islink(voll) or not os.path.isfile(voll):
                    self.uebersprungen.append(rel)
                    continue
                gefunden.append(BaumDatei(rel, os.path.getsize(voll), self._leser_fuer(voll)))
        gefunden.sort(key=lambda d: d.rel)
        self._dateien = gefunden
        # Der Stand beim Oeffnen (= beim ersten Auflisten), gegen den :meth:`unveraendert` spaeter vergleicht.
        self._stempel_oeffnen = self.stempel()
        return gefunden

    def stempel(self) -> tuple:
        """Pfad, Groesse und Aenderungszeit jeder Datei - ein Spiel mit 84.000 Dateien braucht dafuer Sekunden, keine Minuten."""
        zeilen = []
        for d in self.dateien():
            try:
                st = os.stat(os.path.join(self.wurzel, *d.rel.split("/")))
            except OSError:
                zeilen.append((d.rel, -1, -1))
                continue
            zeilen.append((d.rel, st.st_size, st.st_mtime_ns))
        return ("ordner", self.wurzel, tuple(zeilen))

    def unveraendert(self) -> bool:
        """Ob die Dateien noch so sind wie beim ersten Auflisten (Pfad, Groesse, Aenderungszeit); neue oder fehlende Dateien zaehlen mit."""
        if self._stempel_oeffnen is None:
            return True
        # Neu auflisten: eine Datei, die dazugekommen ist, steht nicht in der gemerkten Liste.
        try:
            jetzt = OrdnerBaum(self.wurzel, ignoriert=self._ignoriert)
            jetzt.dateien()                       # merkt den Stand dieses Augenblicks in ``_stempel_oeffnen``
            return jetzt._stempel_oeffnen == self._stempel_oeffnen
        except (OSError, BaumFehler):
            return False


class ExfatBaum(_Baum):
    """Die Dateien in einer ``.exfat``-Datei, gelesen ohne Einhaengen und ohne Entpacken.

    ``mkpfs_ordner`` ist der Ordner, der das Paket ``mkpfs`` enthaelt (Hauptmodul: ``_extract_embedded_mkpfs()``); ohne Angabe
    muss ``mkpfs`` schon importierbar sein.
    """

    def __init__(self, pfad: str, mkpfs_ordner: str = "", ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.pfad = os.path.abspath(pfad)
        if not os.path.isfile(self.pfad):
            raise BaumFehler("keine Datei: %s" % self.pfad)
        if mkpfs_ordner:
            import sys
            if mkpfs_ordner not in sys.path:
                sys.path.insert(0, mkpfs_ordner)
        try:
            from mkpfs.exfat import ExfatError, ExfatReader     # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        except ImportError as exc:                                 # pragma: no cover - ohne MkPFS gibt es das Programm nicht
            raise BaumFehler("MkPFS nicht gefunden: %s" % exc) from exc
        self._ExfatReader = ExfatReader
        self._ExfatError = ExfatError
        self._ignoriert = ignoriert
        self._lokal = threading.local()
        self._griffe: list[Any] = []
        self._sperre = threading.Lock()
        self._stempel = self._datei_stempel()
        self._dateien: "list[BaumDatei] | None" = None
        self._geschlossen = False

    def _datei_stempel(self) -> tuple:
        st = os.stat(self.pfad)
        return ("exfat", self.pfad, st.st_size, st.st_mtime_ns)

    def _leser(self) -> Any:
        """Der Leser dieses Fadens; der erste Aufruf je Faden oeffnet Datei und liest die FAT."""
        leser = getattr(self._lokal, "leser", None)
        if leser is None:
            if self._geschlossen:
                raise BaumFehler("Lesebaum ist geschlossen")
            fh = open(self.pfad, "rb")
            try:
                leser = self._ExfatReader(fh)
            except Exception:
                fh.close()
                raise
            with self._sperre:
                self._griffe.append(fh)
            self._lokal.leser = leser
        return leser

    def dateien(self) -> list[BaumDatei]:
        if self._dateien is not None:
            return self._dateien
        try:
            eintraege = list(self._leser().iter_files())
        except self._ExfatError as exc:
            raise BaumFehler("exFAT-Abbild nicht lesbar: %s" % exc) from exc
        gefunden: list[BaumDatei] = []
        for eintrag in eintraege:
            rel = eintrag.rel_path
            if self._ignoriert is not None and any(self._ignoriert(t) for t in rel.split("/")):
                continue
            gefunden.append(BaumDatei(rel, int(eintrag.length), self._leser_fuer(eintrag)))
        gefunden.sort(key=lambda d: d.rel)
        self._dateien = gefunden
        return gefunden

    def _leser_fuer(self, eintrag: Any) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            try:
                yield from self._leser().read_file(eintrag, chunk_size=stueck)
            except self._ExfatError as exc:
                raise BaumFehler("%s: %s" % (eintrag.rel_path, exc)) from exc
        return lesen

    def stempel(self) -> tuple:
        """Stand der Abbilddatei **jetzt** (Groesse und Zeit); mit dem beim Oeffnen gemerkten zu vergleichen: :meth:`unveraendert`."""
        return self._datei_stempel()

    def unveraendert(self) -> bool:
        """Ob die Abbilddatei noch so ist wie beim Oeffnen des Baums."""
        try:
            return self._datei_stempel() == self._stempel
        except OSError:
            return False

    def schliessen(self) -> None:
        with self._sperre:
            self._geschlossen = True
            griffe, self._griffe = self._griffe, []
        for fh in griffe:
            try:
                fh.close()
            except OSError:
                pass
        self._lokal = threading.local()


class PfsBaum(_Baum):
    """Die Dateien in einem ``.ffpfs``/``.ffpfsc`` (PFS-Abbild, mit oder ohne PFSC-Kompression), gelesen ohne Entpacken.

    Drei Bauformen, die der Baum selbst erkennt (nicht an der Endung, sondern am Inhalt):

    * **flach** - die Spieldateien liegen im PFS (``mkpfs pack folder``): ``art == "pfs"``,
    * **umhuellend** - das PFS enthaelt genau eine Datei, ein inneres ``exFAT``-Abbild (die Bauform dieses Programms):
      ``art == "exfat"``, gelesen mit dem exFAT-Leser ueber eine Ansicht, die die PFSC-Bloecke erst beim Lesen entpackt,
    * **mehrfach umhuellt** - das innere Abbild ist selbst ein PFS (``ebenen`` zaehlt die Huellen).

    Signierte oder verstreut gespeicherte Dateien kann die Ansicht nicht bedienen; ein solches Abbild oder jedes, dessen
    Baum Fehler meldet, ist ein :class:`BaumFehler` - der Aufrufer nimmt dann den Weg ueber das Entpacken. Jeder Faden bekommt
    seinen eigenen Dateigriff (und bei exFAT seinen eigenen Leser); der Aufbau (Kopf, Inode-Tabelle, Baum) wird nur einmal gelesen.
    """

    MAX_EBENEN = 4

    def __init__(self, pfad: str, mkpfs_ordner: str = "", ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.pfad = os.path.abspath(pfad)
        if not os.path.isfile(self.pfad):
            raise BaumFehler("keine Datei: %s" % self.pfad)
        if mkpfs_ordner:
            import sys
            if mkpfs_ordner not in sys.path:
                sys.path.insert(0, mkpfs_ordner)
        try:
            from mkpfs import consts as _consts                           # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            from mkpfs import pfs as _pfs                                 # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            from mkpfs.compression import CompressionError                # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            from mkpfs.exfat import EXFAT_SIGNATURE, ExfatError, ExfatReader   # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        except ImportError as exc:                                         # pragma: no cover - ohne MkPFS gibt es das Programm nicht
            raise BaumFehler("MkPFS nicht gefunden: %s" % exc) from exc
        self._consts, self._pfs = _consts, _pfs
        self._ExfatReader, self._ExfatError, self._EXFAT = ExfatReader, ExfatError, EXFAT_SIGNATURE
        self._fehler_arten = (ValueError, CompressionError)
        self._ignoriert = ignoriert
        self._lokal = threading.local()
        self._griffe: list[Any] = []
        self._sperre = threading.Lock()
        self._stempel = self._datei_stempel()
        self._dateien: "list[BaumDatei] | None" = None
        self._geschlossen = False
        #: ``"exfat"`` oder ``"pfs"``; erst nach dem ersten Auflisten gesetzt.
        self.art = ""
        #: Wie viele Huellen (PFS mit genau einem inneren Abbild) um das eigentliche Spiel liegen.
        self.ebenen = 0
        self._huellen: list[tuple[Any, Any]] = []            # je Huelle (Kopf, Inode) der einen inneren Datei
        self._flach: "tuple[Any, list[Any], dict[str, int]] | None" = None     # (Kopf, Inodes, Pfad -> Inode-Nummer)

    def _datei_stempel(self) -> tuple:
        st = os.stat(self.pfad)
        return ("pfs", self.pfad, st.st_size, st.st_mtime_ns)

    # -- Aufbau ---------------------------------------------------------------------------------------------------------

    def _ansicht(self, unten: Any, huellen: "list[tuple[Any, Any]]") -> Any:
        """Die Ansicht auf das innerste Abbild: je Huelle eine Ansicht auf die eine Datei darin."""
        aktuell = unten
        for kopf, inode in huellen:
            aktuell = self._pfs._LogicalFileView(aktuell, kopf, inode)
        return aktuell

    def _aufloesen(self) -> None:
        """Erkennt die Bauform: liest Kopf, Inode-Tabelle und Verzeichnisse (keine Nutzdaten) und merkt sie sich."""
        pfs, consts = self._pfs, self._consts
        try:
            fh = open(self.pfad, "rb")
        except OSError as exc:
            raise BaumFehler("Abbild nicht lesbar: %s" % exc) from exc
        try:
            aktuell: Any = fh
            for _ in range(self.MAX_EBENEN):
                aktuell.seek(0)
                kopf16 = aktuell.read(16)
                if len(kopf16) >= 11 and kopf16[3:11] == self._EXFAT:
                    self.art = "exfat"
                    return
                kopf = pfs.parse_image_header(aktuell)
                if kopf.magic != consts.PFS_MAGIC:
                    raise BaumFehler("weder exFAT noch PFS (Kennung 0x%X)" % kopf.magic)
                if kopf.block_size <= 0 or (kopf.block_size & (kopf.block_size - 1)) != 0:
                    raise BaumFehler("PFS mit unbrauchbarer Blockgroesse %d" % kopf.block_size)
                inodes = pfs.parse_image_inodes(aktuell, kopf)
                fehler: list[str] = []
                wurzel, _fpt, _koll, _bes = pfs.parse_superroot_and_indexes(aktuell, kopf, inodes, fehler)
                if wurzel < 0:
                    raise BaumFehler("PFS ohne Wurzelverzeichnis")
                dateien, _ordner, _eintraege = pfs.build_tree_from_uroot(aktuell, kopf, inodes, wurzel, fehler)
                if fehler:
                    raise BaumFehler("PFS-Baum fehlerhaft: %s" % "; ".join(fehler[:3]))
                if len(dateien) == 1:
                    _rel, nummer = next(iter(dateien.items()))
                    inode = inodes[nummer]
                    if not (inode.db_sig or inode.ib_sig) and inode.blocks > 0 and inode.logical_size >= 16:
                        sicht = pfs._LogicalFileView(aktuell, kopf, inode)
                        sicht.seek(0)
                        innen = sicht.read(16)
                        ist_exfat = innen[3:11] == self._EXFAT
                        ist_pfs = len(innen) == 16 and int.from_bytes(innen[8:16], "little", signed=True) == consts.PFS_MAGIC
                        if ist_exfat or ist_pfs:
                            self._huellen.append((kopf, inode))
                            aktuell = sicht
                            continue
                self.art = "pfs"
                self._flach = (kopf, inodes, dateien)
                return
            raise BaumFehler("mehr als %d verschachtelte Abbilder" % self.MAX_EBENEN)
        except BaumFehler:
            raise
        except (OSError, *self._fehler_arten, self._ExfatError) as exc:
            raise BaumFehler("Abbild nicht lesbar: %s" % exc) from exc
        finally:
            self.ebenen = len(self._huellen)
            fh.close()

    def _stapel(self) -> tuple[Any, Any]:
        """``(Datei oder Ansicht, exFAT-Leser | None)`` dieses Fadens; der erste Aufruf je Faden oeffnet die Datei."""
        stapel = getattr(self._lokal, "stapel", None)
        if stapel is None:
            if self._geschlossen:
                raise BaumFehler("Lesebaum ist geschlossen")
            fh = open(self.pfad, "rb")
            try:
                ansicht = self._ansicht(fh, self._huellen)
                leser = self._ExfatReader(ansicht) if self.art == "exfat" else None
            except Exception:
                fh.close()
                raise
            with self._sperre:
                self._griffe.append(fh)
            stapel = self._lokal.stapel = (ansicht, leser)
        return stapel

    # -- Dateien --------------------------------------------------------------------------------------------------------

    def dateien(self) -> list[BaumDatei]:
        if self._dateien is not None:
            return self._dateien
        self._aufloesen()
        gefunden: list[BaumDatei] = []
        try:
            if self.art == "exfat":
                _ansicht, leser = self._stapel()
                for eintrag in leser.iter_files():
                    gefunden.append(BaumDatei(eintrag.rel_path, int(eintrag.length), self._exfat_leser(eintrag)))
            else:
                kopf, inodes, pfade = self._flach
                for rel, nummer in pfade.items():
                    inode = inodes[nummer]
                    gefunden.append(BaumDatei(rel, max(0, int(inode.logical_size)), self._pfs_leser(kopf, inode, rel)))
        except (*self._fehler_arten, self._ExfatError) as exc:
            raise BaumFehler("Abbild nicht lesbar: %s" % exc) from exc
        if self._ignoriert is not None:
            gefunden = [d for d in gefunden if not any(self._ignoriert(t) for t in d.rel.split("/"))]
        gefunden.sort(key=lambda d: d.rel)
        self._dateien = gefunden
        return gefunden

    def _exfat_leser(self, eintrag: Any) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            try:
                yield from self._stapel()[1].read_file(eintrag, chunk_size=stueck)
            except (*self._fehler_arten, self._ExfatError) as exc:
                raise BaumFehler("%s: %s" % (eintrag.rel_path, exc)) from exc
        return lesen

    def _pfs_leser(self, kopf: Any, inode: Any, rel: str) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            try:
                for block in self._pfs.iter_inode_logical_blocks(self._stapel()[0], kopf, inode, chunk_size=stueck):
                    # Ein PFSC-Block ist so gross wie die Blockgroesse des Abbilds (meist 64 KiB), nicht wie ``stueck``.
                    if len(block) <= stueck:
                        yield block
                    else:
                        for ab in range(0, len(block), stueck):
                            yield block[ab:ab + stueck]
            except self._fehler_arten as exc:
                raise BaumFehler("%s: %s" % (rel, exc)) from exc
        return lesen

    def stempel(self) -> tuple:
        """Stand der Abbilddatei **jetzt** (Groesse und Zeit); mit dem beim Oeffnen gemerkten zu vergleichen: :meth:`unveraendert`."""
        return self._datei_stempel()

    def unveraendert(self) -> bool:
        """Ob die Abbilddatei noch so ist wie beim Oeffnen des Baums."""
        try:
            return self._datei_stempel() == self._stempel
        except OSError:
            return False

    def schliessen(self) -> None:
        with self._sperre:
            self._geschlossen = True
            griffe, self._griffe = self._griffe, []
        for fh in griffe:
            try:
                fh.close()
            except OSError:
                pass
        self._lokal = threading.local()


class UeberlagerBaum(_Baum):
    """``basis`` mit Aenderungen: Dateien aus ``ueberlager`` ersetzen oder ergaenzen, ``entfernt`` faellt weg."""

    def __init__(self, basis: _Baum, ueberlager: "_Baum | None" = None, entfernt: Iterable[str] = ()) -> None:
        self.basis = basis
        self.ueberlager = ueberlager
        self.entfernt = frozenset(str(e).replace("\\", "/").strip("/") for e in entfernt)

    def dateien(self) -> list[BaumDatei]:
        ersetzt = self.ueberlager.suchen() if self.ueberlager is not None else {}
        ergebnis = [d for d in self.basis.dateien() if d.rel not in ersetzt and d.rel not in self.entfernt]
        ergebnis.extend(d for rel, d in ersetzt.items() if rel not in self.entfernt)
        ergebnis.sort(key=lambda d: d.rel)
        return ergebnis

    def stempel(self) -> tuple:
        return ("ueberlagert", self.basis.stempel(),
                self.ueberlager.stempel() if self.ueberlager is not None else (), tuple(sorted(self.entfernt)))

    def schliessen(self) -> None:
        self.basis.schliessen()
        if self.ueberlager is not None:
            self.ueberlager.schliessen()


def einordnen(baum: _Baum) -> list[tuple[str, int]]:
    """``(Pfad, Groesse)`` aller Dateien des Baums - die Eingabe fuer ``ampr_zstdpack.auswahl_aus_liste``."""
    return [(d.rel, d.groesse) for d in baum.dateien()]
