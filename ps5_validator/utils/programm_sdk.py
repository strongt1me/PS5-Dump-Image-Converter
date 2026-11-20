# -*- coding: utf-8 -*-
"""Das SDK der ``eboot.bin`` eines Spiels - gelesen aus einem Ordner oder einem Abbild (``.ffpkg``, ``.exfat``, ``.ffpfs``,
``.ffpfsc``), ohne die Datei zu laden oder zu entpacken.

Warum das Programm das selbst liest: Die Konsole prueft beim Start das **SDK in den Programmen** (``eboot.bin``, ``.prx``/``.sprx``)
gegen ihre Firmware. Ein Backport setzt genau dieses SDK herab - die Angaben in ``sce_sys/param.json`` (``sdkVersion``,
``requiredSystemSoftwareVersion``) fasst nicht jedes Werkzeug an. Dump Forges ``inspect`` nennt nur die Angaben der ``param.json``;
das SDK der Programme (``backport_firmware``) nennt es nur, wenn das Spiel einen ``fakelib/``-Ordner hat. Wer allein nach der
``param.json`` urteilt, haelt ein schon herabgesetztes Spiel fuer eines, das noch einen Backport braucht (gemeldet 20.11.2026: ein
``.ffpkg``, das unter Firmware 12 laeuft, wurde beim Umwandeln in ein PKG als "Backport noetig" beanstandet).

Der Lesevorgang folgt Dump Forges ``sdk.rs`` (``ps5_sdk``, an den Programmen echter Spiele gegen Forges eigene Ausgabe gemessen):
Kopf der Datei (64 KiB) lesen, den Programmkopf (``PT_SCE_PROCPARAM`` oder ``PT_SCE_MODULE_PARAM``) suchen, bei einer signierten
Datei (fSELF) ueber deren Segmenttabelle auf die gespeicherte Stelle umrechnen und dort die 32 Bytes des Modulkopfs lesen. Mehr als
einige KiB werden nie gelesen, auch bei einer ``eboot.bin`` von 300 MB. Verschluesselte oder komprimierte Segmente lassen sich so
nicht lesen - das Ergebnis ist dann "nicht zu sagen", nie geraten.

Abbilder erkennt es am Inhalt: exFAT, UFS2 und PFS (``.ffpfs``/``.ffpfsc``, flach oder um ein inneres Abbild gelegt, auch ein ``.ffpkg``
in einer ``.ffpfsc``, wie Dump Forge es baut). Ein ``.pkg`` (Debug-Paket mit Kraken-Bloecken, auch AES-XTS) liest :mod:`pkg_eboot`; was sich
dort nicht lesen laesst (Verkaufsfassung, fremder Passcode, Update-Paket, anderes Verdichtungsverfahren), bleibt "nicht zu sagen".

Das Modul kennt keine Oberflaeche. Nichts wird veraendert.
"""
from __future__ import annotations

import os
import struct
import sys
from typing import Any, Callable

from . import ps5_backport as _bp
from . import ufs2_dateisystem as _ufs2_dateisystem
from . import ufs2_leser as _ufs2
from . import werkzeuge_bereitstellen as _werkzeuge_bereitstellen

#: ``(Offset, Laenge) -> Bytes``; am Dateiende liefert sie weniger.
LeseFunktion = Callable[[int, int], bytes]

#: So viel vom Dateianfang genuegt fuer die Kopfzeilen (echte brauchen einige hundert Bytes).
KOPF = 0x10000
#: Der Modulkopf (``sceProcessParam`` / ``sceModuleParam``): so viele Bytes werden dort gelesen.
MODULKOPF = 0x20
_SDK_IM_MODULKOPF = 0xC

_ELF = b"\x7fELF"
_SELF_PS5 = b"\x54\x14\xF5\xEE"
_SELF_PS4 = b"\x4F\x15\x3D\x1D"
#: Eigenschaften eines SELF-Segments: Inhalt verschluesselt oder komprimiert - nicht an Ort und Stelle lesbar.
_SELF_VERSCHLUESSELT = 1 << 1
_SELF_KOMPRIMIERT = 1 << 3
#: Mehr Programmkoepfe hat keine echte Datei; schuetzt vor einem beschaedigten Kopf.
_MAX_PROGRAMMKOEPFE = 4096


def _zahl(daten: bytes, ab: int, fmt: str) -> "int | None":
    groesse = struct.calcsize(fmt)
    if ab < 0 or ab + groesse > len(daten):
        return None
    return struct.unpack_from(fmt, daten, ab)[0]


