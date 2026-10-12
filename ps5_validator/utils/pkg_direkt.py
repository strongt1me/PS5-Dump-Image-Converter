# -*- coding: utf-8 -*-
"""Ein PS5-Paket ohne lokale Kopie auf die Konsole entpacken (seit v1.9.72).

Das PKG-Werkzeug liest die Dateien aus dem Paket (``stream-inner``) und gibt sie als Datenstrom aus; dieses Modul schickt
sie gleich per FTP an die Konsole. Auf dem PC entsteht kein entpackter Ordner - ein Spiel von 50 GB braucht dort keine
50 GB freien Platz, und die Zeit fuer erst Entpacken, dann Senden entfaellt.

Die Idee stammt von **fpkg2ftp** (kvaps, GPL-3.0-or-later, https://github.com/kvaps/fpkg2ftp): ein fPKG lesen, seine
Dateien gleich per FTP schicken und nach einem Abriss mit dem Rest weitermachen. Der Code ist hier neu geschrieben.

**Der Datenstrom** (``stream-inner <Paket> --plan <Datei>``, little-endian, nichts anderes auf stdout; die Meldungen des
Werkzeugs gehen auf stderr)::

    Plan   eine Zeile je Datei:  <Start> TAB <Pfad>   (Start = ab dieser Stelle weitersenden, 0 = ganz)
    Datei  "PKF1"  u32 Pfadlaenge  Pfad (UTF-8)  i64 Groesse  i64 Start   danach genau (Groesse - Start) Bytes
    Ende   "PKE1"  u32 Anzahl der Dateien

Der Rahmen nennt den Start, bei dem die Datei wirklich beginnt: Nur eine einfache, zusammenhaengende Datei kann mitten
drin anfangen; jede andere kommt ganz und sagt Start 0. Aufgesetzt wird nach dem Rahmen, nicht nach dem Wunsch -
``APPE`` nur bei Start > 0, sonst ``STOR`` (das schneidet ab).

Es gilt die Regel von :mod:`konsole_ftp`: **Abgebrochen wird nur zwischen zwei Dateien.** Das Werkzeug wird dann beendet,
waehrend die FTP-Verbindung ruht - ein Abbruch mitten im ``STOR`` hinterliesse eine halbe Datei, und die Konsole haengt
sich an halben Uebertragungen gelegentlich auf.
"""
from __future__ import annotations

import ftplib
import logging
import os
import posixpath
import struct
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from typing import Callable, Sequence

from . import konsole_ftp as ftp
from . import ps5_pkg_werkzeug as wz

logger = logging.getLogger("PS5Converter.pkg_direkt")

MAGIE_DATEI = b"PKF1"
MAGIE_ENDE = b"PKE1"
#: Pufferung des Rohrs: Das Senden liest in Bloecken von :data:`konsole_ftp.SENDE_BLOCK` und soll nicht je Block
#: ein Systemaufruf sein.
_STROM_BLOCK = 1 << 20
#: Laenger darf ein Pfad im Rahmenkopf nicht sein - ein groesserer Wert ist ein verrutschter Strom, kein Pfad.
MAX_PFAD = 4096
#: So lange darf das Werkzeug nach dem Endrahmen noch brauchen, um sich zu beenden.
_ENDE_WARTEN = 60


class StromFehler(ftp.FtpFehler):
    """Der Datenstrom des Werkzeugs ist unbrauchbar: zu kurz, falsche Rahmen, oder das Werkzeug ist abgestuerzt."""


@dataclass(frozen=True)
class Datei:
    """Eine Datei im Paket: Pfad (relativ zu ``/app0``, mit ``/``) und logische Groesse."""

    pfad: str
    groesse: int


@dataclass(frozen=True)
class Rahmen:
    """Der Kopf einer Datei im Strom: ab ``start`` folgen genau ``groesse - start`` Bytes."""

    pfad: str
    groesse: int
    start: int


