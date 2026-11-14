# -*- coding: utf-8 -*-
"""Ein ZIP-Archiv als Lesebaum: Das Spiel wird gelesen, ohne es vorher zu entpacken (Stufe 3, Archive; 14.11.2026).

Bisher entpackte jeder Weg ein Archiv als Quelle in einen Ordner im Temp-Ordner und baute das Ergebnis daraus - bei einem Spiel von
100 GB hiess das 100 GB Platz und die Zeit des Entpackens vorab. Ein :class:`ZipBaum` meldet nur, **was** im Archiv liegt (Pfad,
entpackte Groesse) und **wie** man es liest (``zipfile``, Strom je Datei); wer ihn benutzt (:mod:`spielbaum` -> Strom), braucht
keinen Ordner. So arbeitet auch Dump Forge (``archive/src/stream.rs``).

Was das kann und was nicht:

* ``.zip`` mit Packverfahren Stored, Deflate, BZip2 und LZMA - die ``zipfile`` der Standardbibliothek kennt. Jeder Faden bekommt
  seinen eigenen Griff (ein Archivgriff merkt sich nur eine Stelle in der Datei).
* **ZipCrypto**-Passwoerter werden der Reihe nach probiert (ohne, die bekannten, die des Anwenders): an der kleinsten verschluesselten
  Datei, vollstaendig gelesen (die Pruefsumme entscheidet - ein einzelnes Byte verraet ein falsches Passwort nur zu 255 von 256 Malen).
  AES-verschluesselte Archive kann ``zipfile`` nicht: :class:`BaumFehler`, der Aufrufer nimmt den bisherigen Weg (7-Zip).
* ``.7z`` und ``.rar`` nicht: Sie sind meist **solide** gepackt, und ein solides Archiv laesst sich nicht wahlfrei lesen - jede Datei
  braeuchte das Dekodieren von vorn. Dort bleibt es beim Entpacken (:mod:`archiv_quelle`).

Der Spielordner im Archiv wird wie beim Entpacken gesucht: ``sce_sys/param.json`` am Stamm oder bis zu drei Ebenen tiefer
(:func:`spielwurzel_aus_namen`). Alles ausserhalb davon zaehlt nicht.
"""
from __future__ import annotations

import os
import stat
import threading
import zipfile
from typing import Any, Callable, Iterable, Iterator

from ps5_validator.utils import archiv_quelle as aq
from ps5_validator.utils.spielbaum import BaumDatei, BaumFehler, _Baum, _ordner_ohne_ignorierte

#: Packverfahren, die ``zipfile`` lesen kann.
_VERFAHREN = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA)
#: Hoechstens so gross darf die Datei sein, an der ein Passwort probiert wird - sonst die kleinste verfuegbare.
_PROBE_BYTES = 8 * 1024 * 1024


def _ist_unzulaessig(name: str) -> bool:
    """Ein Pfad im Archiv, der aus dem Zielordner herausfuehren oder ein Laufwerk meinen wuerde."""
    teile = name.replace("\\", "/").split("/")
    if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
        return True
    return any(t == ".." for t in teile)


def spielwurzel_aus_namen(pfade: Iterable[str]) -> "str | None":
    """Der Ordner im Archiv, der ein Spiel enthaelt (``<Ordner>/sce_sys/param.json``), als Pfad mit ``/`` ohne Ende; ``""`` = Stamm.

    Gesucht wird hoechstens drei Ebenen tief; bei mehreren Treffern gewinnt der flachste (dann der erste nach dem Namen) - wie
    :func:`archiv_quelle.spielwurzel` beim entpackten Ordner. ``None``, wenn kein Spiel darin liegt.
    """
    treffer = []
    for pfad in pfade:
        norm = pfad.replace("\\", "/").strip("/")
        if not norm.lower().endswith("sce_sys/param.json"):
            continue
        wurzel = norm[: -len("sce_sys/param.json")].rstrip("/")
        if wurzel.count("/") + (1 if wurzel else 0) <= 3:
            treffer.append(wurzel)
    if not treffer:
        return None
    return sorted(treffer, key=lambda w: (w.count("/") if w else -1, w))[0]


