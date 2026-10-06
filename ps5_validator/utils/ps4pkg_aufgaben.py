# -*- coding: utf-8 -*-
"""Die Aufgabenliste von „PS4 PKG -> OTA“ und die Arbeiten, die sie abarbeitet.

Zwei Teile:

* :class:`Warteschlange` - eine Liste von Aufgaben, die nacheinander in
  **einem** Arbeitsfaden laufen (Entpacken, Zusammenfuehren, Neupacken,
  Pruefen, Bauen, Update laden, Senden). Sie kennt kein Fenster und keine
  Tk-Variablen: Das Fenster liest :meth:`Warteschlange.schnappschuss` im
  Takt des Hauptfadens (dieselbe Regel wie in ``project_tk_faden_variablen``:
  Tk-Variablen nie aus dem Faden).
* Die ``arbeit_*``-Funktionen - je eine fuer eine Art Aufgabe. Sie rufen
  ``orbispkg`` (das Werkzeug), ``ps4pkg_ota`` (Netz) und ``ps4pkg_updates``
  und melden ueber die Aufgabe, wie weit sie sind.

Was der Anwender liest, kommt ueber ``t(schluessel, **werte)`` herein - das
Modul bindet ``i18n`` nicht ein.
"""
from __future__ import annotations

import itertools
import logging
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ps5_validator.utils import orbispkg, ps4pkg_ota, ps4pkg_updates
from ps5_validator.utils.ps4pkg_bibliothek import PkgEintrag, TYP_UPDATE, TYP_ZUSATZ, dateiname_bereinigen

logger = logging.getLogger("PS5Converter.ps4pkg_aufgaben")

#: Zustaende einer Aufgabe.
WARTET = "wartet"
LAEUFT = "laeuft"
FERTIG = "fertig"
FEHLER = "fehler"
ABGEBROCHEN = "abgebrochen"
ENDZUSTAENDE = (FERTIG, FEHLER, ABGEBROCHEN)


class AufgabeFehler(Exception):
    """Eine Aufgabe ist gescheitert. ``schluessel`` ist ein ``ps4ota.fehler_*``-Schluessel
    (ohne Vorsatz), ``werte`` die Platzhalter dazu; ``text`` ein Klartext fuer das Protokoll."""

    def __init__(self, schluessel: str, text: str = "", **werte) -> None:
        super().__init__(text or schluessel)
        self.schluessel = schluessel
        self.werte = werte
        self.text = text


class AufgabeAbgebrochen(Exception):
    """Der Anwender hat die Aufgabe abgebrochen."""


@dataclass
class Aufgabe:
    """Eine Aufgabe der Liste."""
    kennung: int
    art: str
    titel: str
    quelle: str = ""
    ziel: str = ""
    arbeit: "Callable[[Aufgabe], None] | None" = field(default=None, repr=False)
    status: str = WARTET
    prozent: float = 0.0
    text: str = ""
    ergebnis: str = ""
    fehler: str = ""
    beginn: float = 0.0
    ende: float = 0.0
    protokoll: list[str] = field(default_factory=list)
    abbruch: threading.Event = field(default_factory=threading.Event, repr=False)
    prozess_ablage: dict = field(default_factory=dict, repr=False)

    @property
    def abbruch_verlangt(self) -> bool:
        return self.abbruch.is_set()

    def melden(self, text: str, prozent: "float | None" = None) -> None:
        """Setzt Statustext und (wenn angegeben) Fortschritt."""
        self.text = text
        if prozent is not None:
            self.prozent = max(0.0, min(100.0, float(prozent)))

    def schreiben(self, zeile: str) -> None:
        """Haengt eine Zeile an das Protokoll der Aufgabe."""
        self.protokoll.append(zeile)
        del self.protokoll[:-500]

    def pruefen_abbruch(self) -> None:
        if self.abbruch.is_set():
            raise AufgabeAbgebrochen()

    def kopie(self) -> "Aufgabe":
        """Eine Momentaufnahme fuer das Fenster (ohne Faden-Objekte)."""
        return Aufgabe(kennung=self.kennung, art=self.art, titel=self.titel, quelle=self.quelle,
                       ziel=self.ziel, status=self.status, prozent=self.prozent, text=self.text,
                       ergebnis=self.ergebnis, fehler=self.fehler, beginn=self.beginn, ende=self.ende,
                       protokoll=list(self.protokoll))


