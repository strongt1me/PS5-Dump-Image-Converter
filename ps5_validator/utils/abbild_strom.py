# -*- coding: utf-8 -*-
"""Ein exFAT-Abbild direkt aus Lesebaum und zstd-Strom - ohne Zwischenordner (Stufe 3, Etappe 3).

Bisher entpackte der Weg ``.exfat`` -> ``.exfat`` mit zstd das ganze Spiel in einen Ordner, packte dort und baute aus dem Ordner das
Abbild. Hier laufen die Quelle (ein Lesebaum, :mod:`spielbaum`) und die Packdateien (:func:`ampr_zstdpack.strom`) als Dateiliste
durch den Schreiber von MkPFS (``iter_exfat_image_liste``) und kommen als Bytes des fertigen Abbilds heraus.

Die Packdateien (Baender und Index) kennt der Schreiber vorab nur nach Name und Groesse (aus dem Messdurchgang); ihre Bytes liefert
der Schreibdurchgang erst, wenn der Schreiber sie braucht. Der Strom kann nur vorwaerts gelesen werden, deshalb muss die Reihenfolge,
in der der Schreiber die Dateien anfordert, die des Stroms sein; :func:`abbild_strom` prueft das, **bevor** das erste Byte kommt.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Iterator

from ps5_validator.utils import ampr_zstdpack as z
from ps5_validator.utils import dlc_emu
from ps5_validator.utils import fake_signieren

Oeffner = Callable[[], Iterator[bytes]]


class StromDateien:
    """Macht aus dem Erzeuger ``strom()`` (``(Name, Bytes)``, Name wechselt von Datei zu Datei) einzelne Dateien.

    Jede Datei hat einen Oeffner; der Oeffner einer Datei darf erst gerufen werden, wenn die davor fertig gelesen sind.
    """

    def __init__(self, erzeuger: Iterator[tuple[str, bytes]], dateien: "list[tuple[str, int]]") -> None:
        self._erzeuger = iter(erzeuger)
        self._reihe = [name for name, _g in dateien]
        self._groessen = dict(dateien)
        self._pos = 0
        self._vorrat: "tuple[str, bytes] | None" = None
        self._zu = False

    def eintraege(self) -> "list[tuple[str, int, Oeffner]]":
        """``(Name, Groesse, Oeffner)`` in der Reihenfolge des Stroms; die Namen liegen im Wurzelordner des Spiels."""
        return [(name, self._groessen[name], self._oeffner(name)) for name in self._reihe]

    def _oeffner(self, name: str) -> Oeffner:
        def lesen() -> Iterator[bytes]:
            if self._pos >= len(self._reihe) or self._reihe[self._pos] != name:
                raise z.ZstdPackFehler("Packdatei %s wird nicht in der Reihenfolge des Stroms gelesen" % name)
            while True:
                if self._vorrat is None:
                    try:
                        self._vorrat = next(self._erzeuger)
                    except StopIteration:
                        break
                gelesen_name, daten = self._vorrat
                if gelesen_name != name:
                    break
                self._vorrat = None
                yield daten
            self._pos += 1
        return lesen

    def schliessen(self) -> None:
        """Beendet den Erzeuger (Faeden, Lesevorlauf); mehrfaches Rufen schadet nicht."""
        if self._zu:
            return
        self._zu = True
        schliessen = getattr(self._erzeuger, "close", None)
        if callable(schliessen):
            schliessen()


def reihenfolge_pruefen(anforderung: Iterable[str], strom_reihe: Iterable[str]) -> None:
    """Die Packdateien muessen in der Reihenfolge angefordert werden, in der der Strom sie liefert.

    ``anforderung`` ist die Reihenfolge, in der der Schreiber alle Dateien liest; nur die Namen aus ``strom_reihe`` zaehlen.
    Zwischen zwei Packdateien duerfen andere Dateien gelesen werden - sie kommen aus dem Lesebaum und nicht aus dem Strom.
    """
    reihe = list(strom_reihe)
    menge = set(reihe)
    gesehen = [rel for rel in anforderung if rel in menge]
    if gesehen != reihe:
        raise z.ZstdPackFehler("Reihenfolge der Packdateien im Abbild (%s) weicht vom Strom (%s) ab" % (
            ", ".join(gesehen[:3]), ", ".join(reihe[:3])))


def abbild_strom(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung", *, iter_liste: Callable[..., Iterator[bytes]],
                 reihenfolge_liste: Callable[[Iterable], "list[str]"], originale_behalten: bool = False, arbeiter: int = 0,
                 abbruch: Callable[[], bool] = lambda: False, fortschritt: "Callable[[float], None] | None" = None,
                 on_layout: "Callable[[int], None] | None" = None,
                 pruefen: "bool | frozenset[int] | set[int] | None" = None) -> Iterator[bytes]:
    """Die Bytes eines exFAT-Abbilds mit den losen Dateien des Baums und den zstd-Packs aus dem Strom.

    ``iter_liste`` und ``reihenfolge_liste`` sind ``mkpfs.exfat_writer.iter_exfat_image_liste`` und ``dateireihenfolge_liste``
    (das Paket ``mkpfs`` liegt nicht im Importpfad, bis das Hauptmodul es einbettet). Ohne ``originale_behalten`` fallen die
    gepackten Dateien weg, wie bei "Originale weglassen"; mit bleiben sie neben den Packs im Abbild.

    ``fortschritt`` bekommt den Anteil des **Strom-Schreibdurchgangs** (0..1), nicht den des Abbilds - dafuer ist ``on_layout``
    mit der Gesamtgroesse und die Zahl der gelieferten Bytes da.

    ``pruefen``: ``True`` entpackt jeden Chunk der Packdateien auf dem Weg ins Abbild und vergleicht ihn mit der Pruefsumme der
    Quelle, eine Menge von Chunknummern (``ampr_zstdpack.stichprobe_chunks``) nur diese (siehe ``ampr_zstdpack.strom``).
    """
    lose, dateien, ordner = _vorbereiten(baum, auswahl, messung, originale_behalten, arbeiter, abbruch, fortschritt, pruefen)
    try:
        gesamt = lose + dateien.eintraege()
        reihenfolge_pruefen(reihenfolge_liste(gesamt, ordner), [name for name, _g in messung.dateien()])
        yield from iter_liste(gesamt, on_layout=on_layout, ordner=ordner)
    finally:
        dateien.schliessen()


def _vorbereiten(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung", originale_behalten: bool, arbeiter: int,
                 abbruch: Callable[[], bool], fortschritt: "Callable[[float], None] | None",
                 pruefen: "bool | frozenset[int] | set[int] | None") -> "tuple[list[tuple[str, int, Oeffner]], StromDateien, list[str]]":
    """Die losen Dateien des Baums, die Packdateien als Strom und die Verzeichnisse - fuer jede Art von Ausgabe dasselbe."""
    gepackt = {rel for rel, _g in auswahl.gepackt}
    vorhanden = baum.suchen()
    for rel in vorhanden:
        if z.ist_packname(rel):
            raise z.ZstdPackFehler("ampr_zstd.ausgabe_belegt")
    lose = [(d.rel, d.groesse, d.lesen) for d in baum.dateien() if originale_behalten or d.rel not in gepackt]
    fehlend = [rel for rel in gepackt if rel not in vorhanden]
    if fehlend:
        raise z.ZstdPackFehler("%s fehlt in der Quelle" % fehlend[0])
    # Auch die leeren Verzeichnisse kommen ins Abbild, wie im Ordnerweg (eine Dateiliste zeigt sie nicht).
    ordner = abbild_ordner(baum, auswahl, originale_behalten)

    dateien = StromDateien(z.strom(baum, auswahl, messung, arbeiter=arbeiter, abbruch=abbruch, fortschritt=fortschritt,
                                   pruefen=pruefen),
                           messung.dateien())
    return lose, dateien, ordner


def abbild_liste(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung", *, originale_behalten: bool = False, arbeiter: int = 0,
                 abbruch: Callable[[], bool] = lambda: False, fortschritt: "Callable[[float], None] | None" = None,
                 pruefen: "bool | frozenset[int] | set[int] | None" = None
                 ) -> "tuple[list[tuple[str, int, Oeffner]], list[str], Callable[[], None]]":
    """Die Dateien eines **flachen** Abbilds (``.ffpfs``): ``(Pfad, Groesse, Oeffner)``, die Schreibreihenfolge und ``schliessen``.

    Wie :func:`abbild_strom`, nur ohne exFAT: Ein flaches PFS legt die Dateien nach ihrer Groesse an feste Plaetze, es kennt die
    Reihenfolge nicht - die Oeffner duerfen in jeder Reihenfolge gerufen werden, solange die Packdateien in der des Stroms kommen.
    Die Schreibreihenfolge nennt deshalb erst die losen Dateien, dann die Packdateien in Stromreihenfolge. ``schliessen()`` beendet
    den Strom (Faeden, Lesevorlauf); mehrfaches Rufen schadet nicht. Leere Verzeichnisse kennt ein flaches PFS nie.
    """
    lose, dateien, _ordner = _vorbereiten(baum, auswahl, messung, originale_behalten, arbeiter, abbruch, fortschritt, pruefen)
    gesamt = lose + dateien.eintraege()
    reihenfolge = [rel for rel, _g, _o in lose] + [name for name, _g in messung.dateien()]
    return gesamt, reihenfolge, dateien.schliessen


def ffpfs_schreiben(eintraege: "Iterable[tuple[str, int, Oeffner]]", ziel: str, *, reihenfolge: Iterable[str] = (),
                    block_size: int = 65536, case_insensitive: bool = True, abbruch: Callable[[], bool] = lambda: False,
                    melden: "Callable[[str, int, int, int], None] | None" = None, bezeichnung: str = "") -> Any:
    """Schreibt eine Dateiliste als flaches, unkomprimiertes PFS (``.ffpfs``) - ohne Zwischenordner.

    Das ist, was ``mkpfs pack folder --raw --no-compress`` fuer einen Ordner baut: die Spieldateien liegen in der Wurzel des PFS.
    ``eintraege`` sind ``(Pfad, Groesse, Oeffner)``; ``reihenfolge`` nennt die Pfade, deren Oeffner zuerst gerufen werden (siehe
    :func:`abbild_liste`). ``ziel`` ist die fertige Datei; MkPFS schreibt zuerst ``ziel + ".tmp"`` und setzt es nach der
    Strukturpruefung um. ``melden(phase, fertig, gesamt, bytes)`` bekommt den Fortschritt. Bricht ``abbruch()`` ab, kommt
    :class:`StromAbgebrochen` - auch mitten in einer grossen Datei -, und es bleibt keine Teildatei liegen.

    Returns:
        Die ``BuildStats`` von MkPFS.
    """
    from pathlib import Path

    from mkpfs import consts                                    # pyright: ignore[reportMissingImports]
    from mkpfs.pbar import Progress                             # pyright: ignore[reportMissingImports]
    from mkpfs.pfs import build_pfs                             # pyright: ignore[reportMissingImports]

    def _hoeren(art: str, *args: Any) -> None:
        if abbruch():
            raise StromAbgebrochen("abgebrochen")
        if art == "step" and melden is not None:
            phase, fertig, gesamt, byte_zahl = args
            melden(str(phase), int(fertig), int(gesamt), int(byte_zahl))

    def _bewacht(oeffner: Oeffner) -> Oeffner:
        def lesen() -> Iterator[bytes]:
            strom = iter(oeffner())
            try:
                for stueck in strom:
                    if abbruch():
                        raise StromAbgebrochen("abgebrochen")
                    yield stueck
            finally:
                schliessen = getattr(strom, "close", None)
                if callable(schliessen):
                    schliessen()
        return lesen

    liste = [(rel, groesse, _bewacht(oeffner)) for rel, groesse, oeffner in eintraege]
    return build_pfs(
        source_root=Path(bezeichnung or "stream"), output_path=Path(ziel), block_size=block_size,
        pfs_version=consts.PFS_VERSION_PS5, inode_bits=32, case_insensitive=case_insensitive, signed=False, compress=False,
        threshold_gain=0, cpu_count=1, zlib_level=6, dry_run=False, verbose=False, eintraege=liste,
        reihenfolge=list(reihenfolge), progress=Progress(enabled=False, listener=_hoeren))


def _eltern(pfad: str) -> "Iterator[str]":
    """Alle Verzeichnispfade ueber ``pfad`` (``a/b/c.bin`` -> ``a/b``, ``a``)."""
    while "/" in pfad:
        pfad = pfad.rsplit("/", 1)[0]
        yield pfad


def abbild_ordner(baum: Any, auswahl: "z.Auswahl | None" = None, originale_behalten: bool = True) -> list[str]:
    """Die Verzeichnisse des fertigen Abbilds **einschliesslich der leeren** (sortiert).

    Der Ordnerweg kannte leere Verzeichnisse (``exfat_writer._scan_tree``, ebenso das Entpacken eines Abbilds); eine Dateiliste
    allein zeigt sie nicht. Fallen die gepackten Originale weg (``originale_behalten=False``), geht es wie im Ordnerweg
    (``ampr_zstdpack.originale_entfernen``): Ein Verzeichnis, das dadurch leer wird, faellt mit weg - bis hinauf zum ersten, in dem
    noch etwas liegt. Ein Verzeichnis, das **schon vorher** leer war, bleibt.
    """
    dateien = {d.rel for d in baum.dateien()}
    alle = set(baum.ordner())
    for rel in dateien:
        alle.update(_eltern(rel))
    if auswahl is not None and not originale_behalten:
        gepackt = {rel for rel, _g in auswahl.gepackt}
        rest = dateien - gepackt
        mit_datei: set[str] = set()
        for rel in rest:
            mit_datei.update(_eltern(rel))
        kinder: dict[str, int] = {}
        for ordner in alle:
            vater = ordner.rsplit("/", 1)[0] if "/" in ordner else ""
            kinder[vater] = kinder.get(vater, 0) + 1
        kandidaten: set[str] = set()
        for rel in gepackt:
            kandidaten.update(_eltern(rel))
        for ordner in sorted(kandidaten, key=len, reverse=True):
            if ordner in alle and ordner not in mit_datei and kinder.get(ordner, 0) == 0:
                alle.discard(ordner)
                vater = ordner.rsplit("/", 1)[0] if "/" in ordner else ""
                kinder[vater] = kinder.get(vater, 0) - 1
    return sorted(alle)


class StromAbgebrochen(RuntimeError):
    """Der Auftrag wurde waehrend des Schreibens abgebrochen; die Teildatei ist schon weggeraeumt."""


def ffpfsc_schreiben(erzeuger: Callable[[Callable[[int], None]], Iterator[bytes]], ziel: str, *, quelle_ordner: str,
                     block_size: int = 65536, zlib_level: int = 6, cpu_count: int = 0, threshold_gain: int = 0,
                     case_insensitive: bool = True, abbruch: Callable[[], bool] = lambda: False,
                     melden: "Callable[[str, int, int, int], None] | None" = None,
                     on_layout: "Callable[[int], None] | None" = None, backend: str = "zlib-ng") -> Any:
    """Schreibt den exFAT-Strom als einzige Datei in ein komprimiertes PFS-Abbild (``.ffpfsc``) - ohne Zwischendatei.

    ``erzeuger(on_layout)`` liefert die Bytes des exFAT-Abbilds (:func:`abbild_strom` oder ``iter_exfat_image_liste``). Das ist
    die Bauform, die ``mkpfs pack folder --compress`` fuer einen Ordner baut: ein PFS mit **einer** Datei ``<TitleID>.exfat``,
    deren Bytes in PFSC-Bloecke komprimiert werden. Den Namen leitet MkPFS aus ``quelle_ordner`` ab (``sce_sys/param.json``, sonst
    der Ordnername) - hier der Ueberlagerungsordner, in dem die param.json der Ansicht liegt.

    ``ziel`` ist der Pfad der fertigen Datei; MkPFS schreibt zuerst ``ziel + ".tmp"`` und setzt es nach der Strukturpruefung um.
    ``melden(phase, fertig, gesamt, bytes)`` bekommt den Fortschritt der Kompression. Bricht ``abbruch()`` ab, kommt
    :class:`StromAbgebrochen`; auch bei jedem anderen Fehler bleibt keine Teildatei liegen.

    ``backend`` ist das Rechenwerk der PFSC-Bloecke (``MKPFS_BACKEND`` des Hauptmoduls, ``zlib-ng``). Die MkPFS-Kommandozeile bekam
    es als ``--compression-backend`` mit; im eigenen Prozess muss es hier gesetzt werden, sonst gilt, was zuletzt jemand eingestellt
    hat. Laesst es sich nicht laden, packt der Standard-``zlib`` - langsamer, aber derselbe Datenstrom.

    Returns:
        Die ``BuildStats`` von MkPFS.
    """
    import itertools
    from pathlib import Path

    from mkpfs import compression                               # pyright: ignore[reportMissingImports]
    from mkpfs import consts                                    # pyright: ignore[reportMissingImports]
    from mkpfs.pbar import Progress                             # pyright: ignore[reportMissingImports]
    from mkpfs.pfs import build_pfs_stream_from_blocks          # pyright: ignore[reportMissingImports]
    from mkpfs.utils import default_image_basename              # pyright: ignore[reportMissingImports]

    try:
        compression.set_backend(backend)
    except (ImportError, ValueError):
        compression.set_backend("zlib")

    groesse: list[int] = []

    def _layout(gesamt: int) -> None:
        groesse.append(int(gesamt))
        if on_layout is not None:
            on_layout(gesamt)

    strom = iter(erzeuger(_layout))

    def _bewacht() -> Iterator[bytes]:
        try:
            for stueck in strom:
                if abbruch():
                    raise StromAbgebrochen("abgebrochen")
                yield stueck
        finally:
            schliessen = getattr(strom, "close", None)
            if callable(schliessen):
                schliessen()

    inner_name = "%s.exfat" % default_image_basename(Path(quelle_ordner))
    nutzdaten = _bewacht()
    try:
        erstes = next(nutzdaten)                                # stoesst Planung und Layout an: danach ist die Groesse bekannt
    except StopIteration:
        raise RuntimeError("Der Erzeuger hat keine Daten geliefert") from None     # ein Fehler, kein Abbruch des Anwenders
    if not groesse:
        nutzdaten.close()
        raise RuntimeError("Der Schreiber hat die Groesse des Abbilds nicht gemeldet")

    def _hoeren(art: str, *args: Any) -> None:
        if art == "step" and melden is not None:
            phase, fertig, gesamt, byte_zahl = args
            melden(str(phase), int(fertig), int(gesamt), int(byte_zahl))

    return build_pfs_stream_from_blocks(
        payload_stream=itertools.chain([erstes], nutzdaten), raw_size=groesse[0], inner_name=inner_name,
        source_label=Path(quelle_ordner), output_path=Path(ziel), block_size=block_size,
        pfs_version=consts.PFS_VERSION_PS5, case_insensitive=case_insensitive, zlib_level=zlib_level,
        threshold_gain=threshold_gain, cpu_count=cpu_count, progress=Progress(enabled=False, listener=_hoeren))


def ufs2_planen(eintraege: "Iterable[tuple[str, int, Oeffner]]", ordner: Iterable[str] = (),
                abbruch: Callable[[], bool] = lambda: False) -> "tuple[Any, str]":
    """Plant das UFS2-Abbild (``.ffpkg``) fuer diese Dateiliste: erst mit dem Profil, das UFS2Tool zuerst versucht, dann mit dem zweiten.

    Wie der bisherige Bau (``_build_ffpkg_from_folder``: Referenzprofil 64 KiB, danach Kompatibilitaetsprofil 32 KiB/4 KiB).
    Planen rechnet nur - es liest keine Datei. Gibt ``(Plan, Profilkennung)`` zurueck; scheitern beide, kommt der Fehler des zweiten
    (:class:`ufs2_schreiber.Ufs2SchreibFehler`).
    """
    from ps5_validator.utils import ffpkg_support as ffs
    from ps5_validator.utils import ufs2_schreiber as w

    eintraege = list(eintraege)
    ordner = list(ordner)
    fehler: "Exception | None" = None
    for profil in (ffs.primary_newfs_profile(), ffs.compatibility_newfs_profile()):
        try:
            return w.planen(eintraege, ordner, profil=w.profil_aus_newfs(profil), abbruch=abbruch), profil.identifier
        except w.Ufs2SchreibFehler as exc:
            fehler = exc
        except InterruptedError:
            raise StromAbgebrochen("abgebrochen") from None
    assert fehler is not None
    raise fehler


def ufs2_schreiben(plan: Any, ziel: str, *, reihenfolge: Iterable[str] = (), abbruch: Callable[[], bool] = lambda: False,
                   melden: "Callable[[str, int, int, int], None] | None" = None) -> int:
    """Schreibt den Plan (:func:`ufs2_planen`) als ``.ffpkg`` nach ``ziel`` - ohne Zwischenordner, ohne UFS2Tool, ohne Administratorrechte.

    ``melden(phase, fertig, gesamt, bytes)`` bekommt ``"write"`` nach jeder Datei. Bricht ``abbruch()`` ab (auch mitten in einer grossen
    Datei), kommt :class:`StromAbgebrochen`; das halbe ``ziel`` raeumt der Aufrufer weg. Gibt die Groesse des Abbilds zurueck.
    """
    try:
        return int(plan.schreiben(ziel, reihenfolge=reihenfolge, abbruch=abbruch, melden=melden))
    except InterruptedError:
        raise StromAbgebrochen("abgebrochen") from None


def pfs_pruefen(pfad: str, *, abbruch: Callable[[], bool] = lambda: False,
                melden: "Callable[[int, int], None] | None" = None) -> "tuple[list[str], list[str]]":
    """Prueft ein fertiges PFS-Abbild wie die MkPFS-Kommandozeile nach dem Packen: Aufbau, Verzeichnisse und **jeden Block** der Dateien.

    Das ist die Pruefung, die ``mkpfs pack folder`` ausser bei der Stufe "aus" nach dem Bauen laufen laesst
    (``run_image_check`` mit ``verify_payloads``): Sie entpackt jeden PFSC-Block und zaehlt die Pruefsumme. Ein beschaedigter Block in einer
    Datei, die die Stichprobe der Rueckleseprobe nicht gezogen hat, faellt nur hier auf. ``melden(fertig, gesamt)`` bekommt die
    Fortschritte der Pruefung; ``abbruch()`` wird dabei gefragt und beendet sie mit :class:`StromAbgebrochen`.

    Returns:
        ``(Fehler, Warnungen)`` als Texte von MkPFS; leere Fehlerliste heisst bestanden.
    """
    from pathlib import Path

    from mkpfs.pbar import Progress                             # pyright: ignore[reportMissingImports]
    from mkpfs.pfs import inspect_pfs_image                     # pyright: ignore[reportMissingImports]

    def _hoeren(art: str, *args: Any) -> None:
        if abbruch():
            raise StromAbgebrochen("abgebrochen")
        if art == "step" and melden is not None:
            _phase, fertig, gesamt, _bytes = args
            melden(int(fertig), int(gesamt))

    befund = inspect_pfs_image(Path(pfad), verify_payloads=True, progress=Progress(enabled=False, listener=_hoeren))
    return list(befund.errors), list(befund.warnings)


# ---------------------------------------------------------------------------
# Einbau ohne Entpacken: Ueberlagerungsordner und Ansicht
# ---------------------------------------------------------------------------
#: Zeitstempel, den der Schreiber jeder Datei im Abbild gibt (2024-01-01 00:00:00); der ``ampr_emu.index`` traegt ihn ebenso.
FESTER_MTIME = 1704067200


def _kopf(datei: Any, laenge: int = 4) -> bytes:
    erzeuger = datei.lesen(laenge)
    try:
        return next(erzeuger, b"")[:laenge]
    finally:
        erzeuger.close()


def _ziel_pfad(ziel: str, rel: str) -> str:
    wurzel = os.path.normpath(os.path.abspath(ziel))
    voll = os.path.normpath(os.path.join(wurzel, *rel.split("/")))
    if os.path.commonpath([voll, wurzel]) != wurzel:
        raise z.ZstdPackFehler("Pfad liegt ausserhalb des Ordners: %s" % rel)
    return voll


def schatten_fuellen(baum: Any, ziel: str, *, programmdateien: bool = False, abbruch: Callable[[], bool] = lambda: False,
                     fortschritt: "Callable[[int, int], None] | None" = None) -> "tuple[list[str], int]":
    """Legt die Dateien in einen kleinen Ordner, die der Einbau braucht: die Systemschicht (``ampr_zstdpack.bleibt_lose``:
    ``eboot.bin``, Module, ``sce_sys``, ``fakelib*``, ``.ini``) und mit ``programmdateien`` jede Datei mit der Kennung eines
    ELF oder SELF (der Backport patcht auch solche mit anderem Namen).

    Backport, Fake-Signatur, DLC EMU und AMPR EMU arbeiten auf einem Ordner; hier ist es dieser kleine statt eines entpackten
    Spiels. Alles andere bleibt in der Quelle und wird nur gelesen. Rueckgabe: die Pfade der abgelegten Dateien und ihre Bytes.
    """
    from ps5_validator.utils import ps5_backport

    os.makedirs(ziel, exist_ok=True)
    dateien = baum.dateien()
    abgelegt: list[str] = []
    gesamt_bytes = 0
    for nummer, datei in enumerate(dateien, 1):
        if abbruch():
            raise z.ZstdPackFehler("ampr_pack.abgebrochen")
        if fortschritt is not None and not nummer % 512:
            fortschritt(nummer, len(dateien))
        rel = datei.rel
        wanted = z.bleibt_lose(rel)
        # Die Karte der Zusatzinhalte (PS5-App-Dumper): DLC EMU liest sie aus der Spielwurzel (``dlc_emu.ini_anlegen``); ohne sie
        # im Ordner entstuende die ``dlc_emu.ini`` mit den falschen oder gar keinen Eintraegen.
        if not wanted and rel.lower() == dlc_emu.DLCMAP_NAME.lower():
            wanted = True
        # Programm nach dem Namen (``eboot*.bin`` auch mit anderem Namen als ``eboot.bin``): Die Fake-Signatur sucht genau so und
        # muss die Datei im Ordner finden, auch wenn kein Backport nach der ELF-Kennung fragt.
        if not wanted and fake_signieren.ist_ausfuehrbar(rel):
            wanted = True
        if not wanted and programmdateien and datei.groesse >= 4 and not rel.lower().endswith(ps5_backport.SICHERUNGS_ENDUNGEN):
            erster = rel.split("/", 1)[0].lower()
            if erster not in ps5_backport.FAKELIB_ORDNERNAMEN:
                wanted = _kopf(datei) in ps5_backport._KENNUNGEN
        if not wanted:
            continue
        voll = _ziel_pfad(ziel, rel)
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        try:
            with open(voll, "wb") as fh:
                for stueck in datei.lesen():
                    fh.write(stueck)
        except OSError as exc:
            raise z.ZstdPackFehler("%s nicht schreibbar: %s" % (rel, exc)) from exc
        abgelegt.append(rel)
        gesamt_bytes += datei.groesse
    if fortschritt is not None:
        fortschritt(len(dateien), len(dateien))
    return abgelegt, gesamt_bytes


class Ansicht:
    """Das Spiel, wie es nach dem Einbau aussieht: die Quelle, darueber die Dateien des Ueberlagerungsordners.

    Der Einbau aendert Dateien im Ordner (patcht, signiert, ergaenzt Bibliotheken und Index). Die Ansicht liest bei jedem
    :meth:`baum` den Ordner neu und nennt, was seit dem Fuellen dort fehlt, als entfernt.
    """

    def __init__(self, quelle: Any, ordner: str, abgelegt: Iterable[str], ignoriert: "Callable[[str], bool] | None" = None):
        self.quelle = quelle
        self.ordner = os.path.abspath(ordner)
        self.ordner_norm = os.path.normcase(os.path.realpath(self.ordner))
        self.abgelegt = set(abgelegt)
        self._ignoriert = ignoriert

    def baum(self) -> Any:
        from ps5_validator.utils import spielbaum as sb

        ueber = sb.OrdnerBaum(self.ordner, ignoriert=self._ignoriert)
        jetzt = {d.rel for d in ueber.dateien()}
        return sb.UeberlagerBaum(self.quelle, ueber, entfernt=self.abgelegt - jetzt)


def abbild_eintraege(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung",
                     originale_behalten: bool = False) -> "list[tuple[str, int]]":
    """``(Pfad, Groesse)`` jeder Datei des fertigen Abbilds: die losen aus dem Baum, dazu Baender und Index."""
    gepackt = {rel for rel, _g in auswahl.gepackt}
    lose = [(d.rel, d.groesse) for d in baum.dateien() if originale_behalten or d.rel not in gepackt]
    return lose + list(messung.dateien())


def pruef_eintraege(baum: Any, auswahl: "z.Auswahl | None", messung: "z.Messung | None",
                    originale_behalten: bool = False) -> "list[tuple[str, int, Callable[[int], bytes] | None]]":
    """``(Pfad, Groesse, Anfang)`` jeder Datei des fertigen Abbilds fuers Zuruecklesen (Stufe 3, Etappe 5).

    Wie :func:`abbild_eintraege`, aber mit einer Funktion je loser Datei, die ihre ersten ``n`` Bytes aus dem Baum liefert
    (``abbild_pruefen.exfat_ruecklesen_liste`` vergleicht damit eine Stichprobe). Baender und Index aus dem Strom haben keinen
    Anfang (``None``): Ihre Bytes hat der Schreibdurchgang Chunk fuer Chunk gegen die Messung gehalten. Ohne Auswahl und Messung
    (kein Pack gebaut) kommt alles aus dem Baum.
    """
    from ps5_validator.utils.abbild_pruefen import anfang_aus_baumdatei

    gepackt = {rel for rel, _g in auswahl.gepackt} if auswahl is not None else set()
    lose = [(d.rel, d.groesse, anfang_aus_baumdatei(d)) for d in baum.dateien() if originale_behalten or d.rel not in gepackt]
    packs = [(name, groesse, None) for name, groesse in messung.dateien()] if messung is not None else []
    return lose + packs


def liste_pruefen(exfat_pfad: str, erwartet: "Iterable[tuple[str, int]]", mkpfs_ordner: str = "",
                  ignoriert: "Callable[[str], bool] | None" = None) -> "dict[str, Any]":
    """Liest die Dateiliste des fertigen Abbilds zurueck und vergleicht Pfade und Groessen mit ``erwartet``.

    Rueckgabe wie ``abbild_pruefen.exfat_ruecklesen``: ``fehlen``, ``zuviel``, ``groesse`` (Listen von Pfaden) und ``dateien``.
    Der Inhalt wird hier nicht verglichen - die Packdateien hat der Schreibdurchgang Chunk fuer Chunk gegen die Messung gehalten.
    """
    from ps5_validator.utils import spielbaum as sb

    soll = {rel: groesse for rel, groesse in erwartet if not (ignoriert and any(ignoriert(t) for t in rel.split("/")))}
    with sb.ExfatBaum(exfat_pfad, mkpfs_ordner=mkpfs_ordner) as neu:
        ist = {d.rel: d.groesse for d in neu.dateien()}
    return {
        "dateien": len(ist),
        "fehlen": sorted(set(soll) - set(ist)),
        "zuviel": sorted(set(ist) - set(soll)),
        "groesse": sorted(rel for rel in set(soll) & set(ist) if soll[rel] != ist[rel]),
    }
