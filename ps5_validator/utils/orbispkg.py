# -*- coding: utf-8 -*-
"""Ruft ``OrbisPkgTool`` auf - die Befehlszeile, die PS4-Pakete liest,
entpackt, prueft, zusammenfuehrt und baut.

Herkunft: ``pearlxcore/OrbisPkgTool`` 1.0.0 (MIT-Lizenz, Commit ``5cd42a5``),
dieselbe Bibliothek, auf der das PS4 PKG Tool aufsetzt. Sie ist reines C# und
braucht weder Sonys ``orbis-pub-cmd`` noch einen Schluessel, den man erst
beschaffen muesste: Die Schluessel fuer Fake-Pakete (Passcode aus lauter
Nullen) stecken in der Bibliothek. Einzelheiten, Pruefsummen und die eine
Aenderung am Quelltext stehen in ``OrbisPkgTool-1.0.0/UPSTREAM.md``.

**Warum ein eigener Prozess**, obwohl die MIT-Lizenz auch ein Einbinden
erlaubte: Es ist .NET, das Programm ist Python - und so laeuft das Werkzeug
wie ``UFS2Tool`` und ``prosperopkg`` ueber die Prozessgrenze, ohne dass
``pythonnet`` oder eine .NET-Laufzeit beim Anwender gebraucht wird (die
mitgelieferte Fassung ist eigenstaendig).

Das Werkzeug meldet sich zeilenweise. Zwei Zeilenenden kommen vor:
``\\n`` und ``\\r`` - der Fortschritt eines Entpackens oder Baus ueberschreibt
dieselbe Zeile mit ``\\r``. :func:`_laufen` teilt an beiden.

Dieses Modul bleibt sprachfrei wie alle unter ``ps5_validator/utils``: Die
Saetze, die der Anwender liest, kommen als ``MELDUNGEN`` mit uebersetzbaren
Vorlagen herein.
"""
from __future__ import annotations

import logging
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("PS5Converter.orbispkg")

#: Der Ordner des Werkzeugs, relativ zum Programm.
WERKZEUGORDNER = "OrbisPkgTool-1.0.0"

#: Die ausfuehrbare Datei je Plattform.
PROGRAMMNAME = "OrbisPkgTool.exe" if sys.platform == "win32" else "OrbisPkgTool"

#: Unterordner je Plattform - wie bei UFS2Tool und prosperopkg.
PLATTFORMORDNER = {
    "win32": "win-x64",
    "linux": "linux-x64",
    "darwin": "osx-x64",
}

#: Der Passcode, mit dem Fake-Pakete gesiegelt sind (32 Nullen).
STANDARD_PASSCODE = "0" * 32

#: Die Eintrags-Kennungen der Systemdateien eines Pakets (``Sc0``). Sie stehen
#: in der Eintragstabelle jedes PS4-Pakets und sind im Klartext lesbar.
EINTRAG_PARAM_SFO = 0x1000
EINTRAG_ICON0 = 0x1200
EINTRAG_PIC0 = 0x1220
EINTRAG_PIC1 = 0x1240

MELDUNGEN: dict[str, str] = {
    "nicht_gefunden":
        "OrbisPkgTool wurde nicht gefunden (erwartet in {ordner}/{plattform}/).",
    "abgebrochen": "Abgebrochen.",
    "zeit": "Zeitgrenze von {sekunden} Sekunden ueberschritten.",
    "kein_ergebnis": "Das Werkzeug lieferte keine auswertbare Ausgabe.",
}


class OrbisFehler(Exception):
    """Das Werkzeug fehlt, bricht ab oder antwortet unverstaendlich."""


# ---------------------------------------------------------------------------
# Das Werkzeug finden
# ---------------------------------------------------------------------------