class Warteschlange:
    """Arbeitet Aufgaben nacheinander in einem Faden ab.

    Args:
        bei_aenderung: Wird nach jeder Aenderung (neue Aufgabe, Zustandswechsel)
            aus irgendeinem Faden gerufen - das Fenster setzt damit nur ein
            Merkzeichen und liest im Takt.
        automatisch: ``True`` startet neue Aufgaben von selbst; sonst nur auf
            :meth:`naechste_starten`.
    """

    def __init__(self, bei_aenderung: "Callable[[], None] | None" = None,
                 automatisch: bool = True,
                 uebersetzer: "Callable[..., str] | None" = None) -> None:
        self.bei_aenderung = bei_aenderung
        self.automatisch = automatisch
        #: ``t(schluessel, **werte)``: Damit werden die Fehlergruende einer Aufgabe
        #: (``ps4ota.fehler_<schluessel>``) in der Sprache des Fensters gemeldet.
        self.uebersetzer = uebersetzer
        self._aufgaben: list[Aufgabe] = []
        self._zaehler = itertools.count(1)
        self._schloss = threading.RLock()
        self._faden: "threading.Thread | None" = None
        self._einmal = False

    # -- Pflege ----------------------------------------------------------
    def _geaendert(self) -> None:
        if self.bei_aenderung is not None:
            try:
                self.bei_aenderung()
            except Exception:  # noqa: BLE001
                logger.exception("bei_aenderung gescheitert")

    def hinzufuegen(self, art: str, titel: str, arbeit: "Callable[[Aufgabe], None]", *,
                    quelle: str = "", ziel: str = "") -> Aufgabe:
        aufgabe = Aufgabe(kennung=next(self._zaehler), art=art, titel=titel, quelle=quelle,
                          ziel=ziel, arbeit=arbeit)
        with self._schloss:
            self._aufgaben.append(aufgabe)
        self._geaendert()
        if self.automatisch:
            self.starten()
        return aufgabe

    def schnappschuss(self) -> list[Aufgabe]:
        with self._schloss:
            return [a.kopie() for a in self._aufgaben]

    def aufgabe(self, kennung: int) -> "Aufgabe | None":
        with self._schloss:
            return next((a for a in self._aufgaben if a.kennung == kennung), None)

    @property
    def beschaeftigt(self) -> bool:
        with self._schloss:
            return any(a.status == LAEUFT for a in self._aufgaben)

    @property
    def offen(self) -> int:
        """Wartende und laufende Aufgaben."""
        with self._schloss:
            return sum(1 for a in self._aufgaben if a.status in (WARTET, LAEUFT))

    def abbrechen(self, kennung: int) -> bool:
        """Bricht eine Aufgabe ab: eine wartende wird sofort gestrichen, eine laufende beendet."""
        with self._schloss:
            a = next((x for x in self._aufgaben if x.kennung == kennung), None)
            if a is None or a.status in ENDZUSTAENDE:
                return False
            a.abbruch.set()
            if a.status == WARTET:
                a.status = ABGEBROCHEN
                a.ende = time.time()
            else:
                prozess = a.prozess_ablage.get("prozess")
                if prozess is not None:
                    try:
                        prozess.terminate()
                    except OSError:
                        pass
        self._geaendert()
        return True

    def alle_abbrechen(self) -> None:
        for a in self.schnappschuss():
            self.abbrechen(a.kennung)

    def entfernen(self, kennung: int) -> bool:
        """Nimmt eine Aufgabe aus der Liste - nicht, solange sie laeuft."""
        with self._schloss:
            a = next((x for x in self._aufgaben if x.kennung == kennung), None)
            if a is None or a.status == LAEUFT:
                return False
            self._aufgaben.remove(a)
        self._geaendert()
        return True

    def erledigte_leeren(self) -> int:
        with self._schloss:
            vorher = len(self._aufgaben)
            self._aufgaben = [a for a in self._aufgaben if a.status not in ENDZUSTAENDE]
            n = vorher - len(self._aufgaben)
        if n:
            self._geaendert()
        return n

    def wiederholen(self, kennung: int) -> "Aufgabe | None":
        """Stellt eine gescheiterte oder abgebrochene Aufgabe wieder hinten an."""
        with self._schloss:
            a = next((x for x in self._aufgaben if x.kennung == kennung), None)
            if a is None or a.status not in (FEHLER, ABGEBROCHEN) or a.arbeit is None:
                return None
            neu = Aufgabe(kennung=next(self._zaehler), art=a.art, titel=a.titel, quelle=a.quelle,
                          ziel=a.ziel, arbeit=a.arbeit)
            self._aufgaben.append(neu)
        self._geaendert()
        if self.automatisch:
            self.starten()
        return neu

    def _fehlertext(self, fehler: "AufgabeFehler") -> str:
        """Der Fehlergrund in der Sprache des Fensters - sonst der Klartext der Arbeit.

        Ein unbekannter Schluessel kommt von ``translate`` unveraendert zurueck;
        dann gilt der Klartext.
        """
        if self.uebersetzer is not None:
            schluessel = "ps4ota.fehler_" + fehler.schluessel
            try:
                text = self.uebersetzer(schluessel, **fehler.werte)
            except Exception:  # noqa: BLE001
                text = schluessel
            if text and text != schluessel:
                return text
        return fehler.text or fehler.schluessel

    # -- Abarbeiten ------------------------------------------------------
    def starten(self) -> None:
        """Startet den Arbeitsfaden, falls er nicht schon laeuft und etwas wartet."""
        with self._schloss:
            if self._faden is not None and self._faden.is_alive():
                return
            if not any(a.status == WARTET for a in self._aufgaben):
                return
            self._faden = threading.Thread(target=self._abarbeiten, name="ps4ota-aufgaben", daemon=True)
            self._faden.start()

    def naechste_starten(self) -> None:
        """Bei ``automatisch=False``: Die naechste wartende Aufgabe laufen lassen."""
        self._einmal = True
        self.starten()

    def _naechste(self) -> "Aufgabe | None":
        with self._schloss:
            return next((a for a in self._aufgaben if a.status == WARTET), None)

    def _abarbeiten(self) -> None:
        while True:
            a = self._naechste()
            if a is None:
                return
            if not self.automatisch and not self._einmal:
                return
            self._einmal = False
            with self._schloss:
                a.status = LAEUFT
                a.beginn = time.time()
            self._geaendert()
            try:
                a.pruefen_abbruch()
                if a.arbeit is None:
                    raise AufgabeFehler("ohne_arbeit", "Aufgabe ohne Arbeit")
                a.arbeit(a)
                a.status = FERTIG
                a.prozent = 100.0
            except AufgabeAbgebrochen:
                a.status = ABGEBROCHEN
            except AufgabeFehler as fehler:
                a.status = FEHLER
                a.fehler = self._fehlertext(fehler)
                a.schreiben(a.fehler)
            except orbispkg.OrbisFehler as fehler:
                a.status = FEHLER
                a.fehler = str(fehler)
                a.schreiben(a.fehler)
            except Exception as fehler:  # noqa: BLE001
                logger.exception("Aufgabe %s gescheitert", a.titel)
                a.status = FEHLER
                a.fehler = "%s: %s" % (type(fehler).__name__, fehler)
                a.schreiben(a.fehler)
            finally:
                a.ende = time.time()
                a.prozess_ablage.clear()
            self._geaendert()


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _lang(pfad: str) -> str:
    """Windows: ``\\\\?\\``-Schreibweise fuer lange Pfade - sonst unveraendert."""
    if sys.platform != "win32":
        return pfad
    pfad = os.path.abspath(pfad)
    if len(pfad) < 240 or pfad.startswith("\\\\?\\"):
        return pfad
    if pfad.startswith("\\\\"):
        return "\\\\?\\UNC\\" + pfad[2:]
    return "\\\\?\\" + pfad