def pfad_ok(pfad: str) -> bool:
    """Darf dieser Pfad aus dem Paket so auf die Konsole? Relativ, ohne ``..``, ohne Steuerzeichen und Rueckstrich."""
    if not pfad or pfad.startswith("/") or "\\" in pfad or any(ord(z) < 32 for z in pfad):
        return False
    return all(teil not in ("", ".", "..") for teil in pfad.split("/"))


def dateien_und_ordner(baum: Sequence[dict]) -> tuple[list[Datei], list[str]]:
    """Teilt den Baum von ``list-inner`` in Dateien und Ordner (je nach Pfad sortiert).

    Raises:
        FtpFehler: ein Pfad ist unsicher (:func:`pfad_ok`) - nichts wird dann uebertragen.
    """
    dateien: list[Datei] = []
    ordner: list[str] = []
    for eintrag in baum:
        pfad = str(eintrag.get("path", ""))
        art = eintrag.get("type")
        if art == "dir":
            ordner.append(pfad)
        elif art == "file":
            dateien.append(Datei(pfad, int(eintrag.get("size") or 0)))
    for pfad in [d.pfad for d in dateien] + ordner:
        if not pfad_ok(pfad):
            raise ftp.FtpFehler("Der Pfad %r im Paket laesst sich nicht sicher auf die Konsole uebertragen." % pfad)
    return sorted(dateien, key=lambda d: d.pfad), sorted(ordner)


# ---------------------------------------------------------------------------------------------------------------------
# Der Datenstrom
# ---------------------------------------------------------------------------------------------------------------------
def _genau(strom, anzahl: int, was: str) -> bytes:
    """Liest genau ``anzahl`` Bytes - ein Rohr liefert gern weniger auf einmal."""
    teile: list[bytes] = []
    noch = anzahl
    while noch > 0:
        try:
            stueck = strom.read(noch)
        except (OSError, ValueError) as fehler:
            raise StromFehler("Der Strom des Werkzeugs liess sich nicht lesen (%s): %s" % (was, fehler)) from fehler
        if not stueck:
            raise StromFehler("Der Strom des Werkzeugs endete mitten in %s." % was)
        teile.append(stueck)
        noch -= len(stueck)
    return b"".join(teile)


def rahmen_lesen(strom) -> "Rahmen | int":
    """Der naechste Rahmen: ein :class:`Rahmen` (eine Datei folgt) oder am Ende die Zahl der Dateien (Endrahmen).

    Raises:
        StromFehler: der Strom endet vorzeitig, trägt keinen Rahmen oder einen unmoeglichen (Pfadlaenge, Groesse, Start).
    """
    magie = _genau(strom, 4, "einem Rahmenkopf")
    if magie == MAGIE_ENDE:
        return int(struct.unpack("<I", _genau(strom, 4, "dem Endrahmen"))[0])
    if magie != MAGIE_DATEI:
        raise StromFehler("Unerwartete Ausgabe des Werkzeugs (%r) - das ist kein Rahmen." % magie)
    (laenge,) = struct.unpack("<I", _genau(strom, 4, "einem Rahmenkopf"))
    if not 0 < laenge <= MAX_PFAD:
        raise StromFehler("Unmoegliche Pfadlaenge im Rahmen: %d." % laenge)
    try:
        pfad = _genau(strom, laenge, "einem Pfad").decode("utf-8")
    except UnicodeDecodeError as fehler:
        raise StromFehler("Ein Pfad im Rahmen ist kein UTF-8.") from fehler
    groesse, start = struct.unpack("<qq", _genau(strom, 16, "einem Rahmenkopf"))
    if groesse < 0 or not 0 <= start <= groesse:
        raise StromFehler("Unmoegliche Groesse oder Startstelle im Rahmen (%d, %d) bei %s." % (groesse, start, pfad))
    return Rahmen(pfad, groesse, start)