def sdk_wort_lesen(lesen: LeseFunktion) -> "int | None":
    """Das PS5-SDK der Datei als Zahl (``0x07000038`` = 7.00); ``None``, wenn es sich nicht lesen laesst. Wirft nie."""
    try:
        return _sdk_wort(lesen)
    except (OSError, ValueError, struct.error, OverflowError):
        return None


def _sdk_wort(lesen: LeseFunktion) -> "int | None":
    kopf = lesen(0, KOPF)
    magic = kopf[:4]
    if magic in (_SELF_PS5, _SELF_PS4):
        segmente = _zahl(kopf, 0x18, "<H")
        if segmente is None:
            return None
        elf = 0x20 + segmente * 0x20
    elif magic == _ELF:
        segmente, elf = 0, 0
    else:
        return None
    if kopf[elf:elf + 4] != _ELF:
        return None
    phoff = _zahl(kopf, elf + 0x20, "<Q")
    phentsize = _zahl(kopf, elf + 0x36, "<H")
    phnum = _zahl(kopf, elf + 0x38, "<H")
    if phoff is None or phentsize is None or phnum is None or phnum > _MAX_PROGRAMMKOEPFE:
        return None
    koepfe: "list[tuple[int, int, int]]" = []
    for i in range(phnum):
        ph = elf + phoff + i * phentsize
        art, ab, groesse = _zahl(kopf, ph, "<I"), _zahl(kopf, ph + 8, "<Q"), _zahl(kopf, ph + 0x20, "<Q")
        if art is None or ab is None or groesse is None:
            return None                       # ein unlesbarer Programmkopf: nichts davon ist zu trauen (wie Dump Forge)
        koepfe.append((art, ab, groesse))
    modul = next(((art, ab) for art, ab, _g in koepfe if art in (_bp.PT_SCE_PROCPARAM, _bp.PT_SCE_MODULE_PARAM)), None)
    if modul is None:
        return None
    art, param = modul
    stelle = param if segmente == 0 else _gespeicherte_stelle(kopf, segmente, koepfe, param)
    if stelle is None:
        return None
    modulkopf = lesen(stelle, MODULKOPF)
    erwartet = _bp.SCE_PROCESS_PARAM_MAGIC if art == _bp.PT_SCE_PROCPARAM else _bp.SCE_MODULE_PARAM_MAGIC
    for basis in (0, 8):
        if _zahl(modulkopf, basis, "<I") == erwartet:
            return _zahl(modulkopf, basis + _SDK_IM_MODULKOPF, "<I")
    return None


def _gespeicherte_stelle(kopf: bytes, segmente: int, koepfe: "list[tuple[int, int, int]]", param: int) -> "int | None":
    """Wo der Modulkopf in einer signierten Datei (fSELF) liegt: Jedes ELF-Segment hat einen Eintrag in der Segmenttabelle
    (``{Eigenschaften, Offset, gespeicherte Groesse, Speichergroesse}``, Segment-Nummer in ``Eigenschaften >> 20``); gelesen wird
    durch das erste Segment, das den Modulkopf traegt und unverschluesselt und unkomprimiert gespeichert ist."""
    for nummer, (_art, ab, groesse) in enumerate(koepfe):
        if not ab <= param < ab + groesse:
            continue
        for k in range(segmente):
            eintrag = 0x20 + k * 0x20
            eigenschaften = _zahl(kopf, eintrag, "<Q")
            gespeichert = _zahl(kopf, eintrag + 0x10, "<Q")
            if eigenschaften is None or gespeichert is None:
                continue
            if eigenschaften & (_SELF_VERSCHLUESSELT | _SELF_KOMPRIMIERT):
                continue
            if (eigenschaften >> 20) & 0xFFFF != nummer or gespeichert != groesse:
                continue
            offset = _zahl(kopf, eintrag + 8, "<Q")
            if offset is not None:
                return offset + (param - ab)
    return None


def sdk_text(wort: "int | None") -> str:
    """``0x07000038`` als ``"7.00"``, ``0x10500040`` als ``"10.50"``; ``""``, wenn es kein gueltiges SDK ist (die obersten zwei Bytes sind BCD)."""
    if not wort:
        return ""
    haupt, neben = (wort >> 24) & 0xFF, (wort >> 16) & 0xFF
    if any(b >> 4 > 9 or b & 0xF > 9 for b in (haupt, neben)):
        return ""
    return "%x.%02x" % (haupt, neben)