def freier_platz(ordner: str) -> int:
    """Freie Bytes auf dem Datentraeger von ``ordner`` (der Ordner darf noch fehlen); ``-1`` unbekannt."""
    pfad = os.path.abspath(ordner)
    while pfad and not os.path.exists(pfad):
        eltern = os.path.dirname(pfad)
        if eltern == pfad:
            break
        pfad = eltern
    try:
        return shutil.disk_usage(pfad).free
    except OSError:
        return -1


def zielordner_name(e: PkgEintrag) -> str:
    """Der Ordnername fuer ein entpacktes Paket: ``CUSA00775``, ``CUSA16627_patch_01.02``, ``CUSA16627_dlc_<Label>``."""
    title_id = dateiname_bereinigen(e.title_id) if e.title_id else ""
    if not title_id or title_id == "_":
        return dateiname_bereinigen(os.path.splitext(e.datei)[0]) or "pkg"
    if e.typ == TYP_UPDATE:
        version = dateiname_bereinigen(e.app_ver or e.version)
        return "%s_patch_%s" % (title_id, version) if version and version != "_" else title_id + "_patch"
    if e.typ == TYP_ZUSATZ:
        label = dateiname_bereinigen(e.content_id[-16:]) if len(e.content_id) >= 16 else ""
        return "%s_dlc_%s" % (title_id, label) if label and label != "_" else title_id + "_dlc"
    return title_id