class _FehlerLeser(threading.Thread):
    """Liest stderr des Werkzeugs, damit dessen Rohr nie voll laeuft, und merkt sich die letzten Zeilen."""

    def __init__(self, strom, zeile: "Callable[[str], None] | None") -> None:
        super().__init__(daemon=True, name="pkg-direkt-stderr")
        self._strom = strom
        self._zeile = zeile
        self.zeilen: list[str] = []

    def run(self) -> None:
        try:
            for roh in iter(self._strom.readline, b""):
                text = roh.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                self.zeilen.append(text)
                del self.zeilen[:-40]
                if self._zeile is not None:
                    try:
                        self._zeile(text)
                    except Exception:  # noqa: BLE001 - eine Rueckmeldung darf das Lesen nie beenden
                        logger.debug("Rueckmeldung des Werkzeugs nicht verarbeitet", exc_info=True)
        except (OSError, ValueError):
            pass

    def fehlertext(self) -> str:
        """Die letzte Fehlerzeile des Werkzeugs, sonst die letzte Zeile, sonst leer."""
        fehler = [z for z in self.zeilen if z.startswith(("[error]", "[usage]"))]
        return (fehler or self.zeilen or [""])[-1][:300]


# ---------------------------------------------------------------------------------------------------------------------
# Der Ablauf
# ---------------------------------------------------------------------------------------------------------------------
class _Uebertrag:
    """Ein Lauf: Paket lesen, Dateien senden, nach einem Abriss mit frischer Verbindung dort weitermachen."""

    def __init__(self, werkzeug: "str | Sequence[str]", paket: str, adresse: str, fern: str, *, port: int,
                 fortsetzen: bool, baum: "Sequence[dict] | None", passcode: str,
                 auf_fortschritt: "Callable[[ftp.Fortschritt], None] | None",
                 abbruch: "Callable[[], bool] | None", zeile: "Callable[[str], None] | None",
                 popen_extra: "dict | None", arbeitsordner: "str | None", versuche: int, pause: float) -> None:
        self.kommando = [werkzeug] if isinstance(werkzeug, str) else list(werkzeug)
        self.paket, self.adresse, self.port = paket, adresse, int(port)
        self.passcode = passcode
        self.fern = "/" + str(fern or "").strip().strip("/")
        self.fortsetzen = fortsetzen
        self.baum = baum
        self.auf_fortschritt, self.abbruch, self.zeile = auf_fortschritt, abbruch, zeile
        self.popen_extra, self.arbeitsordner = popen_extra, arbeitsordner
        self.versuche, self.pause = versuche, pause
        self.stand = ftp.Fortschritt()
        self.verbindung: "ftplib.FTP | None" = None
        self.angelegt: set[str] = set()
        self.appe_geht = True
        self.fertig_bytes = 0
        self.begonnen = ""                 # Pfad der Datei, von der dieser Lauf schon etwas gesendet hat

    # --- Hilfen ---------------------------------------------------------------------------------------------------
    def _stand_melden(self) -> None:
        if self.auf_fortschritt is not None:
            self.auf_fortschritt(self.stand)

    def _fertig(self, datei: Datei, uebersprungen: bool) -> None:
        self.fertig_bytes += datei.groesse
        self.stand.bytes = self.fertig_bytes
        self.stand.dateien += 1
        if uebersprungen:
            self.stand.uebersprungen += 1
        self._stand_melden()

    def _verbinden(self) -> ftplib.FTP:
        verbindung = ftp.verbinden(self.adresse, self.port)
        verbindung.timeout = ftp.DATEN_ZEIT
        return verbindung

    # --- Ablauf ---------------------------------------------------------------------------------------------------
    def ausfuehren(self) -> ftp.Fortschritt:
        baum = (self.baum if self.baum is not None
               else wz.baum(self.kommando[0], self.paket, self.popen_extra, passcode=self.passcode))
        dateien, ordner = dateien_und_ordner(baum)
        if not dateien:
            raise ftp.FtpFehler("Im Paket liegen keine Dateien.")
        self.stand = ftp.Fortschritt(dateien_gesamt=len(dateien), bytes_gesamt=sum(d.groesse for d in dateien))
        try:
            self.verbindung = self._verbinden()
            try:
                ftp.ordner_sichern(self.verbindung, self.fern, self.angelegt)
                for unter in ordner:                       # auch die leeren Ordner des Spiels
                    ftp.ordner_sichern(self.verbindung, posixpath.join(self.fern, unter), self.angelegt)
                vorhanden = ftp.fern_baum(self.verbindung, self.fern, self.abbruch) if self.fortsetzen else {}
            except ftp.FtpAbgebrochen:
                self.stand.abgebrochen = True
                return self.stand
            except ftp.FtpFehler:
                raise
            except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
                raise ftp.FtpFehler("%s nicht vorbereitbar: %s" % (self.fern, fehler)) from fehler
            offen: list[list] = []                          # [Datei, Startstelle]
            for datei in dateien:
                aktion, start = (ftp.fortsetzen_ab(datei.groesse, vorhanden.get(datei.pfad))
                                 if self.fortsetzen else ("neu", 0))
                if aktion == "ueberspringen":
                    self._fertig(datei, uebersprungen=True)
                else:
                    offen.append([datei, start])
            self._schleife(offen)
            return self.stand
        finally:
            if self.verbindung is not None:
                ftp.schliessen(self.verbindung)

    def _schleife(self, offen: list) -> None:
        """Laeuft, bis alles gesendet, abgebrochen oder endgueltig gescheitert ist."""
        versuch = 0
        while offen and not self.stand.abgebrochen:
            vorher = len(offen)
            try:
                self._lauf(offen)
            except (StromFehler, ftp.LeseFehler):
                raise
            except ftplib.error_perm as fehler:
                datei, start = offen[0]
                if start > 0 and self.appe_geht:
                    # Der Server nimmt kein APPE (oder lehnt es hier ab): Die Datei geht neu, ab jetzt alle so.
                    logger.info("APPE abgelehnt (%s) - %s wird neu gesendet", fehler, datei.pfad)
                    self.appe_geht = False
                    offen[0][1] = 0
                    continue
                raise ftp.FtpFehler("%s nicht schreibbar: %s" % (datei.pfad, fehler)) from fehler
            except ftp.FtpFehler:
                raise
            except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
                datei = offen[0][0]
                if not ftp.ist_netzfehler(fehler):
                    raise ftp.FtpFehler("%s nicht schreibbar: %s" % (datei.pfad, fehler)) from fehler
                if len(offen) < vorher:
                    versuch = 0                              # zwischendurch ging etwas durch: die Zaehlung beginnt neu
                self.verbindung, versuch, ende = ftp._nach_abriss(  # noqa: SLF001 - dieselbe Behandlung wie ordner_senden
                    fehler, datei.pfad, self.adresse, self.port, versuch, self.versuche, self.pause, self.abbruch,
                    self.verbindung, self.stand)
                if ende:
                    break
                self._nach_abriss_klaeren(offen)

    def _nach_abriss_klaeren(self, offen: list) -> None:
        """Nach dem Abriss: Was liegt von der laufenden Datei auf der Konsole? Dort geht es weiter - oder neu."""
        datei, _start = offen[0]
        if self.begonnen != datei.pfad:
            return                                           # von dieser Datei ging noch nichts hinaus
        try:
            fern = ftp.groesse_fern(self.verbindung, posixpath.join(self.fern, datei.pfad))
        except Exception as fehler:  # noqa: BLE001
            logger.debug("Groesse nach dem Abriss nicht lesbar (%s): die Datei wird neu gesendet", fehler)
            fern = None
        # Was dort liegt, hat dieser Lauf selbst geschrieben (STOR schneidet ab, APPE haengt an).
        aktion, neu = ftp.fortsetzen_ab(datei.groesse, fern)
        if aktion == "ueberspringen":
            offen.pop(0)                                     # alles war schon da, nur die Antwort ging verloren
            self._fertig(datei, uebersprungen=False)
        elif aktion == "fortsetzen" and self.appe_geht:
            offen[0][1] = neu
        else:
            offen[0][1] = 0

    def _starten(self, plan: str) -> subprocess.Popen:
        werkzeug = self.kommando[0]
        if sys.platform != "win32":
            try:
                os.chmod(werkzeug, os.stat(werkzeug).st_mode | 0o111)    # aus einem Archiv kommt es ohne Ausfuehrungsrecht
            except OSError:
                pass
        try:
            passcode_args = ["--passcode", self.passcode] if self.passcode else []
            return subprocess.Popen([*self.kommando, "stream-inner", self.paket, "--plan", plan] + passcode_args,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    env=wz._umgebung(), bufsize=_STROM_BLOCK,   # noqa: SLF001
                                    **(self.popen_extra or {}))
        except OSError as fehler:
            raise ftp.FtpFehler("Das Werkzeug laesst sich nicht starten: %s" % fehler) from fehler

    def _lauf(self, offen: list) -> None:
        """Ein Durchgang des Werkzeugs ueber alle offenen Dateien; ``offen`` wird Datei fuer Datei kuerzer."""
        plan = [(0 if (start > 0 and not self.appe_geht) else start, datei) for datei, start in offen]
        handle, planpfad = tempfile.mkstemp(prefix="ps5conv_plan_", suffix=".txt", dir=self.arbeitsordner or None)
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as ausgabe:
            ausgabe.write("".join("%d\t%s\n" % (start, datei.pfad) for start, datei in plan))
        prozess = None
        leser: "_FehlerLeser | None" = None
        try:
            prozess = self._starten(planpfad)
            leser = _FehlerLeser(prozess.stderr, self.zeile)
            leser.start()
            for _wunsch, datei in plan:
                if self.abbruch is not None and self.abbruch():
                    self.stand.abgebrochen = True            # zwischen zwei Dateien: die FTP-Verbindung ruht
                    return
                rahmen = rahmen_lesen(prozess.stdout)
                if not isinstance(rahmen, Rahmen) or rahmen.pfad != datei.pfad or rahmen.groesse != datei.groesse:
                    raise StromFehler("Das Werkzeug lieferte %s statt %s." % (
                        rahmen.pfad if isinstance(rahmen, Rahmen) else "das Ende", datei.pfad))
                self._senden(prozess.stdout, rahmen)
                offen.pop(0)
            ende = rahmen_lesen(prozess.stdout)
            if ende != len(plan):
                raise StromFehler("Der Endrahmen nennt %s Dateien, gesendet wurden %d." % (ende, len(plan)))
            try:
                rueckgabe = prozess.wait(timeout=_ENDE_WARTEN)
            except subprocess.TimeoutExpired as fehler:
                raise StromFehler("Das Werkzeug beendet sich nach dem Ende des Stroms nicht.") from fehler
            if rueckgabe != 0:
                raise StromFehler("Das Werkzeug meldet Rueckgabewert %d." % rueckgabe)
        except (StromFehler, ftp.LeseFehler) as fehler:
            # Warum das Werkzeug aufgehoert hat, steht auf stderr - nachlesen, bevor es aufgeraeumt wird.
            grund = ""
            if prozess is not None and leser is not None:
                try:
                    prozess.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                leser.join(timeout=2)
                grund = leser.fehlertext()
            raise StromFehler("%s%s" % (fehler, " - " + grund if grund else "")) from fehler
        finally:
            if prozess is not None and prozess.poll() is None:
                wz._beenden(prozess)                         # noqa: SLF001
            if leser is not None:
                leser.join(timeout=2)
            try:
                os.remove(planpfad)
            except OSError:
                pass

    def _senden(self, strom, rahmen: Rahmen) -> None:
        """Schickt die Daten einer Datei aus dem Strom an die Konsole."""
        ziel = posixpath.join(self.fern, rahmen.pfad)
        ftp.ordner_sichern(self.verbindung, posixpath.dirname(ziel), self.angelegt)
        stand = self.stand
        stand.aktuell = rahmen.pfad
        stand.bytes = self.fertig_bytes + rahmen.start      # was schon dort liegt, zaehlt als erledigt
        self._stand_melden()
        self.begonnen = rahmen.pfad

        def gelesen(block: bytes) -> None:
            stand.bytes += len(block)
            self._stand_melden()

        ftp.datei_senden(self.verbindung, strom, rahmen.groesse, ziel, rahmen.start, callback=gelesen)
        if rahmen.start > 0:
            stand.fortgesetzt += 1
        self._fertig(Datei(rahmen.pfad, rahmen.groesse), uebersprungen=False)