class ZipBaum(_Baum):
    """Die regulaeren Dateien im Spielordner eines ZIP-Archivs. Verweise im Archiv zaehlen nicht (``uebersprungen``)."""

    def __init__(self, pfad: str, passwort: str = "", weitere_passwoerter: "Iterable[str]" = (),
                 ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.pfad = os.path.abspath(pfad)
        if not os.path.isfile(self.pfad):
            raise BaumFehler("kein Archiv: %s" % self.pfad)
        self._ignoriert = ignoriert
        # Mit Angabe nur dieses Passwort: ein falsches des Anwenders soll nicht still durch ein bekanntes ersetzt werden.
        if passwort:
            self._kandidaten = [passwort]
        else:
            gesehen: "list[str]" = []
            for kandidat in ("", *aq.BEKANNTE_PASSWOERTER, *weitere_passwoerter):
                if kandidat not in gesehen:
                    gesehen.append(kandidat)
            self._kandidaten = gesehen
        self.passwort = ""                                  # das Passwort, das gepasst hat (sonst leer)
        self.wurzel = ""                                    # der Spielordner im Archiv (``""`` = Stamm)
        self.uebersprungen: "list[str]" = []
        self._pwd: "bytes | None" = None
        self._dateien: "list[BaumDatei] | None" = None
        self._ordner: "list[str]" = []
        self._lokal = threading.local()
        self._griffe: "list[zipfile.ZipFile]" = []
        self._sperre = threading.Lock()
        self._stempel_oeffnen = self._datei_stempel()

    # -- Griffe -------------------------------------------------------------------------------------------------------------
    def _datei_stempel(self) -> tuple:
        try:
            st = os.stat(self.pfad)
        except OSError:
            return ("zip", self.pfad, -1, -1)
        return ("zip", self.pfad, st.st_size, st.st_mtime_ns)

    def _zip(self) -> zipfile.ZipFile:
        """Der Griff dieses Fadens (jeder Faden oeffnet seinen eigenen)."""
        griff = getattr(self._lokal, "zip", None)
        if griff is None:
            try:
                griff = zipfile.ZipFile(self.pfad)
            except (zipfile.BadZipFile, OSError) as exc:
                raise BaumFehler("Kein lesbares ZIP-Archiv: %s" % exc) from exc
            self._lokal.zip = griff
            with self._sperre:
                self._griffe.append(griff)
        return griff

    # -- Aufbau -------------------------------------------------------------------------------------------------------------
    def _passwort_finden(self, zf: zipfile.ZipFile, infos: "list[zipfile.ZipInfo]") -> None:
        """Setzt ``self._pwd``: das erste Passwort, mit dem die kleinste verschluesselte Datei vollstaendig lesbar ist."""
        verschluesselt = [i for i in infos if i.flag_bits & 0x1 and i.file_size > 0 and not i.is_dir()]
        if not verschluesselt:
            return
        if any(i.compress_type == 99 for i in verschluesselt):
            raise BaumFehler("Das Archiv ist AES-verschluesselt; das kann der Lesebaum nicht (7-Zip entpackt es)")
        kleiner = [i for i in verschluesselt if i.file_size <= _PROBE_BYTES]
        probe = min(kleiner or verschluesselt, key=lambda i: i.file_size)
        for kandidat in self._kandidaten:
            pwd = kandidat.encode("utf-8") if kandidat else None
            if pwd is None:
                continue                                    # ohne Passwort liesse sich eine verschluesselte Datei nicht lesen
            try:
                with zf.open(probe, pwd=pwd) as quelle:
                    while quelle.read(1 << 20):
                        pass
            except (RuntimeError, zipfile.BadZipFile, OSError, EOFError):
                continue
            self._pwd = pwd
            self.passwort = kandidat
            return
        raise aq.PasswortFehler("Das Archiv ist verschluesselt und kein bekanntes Passwort passt")

    def dateien(self) -> "list[BaumDatei]":
        if self._dateien is not None:
            return self._dateien
        zf = self._zip()
        infos = zf.infolist()
        namen = [i.filename for i in infos if not i.is_dir()]
        for name in (i.filename for i in infos):
            if _ist_unzulaessig(name):
                raise BaumFehler("Unzulaessiger Pfad im Archiv: %s" % name)
        wurzel = spielwurzel_aus_namen(namen)
        if wurzel is None:
            raise BaumFehler("Im Archiv liegt kein Spiel (sce_sys/param.json fehlt)")
        self.wurzel = wurzel
        vorne = wurzel + "/" if wurzel else ""
        im_spiel = [i for i in infos if i.filename.startswith(vorne) and i.filename != vorne]
        for info in im_spiel:
            if not info.is_dir() and info.compress_type not in _VERFAHREN and info.compress_type != 99:
                raise BaumFehler("Packverfahren %d im Archiv wird nicht unterstuetzt: %s" % (info.compress_type, info.filename))
        self._passwort_finden(zf, [i for i in im_spiel])

        gefunden: "list[BaumDatei]" = []
        ordner: "list[str]" = []
        self.uebersprungen = []
        sichtbar: "set[str]" = set()
        for info in im_spiel:
            rel = info.filename[len(vorne):].rstrip("/")
            if not rel:
                continue
            if self._ignoriert is not None and any(self._ignoriert(t) for t in rel.split("/")):
                continue
            if info.is_dir():
                ordner.append(rel)
                continue
            modus = (info.external_attr >> 16) & 0o170000
            if modus == stat.S_IFLNK:
                self.uebersprungen.append(rel)             # ein Verweis im Archiv: nicht ins Spiel, aber nicht verschweigen
                continue
            if rel in sichtbar:
                raise BaumFehler("Der Pfad steht zweimal im Archiv: %s" % rel)
            sichtbar.add(rel)
            gefunden.append(BaumDatei(rel, info.file_size, self._leser_fuer(info)))
        # Verzeichnisse mit Dateien darin ergeben sich aus den Pfaden; hier zaehlen auch die leeren (eigene Eintraege im Archiv).
        gefunden.sort(key=lambda d: d.rel)
        self._ordner = _ordner_ohne_ignorierte(set(ordner), self._ignoriert)
        self._dateien = gefunden
        self._stempel_oeffnen = self._datei_stempel()
        return gefunden

    def _leser_fuer(self, info: zipfile.ZipInfo) -> "Callable[[int], Iterator[bytes]]":
        def lesen(stueck: int) -> "Iterator[bytes]":
            zf = self._zip()
            try:
                with zf.open(info, pwd=self._pwd) as quelle:
                    while True:
                        daten = quelle.read(stueck)
                        if not daten:
                            return
                        yield daten
            except zipfile.BadZipFile as exc:
                raise BaumFehler("%s ist im Archiv beschaedigt: %s" % (info.filename, exc)) from exc
            except (RuntimeError, NotImplementedError, EOFError) as exc:
                raise BaumFehler("%s laesst sich im Archiv nicht lesen: %s" % (info.filename, exc)) from exc
        return lesen

    def ordner(self) -> "list[str]":
        self.dateien()
        return list(self._ordner)

    def stempel(self) -> tuple:
        return self._datei_stempel() + (len(self.dateien()),)

    def unveraendert(self) -> bool:
        """Ob die Archivdatei noch so ist wie beim ersten Auflisten (Groesse, Aenderungszeit)."""
        return self._dateien is None or self._datei_stempel() == self._stempel_oeffnen

    def schliessen(self) -> None:
        with self._sperre:
            griffe, self._griffe = self._griffe, []
        for griff in griffe:
            try:
                griff.close()
            except Exception:  # noqa: BLE001 - ein Griff, der sich nicht schliessen laesst, haelt das Schliessen der anderen nicht auf
                pass
        self._lokal = threading.local()