#: Nach so vielen verschobenen Dateien meldet sich :func:`_verschmelzen` wieder.
ORDNEN_SCHRITT = 250


def _verschmelzen(quelle: str, ziel: str, melden: "Callable[[int], None] | None" = None) -> int:
    """Verschiebt den Inhalt von ``quelle`` nach ``ziel`` - bestehende Dateien werden ersetzt.

    Ein Spiel hat tausende Dateien; deshalb meldet sich die Funktion alle
    :data:`ORDNEN_SCHRITT` Dateien (``melden(bisher)``), statt still zu bleiben.

    Returns:
        Die Zahl der verschobenen Dateien.
    """
    zaehler = [0, 0]                    # verschoben, bisher gemeldet

    def melden_zaehlen(n: int) -> None:
        zaehler[0] += n
        if melden is not None and zaehler[0] - zaehler[1] >= ORDNEN_SCHRITT:
            zaehler[1] = zaehler[0]
            melden(zaehler[0])

    def lauf(q: str, z: str) -> None:
        os.makedirs(_lang(z), exist_ok=True)
        for name in os.listdir(_lang(q)):
            von = os.path.join(q, name)
            nach = os.path.join(z, name)
            if os.path.isdir(_lang(von)) and not os.path.islink(_lang(von)):
                if os.path.isdir(_lang(nach)):
                    lauf(von, nach)
                    try:
                        os.rmdir(_lang(von))
                    except OSError:
                        pass
                else:
                    if os.path.exists(_lang(nach)):
                        os.remove(_lang(nach))
                    os.replace(_lang(von), _lang(nach))
                    melden_zaehlen(sum(len(f) for _, _, f in os.walk(_lang(nach))))
            else:
                os.replace(_lang(von), _lang(nach))
                melden_zaehlen(1)

    lauf(quelle, ziel)
    return zaehler[0]


def dump_ordner_machen(roh: str, melden: "Callable[[int], None] | None" = None) -> dict:
    """Macht aus ``Image0/`` und ``Sc0/`` einen Dump-Ordner: Spieldateien in die Wurzel, Systemdateien nach ``sce_sys/``.

    So sieht ein entpacktes PS4-Spiel ueberall aus - auch das Ergebnis von
    „PS4 PKG -> Dump Ordner“. Die ``Sc0``-Dateien ersetzen gleichnamige in
    ``sce_sys`` (so macht es auch das Zusammenfuehren des Werkzeugs).

    Args:
        melden: ``(bisher)`` - wie viele Dateien schon umgeordnet sind (siehe :func:`_verschmelzen`).

    Returns:
        ``{"dateien": n, "systemdateien": m}``.

    Raises:
        AufgabeFehler: ``ohne_image0`` - das Paket brachte keine Spieldateien.
    """
    image0 = os.path.join(roh, "Image0")
    sc0 = os.path.join(roh, "Sc0")
    if not os.path.isdir(_lang(image0)):
        raise AufgabeFehler("ohne_image0", "Image0 fehlt im entpackten Paket")
    erg = {"dateien": 0, "systemdateien": 0}
    erg["dateien"] = _verschmelzen(image0, roh, melden)
    try:
        os.rmdir(_lang(image0))
    except OSError:
        pass
    if os.path.isdir(_lang(sc0)):
        erg["systemdateien"] = _verschmelzen(sc0, os.path.join(roh, "sce_sys"), melden)
        try:
            os.rmdir(_lang(sc0))
        except OSError:
            pass
    return erg


def _aufraeumen(ordner: str, melden: "Callable[[], None] | None" = None) -> None:
    """Loescht einen Arbeitsordner. Je nach Groesse dauert das; ``melden`` sagt vorher Bescheid."""
    if melden is not None and os.path.isdir(_lang(ordner)):
        melden()
    shutil.rmtree(_lang(ordner), ignore_errors=True)