def direkt_entpacken(werkzeug: "str | Sequence[str]", paket: str, adresse: str, fern: str, *,
                     port: int = ftp.FTP_PORT, fortsetzen: bool = False, baum: "Sequence[dict] | None" = None,
                     passcode: str = "",
                     auf_fortschritt: "Callable[[ftp.Fortschritt], None] | None" = None,
                     abbruch: "Callable[[], bool] | None" = None, zeile: "Callable[[str], None] | None" = None,
                     popen_extra: "dict | None" = None, arbeitsordner: "str | None" = None,
                     versuche: int = ftp.VERSUCHE, pause: float = ftp.PAUSE) -> ftp.Fortschritt:
    """Entpackt ``paket`` (ein PS5-Paket) direkt nach ``fern`` auf der Konsole.

    Args:
        werkzeug: Pfad zu ``ffpfsc-pkg-tool`` - oder eine Befehlsliste, die davor steht (Tests).
        fern: Zielordner auf der Konsole; er wird samt allen Ordnern des Spiels angelegt.
        fortsetzen: Eine Datei, die dort schon in voller Groesse liegt, wird uebersprungen, eine angefangene von der Stelle
            an weitergeschrieben (``APPE``), alles andere neu gesendet. Nur richtig, wenn dort dieselbe Fassung liegt
            (gleich grosse Dateien mit anderem Inhalt blieben stehen). Ohne ``fortsetzen`` wird jede Datei neu geschrieben.
        baum: der Inhalt, wenn der Aufrufer ihn schon hat (``wz.baum``); sonst wird er gelesen.
        passcode: leer (Standard des Werkzeugs, 32 Nullen) oder genau 32 druckbare ASCII-Zeichen.
        auf_fortschritt: bekommt den :class:`konsole_ftp.Fortschritt` nach jedem Block; ``bytes`` zaehlt auch, was beim
            Fortsetzen schon auf der Konsole lag.
        abbruch: wird vor jeder Datei gefragt, nie mittendrin (siehe Modulkopf).
        zeile: bekommt die Meldungen des Werkzeugs (stderr). Aus einem Faden gerufen.
        arbeitsordner: wohin die kleine Plandatei kommt (sonst der Temp-Ordner).
        versuche, pause: wie bei :func:`konsole_ftp.ordner_senden`.

    Returns:
        Den Endstand; ``abgebrochen`` sagt, ob das Ziel unvollstaendig ist.

    Raises:
        FtpFehler: keine Verbindung, ein Pfad im Paket ist unsicher, der Server lehnt ab, die Versuche sind aufgebraucht.
        StromFehler: das Werkzeug liefert einen unbrauchbaren Strom oder stuerzt ab (mit seiner Fehlerzeile).
    """
    return _Uebertrag(werkzeug, paket, adresse, fern, port=port, fortsetzen=fortsetzen, baum=baum, passcode=passcode,
                      auf_fortschritt=auf_fortschritt, abbruch=abbruch, zeile=zeile, popen_extra=popen_extra,
                      arbeitsordner=arbeitsordner, versuche=versuche, pause=pause).ausfuehren()