def _eboot_im_ordner(ordner: str) -> str:
    """Der Pfad der ``eboot.bin`` an der Wurzel des Spielordners (Gross-/Kleinschreibung egal); ``""``, wenn es keine gibt."""
    with os.scandir(ordner) as eintraege:
        for eintrag in eintraege:
            if eintrag.name.lower() == "eboot.bin" and eintrag.is_file():
                return eintrag.path
    return ""


def eboot_sdk_im_ordner(ordner: str) -> str:
    """Das SDK der ``eboot.bin`` in einem Spielordner als Text (``"10.00"``); ``""``, wenn nichts zu lesen ist."""
    try:
        pfad = _eboot_im_ordner(ordner)
        if not pfad:
            return ""
        with open(pfad, "rb") as datei:
            def lesen(ab: int, laenge: int) -> bytes:
                datei.seek(ab)
                return datei.read(laenge)
            return sdk_text(sdk_wort_lesen(lesen))
    except (OSError, ValueError):
        return ""


# ------------------------------------------------------------------------------------------------------------------ Abbilder
#: Der Ordner mit dem Paket ``mkpfs`` (die Engine, die das Hauptprogramm bereitstellt); gemerkt von :func:`mkpfs_ordner_merken`.
_mkpfs_ordner = ""
#: Wie tief ein PFS-Abbild in einem anderen liegen darf (wie ``spielbaum.PfsBaum.MAX_EBENEN``).
_MAX_EBENEN = 4
_EXFAT_KENNUNG = b"EXFAT   "


def mkpfs_ordner_merken(ordner: str) -> None:
    """Merkt den Ordner, der das Paket ``mkpfs`` enthaelt: ``.exfat``, ``.ffpfs`` und ``.ffpfsc`` liest das Programm mit dessen Lesern."""
    global _mkpfs_ordner
    _mkpfs_ordner = str(ordner or "")


class _Mkpfs:
    """Die Teile von MkPFS, die der Abbild-Leser braucht (erst beim Gebrauch geladen: ohne MkPFS gibt es das Programm nicht, einen
    Test oder ein Werkzeug schon)."""

    def __init__(self, ordner: str = "") -> None:
        """Sucht ``mkpfs``: im angegebenen Ordner, im gemerkten (:func:`mkpfs_ordner_merken`), im Suchpfad - und zuletzt im mitgelieferten
        (``werkzeuge_bereitstellen.mkpfs_ordner_vorhanden``: ohne Entpacken, nicht von einem Vorwaermen des Hauptfensters abhaengig).

        Raises:
            ImportError: ``mkpfs`` ist nirgends zu finden.
        """
        for wo in (ordner, _mkpfs_ordner, None, ""):
            if wo is None:
                wo = _werkzeuge_bereitstellen.mkpfs_ordner_vorhanden()
            if wo and wo not in sys.path:
                sys.path.insert(0, wo)
            try:
                from mkpfs import consts, exfat, pfs                        # noqa: PLC0415  # pyright: ignore[reportMissingImports]
                from mkpfs.compression import CompressionError              # noqa: PLC0415  # pyright: ignore[reportMissingImports]
            except ImportError:
                continue
            break
        else:
            raise ImportError("mkpfs nicht gefunden")
        self.consts, self.exfat, self.pfs = consts, exfat, pfs
        #: Was beim Lesen eines beschaedigten oder fremden Abbilds fliegen kann (``CompressionError`` ist kein ``ValueError``).
        self.fehler = (OSError, ValueError, struct.error, KeyError, IndexError, CompressionError)


def _ist_exfat(fh: Any) -> bool:
    fh.seek(3)
    return fh.read(8) == _EXFAT_KENNUNG


def _ist_ufs2(fh: Any) -> bool:
    fh.seek(_ufs2_dateisystem.SUPERBLOCK_OFFSET + _ufs2_dateisystem.MAGIC_OFFSET)
    kennung = fh.read(4)
    return len(kennung) == 4 and struct.unpack("<I", kennung)[0] == _ufs2_dateisystem.UFS2_MAGIC


def _sdk_in_ufs2(fh: Any) -> str:
    """Das SDK der ``eboot.bin`` an der Wurzel eines UFS2-Abbilds (Datei oder Ansicht); ``""``, wenn keine da ist."""
    with _ufs2.Ufs2Leser(fh) as leser:                       # ein fremder Griff: der Leser schliesst ihn nicht
        name = next((n for n, ordner, _g in leser.auflisten("") if not ordner and n.lower() == "eboot.bin"), "")
        if not name:
            return ""
        return sdk_text(sdk_wort_lesen(lambda ab, laenge: leser.datei_bereich(name, ab, laenge)))