# ---------------------------------------------------------------------------
# Die Arbeiten
# ---------------------------------------------------------------------------

Uebersetzer = Callable[..., str]


def _aufraeumer(a: "Aufgabe", t: Uebersetzer) -> Callable[[str], None]:
    """Ein ``_aufraeumen``, das vorher in den Status der Aufgabe schreibt, dass aufgeraeumt wird."""
    def weg(ordner: str) -> None:
        _aufraeumen(ordner, lambda: a.melden(t("ps4ota.status_raeume_auf")))
    return weg


def arbeit_entpacken(a: Aufgabe, paket: str, ziel: str, t: Uebersetzer, *, dump_form: bool = True,
                     passcode: "str | None" = None) -> None:
    """Entpackt ein Paket nach ``ziel``.

    Es wird erst nach ``<ziel>.partial`` entpackt; erst ein vollstaendiger
    Lauf bekommt den richtigen Namen (wie ``pkg_entpacken``). Mit
    ``dump_form`` entsteht ein Dump-Ordner, sonst bleiben ``Image0``/``Sc0``.
    """
    ziel = os.path.abspath(ziel)
    if os.path.exists(ziel):
        raise AufgabeFehler("ziel_existiert", "Das Ziel gibt es schon: %s" % ziel, pfad=ziel)
    teil = ziel + ".partial"
    aufraeumen = _aufraeumer(a, t)
    aufraeumen(teil)
    os.makedirs(os.path.dirname(ziel) or ".", exist_ok=True)
    a.melden(t("ps4ota.status_lese_inhalt"), 0)
    try:
        eintraege = orbispkg.liste(paket, passcode=passcode, abbruch=lambda: a.abbruch_verlangt,
                                   prozess_ablage=a.prozess_ablage)
    except orbispkg.OrbisFehler as fehler:
        a.pruefen_abbruch()
        raise AufgabeFehler("paket_unlesbar", str(fehler), grund=str(fehler)) from fehler
    gesamt = sum(e.groesse for e in eintraege if not e.ist_ordner)
    frei = freier_platz(os.path.dirname(ziel) or ".")
    if frei >= 0 and gesamt > frei:
        raise AufgabeFehler("kein_platz", "Es fehlen Platz: %d noetig, %d frei" % (gesamt, frei),
                            noetig=gesamt, frei=frei, noetig_text=_mb(gesamt), frei_text=_mb(frei))
    a.schreiben(t("ps4ota.log_entpacke", paket=os.path.basename(paket), ziel=ziel))

    def _fortschritt(aktuell: int, anzahl: int, datei: str) -> None:
        a.melden(t("ps4ota.status_entpacke", aktuell=aktuell, gesamt=anzahl, datei=datei),
                 85.0 * aktuell / anzahl if anzahl else 0.0)

    erg = orbispkg.entpacken(paket, teil, passcode=passcode, fortschritt=_fortschritt,
                             abbruch=lambda: a.abbruch_verlangt, prozess_ablage=a.prozess_ablage)
    if erg.abgebrochen or a.abbruch_verlangt:
        aufraeumen(teil)
        raise AufgabeAbgebrochen()
    if not erg.ok:
        aufraeumen(teil)
        text = erg.meldung or "; ".join(erg.fehler[:3])
        raise AufgabeFehler("werkzeug", text, grund=text)
    if dump_form:
        a.melden(t("ps4ota.status_ordnen"), 90)
        try:
            dump_ordner_machen(teil, lambda n: a.melden(t("ps4ota.status_ordnen_n", anzahl=n), 90))
        except AufgabeFehler:
            aufraeumen(teil)
            raise
    os.replace(_lang(teil), _lang(ziel))
    a.ergebnis = ziel
    a.melden(t("ps4ota.status_entpackt", dateien=erg.dateien_ok), 100)
    a.schreiben(t("ps4ota.log_entpackt", ziel=ziel))


