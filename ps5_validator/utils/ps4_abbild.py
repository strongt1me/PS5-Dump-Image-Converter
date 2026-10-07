# -*- coding: utf-8 -*-
"""Die Arbeit hinter „PS4 PKG Dump & Image Converter“: Spiele ordnen, entpacken, einspielen, Abbild bauen.

Seit dem 07.10.2026 ersetzt dieses Fenster „PS4 PKG -> OTA“ und das alte „PS4 PKG -> ffpfsc“ (Nutzerwunsch).
Die **Technik** teilt sich so auf (Entscheid „Hybrid“):

* **Entpacken, Updates einspielen, Zusammenfuehren** macht die Engine des fruehren OTA-Fensters,
  OrbisPkgTool (``orbispkg``) - je Paket nach ``Image0``/``Sc0`` entpackt und zu einem Dump-Ordner geordnet
  (``ps4pkg_aufgaben.dump_ordner_machen``); Updates werden in der Reihenfolge ihrer Fassung darueber gelegt.
* **ffpfsc/exFAT** baut weiter PS4 FFPFSC (MkPFS): Es bekommt den fertigen Dump-Ordner (``--dump-dir``) und macht
  daraus das ShadowMount-Abbild samt ``param.json``, Korrektur der ``npbind.dat`` und Pruefung. Die Teile, die dort
  fuer die Konsole gemessen sind, bleiben also unangetastet. Mit DLC wird der Ordner im Dumper-Aufbau
  (``app/`` und ``addcont/<Kennung>/``) bereitgestellt; ohne OrbisPkgTool (Linux, macOS) greift der bisherige
  Weg ueber ``--pkg-file``.

Das Modul kennt keine Oberflaeche. Die Arbeiten laufen als ``Aufgabe`` der Warteschlange aus
``ps4pkg_aufgaben`` (Abbruch, Fortschritt, Protokoll); Fehler tragen einen ``ps4ota.fehler_<Schluessel>``.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable

from ps5_validator.utils import orbispkg, ps4_fortschritt, ps4_werkzeug
from ps5_validator.utils import ps4pkg_aufgaben as au
from ps5_validator.utils import ps4pkg_bibliothek as bib

logger = logging.getLogger("PS5Converter.ps4_abbild")

#: Die Ergebnisformen des Fensters.
FORMAT_DUMP = "dump"
FORMAT_FFPFSC = "ffpfsc"
FORMAT_EXFAT = "exfat"
FORMAT_PKG = "pkg"
FORMATE = (FORMAT_DUMP, FORMAT_FFPFSC, FORMAT_EXFAT, FORMAT_PKG)
#: Formen, die PS4 FFPFSC (MkPFS) baut.
ABBILD_FORMATE = (FORMAT_FFPFSC, FORMAT_EXFAT)

#: Platzbedarf als Vielfaches der Paketgroessen: ein entpacktes PFSC-Paket ist gross (gemessen am
#: Offroad-Spiel: Paket 4,9 GB, entpackt etwa das Doppelte), das Abbild liegt dann noch dazu.
FAKTOR_DUMP = 2.2
FAKTOR_ABBILD = 1.3
FAKTOR_PKG = 1.5

#: Anteil des Gesamtbalkens, den das Entpacken und Einspielen vor dem Abbildbau belegt.
ANTEIL_ENTPACKEN = 35.0

_ID = re.compile(r"^[A-Z]{4}\d{5}$")


@dataclass
class Spiel:
    """Ein Titel mit Basis, Updates und Zusaetzen - oder ein bereits entpackter Ordner."""
    title_id: str
    titel: str = ""
    basis: "bib.PkgEintrag | None" = None
    updates: list = field(default_factory=list)       #: aufsteigend nach Fassung
    zusaetze: list = field(default_factory=list)      #: DLC und Themen
    dump_ordner: str = ""                             #: gesetzt: ein entpacktes Spiel (keine Pakete)
    dump_version: str = ""
    mehrere_basen: bool = False

    @property
    def baubar(self) -> bool:
        return bool(self.dump_ordner) or self.basis is not None

    @property
    def version(self) -> str:
        if self.dump_ordner:
            return self.dump_version or "-"
        if self.updates:
            return self.updates[-1].app_ver or self.updates[-1].version or "-"
        return (self.basis.app_ver or self.basis.version or "-") if self.basis else "-"

    def pakete(self, mit_zusaetzen: bool = False) -> list:
        """Die Pakete in Einspielreihenfolge: Basis, Updates, auf Wunsch DLC."""
        erg = ([self.basis] if self.basis is not None else []) + list(self.updates)
        if mit_zusaetzen:
            erg += list(self.zusaetze)
        return erg

    def groesse(self, mit_zusaetzen: bool = False) -> int:
        return sum(p.groesse for p in self.pakete(mit_zusaetzen))

    @property
    def neuestes_update(self):
        return self.updates[-1] if self.updates else None


def spiele_gruppieren(eintraege) -> list[Spiel]:
    """Ordnet die gelesenen Pakete nach Title-ID: je Titel eine Basis, die Updates nach Fassung, die Zusaetze.

    Unlesbare Pakete und solche ohne gueltige Title-ID zaehlen nicht. Zwei Basispakete desselben Titels
    (zwei Fassungen) ergeben eine Basis - die mit der hoeheren Fassung, bei Gleichstand die groessere - und
    ``mehrere_basen``; zwei Updates gleicher Fassung ergeben eines.
    """
    gruppen: dict[str, Spiel] = {}
    for e in eintraege:
        if not e.lesbar or not _ID.match(e.title_id or ""):
            continue
        s = gruppen.setdefault(e.title_id, Spiel(title_id=e.title_id))
        if e.typ in (bib.TYP_BASIS, bib.TYP_APP):
            if s.basis is not None:
                s.mehrere_basen = True
                neu = (bib.fassung_zahlen(e.app_ver), e.groesse)
                alt = (bib.fassung_zahlen(s.basis.app_ver), s.basis.groesse)
                if neu > alt:
                    s.basis = e
            else:
                s.basis = e
        elif e.typ == bib.TYP_UPDATE:
            if all(bib.fassung_zahlen(u.app_ver) != bib.fassung_zahlen(e.app_ver) for u in s.updates):
                s.updates.append(e)
        elif e.typ == bib.TYP_ZUSATZ:
            if all(z.pfad != e.pfad for z in s.zusaetze):
                s.zusaetze.append(e)
    for s in gruppen.values():
        s.updates.sort(key=lambda u: bib.fassung_zahlen(u.app_ver))
        namensgeber = s.basis or (s.updates[-1] if s.updates else (s.zusaetze[0] if s.zusaetze else None))
        s.titel = (namensgeber.titel if namensgeber else "") or s.title_id
    return sorted(gruppen.values(), key=lambda s: (s.titel.lower(), s.title_id))


def spiel_aus_dump(ordner: str) -> "Spiel | None":
    """Liest ein entpacktes Spiel (``sce_sys/param.sfo`` in der Wurzel oder unter ``app/``); sonst ``None``."""
    for kandidat in (ordner, os.path.join(ordner, "app")):
        sfo = os.path.join(kandidat, "sce_sys", "param.sfo")
        try:
            with open(sfo, "rb") as datei:
                werte = bib.sfo_lesen(datei.read(1024 * 1024))
        except OSError:
            continue
        title_id = str(werte.get("TITLE_ID") or "")
        if _ID.match(title_id):
            titel = str(werte.get("TITLE") or werte.get("TITLE_00") or title_id)
            return Spiel(title_id=title_id, titel=titel, dump_ordner=os.path.abspath(ordner),
                         dump_version=str(werte.get("APP_VER") or ""))
    return None


def zusatz_kennung(e: "bib.PkgEintrag") -> str:
    """Der Ordnername eines DLC im Dumper-Aufbau: die letzten 16 Zeichen der Content-ID (wie PS4 FFPFSC)."""
    kennung = bib.dateiname_bereinigen(e.content_id[-16:]) if len(e.content_id) >= 16 else ""
    return kennung if kennung and kennung != "_" else bib.dateiname_bereinigen(os.path.splitext(e.datei)[0])


def platz_noetig(spiel: Spiel, format_: str, mit_dlc: bool = False) -> "tuple[int, int]":
    """``(Arbeitsordner, Ziel)``: Bytes, die der Lauf auf beiden Datentraegern braucht (grob)."""
    pakete = spiel.groesse(mit_dlc)
    if spiel.dump_ordner:
        return 0, 0
    if format_ == FORMAT_DUMP:
        return 0, int(FAKTOR_DUMP * pakete)
    if format_ == FORMAT_PKG:
        return int(FAKTOR_PKG * pakete), int(1.1 * pakete)
    return int(FAKTOR_DUMP * pakete), int(FAKTOR_ABBILD * pakete)


def _fehler_platz(noetig: int, frei: int) -> au.AufgabeFehler:
    return au.AufgabeFehler("kein_platz", "Es fehlt Platz: %d noetig, %d frei" % (noetig, frei), noetig=noetig,
                            frei=frei, noetig_text=au._mb(noetig), frei_text=au._mb(frei))


def _platz_pruefen(ordner: str, noetig: int) -> None:
    frei = au.freier_platz(ordner)
    if frei >= 0 and noetig > frei:
        raise _fehler_platz(noetig, frei)


class _Nichts:
    """Ein Kontext, der nichts tut (kein Waechter noetig)."""

    def __enter__(self) -> "_Nichts":
        return self

    def __exit__(self, *_) -> None:
        return None


def ordner_groesse(ordner: str) -> int:
    """Summe der Dateigroessen unter ``ordner`` (laeuft auch waehrend dort geschrieben wird)."""
    gesamt = 0
    stapel = [au._lang(ordner)]
    while stapel:
        try:
            with os.scandir(stapel.pop()) as eintraege:
                for e in eintraege:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stapel.append(e.path)
                        else:
                            gesamt += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return gesamt


class _Groessenwaechter:
    """Liest waehrend des Entpackens die Groesse des Zielordners nach.

    OrbisPkgTool meldet nur je **Datei**; ein Spiel hat oft wenige, riesige Dateien (am 07.10.2026 gemessen:
    56 Dateien in einem 5-GB-Paket) - der Balken stand dann minutenlang still. Der Waechter laeuft in einem
    eigenen Faden, fasst nur die Aufgabe an (keine Tk-Teile) und meldet ``(Bytes bisher)``.
    """

    def __init__(self, ordner: str, melden: Callable[[int], None], takt: float = 2.0) -> None:
        import threading
        self._ordner, self._melden, self._takt = ordner, melden, takt
        self._halt = threading.Event()
        self._faden = threading.Thread(target=self._lauf, daemon=True, name="ps4dib-groesse")

    def _lauf(self) -> None:
        while not self._halt.wait(self._takt):
            try:
                self._melden(ordner_groesse(self._ordner))
            except Exception:  # noqa: BLE001 - eine Anzeige darf den Lauf nie stoeren
                logger.debug("Groessenwaechter", exc_info=True)

    def __enter__(self) -> "_Groessenwaechter":
        self._faden.start()
        return self

    def __exit__(self, *_) -> None:
        self._halt.set()
        self._faden.join(2.0)


def _teil_entpacken(a: au.Aufgabe, paket: str, ziel: str, t, von: float, bis: float,
                    passcode: "str | None") -> None:
    """Entpackt ein Paket nach ``ziel`` und ordnet es zum Dump-Ordner; der Balken geht von ``von`` bis ``bis``."""
    a.schreiben(t("ps4ota.log_entpacke", paket=os.path.basename(paket), ziel=ziel))
    a.melden(t("ps4ota.status_lese_inhalt"), von)
    try:
        eintraege = orbispkg.liste(paket, passcode=passcode, abbruch=lambda: a.abbruch_verlangt,
                                   prozess_ablage=a.prozess_ablage)
    except orbispkg.OrbisFehler as fehler:
        a.pruefen_abbruch()
        raise au.AufgabeFehler("paket_unlesbar", str(fehler), grund=str(fehler)) from fehler
    gesamt_bytes = sum(e.groesse for e in eintraege if not e.ist_ordner)
    stand = {"datei": "", "aktuell": 0, "anzahl": 0, "bytes": 0}

    def _zeigen() -> None:
        # Der Balken geht nie zurueck (``max`` unten). Bytes zaehlen genauer als die Dateizahl: Am 07.10.2026
        # stand ein 11-GB-Spiel bei "Datei 33 von 56" erst bei 1,7 GB, weil die grossen Dateien am Ende liegen.
        if gesamt_bytes:
            anteil = min(1.0, stand["bytes"] / gesamt_bytes)
        else:
            anteil = stand["aktuell"] / stand["anzahl"] if stand["anzahl"] else 0.0
        text = t("ps4ota.status_entpacke", aktuell=stand["aktuell"], gesamt=stand["anzahl"], datei=stand["datei"])
        if gesamt_bytes:
            text += "  (%s / %s)" % (au._mb(stand["bytes"]), au._mb(gesamt_bytes))
        a.melden(text, max(a.prozent, von + (bis - von) * 0.9 * anteil))

    def _fortschritt(aktuell: int, anzahl: int, datei: str) -> None:
        stand.update(aktuell=aktuell, anzahl=anzahl, datei=datei)
        _zeigen()

    def _bytes(gelesen: int) -> None:
        stand["bytes"] = gelesen
        if stand["anzahl"]:
            _zeigen()

    with _Groessenwaechter(ziel, _bytes) if gesamt_bytes else _Nichts():
        erg = orbispkg.entpacken(paket, ziel, passcode=passcode, fortschritt=_fortschritt,
                                 abbruch=lambda: a.abbruch_verlangt, prozess_ablage=a.prozess_ablage)
    if erg.abgebrochen or a.abbruch_verlangt:
        raise au.AufgabeAbgebrochen()
    if not erg.ok:
        text = erg.meldung or "; ".join(erg.fehler[:3])
        raise au.AufgabeFehler("werkzeug", text, grund=text)
    a.melden(t("ps4ota.status_ordnen"), von + (bis - von) * 0.92)
    au.dump_ordner_machen(ziel, lambda n: a.melden(t("ps4ota.status_ordnen_n", anzahl=n), von + (bis - von) * 0.95))


def dump_bereitstellen(a: au.Aufgabe, spiel: Spiel, ziel: str, t, *, von: float = 0.0, bis: float = 100.0,
                       passcode: "str | None" = None, mit_dlc: bool = False, dumper_aufbau: bool = False) -> str:
    """Macht aus Basis und Updates (auf Wunsch DLC) einen Dump-Ordner in ``ziel``.

    Es wird nach ``<ziel>.partial`` gearbeitet; erst ein vollstaendiger Lauf bekommt den Namen. Die Updates
    kommen in der Reihenfolge ihrer Fassung darueber: Dateien werden ersetzt, die ``param.sfo`` des Updates
    gewinnt (so macht es auch PS4 FFPFSC beim Zusammenfuehren).

    Args:
        dumper_aufbau: ``True`` legt ``app/`` und ``addcont/<Kennung>/`` an (so liest PS4 FFPFSC DLC aus einem
            Ordner); sonst steht das Spiel flach in der Wurzel.

    Returns:
        ``ziel``.

    Raises:
        AufgabeFehler: ``ohne_basis``, ``ziel_existiert``, ``paket_unlesbar``/``werkzeug``, ``kein_platz``.
    """
    if spiel.basis is None:
        raise au.AufgabeFehler("ohne_basis", "Zu %s liegt kein Basisspiel vor" % spiel.title_id,
                               title_id=spiel.title_id)
    ziel = os.path.abspath(ziel)
    if os.path.exists(ziel):
        raise au.AufgabeFehler("ziel_existiert", "Das Ziel gibt es schon: %s" % ziel, pfad=ziel)
    pakete = spiel.pakete()
    zusaetze = list(spiel.zusaetze) if mit_dlc else []
    teil = ziel + ".partial"
    app = os.path.join(teil, "app") if dumper_aufbau else teil
    aufraeumen = au._aufraeumer(a, t)
    aufraeumen(teil)
    os.makedirs(os.path.dirname(ziel) or ".", exist_ok=True)
    gesamt = max(1, sum(max(1, p.groesse) for p in pakete + zusaetze))
    stand = [von]

    def _abschnitt(p: "bib.PkgEintrag") -> "tuple[float, float]":
        anfang = stand[0]
        stand[0] = anfang + (bis - von) * max(1, p.groesse) / gesamt
        return anfang, stand[0]

    try:
        os.makedirs(app, exist_ok=True)
        a.pruefen_abbruch()
        anfang, ende = _abschnitt(spiel.basis)
        _teil_entpacken(a, spiel.basis.pfad, app, t, anfang, ende, passcode)
        for u in spiel.updates:
            a.pruefen_abbruch()
            zwischen = teil + "_update"
            aufraeumen(zwischen)
            anfang, ende = _abschnitt(u)
            _teil_entpacken(a, u.pfad, zwischen, t, anfang, ende, passcode)
            a.melden(t("ps4dib.status_einspielen", version=u.app_ver or "-"), ende)
            a.schreiben(t("ps4dib.log_einspielen", version=u.app_ver or "-", datei=u.datei))
            au._verschmelzen(zwischen, app,
                             lambda n: a.melden(t("ps4dib.status_einspielen_n", anzahl=n, version=u.app_ver or "-"), ende))
            aufraeumen(zwischen)
        for z in zusaetze:
            a.pruefen_abbruch()
            anfang, ende = _abschnitt(z)
            _teil_entpacken(a, z.pfad, os.path.join(teil, "addcont", zusatz_kennung(z)), t, anfang, ende, passcode)
        os.replace(au._lang(teil), au._lang(ziel))
    except BaseException:
        aufraeumen(teil)
        aufraeumen(teil + "_update")
        raise
    return ziel


def arbeit_dump(a: au.Aufgabe, spiel: Spiel, ziel: str, t, *, passcode: "str | None" = None,
                mit_dlc: bool = False) -> None:
    """Aufgabe „Dump-Ordner“: Basis und Updates entpackt und eingespielt nach ``ziel``."""
    a.schreiben(t("ps4dib.log_dump", titel=spiel.titel, ziel=ziel))
    noetig_arbeit, noetig_ziel = platz_noetig(spiel, FORMAT_DUMP, mit_dlc)
    _platz_pruefen(os.path.dirname(os.path.abspath(ziel)) or ".", noetig_ziel)
    dump_bereitstellen(a, spiel, ziel, t, passcode=passcode, mit_dlc=mit_dlc, dumper_aufbau=mit_dlc and bool(spiel.zusaetze))
    a.ergebnis = ziel
    a.melden(t("ps4dib.status_dump_fertig", ziel=ziel), 100)
    a.schreiben(t("ps4ota.log_entpackt", ziel=ziel))


def arbeit_pkg_zusammen(a: au.Aufgabe, spiel: Spiel, ziel_ordner: str, t, *, pfsc_modus: str = "compressed",
                        arbeiter: int = 1, pruefen_danach: bool = False, passcode: "str | None" = None) -> None:
    """Aufgabe „Paket“: Basis und das neueste Update zu **einem** Paket zusammengefuehrt (OrbisPkgTool ``merge``).

    Das Werkzeug nimmt genau ein Update; PS4-Updates sind kumulativ, das neueste enthaelt also die frueheren.
    """
    if spiel.basis is None:
        raise au.AufgabeFehler("ohne_basis", "Zu %s liegt kein Basisspiel vor" % spiel.title_id, title_id=spiel.title_id)
    neu = spiel.neuestes_update
    if neu is None:
        raise au.AufgabeFehler("ohne_update", "Zu %s liegt kein Update vor" % spiel.title_id, title_id=spiel.title_id)
    name = bib.dateiname_bereinigen("%s [%s] [v%s].pkg" % (spiel.titel, spiel.title_id, neu.app_ver or "update"))
    ausgabe = os.path.join(os.path.abspath(ziel_ordner), name)
    au.arbeit_zusammenfuehren(a, spiel.basis.pfad, neu.pfad, ausgabe, t, pruefen_danach=pruefen_danach,
                              pfsc_modus=pfsc_modus, arbeiter=arbeiter, passcode=passcode,
                              arbeitsordner=os.path.abspath(ziel_ordner))


#: ``lauf(argumente, arbeitsordner=, zeile_callback=, fortschritt_callback=, prozess_ablage=)`` -> ``(rc, text)``.
LaufFunktion = Callable[..., "tuple[int, str]"]


def _quell_argumente(spiel: Spiel, *, mit_dlc: bool, dump: str) -> list[str]:
    if dump:
        return ["--dump-dir", dump]
    return [x for p in spiel.pakete(mit_dlc) for x in ("--pkg-file", p.pfad)]


def arbeit_abbild(a: au.Aufgabe, spiel: Spiel, ziel: str, format_: str, t, *, lauf: LaufFunktion,
                  arbeitsordner: str, stufe: int = 7, worker: int = 1, mit_dlc: bool = False,
                  passcode: "str | None" = None, hinweis_texte: "dict | None" = None,
                  engine_orbis: "bool | None" = None) -> None:
    """Aufgabe „Abbild“: Entpacken und Einspielen mit OrbisPkgTool, dann PS4 FFPFSC (``build --dump-dir``).

    Args:
        lauf: Fuehrt einen PS4-FFPFSC-Befehl aus (siehe ``ps4_werkzeug.lauf``).
        arbeitsordner: Ort fuer Zwischenstaende und das Protokoll des Werkzeugs; je Lauf entsteht darin ein
            eigener Unterordner, der am Ende wieder verschwindet.
        engine_orbis: ``None`` = ``orbispkg.verfuegbar()``. ``False`` erzwingt den bisherigen Weg ueber
            ``--pkg-file`` (Linux, macOS).
    """
    if format_ not in ABBILD_FORMATE:
        raise ValueError("kein Abbildformat: %r" % (format_,))
    if not spiel.baubar:
        raise au.AufgabeFehler("ohne_basis", "Zu %s liegt kein Basisspiel vor" % spiel.title_id, title_id=spiel.title_id)
    ziel = os.path.abspath(ziel)
    os.makedirs(ziel, exist_ok=True)
    arbeitsordner = os.path.abspath(arbeitsordner)
    lauf_ordner = os.path.join(arbeitsordner, "lauf_%d" % a.kennung)
    # Die Quelle liegt NEBEN dem Arbeitsordner des Werkzeugs, nicht darin: PS4 FFPFSC lehnt einen Dump-Ordner ab,
    # der sich mit seinem Arbeits- oder Entpackordner ueberschneidet.
    quell_ordner = os.path.join(arbeitsordner, "quelle_%d" % a.kennung)
    mit_orbis = orbispkg.verfuegbar() if engine_orbis is None else engine_orbis
    aufraeumen = au._aufraeumer(a, t)
    noetig_arbeit, noetig_ziel = platz_noetig(spiel, format_, mit_dlc)
    if mit_orbis and not spiel.dump_ordner:
        _platz_pruefen(arbeitsordner, noetig_arbeit)
    _platz_pruefen(ziel, noetig_ziel)
    dump = ""
    anteil = 0.0
    a.schreiben(t("ps4dib.log_abbild", titel=spiel.titel, ziel=ziel, format=format_))
    try:
        os.makedirs(lauf_ordner, exist_ok=True)
        if spiel.dump_ordner:
            dump = spiel.dump_ordner
        elif mit_orbis:
            anteil = ANTEIL_ENTPACKEN
            dumper = mit_dlc and bool(spiel.zusaetze)
            wurzel = dump_bereitstellen(a, spiel, os.path.join(quell_ordner, spiel.title_id), t,
                                        von=0.0, bis=anteil, passcode=passcode, mit_dlc=mit_dlc,
                                        dumper_aufbau=dumper)
            dump = wurzel
        a.pruefen_abbruch()
        befehl = ["build", spiel.title_id, *_quell_argumente(spiel, mit_dlc=mit_dlc, dump=dump),
                  "--output-dir", ziel, "--work-dir", lauf_ordner,
                  "--unpacked-dir", os.path.join(lauf_ordner, "unpacked"),
                  "--output-format", format_, "--compression-level", str(int(stufe)),
                  "--compression-workers", str(int(worker)),
                  "--dlc-mode", "single-experimental" if mit_dlc else "off",
                  "--verbose", "--console-log"]
        if dump and not spiel.dump_ordner:
            # Der Ordner ist unser Wegwerf-Bestand: verschieben statt kopieren (auf exFAT sonst ein zweites Mal
            # der ganze Spielordner - siehe PS4FFPFSC-0.2.9/UPSTREAM.md, "--consume-dump").
            befehl.append("--consume-dump")
        fp = ps4_fortschritt.Gesamtfortschritt()
        letzte: list[str] = []

        def _zeile(text: str) -> None:
            sauber = str(text).rstrip("\n")
            if not sauber.strip():
                return
            letzte.append(sauber)
            del letzte[:-20]
            a.schreiben(sauber)
            if fp.zeile(sauber):
                _melden()

        def _melden() -> None:
            s = fp.stand()
            a.melden(t("ps4dib.status_abbild", stufe=max(1, s.stufe), stufen=s.stufen_gesamt),
                     anteil + (100.0 - anteil) * min(99.0, s.prozent) / 100.0)

        def _ereignis(daten: dict) -> None:
            fp.ereignis(daten)
            _melden()

        a.melden(t("ps4dib.status_abbild", stufe=1, stufen=5), anteil)
        rc, _ausgabe = lauf(befehl, arbeitsordner=arbeitsordner, zeile_callback=_zeile,
                            fortschritt_callback=_ereignis, prozess_ablage=a.prozess_ablage)
        if a.abbruch_verlangt:
            raise au.AufgabeAbgebrochen()
        if rc != 0:
            text = "; ".join(letzte[-3:]) or ("Rueckgabewert %d" % rc)
            raise au.AufgabeFehler("abbild", text, code=rc, grund=text)
    finally:
        for ordner in (lauf_ordner, quell_ordner):
            if os.path.isdir(ordner):
                aufraeumen(ordner)
    a.melden(t("ps4dib.status_pruefe_abbild"), 99.0)
    abbild = ps4_werkzeug.ergebnis_finden(ziel, spiel.title_id, format_)
    if not abbild:
        a.schreiben(t("ps4pkg.check_no_image"))
        a.ergebnis = ziel
        a.melden(t("ps4pkg.status_done", path=ziel), 100)
        return
    a.ergebnis = abbild
    befund = ps4_werkzeug.abbild_pruefen(abbild, texte=hinweis_texte)
    if befund.get("fehler"):
        a.schreiben(t("ps4pkg.check_failed", error=befund["fehler"]))
    else:
        a.schreiben(t("ps4pkg.check_files", count=befund["dateien"]))
        if befund.get("ps4"):
            a.schreiben(t("ps4pkg.check_ps4_title"))
            a.schreiben(t("ps4pkg.check_trophy_note"))
        else:
            for fehlt in befund.get("fehlend", []):
                a.schreiben(t("ps4pkg.check_missing", file=fehlt))
            if not befund.get("fehlend"):
                a.schreiben(t("ps4pkg.check_complete"))
    a.melden(t("ps4pkg.status_done", path=ziel), 100)