def _sdk_in_exfat(fh: Any, mk: _Mkpfs) -> str:
    """Das SDK der ``eboot.bin`` an der Wurzel eines exFAT-Abbilds (Datei oder Ansicht).

    Gelesen wird nur das Wurzelverzeichnis, nicht der Baum: Der ganze Baum dauerte gemessen (18.09.2026, HDD, kalter Zwischenspeicher) bei
    einem Spiel mit 67.226 Dateien 137 s (``_abbild_eintraege`` im Hauptmodul bricht den Abstieg aus demselben Grund ab). Von der
    ``eboot.bin`` kommen nur die Cluster, die den Kopf und den Modulkopf tragen; ihre Lage ergibt sich aus der Clusterkette.
    """
    class _Wurzel(mk.exfat.ExfatReader):
        def _walk_directory(self, first_cluster, no_fat_chain, length, rel_dir):          # noqa: ANN001, ANN202
            return [] if rel_dir else super()._walk_directory(first_cluster, no_fat_chain, length, rel_dir)

    fh.seek(0)
    leser = _Wurzel(fh)
    eintrag = next((e for e in leser.root_entries() if not e.is_dir and e.name.lower() == "eboot.bin"), None)
    if eintrag is None or eintrag.length <= 0:
        return ""
    groesse = leser.geometry.cluster_size

    def lesen(ab: int, laenge: int) -> bytes:
        anfang = max(0, ab)
        ende = min(eintrag.length, anfang + max(0, laenge))
        if ende <= anfang:
            return b""
        erster, letzter = anfang // groesse, (ende - 1) // groesse
        teile: list[bytes] = []
        for nummer, cluster in enumerate(leser._iter_clusters(eintrag.first_cluster, eintrag.no_fat_chain, eintrag.length)):
            if nummer < erster:
                continue
            if nummer > letzter:
                break
            fh.seek(leser._cluster_byte_offset(cluster))
            teile.append(fh.read(groesse))
        return b"".join(teile)[anfang - erster * groesse:][:ende - anfang]

    return sdk_text(sdk_wort_lesen(lesen))


def _abbild_art(fh: Any, mk: "_Mkpfs | None") -> str:
    """``"exfat"``, ``"ufs2"`` oder ``"pfs"`` nach dem Inhalt (nicht nach der Endung); ``""``, wenn es keines davon ist."""
    if _ist_exfat(fh):
        return "exfat"
    if _ist_ufs2(fh):
        return "ufs2"
    if mk is not None:
        fh.seek(8)
        kennung = fh.read(8)
        if len(kennung) == 8 and int.from_bytes(kennung, "little", signed=True) == mk.consts.PFS_MAGIC:
            return "pfs"
    return ""


def _sdk_im_abbild(fh: Any, mk: "_Mkpfs | None", ebene: int = 0) -> str:
    """Das SDK der ``eboot.bin`` in einem Abbild - ``exFAT``, ``UFS2`` oder ``PFS`` (flach oder um ein inneres Abbild gelegt) -,
    ``fh`` eine Datei oder die Ansicht auf ein inneres Abbild. ``""``, wenn die Art unbekannt ist oder MkPFS fehlt."""
    art = _abbild_art(fh, mk)
    if art == "ufs2":
        return _sdk_in_ufs2(fh)
    if mk is None:
        return ""
    if art == "exfat":
        return _sdk_in_exfat(fh, mk)
    if art != "pfs":
        return ""
    return _sdk_in_pfs(fh, mk, ebene)


def _sdk_in_pfs(fh: Any, mk: _Mkpfs, ebene: int) -> str:
    """Wie :class:`spielbaum.PfsBaum`: Hat das PFS genau eine Datei und ist diese ein Abbild (exFAT, UFS2, PFS), liegt das Spiel darin
    - die PFSC-Bloecke werden erst beim Lesen entpackt; sonst liegen die Spieldateien im PFS selbst."""
    pfs = mk.pfs
    kopf = pfs.parse_image_header(fh)
    if kopf.magic != mk.consts.PFS_MAGIC or kopf.block_size <= 0 or kopf.block_size & (kopf.block_size - 1):
        return ""
    inodes = pfs.parse_image_inodes(fh, kopf)
    fehler: list[str] = []
    wurzel, _fpt, _koll, _bes = pfs.parse_superroot_and_indexes(fh, kopf, inodes, fehler)
    if wurzel < 0:
        return ""
    dateien, _ordner, _eintraege = pfs.build_tree_from_uroot(fh, kopf, inodes, wurzel, fehler)
    if fehler or not dateien:
        return ""
    if len(dateien) == 1 and ebene < _MAX_EBENEN:
        inode = inodes[next(iter(dateien.values()))]
        if not (inode.db_sig or inode.ib_sig) and inode.blocks > 0 and inode.logical_size >= 16:
            sicht = pfs._LogicalFileView(fh, kopf, inode)
            if _abbild_art(sicht, mk):
                return _sdk_im_abbild(sicht, mk, ebene + 1)
    nummer = next((n for rel, n in dateien.items() if str(rel).replace("\\", "/").lower() == "eboot.bin"), None)
    if nummer is None:
        return ""
    inode = inodes[nummer]
    if inode.db_sig or inode.ib_sig or inode.blocks <= 0 or inode.logical_size <= 0:
        return ""                                          # signiert oder verstreut gespeichert: so nicht in Teilen zu lesen
    sicht = pfs._LogicalFileView(fh, kopf, inode)

    def lesen(ab: int, laenge: int) -> bytes:
        sicht.seek(ab)
        return sicht.read(laenge)

    return sdk_text(sdk_wort_lesen(lesen))