def arbeit_zusammenfuehren(a: Aufgabe, basis: str, update: str, ausgabe: str, t: Uebersetzer, *,
                           pruefen_danach: bool = False, pfsc_modus: str = "compressed",
                           arbeiter: int = 1, passcode: "str | None" = None,
                           arbeitsordner: str = "") -> None:
    """Fuehrt Basisspiel und Update zu einem Paket zusammen (``merge``)."""
    ausgabe = os.path.abspath(ausgabe)
    if os.path.exists(ausgabe):
        raise AufgabeFehler("ziel_existiert", "Das Ziel gibt es schon: %s" % ausgabe, pfad=ausgabe)
    os.makedirs(os.path.dirname(ausgabe) or ".", exist_ok=True)
    # Ein **eigener** Unterordner, auch wenn der Anwender einen Arbeitsordner nennt: Aufgeraeumt
    # wird nur, was dieses Modul angelegt hat - nie der Ordner des Anwenders.
    arbeit = os.path.join(arbeitsordner or os.path.dirname(ausgabe), ".ps4ota_arbeit_%d" % a.kennung)
    noetig = int(1.5 * (os.path.getsize(basis) + os.path.getsize(update)))
    frei = freier_platz(arbeit)
    if frei >= 0 and noetig > frei:
        raise AufgabeFehler("kein_platz", "Es fehlt Platz: %d noetig, %d frei" % (noetig, frei),
                            noetig=noetig, frei=frei, noetig_text=_mb(noetig), frei_text=_mb(frei))
    a.schreiben(t("ps4ota.log_zusammenfuehren", basis=os.path.basename(basis),
                  update=os.path.basename(update), ziel=ausgabe))
    a.melden(t("ps4ota.status_zusammenfuehren"), 1)

    def _fortschritt(text: str, prozent: "int | None") -> None:
        a.melden(text, None if prozent is None else prozent)

    try:
        erg = orbispkg.zusammenfuehren(
            basis, update, ausgabe, passcode=passcode, pruefen_danach=pruefen_danach,
            pfsc_modus=pfsc_modus, arbeiter=arbeiter, arbeitsordner=arbeit,
            fortschritt=_fortschritt, abbruch=lambda: a.abbruch_verlangt,
            prozess_ablage=a.prozess_ablage)
    finally:
        # Das Werkzeug raeumt nach Erfolg selbst auf; nach Fehler oder Abbruch bleibt der Ordner liegen.
        if os.path.isdir(arbeit):
            _aufraeumer(a, t)(arbeit)
    if erg.abgebrochen or a.abbruch_verlangt:
        if os.path.isfile(ausgabe):
            os.remove(ausgabe)
        raise AufgabeAbgebrochen()
    if not erg.ok:
        raise AufgabeFehler("werkzeug", erg.meldung, grund=erg.meldung)
    a.ergebnis = ausgabe
    a.melden(t("ps4ota.status_zusammengefuehrt"), 100)
    a.schreiben(t("ps4ota.log_zusammengefuehrt", ziel=ausgabe))


def arbeit_neu_packen(a: Aufgabe, paket: str, ausgabe: str, t: Uebersetzer, *,
                      pruefen_danach: bool = False, pfsc_modus: str = "compressed",
                      arbeiter: int = 1, passcode: "str | None" = None) -> None:
    """Entpackt ein Paket und baut es neu (``repack``)."""
    ausgabe = os.path.abspath(ausgabe)
    if os.path.exists(ausgabe):
        raise AufgabeFehler("ziel_existiert", "Das Ziel gibt es schon: %s" % ausgabe, pfad=ausgabe)
    os.makedirs(os.path.dirname(ausgabe) or ".", exist_ok=True)
    arbeit = os.path.join(os.path.dirname(ausgabe), ".ps4ota_arbeit_%d" % a.kennung)
    noetig = int(2.0 * os.path.getsize(paket))
    frei = freier_platz(arbeit)
    if frei >= 0 and noetig > frei:
        raise AufgabeFehler("kein_platz", "Es fehlt Platz: %d noetig, %d frei" % (noetig, frei),
                            noetig=noetig, frei=frei, noetig_text=_mb(noetig), frei_text=_mb(frei))
    a.melden(t("ps4ota.status_neu_packen"), 1)
    a.schreiben(t("ps4ota.log_neu_packen", paket=os.path.basename(paket), ziel=ausgabe))
    try:
        erg = orbispkg.neu_packen(
            paket, ausgabe, passcode=passcode, pruefen_danach=pruefen_danach, pfsc_modus=pfsc_modus,
            arbeiter=arbeiter, arbeitsordner=arbeit,
            fortschritt=lambda text, prozent: a.melden(text, prozent),
            abbruch=lambda: a.abbruch_verlangt, prozess_ablage=a.prozess_ablage)
    finally:
        if os.path.isdir(arbeit):
            _aufraeumer(a, t)(arbeit)
    if erg.abgebrochen or a.abbruch_verlangt:
        if os.path.isfile(ausgabe):
            os.remove(ausgabe)
        raise AufgabeAbgebrochen()
    if not erg.ok:
        raise AufgabeFehler("werkzeug", erg.meldung, grund=erg.meldung)
    a.ergebnis = ausgabe
    a.melden(t("ps4ota.status_neu_gepackt"), 100)


