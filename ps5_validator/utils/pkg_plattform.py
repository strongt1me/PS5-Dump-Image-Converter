# -*- coding: utf-8 -*-
"""PS4- oder PS5-Paket? Die Seite "7. PKG / FPKG" waehlt ihren Bereich nach der gewaehlten Quelle selbst.

Gemessen am 30.10.2026 an 49 Paketen auf den Platten des Nutzers (36 mit ``\\x7fCNT``, 13 mit ``\\x7fFIH`` oder
``\\x7fLIH``). Das **Format** trennt PS4 und PS5 eindeutig, der Dateiname nicht:

* ``\\x7fFIH`` (fertiges PS5-Paket) und ``\\x7fLIH`` (PS5-Update, "Delta") sind PS5.
* ``\\x7fCNT`` ist PS4: alle 36 gemessenen Pakete trugen dieselben Kopfwerte (``drm=0x0f``, ``typ=0x1a``,
  ``flg=0x0a000000``), ``param.sfo`` (Eintrag ``0x1000``) und keine ``param.json`` (``0x2000``). Auch die "PS5PKG_..."-
  Homebrew (Itemzflow, FPKGi, PS5-Xplorer, Homebrew Store) ist PS4-Format; der Name sagt nur, wofuer es gedacht ist.
* Ausnahme: ein ``\\x7fCNT``-Paket nur mit Metadaten fuer die PS5 hat ``param.json`` und kein ``param.sfo``, oder eine
  PS5-Titelkennung (``PPSA``/``PPSS``) in der Content-ID - das ist PS5.

Ordner: ``sce_sys/param.json`` heisst PS5-Spielordner, ``sce_sys/param.sfo`` (ohne JSON) entpacktes PS4-Spiel; ein Ordner
mit ``.pkg``-Dateien (eine Ebene tief, wie die Seiten der Pakete selbst suchen) wird nach seinen Dateien entschieden:
alle gleich - diese Plattform; **gemischt - PS4** (die Liste "Gefundene Spiele" des PS4-Bereichs hat eine Spalte
"Konsole" und nimmt beide), mit Hinweis im Ergebnis.

Reine Funktionen, kein Tk, nichts wird geschrieben.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

PS4 = "ps4"
PS5 = "ps5"

#: Wie der PS4-Bereich die Quelle einteilt (Werte wie ``ps4_dump_image.QUELLE_*``).
ART_DATEIEN = "pkg_file"
ART_ORDNER = "pkg_dir"
ART_DUMP = "dump_dir"

CNT_MAGIC = b"\x7fCNT"
FIH_MAGIC = b"\x7fFIH"
LIH_MAGIC = b"\x7fLIH"

_KOPF_GROESSE = 0x5A0
_EINTRAG = 0x20
_MAX_EINTRAEGE = 0x10000
_ID_PARAM_SFO = 0x1000
_ID_PARAM_JSON = 0x2000
_PS5_TITEL = ("PPSA", "PPSS")
#: So viele ``.pkg`` aus einem Ordner werden gelesen (der Kopf ist klein; mehr braucht die Entscheidung nicht).
_MAX_DATEIEN = 400


@dataclass
class Erkennung:
    """Das Ergebnis: ``plattform`` ist ``"ps4"``, ``"ps5"`` oder ``None`` (nichts Erkennbares, ``grund`` sagt warum)."""

    plattform: "str | None"
    grund: str = ""
    #: Fuer PS4: ``ART_DATEIEN`` / ``ART_ORDNER`` / ``ART_DUMP``; sonst leer.
    art: str = ""
    #: Die Quellen, die der gewaehlte Bereich bekommen soll (bei einem Ordner mit Paketen: der Ordner).
    pfade: list = field(default_factory=list)
    anzahl_ps4: int = 0
    anzahl_ps5: int = 0

    @property
    def gemischt(self) -> bool:
        return self.anzahl_ps4 > 0 and self.anzahl_ps5 > 0


def _lesen(pfad: str, menge: int) -> bytes:
    try:
        with open(pfad, "rb") as f:
            return f.read(menge)
    except OSError:
        return b""


def paket_plattform(pfad: str) -> "tuple[str | None, str]":
    """Die Plattform einer ``.pkg``-Datei und der Grund - ``(None, Grund)`` bei einer Datei ohne bekannte Magic."""
    kopf = _lesen(pfad, _KOPF_GROESSE)
    if len(kopf) < 4:
        return None, "Datei zu kurz oder nicht lesbar"
    magic = kopf[:4]
    if magic in (FIH_MAGIC, LIH_MAGIC):
        return PS5, "Magic %s" % magic[1:].decode("ascii")
    if magic != CNT_MAGIC:
        return None, "keine bekannte Paket-Magic"
    # CNT: meist PS4; PS5-Meta-Pakete tragen param.json statt param.sfo oder eine PS5-Titelkennung.
    inhalt_id = kopf[0x40:0x64].split(b"\x00", 1)[0].decode("ascii", errors="replace").upper()
    if any(("-" + kennung) in inhalt_id for kennung in _PS5_TITEL):
        return PS5, "Magic CNT, Titelkennung PPSA/PPSS in der Content-ID"
    kennungen = _eintrag_kennungen(pfad, kopf)
    if _ID_PARAM_JSON in kennungen and _ID_PARAM_SFO not in kennungen:
        return PS5, "Magic CNT mit param.json und ohne param.sfo (PS5, nur Metadaten)"
    return PS4, "Magic CNT"


def _eintrag_kennungen(pfad: str, kopf: bytes) -> "set[int]":
    """Die Kennungen der Eintragstabelle eines CNT-Kopfs - leer, wenn sie nicht lesbar ist."""
    try:
        anzahl, tabelle = struct.unpack_from(">II", kopf, 0x10)[0], struct.unpack_from(">I", kopf, 0x18)[0]
        if not 0 < anzahl <= _MAX_EINTRAEGE:
            return set()
        roh = b""
        with open(pfad, "rb") as f:
            f.seek(tabelle)
            roh = f.read(anzahl * _EINTRAG)
        return {struct.unpack_from(">I", roh, i * _EINTRAG)[0] for i in range(len(roh) // _EINTRAG)}
    except (OSError, struct.error, ValueError):
        return set()


def _pkg_dateien(ordner: str) -> "list[str]":
    """Die ``.pkg`` eines Ordners, eine Ebene tief (Spiele liegen oft in je einem Unterordner)."""
    gefunden: "list[str]" = []
    try:
        for eintrag in sorted(os.scandir(ordner), key=lambda e: e.name.lower()):
            if len(gefunden) >= _MAX_DATEIEN:
                break
            if eintrag.is_file() and eintrag.name.lower().endswith(".pkg"):
                gefunden.append(eintrag.path)
            elif eintrag.is_dir():
                try:
                    for tiefer in sorted(os.scandir(eintrag.path), key=lambda e: e.name.lower()):
                        if tiefer.is_file() and tiefer.name.lower().endswith(".pkg"):
                            gefunden.append(tiefer.path)
                except OSError:
                    continue
    except OSError:
        return []
    return gefunden


def ordner_plattform(ordner: str) -> "tuple[str | None, str]":
    """Die Plattform eines entpackten Spielordners (``sce_sys``) - ``(None, Grund)``, wenn es keiner ist."""
    sce = os.path.join(ordner, "sce_sys")
    if not os.path.isdir(sce):
        return None, "kein sce_sys-Ordner"
    hat_json = os.path.isfile(os.path.join(sce, "param.json"))
    hat_sfo = os.path.isfile(os.path.join(sce, "param.sfo"))
    if hat_json:
        return PS5, "sce_sys/param.json"
    if hat_sfo:
        return PS4, "sce_sys/param.sfo ohne param.json"
    return None, "sce_sys ohne param.json und param.sfo"


def erkennen(pfade: "list[str] | str") -> Erkennung:
    """Entscheidet fuer die gewaehlte Quelle (eine oder mehrere Dateien, oder ein Ordner), welcher Bereich sie bekommt."""
    if isinstance(pfade, str):
        pfade = [pfade]
    pfade = [p for p in pfade if p]
    if not pfade:
        return Erkennung(None, "keine Quelle gewaehlt")

    ps4: "list[str]" = []
    ps5: "list[str]" = []
    basis = {PS4: "", PS5: ""}          # woran die erste Quelle je Plattform erkannt wurde
    ordner_art = ""
    ordner_gewaehlt = ""

    def merken(plattform: str, pfad: str, grund: str) -> None:
        (ps4 if plattform == PS4 else ps5).append(pfad)
        basis[plattform] = basis[plattform] or grund

    for pfad in pfade:
        if os.path.isdir(pfad):
            ordner_gewaehlt = pfad
            spiel, grund = ordner_plattform(pfad)
            if spiel is not None:
                # Ein entpackter Spielordner zaehlt als eine Quelle.
                merken(spiel, pfad, grund)
                ordner_art = ART_DUMP if spiel == PS4 else ART_ORDNER
                continue
            dateien = _pkg_dateien(pfad)
            for datei in dateien:
                plattform, grund = paket_plattform(datei)
                if plattform is not None:
                    merken(plattform, datei, grund)
            ordner_art = ordner_art or ART_ORDNER
        elif os.path.isfile(pfad):
            plattform, grund = paket_plattform(pfad)
            if plattform is not None:
                merken(plattform, pfad, grund)

    if not ps4 and not ps5:
        if ordner_gewaehlt:
            return Erkennung(None, "weder Spielordner (sce_sys) noch .pkg im Ordner", pfade=pfade)
        return Erkennung(None, "keine bekannte Paket-Magic", pfade=pfade)

    erg = Erkennung(None, "", pfade=pfade, anzahl_ps4=len(ps4), anzahl_ps5=len(ps5))
    if ps4 and ps5:
        # Gemischt: Der PS4-Bereich listet beide (Spalte "Konsole") - die Quelle geht dorthin.
        erg.plattform = PS4
        erg.grund = "gemischt: %d PS4, %d PS5" % (len(ps4), len(ps5))
    else:
        erg.plattform = PS4 if ps4 else PS5
        erg.grund = basis[erg.plattform]
    if erg.plattform == PS4:
        if ordner_gewaehlt and not erg.gemischt and ordner_art == ART_DUMP:
            erg.art = ART_DUMP
        elif ordner_gewaehlt:
            erg.art = ART_ORDNER
        else:
            erg.art = ART_DATEIEN
    return erg