def plattformordner() -> str:
    """Der Ordnername des Baus fuer diesen Rechner.

    Betriebssystem **und** Prozessor, wie bei ``prosperopkg``: Ein Mac mit
    M-Prozessor bekaeme sonst den Intel-Bau. Mitgeliefert wird derzeit nur der
    Windows-Bau; die anderen Namen stehen bereit, damit ein spaeterer Bau ohne
    Codeaenderung gefunden wird.
    """
    maschine = (platform.machine() or "").lower()
    arm = maschine in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "osx-arm64" if arm else "osx-x64"
    return PLATTFORMORDNER.get(sys.platform, "win-x64")


def _suchwurzeln() -> list[str]:
    """Die Stellen, an denen mitgelieferte Ordner liegen koennen.

    Im entpackten Bundle, neben der Programmdatei, im Arbeitsverzeichnis und
    drei Ebenen ueber diesem Modul (``ps5_validator/utils`` -> Projektordner).
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
    """Der Pfad zu ``OrbisPkgTool``, oder ein leerer String, wenn es fehlt.

    Das Ausfuehrungsrecht ueberlebt weder NTFS noch eine ZIP-Datei; unter
    Linux und macOS wird es hier gesetzt - derselbe Grund, aus dem
    ``prosperopkg.werkzeug_finden`` es tut.
    """
    unterordner = plattformordner()
    for wurzel in _suchwurzeln():
        pfad = os.path.join(wurzel, WERKZEUGORDNER, unterordner, PROGRAMMNAME)
        if os.path.isfile(pfad):
            if sys.platform != "win32" and not os.access(pfad, os.X_OK):
                try:
                    os.chmod(pfad, os.stat(pfad).st_mode | 0o111)
                except OSError:
                    pass
            return pfad
    return ""


def verfuegbar() -> bool:
    """Gibt es das Werkzeug fuer diesen Rechner?"""
    return bool(werkzeug_finden())


def _satz(texte: "dict[str, str] | None", kennung: str, **werte) -> str:
    """Eine Vorlage, uebersetzt wenn moeglich."""
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)


# ---------------------------------------------------------------------------
# Auswertung der Ausgabe - reine Funktionen
# ---------------------------------------------------------------------------

@dataclass
class PaketInfo:
    """Was ``info`` ueber ein Paket sagt."""
    titel: str = ""
    title_id: str = ""
    content_id: str = ""
    typ: str = ""
    kategorie: str = ""
    content_type: int = 0
    content_flags: int = 0
    app_version: str = ""
    system_version: str = ""
    passcode: str = ""


@dataclass
class ListenEintrag:
    """Eine Zeile von ``list``: Ordner oder Datei im Paket."""
    ist_ordner: bool
    groesse: int
    pfad: str

    @property
    def name(self) -> str:
        return self.pfad.rsplit("/", 1)[-1]


_INFO_SCHLUESSEL = {
    "title": "titel",
    "title id": "title_id",
    "content id": "content_id",
    "type": "typ",
    "category": "kategorie",
    "app version": "app_version",
    "system ver": "system_version",
    "passcode": "passcode",
}

_CONTENT_TYPE = re.compile(r"0x([0-9A-Fa-f]+)\s+flags\s+0x([0-9A-Fa-f]+)")


def info_auswerten(text: str) -> PaketInfo:
    """Liest die Ausgabe von ``info`` (``Schluessel : Wert`` je Zeile).

    Unbekannte Zeilen werden uebergangen. Die Funktion wirft nicht: Fehlt
    etwas, bleibt das Feld leer - der Aufrufer entscheidet, ob das reicht.
    """
    erg = PaketInfo()
    for zeile in text.splitlines():
        if ":" not in zeile:
            continue
        schluessel, wert = zeile.split(":", 1)
        schluessel = schluessel.strip().lower()
        wert = wert.strip()
        if schluessel == "content type":
            treffer = _CONTENT_TYPE.search(wert)
            if treffer:
                erg.content_type = int(treffer.group(1), 16)
                erg.content_flags = int(treffer.group(2), 16)
            continue
        feld = _INFO_SCHLUESSEL.get(schluessel)
        if feld:
            setattr(erg, feld, wert)
    return erg


def liste_auswerten(text: str) -> list[ListenEintrag]:
    """Liest die Ausgabe von ``list``: ``D 0 <pfad>`` und ``F <groesse> <pfad>``."""
    eintraege: list[ListenEintrag] = []
    for zeile in text.splitlines():
        teile = zeile.rstrip("\r\n").split(" ", 2)
        if len(teile) != 3 or teile[0] not in ("D", "F"):
            continue
        try:
            groesse = int(teile[1])
        except ValueError:
            continue
        eintraege.append(ListenEintrag(teile[0] == "D", groesse, teile[2]))
    return eintraege


#: ``  [ 83%] 31/37  Image0/eboot.bin`` - der Fortschritt von ``extract -v``.
_ENTPACK_FORTSCHRITT = re.compile(
    r"^\s*\[\s*(\d+)%\]\s+(\d+)/(\d+)\s+(.*?)\s*$")

#: ``  [ 12%] Compressing (34/160 MB)`` - der Fortschritt von ``build``.
_BAU_FORTSCHRITT = re.compile(
    r"^\s*\[\s*(\d+)%\]\s+(.*?)\s*\((\d+)/(\d+)\s*MB\)\s*$")

#: ``[3/5] Generating GP4 project...`` - die Schritte von ``repack``.
_SCHRITT = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+(.*?)\s*$")

#: ``[Extracting base] 12%`` - die Stufen von ``merge``.
_STUFE = re.compile(r"^\[([^\]]+)\]\s*(.*?)\s*$")

_ENTPACKT = re.compile(r"Extracted\s+(\d+)/(\d+)\s+files\s+in\s+([\d.,]+)s")


def entpack_fortschritt(zeile: str) -> "tuple[int, int, int, str] | None":
    """``(prozent, aktuell, gesamt, datei)`` aus einer Fortschrittszeile."""
    treffer = _ENTPACK_FORTSCHRITT.match(zeile)
    if not treffer:
        return None
    return (int(treffer.group(1)), int(treffer.group(2)),
            int(treffer.group(3)), treffer.group(4))


def bau_fortschritt(zeile: str) -> "tuple[int, str, int, int] | None":
    """``(prozent, stufe, megabyte_fertig, megabyte_gesamt)`` beim Bauen."""
    treffer = _BAU_FORTSCHRITT.match(zeile)
    if not treffer:
        return None
    return (int(treffer.group(1)), treffer.group(2),
            int(treffer.group(3)), int(treffer.group(4)))


def schritt_auswerten(zeile: str) -> "tuple[int, int, str] | None":
    """``(nummer, von, text)`` aus ``[3/5] ...``."""
    treffer = _SCHRITT.match(zeile)
    if not treffer:
        return None
    return int(treffer.group(1)), int(treffer.group(2)), treffer.group(3)


def stufe_auswerten(zeile: str) -> "tuple[str, str] | None":
    """``(stufe, einzelheit)`` aus ``[Stufe] Einzelheit`` (Ausgabe von ``merge``)."""
    treffer = _STUFE.match(zeile)
    if not treffer:
        return None
    return treffer.group(1), treffer.group(2)


@dataclass
class Pruefergebnis:
    """Das Urteil von ``validate``."""
    bestanden: bool
    grund: str = ""
    stufen: list[str] = field(default_factory=list)


def validate_auswerten(text: str) -> Pruefergebnis:
    """Liest ``Validation: PASS|FAIL`` samt ``Reason:`` und den Stufenzeilen."""
    stufen: list[str] = []
    bestanden: bool | None = None
    grund = ""
    for zeile in text.splitlines():
        roh = zeile.strip()
        if re.match(r"^\[\d+/\d+\]", roh):
            stufen.append(roh)
        elif roh.lower().startswith("validation:"):
            bestanden = "pass" in roh.lower()
        elif roh.lower().startswith("reason:"):
            grund = roh.split(":", 1)[1].strip()
    return Pruefergebnis(bool(bestanden), grund, stufen)


# ---------------------------------------------------------------------------
# Den Prozess fuehren
# ---------------------------------------------------------------------------

@dataclass
class LaufErgebnis:
    """Was ein Aufruf des Werkzeugs geliefert hat."""
    rueckgabe: int
    ausgabe: list[str]
    fehler: list[str]
    abgebrochen: bool = False
    zeit_ueberschritten: bool = False
    dauer: float = 0.0

    @property
    def text(self) -> str:
        return "\n".join(self.ausgabe)

    @property
    def fehlertext(self) -> str:
        return "\n".join(self.fehler)

    @property
    def letzte_fehlerzeile(self) -> str:
        """Die letzte Zeile mit ``[error]`` - sonst die letzte Fehlerzeile."""
        for zeile in reversed(self.fehler + self.ausgabe):
            if zeile.strip().startswith("[error]"):
                return zeile.strip()[len("[error]"):].strip()
        return self.fehler[-1].strip() if self.fehler else ""


_ZEILENENDE = re.compile(rb"\r\n|\r|\n")


def _beenden(lauf: "subprocess.Popen[bytes]") -> None:
    """Beendet den Prozess - erst freundlich, dann hart."""
    try:
        lauf.terminate()
        try:
            lauf.wait(timeout=3)
        except subprocess.TimeoutExpired:
            lauf.kill()
    except OSError:
        pass


def _laufen(argumente: list[str], *,
            bei_zeile: "Callable[[str, str], None] | None" = None,
            abbruch: "Callable[[], bool] | None" = None,
            zeitgrenze: float = 4 * 3600.0,
            arbeitsordner: "str | None" = None,
            prozess_ablage: "dict | None" = None,
            programm: str = "",
            texte: "dict[str, str] | None" = None) -> LaufErgebnis:
    """Startet das Werkzeug und reicht jede Zeile weiter, sobald sie kommt.

    Args:
        argumente: Was hinter dem Programmnamen steht.
        bei_zeile: ``(strom, zeile)`` mit ``strom`` ``"aus"`` oder ``"fehler"``;
            wird im Faden des Aufrufers gerufen.
        abbruch: Wird etwa viermal je Sekunde gefragt; ``True`` beendet den
            Prozess.
        zeitgrenze: Nach so vielen Sekunden wird abgebrochen. Ein eigener
            Wecker - ``for zeile in stdout`` blockiert ohne jede Frist
            (dieselbe Falle wie bei ``prosperopkg``).
        prozess_ablage: Nimmt den laufenden Prozess unter ``"prozess"`` auf,
            damit ein Fensterschluss ihn beenden kann.
        programm: Nur fuer Tests - statt des gefundenen Werkzeugs.

    Raises:
        OrbisFehler: Das Werkzeug fehlt oder laesst sich nicht starten.
    """
    pfad = programm or werkzeug_finden()
    if not pfad:
        raise OrbisFehler(_satz(texte, "nicht_gefunden", ordner=WERKZEUGORDNER,
                                plattform=plattformordner()))
    anlauf: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": arbeitsordner,
    }
    if sys.platform == "win32":
        anlauf["creationflags"] = 0x08000000     # CREATE_NO_WINDOW
    try:
        lauf = subprocess.Popen([pfad, *argumente], **anlauf)
    except OSError as fehler:
        raise OrbisFehler(str(fehler)) from fehler
    if prozess_ablage is not None:
        prozess_ablage["prozess"] = lauf

    ereignisse: "queue.Queue[tuple[str, str | None]]" = queue.Queue()

    def _leser(strom, kennung: str) -> None:
        rest = b""
        try:
            while True:
                lese = getattr(strom, "read1", strom.read)
                block = lese(65536)
                if not block:
                    break
                rest += block
                while True:
                    treffer = _ZEILENENDE.search(rest)
                    if not treffer:
                        break
                    stueck, rest = rest[:treffer.start()], rest[treffer.end():]
                    if stueck:
                        ereignisse.put((kennung, stueck.decode("utf-8", "replace")))
        except (OSError, ValueError):
            pass
        finally:
            if rest:
                ereignisse.put((kennung, rest.decode("utf-8", "replace")))
            ereignisse.put((kennung, None))

    faeden = [
        threading.Thread(target=_leser, args=(lauf.stdout, "aus"), daemon=True),
        threading.Thread(target=_leser, args=(lauf.stderr, "fehler"), daemon=True),
    ]
    for faden in faeden:
        faden.start()

    aus: list[str] = []
    fehler: list[str] = []
    offen = 2
    start = time.monotonic()
    naechste_pruefung = start
    abgebrochen = zeit = False
    try:
        while offen > 0:
            try:
                kennung, zeile = ereignisse.get(timeout=0.25)
            except queue.Empty:
                zeile = ""
                kennung = ""
            if kennung and zeile is None:
                offen -= 1
            elif kennung and zeile:
                (aus if kennung == "aus" else fehler).append(zeile)
                if bei_zeile is not None:
                    try:
                        bei_zeile(kennung, zeile)
                    except Exception:  # noqa: BLE001
                        logger.exception("Rueckruf des Werkzeugs gescheitert")
            jetzt = time.monotonic()
            # Hoechstens vier Fragen je Sekunde: Ein Entpacken meldet tausende
            # Zeilen, und der Abbruch-Rueckruf liest unter Umstaenden eine
            # Variable des Fensters.
            if jetzt >= naechste_pruefung and not (abgebrochen or zeit):
                naechste_pruefung = jetzt + 0.25
                if abbruch is not None and abbruch():
                    abgebrochen = True
                    _beenden(lauf)
                elif jetzt - start > zeitgrenze:
                    zeit = True
                    _beenden(lauf)
    finally:
        if lauf.poll() is None:
            _beenden(lauf)
    try:
        rueckgabe = lauf.wait(timeout=30)
    except subprocess.TimeoutExpired:
        lauf.kill()
        rueckgabe = lauf.wait()
    for faden in faeden:
        faden.join(timeout=2)
    return LaufErgebnis(rueckgabe, aus, fehler, abgebrochen, zeit,
                        time.monotonic() - start)


def _passcode(passcode: "str | None") -> list[str]:
    return ["--passcode", passcode] if passcode else []


# ---------------------------------------------------------------------------
# Die Befehle
# ---------------------------------------------------------------------------

def info(paket: str, passcode: "str | None" = None, **laufargs) -> PaketInfo:
    """Titel, Kennungen und Versionen eines Pakets.

    Raises:
        OrbisFehler: Das Paket laesst sich nicht lesen.
    """
    lauf = _laufen(["info", paket, *_passcode(passcode)], **laufargs)
    if lauf.rueckgabe != 0:
        raise OrbisFehler(lauf.letzte_fehlerzeile or lauf.text or "info")
    return info_auswerten(lauf.text)


def liste(paket: str, passcode: "str | None" = None, **laufargs) -> list[ListenEintrag]:
    """Alle Ordner und Dateien im Paket (``Image0/...`` und ``Sc0/...``).

    Raises:
        OrbisFehler: Das Paket laesst sich nicht lesen.
    """
    lauf = _laufen(["list", paket, *_passcode(passcode)], **laufargs)
    if lauf.rueckgabe != 0:
        raise OrbisFehler(lauf.letzte_fehlerzeile or lauf.text or "list")
    return liste_auswerten(lauf.text)


@dataclass
class EntpackErgebnis:
    """Ausgang eines Entpackens."""
    ok: bool
    dateien_ok: int = 0
    dateien_gesamt: int = 0
    fehler: list[str] = field(default_factory=list)
    dauer: float = 0.0
    abgebrochen: bool = False
    meldung: str = ""


def entpacken(paket: str, ziel: str, *, passcode: "str | None" = None,
              fortschritt: "Callable[[int, int, str], None] | None" = None,
              **laufargs) -> EntpackErgebnis:
    """Entpackt das ganze Paket nach ``ziel`` (``Image0/`` und ``Sc0/``).

    ``fortschritt(aktuell, gesamt, datei)`` bekommt jede Meldung des
    Werkzeugs (``extract --verbose``). Ein einzelnes Fehlschlagen von Dateien
    bricht nicht ab: Das Werkzeug liefert den Rest und gibt dann 1 zurueck;
    ``fehler`` nennt die betroffenen Dateien.
    """
    os.makedirs(ziel, exist_ok=True)
    fenster: dict = {"in_fehlern": False}
    fehler_dateien: list[str] = []

    def _zeile(strom: str, zeile: str) -> None:
        if strom == "aus":
            werte = entpack_fortschritt(zeile)
            if werte and fortschritt is not None:
                fortschritt(werte[1], werte[2], werte[3])
        else:
            if "file(s) failed" in zeile:
                fenster["in_fehlern"] = True
            elif fenster["in_fehlern"] and zeile.strip():
                fehler_dateien.append(zeile.strip())

    bei_zeile = laufargs.pop("bei_zeile", None)

    def _beides(strom: str, zeile: str) -> None:
        _zeile(strom, zeile)
        if bei_zeile is not None:
            bei_zeile(strom, zeile)

    lauf = _laufen(["extract", paket, ziel, "--verbose", *_passcode(passcode)],
                   bei_zeile=_beides, **laufargs)
    erg = EntpackErgebnis(ok=lauf.rueckgabe == 0 and not lauf.abgebrochen,
                          fehler=fehler_dateien, dauer=lauf.dauer,
                          abgebrochen=lauf.abgebrochen)
    for zeile in lauf.ausgabe:
        treffer = _ENTPACKT.search(zeile)
        if treffer:
            erg.dateien_ok = int(treffer.group(1))
            erg.dateien_gesamt = int(treffer.group(2))
    if not erg.ok and not erg.abgebrochen:
        erg.meldung = lauf.letzte_fehlerzeile or lauf.text[-300:]
    return erg


def entpacken_eintrag(paket: str, eintrag: str, ziel: str, *,
                      passcode: "str | None" = None, **laufargs) -> LaufErgebnis:
    """Entpackt eine einzelne Datei (``Image0/...`` oder ``Sc0/...``) nach ``ziel``."""
    os.makedirs(ziel, exist_ok=True)
    # ``paket:eintrag`` - das Werkzeug trennt am letzten Doppelpunkt hinter der
    # Laufwerksangabe.
    return _laufen(["extract", f"{paket}:{eintrag}", ziel, *_passcode(passcode)],
                   **laufargs)


def pruefen(paket: str, passcode: "str | None" = None, **laufargs) -> "tuple[bool, str]":
    """Schnelle Pruefung der Pruefsummen und Signaturen (``verify``).

    Returns:
        ``(in_ordnung, text)``.
    """
    lauf = _laufen(["verify", paket, *_passcode(passcode)], **laufargs)
    text = lauf.text.strip() or lauf.fehlertext.strip()
    return lauf.rueckgabe == 0 and "Integrity OK" in lauf.text, text


def tiefenpruefung(paket: str, passcode: "str | None" = None, *,
                   fake_tolerant: bool = False, **laufargs) -> Pruefergebnis:
    """Die achtstufige Pruefung (``validate``).

    Am 05.10.2026 gemessen: Sie lehnt ein einwandfrei entpackbares Paket ab
    (``Mario Kart 64 [PS2toPS4]``: Stufe 3, PFSC - das Werkzeug verwechselt
    dort offenbar ein nicht komprimiertes Endstueck mit einem Deflate-Block),
    obwohl ``verify`` besteht und beide Entpacker dieselben Dateien liefern.
    Ein Fehlschlag heisst deshalb nicht, dass das Paket unbrauchbar ist.
    """
    argumente = ["validate", paket, *_passcode(passcode)]
    if fake_tolerant:
        argumente.append("--fake-tolerant")
    lauf = _laufen(argumente, **laufargs)
    erg = validate_auswerten(lauf.text + "\n" + lauf.fehlertext)
    if lauf.rueckgabe != 0 and erg.bestanden:
        erg.bestanden = False
    return erg


@dataclass
class BauErgebnis:
    """Ausgang von Zusammenfuehren, Neupacken und Bauen."""
    ok: bool
    ausgabe: str = ""
    dauer: float = 0.0
    abgebrochen: bool = False
    meldung: str = ""
    arbeitsordner_behalten: str = ""


def _bau_zeile(fortschritt: "Callable[[str, int | None], None] | None"):
    """Ein Zeilenhoerer, der Stufen und Prozente zu ``fortschritt(text, prozent)`` macht."""
    def _hoeren(strom: str, zeile: str) -> None:
        if fortschritt is None or strom != "aus":
            return
        bau = bau_fortschritt(zeile)
        if bau:
            fortschritt("%s (%d/%d MB)" % (bau[1], bau[2], bau[3]), bau[0])
            return
        schritt = schritt_auswerten(zeile)
        if schritt:
            fortschritt(schritt[2], None)
            return
        stufe = stufe_auswerten(zeile)
        if stufe:
            text = stufe[0] + (": " + stufe[1] if stufe[1] else "")
            prozent = re.match(r"^(\d+)%$", stufe[1])
            fortschritt(text, int(prozent.group(1)) if prozent else None)
    return _hoeren


def zusammenfuehren(basis: str, update: str, ausgabe: str, *,
                    passcode: "str | None" = None,
                    pruefen_danach: bool = False,
                    pfsc_modus: str = "compressed",
                    arbeiter: int = 1,
                    arbeitsordner: "str | None" = None,
                    behalten: bool = False,
                    titel: "str | None" = None,
                    fortschritt: "Callable[[str, int | None], None] | None" = None,
                    **laufargs) -> BauErgebnis:
    """Fuehrt Basisspiel und Update zu **einem** eigenstaendigen Basispaket zusammen.

    Das Werkzeug prueft, dass das erste Paket ein Basisspiel und das zweite
    ein Patch derselben Title-ID ist, legt das Update ueber die Dateien der
    Basis, verschiebt ``Sc0`` nach ``Image0/sce_sys``, erzeugt ein GP4 und
    baut das Ergebnis. Es behaelt den Typ der Basis und nimmt die Fassung des
    Updates; gesiegelt wird mit dem Passcode aus Nullen.

    Es ist **experimentell**: Die gebauten Pakete sind am PC geprueft, an einer
    PS4 aber nie getestet worden (so sagt es der Autor).

    Args:
        arbeiter: Faeden fuer die PFSC-Kompression, ``0`` = alle Kerne.
    """
    argumente = ["merge", basis, update, "--out", ausgabe,
                 "--pfsc-mode", pfsc_modus, "--workers", str(max(0, int(arbeiter)))]
    argumente += _passcode(passcode)
    if pruefen_danach:
        argumente.append("--validate")
    if arbeitsordner:
        argumente += ["--work-dir", arbeitsordner]
    if behalten:
        argumente.append("--keep-work")
    if titel:
        argumente += ["--title", titel]
    bei_zeile = laufargs.pop("bei_zeile", None)
    hoerer = _bau_zeile(fortschritt)

    def _beides(strom: str, zeile: str) -> None:
        hoerer(strom, zeile)
        if bei_zeile is not None:
            bei_zeile(strom, zeile)

    lauf = _laufen(argumente, bei_zeile=_beides, **laufargs)
    return _bauergebnis(lauf, ausgabe)


def neu_packen(paket: str, ausgabe: str, *, passcode: "str | None" = None,
               pruefen_danach: bool = False, pfsc_modus: str = "compressed",
               arbeiter: int = 1, arbeitsordner: "str | None" = None,
               fortschritt: "Callable[[str, int | None], None] | None" = None,
               **laufargs) -> BauErgebnis:
    """Entpackt ein Paket und baut es neu (``repack``): Sie behaelt je Datei die Kompressionswahl."""
    argumente = ["repack", paket, "--out", ausgabe, "--pfsc-mode", pfsc_modus,
                 "--workers", str(max(0, int(arbeiter)))]
    argumente += _passcode(passcode)
    if pruefen_danach:
        argumente.append("--validate")
    if arbeitsordner:
        argumente += ["--work-dir", arbeitsordner]
    bei_zeile = laufargs.pop("bei_zeile", None)
    hoerer = _bau_zeile(fortschritt)

    def _beides(strom: str, zeile: str) -> None:
        hoerer(strom, zeile)
        if bei_zeile is not None:
            bei_zeile(strom, zeile)

    lauf = _laufen(argumente, bei_zeile=_beides, **laufargs)
    return _bauergebnis(lauf, ausgabe)


def projekt_erzeugen(ordner: str, ausgabe_gp4: str, *, patch: bool = False,
                     streng: bool = False, **laufargs) -> LaufErgebnis:
    """Erzeugt ein GP4-Projekt aus einem Ordner (``gp4gen``).

    Die Angaben stehen in ``sce_sys/param.sfo`` des Ordners.
    """
    argumente = ["gp4gen", ordner, "--out", ausgabe_gp4]
    if patch:
        argumente.append("--patch")
    if streng:
        argumente.append("--strict-gengp4")
    return _laufen(argumente, **laufargs)


def bauen(gp4: str, ordner: str, ausgabe: str, *, passcode: "str | None" = None,
          pruefen_danach: bool = False, pfsc_modus: str = "compressed",
          arbeiter: int = 1,
          fortschritt: "Callable[[str, int | None], None] | None" = None,
          **laufargs) -> BauErgebnis:
    """Baut ein Paket aus einem GP4-Projekt und dem Quellordner (``build``)."""
    argumente = ["build", gp4, ordner, "--out", ausgabe, "--pfsc-mode", pfsc_modus,
                 "--workers", str(max(0, int(arbeiter)))]
    argumente += _passcode(passcode)
    if pruefen_danach:
        argumente.append("--validate")
    bei_zeile = laufargs.pop("bei_zeile", None)
    hoerer = _bau_zeile(fortschritt)

    def _beides(strom: str, zeile: str) -> None:
        hoerer(strom, zeile)
        if bei_zeile is not None:
            bei_zeile(strom, zeile)

    lauf = _laufen(argumente, bei_zeile=_beides, **laufargs)
    return _bauergebnis(lauf, ausgabe)


def _bauergebnis(lauf: LaufErgebnis, ausgabe: str) -> BauErgebnis:
    erg = BauErgebnis(ok=lauf.rueckgabe == 0 and not lauf.abgebrochen
                      and os.path.isfile(ausgabe),
                      ausgabe=ausgabe, dauer=lauf.dauer,
                      abgebrochen=lauf.abgebrochen)
    for zeile in lauf.ausgabe:
        if "Work directory kept:" in zeile:
            erg.arbeitsordner_behalten = zeile.split("kept:", 1)[1].strip()
    if not erg.ok and not erg.abgebrochen:
        erg.meldung = lauf.letzte_fehlerzeile or lauf.text[-300:]
    return erg


def version() -> str:
    """Die Fassung des mitgelieferten Werkzeugs, wie sie ``UPSTREAM.md`` nennt."""
    return WERKZEUGORDNER.rsplit("-", 1)[-1]