def arbeit_pruefen(a: Aufgabe, paket: str, t: Uebersetzer, *, tief: bool = False,
                   passcode: "str | None" = None) -> None:
    """Prueft ein Paket: Pruefsummen und Signaturen (``verify``), auf Wunsch die achtstufige Pruefung."""
    a.melden(t("ps4ota.status_pruefe"), 5)
    ok, text = orbispkg.pruefen(paket, passcode=passcode, abbruch=lambda: a.abbruch_verlangt,
                                prozess_ablage=a.prozess_ablage)
    a.pruefen_abbruch()
    a.schreiben(text)
    if not ok:
        raise AufgabeFehler("pruefung", text, grund=text)
    if tief:
        a.melden(t("ps4ota.status_tiefpruefung"), 40)
        erg = orbispkg.tiefenpruefung(paket, passcode=passcode, fake_tolerant=True,
                                      abbruch=lambda: a.abbruch_verlangt,
                                      prozess_ablage=a.prozess_ablage)
        a.pruefen_abbruch()
        for stufe in erg.stufen:
            a.schreiben(stufe)
        if not erg.bestanden:
            a.schreiben(t("ps4ota.log_tiefpruefung_hinweis"))
            raise AufgabeFehler("tiefpruefung", erg.grund, grund=erg.grund)
    a.ergebnis = paket
    a.melden(t("ps4ota.status_pruefung_ok"), 100)


def arbeit_bauen(a: Aufgabe, ordner: str, ausgabe: str, t: Uebersetzer, *, patch: bool = False,
                 pruefen_danach: bool = False, pfsc_modus: str = "compressed", arbeiter: int = 1,
                 passcode: "str | None" = None) -> None:
    """Baut aus einem Dump-Ordner (``sce_sys/param.sfo`` und ``eboot.bin`` in der Wurzel) ein Fake-Paket."""
    ausgabe = os.path.abspath(ausgabe)
    if os.path.exists(ausgabe):
        raise AufgabeFehler("ziel_existiert", "Das Ziel gibt es schon: %s" % ausgabe, pfad=ausgabe)
    if not os.path.isfile(os.path.join(ordner, "sce_sys", "param.sfo")):
        raise AufgabeFehler("ohne_param_sfo", "sce_sys/param.sfo fehlt", pfad=ordner)
    os.makedirs(os.path.dirname(ausgabe) or ".", exist_ok=True)
    arbeit = os.path.join(os.path.dirname(ausgabe), ".ps4ota_arbeit_%d" % a.kennung)
    os.makedirs(arbeit, exist_ok=True)
    try:
        a.melden(t("ps4ota.status_projekt"), 2)
        gp4 = os.path.join(arbeit, "projekt.gp4")
        lauf = orbispkg.projekt_erzeugen(ordner, gp4, patch=patch, abbruch=lambda: a.abbruch_verlangt,
                                         prozess_ablage=a.prozess_ablage)
        a.pruefen_abbruch()
        if lauf.rueckgabe != 0 or not os.path.isfile(gp4):
            raise AufgabeFehler("werkzeug", lauf.letzte_fehlerzeile, grund=lauf.letzte_fehlerzeile)
        a.melden(t("ps4ota.status_baue"), 5)
        erg = orbispkg.bauen(gp4, ordner, ausgabe, passcode=passcode, pruefen_danach=pruefen_danach,
                             pfsc_modus=pfsc_modus, arbeiter=arbeiter,
                             fortschritt=lambda text, prozent: a.melden(text, prozent),
                             abbruch=lambda: a.abbruch_verlangt, prozess_ablage=a.prozess_ablage)
    finally:
        _aufraeumer(a, t)(arbeit)
    if erg.abgebrochen or a.abbruch_verlangt:
        if os.path.isfile(ausgabe):
            os.remove(ausgabe)
        raise AufgabeAbgebrochen()
    if not erg.ok:
        if os.path.isfile(ausgabe):
            os.remove(ausgabe)
        raise AufgabeFehler("werkzeug", erg.meldung, grund=erg.meldung)
    a.ergebnis = ausgabe
    a.melden(t("ps4ota.status_gebaut"), 100)