def eboot_sdk_in_abbild(pfad: str, mkpfs_ordner: str = "") -> str:
    """Das SDK der ``eboot.bin`` in einem Abbild (``.ffpkg``, ``.exfat``, ``.ffpfs``, ``.ffpfsc``) als Text; ``""``, wenn nichts zu lesen ist.

    Die Art erkennt es am Inhalt, auch bei einem ``.ffpfsc``, das ein ``.ffpkg``, ein ``.exfat`` oder ein ``.ffpfs`` umhuellt. Entpackt
    nichts und liest nur Koepfe, Verzeichnisse und die wenigen Cluster oder Bloecke mit der ``eboot.bin``-Kopfzeile.
    """
    mk: "_Mkpfs | None"
    try:
        mk = _Mkpfs(mkpfs_ordner)
    except ImportError:
        mk = None                                          # ohne MkPFS bleibt das ``.ffpkg`` in einer ``.ffpfsc`` zu, ein ``.ffpkg`` selbst nicht
    fehler = mk.fehler if mk is not None else (OSError, ValueError, struct.error, KeyError, IndexError)   # Ufs2Fehler, ExfatError: ValueError
    try:
        with open(pfad, "rb") as fh:
            return _sdk_im_abbild(fh, mk)
    except fehler:
        return ""


def eboot_sdk_in_ffpkg(abbild: str) -> str:
    """Das SDK der ``eboot.bin`` in einer ``.ffpkg`` (UFS2) als Text; ``""``, wenn nichts zu lesen ist. Entpackt nichts."""
    try:
        with open(abbild, "rb") as fh:
            return _sdk_in_ufs2(fh) if _ist_ufs2(fh) else ""
    except (OSError, ValueError):                  # Ufs2Fehler ist ein ValueError
        return ""


#: Die Endungen der Abbilder, die :func:`eboot_sdk` liest (wie ``pkg_plattform.ENDUNGEN_ABBILD``).
_ABBILD_ENDUNGEN = (".ffpkg", ".exfat", ".ffpfs", ".ffpfsc")


def eboot_sdk(quelle: str, mkpfs_ordner: str = "") -> str:
    """Das SDK der ``eboot.bin`` einer Quelle als Text (``"10.00"``): Spielordner, ``.ffpkg``, ``.exfat``, ``.ffpfs``, ``.ffpfsc`` oder ``.pkg``.

    Ein ``.pkg`` liest :mod:`pkg_eboot` (AES-XTS und Kraken-Bloecke wie Forge, nur der Weg zur ``eboot.bin``); ein Paket, das sich so
    nicht lesen laesst (Verkaufsfassung, fremder Passcode, Update-Paket, anderes Verdichtungsverfahren), ergibt ``""``. Archive kommen bei
    der Rueckfrage nicht vor und ergeben ebenfalls ``""`` ("nicht zu sagen"), nie eine Vermutung. Wirft nie.
    """
    try:
        if os.path.isdir(quelle):
            return eboot_sdk_im_ordner(quelle)
        if os.path.isfile(quelle):
            if quelle.lower().endswith(".ffpkg"):
                return eboot_sdk_in_ffpkg(quelle)
            if quelle.lower().endswith(_ABBILD_ENDUNGEN):
                return eboot_sdk_in_abbild(quelle, mkpfs_ordner)
            if quelle.lower().endswith(".pkg"):
                from . import pkg_eboot                    # spaet: pkg_eboot nutzt selbst dieses Modul
                return pkg_eboot.eboot_sdk(quelle)
    except (OSError, ValueError):
        pass
    return ""