def arbeit_update_laden(a: Aufgabe, info: "ps4pkg_updates.UpdateInfo", ordner: str, t: Uebersetzer) -> None:
    """Laedt ein offizielles Update (alle Teile, mit Pruefsumme) in ``ordner``."""
    a.melden(t("ps4ota.status_lade_update", version=info.version), 0)

    def _fortschritt(geladen: int, gesamt: int) -> None:
        a.melden(t("ps4ota.status_lade_update_fortschritt", version=info.version,
                   geladen=_mb(geladen), gesamt=_mb(gesamt)),
                 100.0 * geladen / gesamt if gesamt else 0.0)

    try:
        pfad = ps4pkg_updates.herunterladen(info, ordner, fortschritt=_fortschritt,
                                            abbruch=lambda: a.abbruch_verlangt)
    except ps4pkg_updates.UpdateFehler as fehler:
        if fehler.schluessel == "abgebrochen":
            raise AufgabeAbgebrochen() from fehler
        raise AufgabeFehler("update_" + fehler.schluessel, fehler.text, grund=fehler.text) from fehler
    a.ergebnis = pfad
    a.melden(t("ps4ota.status_update_geladen"), 100)


def _mb(n: int) -> str:
    return "%.1f MB" % (n / (1024.0 * 1024.0))


def _ota_fehler(fehler: ps4pkg_ota.OtaFehler) -> AufgabeFehler:
    return AufgabeFehler("ota_" + fehler.schluessel, fehler.text or fehler.schluessel, grund=fehler.text)


def arbeit_ota_dpi(a: Aufgabe, paket: str, ip: str, api_port: int, t: Uebersetzer, *,
                   web_port: int = 0) -> None:
    """Schickt ein Paket an den OnionHEN-Paketmanager und wartet, bis er fertig ist."""
    a.melden(t("ps4ota.status_ota_verbinde", ip=ip), 0)
    client = ps4pkg_ota.DpiClient(ip, api_port, web_port=web_port)

    def _fortschritt(gesendet: int, gesamt: int) -> None:
        a.melden(t("ps4ota.status_ota_sende", gesendet=_mb(gesendet), gesamt=_mb(gesamt)),
                 95.0 * gesendet / gesamt if gesamt else 0.0)

    try:
        client.hochladen(paket, fortschritt=_fortschritt, abbruch=lambda: a.abbruch_verlangt)
        a.melden(t("ps4ota.status_ota_installiert_wird"), 96)
        client.warten(abbruch=lambda: a.abbruch_verlangt, zeitgrenze=3600.0,
                      bei_ping=lambda p: a.melden(t("ps4ota.status_ota_installiert_wird")))
    except ps4pkg_ota.OtaAbgebrochen as fehler:
        raise AufgabeAbgebrochen() from fehler
    except ps4pkg_ota.OtaFehler as fehler:
        raise _ota_fehler(fehler) from fehler
    a.ergebnis = ip
    a.melden(t("ps4ota.status_ota_fertig"), 100)


def arbeit_ota_rpi(a: Aufgabe, pakete: "list[str]", ip: str, port: int, t: Uebersetzer, *,
                   eigene_ip: str = "", server_port: int = 0) -> None:
    """Laesst eine PS4 (Remote Package Installer) die Pakete von diesem Rechner holen."""
    a.melden(t("ps4ota.status_ota_verbinde", ip=ip), 0)

    def _fortschritt(f: "ps4pkg_ota.RpiFortschritt | None", gesendet: int) -> None:
        if f is None:
            return
        a.melden(t("ps4ota.status_ota_holt", prozent="%.0f" % f.prozent, rest=f.rest_sekunden,
                   gesendet=_mb(gesendet)), f.prozent)

    try:
        ps4pkg_ota.rpi_senden(ip, pakete, port=port, eigene_ip=eigene_ip, server_port=server_port,
                              fortschritt=_fortschritt, abbruch=lambda: a.abbruch_verlangt)
    except ps4pkg_ota.OtaAbgebrochen as fehler:
        raise AufgabeAbgebrochen() from fehler
    except ps4pkg_ota.OtaFehler as fehler:
        raise _ota_fehler(fehler) from fehler
    a.ergebnis = ip
    a.melden(t("ps4ota.status_ota_fertig"), 100)
