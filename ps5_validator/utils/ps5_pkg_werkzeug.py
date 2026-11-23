# -*- coding: utf-8 -*-
"""Die Huelle um ``ffpfsc-pkg-tool`` - lesen, pruefen und entpacken von PS5-Paketen (seit v1.9.71).

Das Werkzeug stammt aus dem Quelltext von **ps5-fpkg-converter 0.0.3** (GPL-3.0-or-later; darin die Engine von
ps5-ultrapack; dessen Quelltext hier ist aus der MIT-Zeit bis 2.4.1) und liegt, fuer jede Plattform einzeln gebaut,
unter ``PS5-PKG-Tool/<Plattform>/``. Es ist ein
.NET-Programm (net10.0, abhaengig von der installierten Laufzeit - die braucht das Programm ohnehin) und kapselt
LibProsperoPkg 1.2.0. Befehle, die hier gebraucht werden: ``inspect``, ``validate``, ``extract-inner`` (ganz oder
mit ``--members``). Gebaut wird seit 17.11.2026 nur noch mit Dump Forge (``utils/forge_cli.py``); ``build``, ``fw_hex`` und
``param_json_setzen`` (Mindest-Firmware, Update-Paket) sind mit dem Bau mit diesem Werkzeug entfallen.

Das Modul kennt keine Oberflaeche. Laeufe mit Fortschritt melden ueber Rueckrufe; der Abbruch beendet den ganzen
Prozessbaum. Fehler sind :class:`Fehler` mit einer Meldung fuer das Protokoll.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import struct
import threading
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import file_io

#: Ordner im Projekt (und im Bau), darin je Plattform ein Unterordner.
ORDNER = "PS5-PKG-Tool"

_Zeile = Callable[[str], None]
_Abbruch = Callable[[], bool]

#: ``PaketInfo.typ`` eines Spielordners.
TYP_ORDNER = "Ordner"
#: ``PaketInfo.typ`` eines Abbilds (``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat``) - gelesen von Dump Forge
#: (:mod:`ps5_validator.utils.forge_cli`), baubar nur zu einem Paket.
TYP_ABBILD = "Abbild"

#: So oft (Sekunden) zeigt :func:`extrahieren` ein Lebenszeichen, wenn das Werkzeug nichts meldet. Gemessen am 12.10.2026
#: an einem 31-GB-Paket auf einer Festplatte: Das Lesen des Inhalts (``list-inner``) dauerte mit kaltem Zwischenspeicher
#: 80 s (das Werkzeug liest dabei nur ~1,5 MB/s, viele kleine Stuecke verstreut), mit warmem 0,5 s - und das Fenster
#: stand die ganze Zeit auf "0 %", sodass es wie ein Absturz aussah.
_HERZSCHLAG = 1.0
#: Ab dieser Spielgroesse stehen Menge und Dateizahl in der Fortschrittszeile (darunter waeren es "0 KB").
_MENGE_AB = 16 * 1024 * 1024

#: ``[####] 42% extract (pfad)`` - so meldet das Werkzeug seinen Fortschritt.
_FORTSCHRITT = re.compile(r"\[#{2,}\]\s*(\d{1,3})%\s*(.*)")


class Fehler(Exception):
    """Ein Lauf des Werkzeugs ist gescheitert; die Meldung ist fuer das Protokoll gedacht."""


def unterordner() -> str:
    """Die Plattform dieses Rechners, wie die Bauordner heissen."""
    if sys.platform == "win32":
        return "win-x64"
    if sys.platform == "darwin":
        return "osx-arm64" if platform.machine().lower() in ("arm64", "aarch64") else "osx-x64"
    return "linux-x64"


def werkzeug_suchen(wurzeln: list[str] | None = None) -> str:
    """Pfad zu ``ffpfsc-pkg-tool`` (``.exe`` unter Windows), sonst ``""``."""
    name = "ffpfsc-pkg-tool.exe" if sys.platform == "win32" else "ffpfsc-pkg-tool"
    for wurzel in wurzeln or []:
        kandidat = os.path.join(wurzel, ORDNER, unterordner(), name)
        if os.path.isfile(kandidat):
            return kandidat
    return ""


def dotnet_ordner() -> str:
    """Der Ordner der installierten .NET-Laufzeit (fuer ``DOTNET_ROOT``), sonst ``""``."""
    umgebung = os.environ.get("DOTNET_ROOT", "")
    if umgebung and os.path.isdir(umgebung):
        return umgebung
    gefunden = shutil.which("dotnet")
    if gefunden:
        return os.path.dirname(os.path.realpath(gefunden))
    if sys.platform == "win32":
        for basis in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
            kandidat = os.path.join(basis, "dotnet")
            if os.path.isfile(os.path.join(kandidat, "dotnet.exe")):
                return kandidat
    for kandidat in ("/usr/share/dotnet", "/usr/lib/dotnet", "/usr/local/share/dotnet", "/opt/homebrew/opt/dotnet/libexec"):
        if os.path.isdir(kandidat):
            return kandidat
    return ""


def _umgebung(temp: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    if temp:
        # Wie ps5-fpkg-converter 0.0.3: Auch Zwischendateien, die nicht ueber ``--temp`` laufen (die .NET-Laufzeit
        # nimmt TMP/TEMP bzw. TMPDIR), bleiben so vom Systemlaufwerk fern.
        for name in ("TMP", "TEMP", "TMPDIR"):
            env[name] = str(temp)
    ordner = dotnet_ordner()
    if ordner:
        env["DOTNET_ROOT"] = ordner
    env.setdefault("DOTNET_NOLOGO", "1")
    env.setdefault("DOTNET_CLI_TELEMETRY_OPTOUT", "1")
    env["DOTNET_gcServer"] = "0"
    return env


def _beenden(prozess: subprocess.Popen) -> None:
    """Beendet den Prozess samt Kindern (das Werkzeug startet keine, die Laufzeit kann es)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(prozess.pid)], capture_output=True, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            prozess.kill()
    except OSError:
        pass
    try:
        prozess.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


#: Die gerade laufenden Werkzeug-Prozesse (:func:`laufen`) - fuer :func:`alle_beenden` beim Programmende.
_LAUFEND: "set[subprocess.Popen]" = set()
_LAUFEND_SPERRE = threading.Lock()
#: So oft fragt der Waechter in :func:`laufen` nach einem Abbruch (Sekunden).
_ABBRUCH_TAKT = 0.2


def laufende() -> int:
    """Wie viele Werkzeug-Prozesse gerade laufen."""
    with _LAUFEND_SPERRE:
        return sum(1 for p in _LAUFEND if p.poll() is None)


def alle_beenden() -> int:
    """Beendet jeden noch laufenden Werkzeug-Prozess samt Kindern - beim Programmende.

    Gemeldet am 03.11.2026: Nach dem Schliessen des Programms lief ``ffpfsc-pkg-tool`` unsichtbar weiter, schrieb in den
    Zielordner und hielt seine Dateien offen - der Anwender konnte sie nicht loeschen. Der Arbeitsfaden starb mit dem
    Programm, der Prozess nicht.

    Returns:
        Die Zahl der beendeten Prozesse.
    """
    with _LAUFEND_SPERRE:
        offen = [p for p in _LAUFEND if p.poll() is None]
    for prozess in offen:
        _beenden(prozess)
    return len(offen)


def _dekodieren(roh: bytes) -> str:
    """Eine Ausgabezeile des Werkzeugs als Text.

    .NET schreibt in eine umgeleitete Ausgabe in der Codeseite der Konsole, nicht in UTF-8: "LEGO\u00ae" kam als
    "LEGO\ufffd" im Protokoll an (14.10.2026). Erst UTF-8, sonst die OEM-Codeseite (Windows), zuletzt Ersatzzeichen.
    """
    try:
        return roh.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            return roh.decode("cp%d" % ctypes.windll.kernel32.GetOEMCP())
        except (LookupError, UnicodeDecodeError, AttributeError, OSError):
            pass
    return roh.decode("utf-8", errors="replace")


def menge_kurz(n: int) -> str:
    """Bytes knapp lesbar: ``31.8 GB``, ``420 MB`` (fuer die Fortschrittszeile, sprachneutral)."""
    if n >= 1024 ** 3:
        return "%.1f GB" % (n / 1024 ** 3)
    if n >= 1024 ** 2:
        return "%d MB" % (n // 1024 ** 2)
    return "%d KB" % max(0, n // 1024)


def laufen(werkzeug: str, argumente: list[str], *, zeile: _Zeile | None = None, abbruch: _Abbruch | None = None,
           popen_extra: dict | None = None, temp: str | None = None) -> tuple[int, str]:
    """Startet das Werkzeug und liest seine Ausgabe zeilenweise (stdout und stderr zusammen).

    ``temp`` setzt zusaetzlich TMP, TEMP und TMPDIR des Werkzeugs auf diesen Ordner (``_umgebung``).

    Returns:
        ``(Rueckgabewert, gesamte Ausgabe)``. Bei Abbruch ``(-1, ...)``.

    Raises:
        Fehler: das Werkzeug laesst sich nicht starten.
    """
    if sys.platform != "win32":
        # Aus einem Archiv oder einem Windows-Dateisystem kommt die Datei ohne Ausfuehrungsrecht.
        try:
            os.chmod(werkzeug, os.stat(werkzeug).st_mode | 0o111)
        except OSError:
            pass
    extra = dict(popen_extra or {})
    if sys.platform == "win32" and not extra.get("creationflags"):
        # Ohne dieses Flag oeffnet jeder Start des Konsolenwerkzeugs ein schwarzes Fenster (gemeldet 31.10.2026: beim
        # Laden eines Pakets drei bis vier hintereinander - die PlayGo-Pruefung rief ``baum`` ohne ``popen_extra``).
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if abbruch and abbruch():
        return -1, ""
    try:
        prozess = subprocess.Popen([werkzeug, *argumente], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=_umgebung(temp), bufsize=0, **extra)
    except OSError as exc:
        raise Fehler("Das Werkzeug laesst sich nicht starten: %s" % exc) from exc
    assert prozess.stdout is not None
    with _LAUFEND_SPERRE:
        _LAUFEND.add(prozess)
    gesammelt: list[str] = []
    rest = b""
    # Der Abbruch wartet nicht auf die naechste Ausgabezeile: Das Werkzeug schweigt beim Lesen grosser Pakete und beim
    # Packen minutenlang, und ``read`` blockiert so lange (gemessen 03.11.2026: ABBRECHEN wirkte erst nach 4 s, beim
    # Programmende gar nicht). Ein Waechter beendet den Prozess, sobald der Abbruch verlangt ist - dann endet ``read``.
    abgebrochen = threading.Event()
    fertig = threading.Event()

    def waechter() -> None:
        while not fertig.wait(_ABBRUCH_TAKT):
            try:
                verlangt = bool(abbruch())
            except Exception:  # noqa: BLE001 - ein Rueckruf darf den Waechter nicht beenden
                verlangt = False
            if verlangt:
                abgebrochen.set()
                _beenden(prozess)
                return

    if abbruch:
        threading.Thread(target=waechter, daemon=True, name="ps5pkg-abbruch").start()
    try:
        while True:
            if abgebrochen.is_set() or (abbruch and abbruch()):
                _beenden(prozess)
                return -1, "".join(gesammelt)
            stueck = prozess.stdout.read(4096)
            if not stueck:
                if abgebrochen.is_set():
                    return -1, "".join(gesammelt)
                break
            rest += stueck
            while True:
                stellen = [i for i in (rest.find(b"\n"), rest.find(b"\r")) if i >= 0]
                if not stellen:
                    break
                i = min(stellen)
                text = _dekodieren(rest[:i]).strip()
                rest = rest[i + 1:]
                if text:
                    gesammelt.append(text + "\n")
                    if zeile:
                        zeile(text)
        if rest.strip():
            text = _dekodieren(rest).strip()
            gesammelt.append(text + "\n")
            if zeile:
                zeile(text)
        rc = prozess.wait()
        if abgebrochen.is_set():
            return -1, "".join(gesammelt)
        return rc, "".join(gesammelt)
    finally:
        fertig.set()
        if prozess.poll() is None:
            _beenden(prozess)
        with _LAUFEND_SPERRE:
            _LAUFEND.discard(prozess)
        # Das Lesende der Ausgabe-Leitung gehoert diesem Aufruf: Ohne Schliessen bleibt es bis zur Speicherbereinigung
        # offen (ResourceWarning "unclosed file", gemessen 16.11.2026 beim Lesen eines Abbilds mit Dump Forge).
        try:
            prozess.stdout.close()
        except OSError:
            pass


def _json_aus(ausgabe: str) -> dict[str, Any]:
    anfang = ausgabe.find("{")
    ende = ausgabe.rfind("}")
    if anfang < 0 or ende < anfang:
        raise Fehler("Keine Antwort des Werkzeugs: %s" % ausgabe.strip()[:300])
    try:
        return json.loads(ausgabe[anfang:ende + 1])
    except ValueError as exc:
        raise Fehler("Antwort des Werkzeugs nicht lesbar: %s" % exc) from exc


def _fehlertext(ausgabe: str) -> str:
    zeilen = [z for z in ausgabe.splitlines() if z.startswith(("[error]", "[usage]"))]
    return (zeilen[-1] if zeilen else ausgabe.strip().splitlines()[-1] if ausgabe.strip() else "kein Text")[:300]


#: Ein Debug-Passcode des Werkzeugs: genau 32 druckbare ASCII-Zeichen (0x20-0x7e). Leer heisst "der Standard des
#: Werkzeugs" (32 Nullen) - dann wird ``--passcode`` gar nicht erst mitgegeben.
PASSCODE_LAENGE = 32
PASSCODE_MUSTER = re.compile(r"^[\x20-\x7e]{32}$")


def passcode_gueltig(passcode: str) -> bool:
    return passcode == "" or bool(PASSCODE_MUSTER.match(passcode))


def _passcode_args(passcode: str) -> list[str]:
    return ["--passcode", passcode] if passcode else []


def inspect(werkzeug: str, paket: str, popen_extra: dict | None = None) -> dict[str, Any]:
    """Kopfdaten eines Pakets (``inspect --json``): Typ, Content-ID, Title-ID, Eintraege.

    Liest nur den aeusseren Kopf (unverschluesselt) - kennt deshalb keinen Passcode, anders als die Befehle unten,
    die das innere Abbild lesen.
    """
    rc, aus = laufen(werkzeug, ["inspect", paket, "--json"], popen_extra=popen_extra)
    if rc != 0:
        raise Fehler(_fehlertext(aus))
    return _json_aus(aus)


def pruefen(werkzeug: str, paket: str, *, passcode: str = "", zeile: _Zeile | None = None,
            abbruch: _Abbruch | None = None, popen_extra: dict | None = None) -> dict[str, Any]:
    """Die Pruefliste des Werkzeugs (``validate --json``): ``{"pass": n, "warn": n, "fail": n, "results": [...]}``."""
    rc, aus = laufen(werkzeug, ["validate", paket, "--json"] + _passcode_args(passcode), zeile=zeile, abbruch=abbruch,
                     popen_extra=popen_extra)
    if rc == -1:
        raise Fehler("abgebrochen")
    try:
        return _json_aus(aus)
    except Fehler:
        raise Fehler(_fehlertext(aus)) from None


#: Eine Title-ID, wie sie in einen Dateinamen darf: vier Buchstaben und fuenf Ziffern (``PPSA01234``, ``CUSA12345``).
TITLE_ID_NAME = re.compile(r"[A-Za-z]{4}\d{5}")


@dataclass
class PaketInfo:
    """Was das Fenster ueber ein Paket zeigt."""
    pfad: str
    groesse: int = 0
    typ: str = ""                 #: ``FullDebug`` usw. (``package_type``)
    content_id: str = ""
    title_id: str = ""
    drm_typ: int = 0
    titel: str = ""
    param: dict = field(default_factory=dict)
    icon: str = ""                #: Pfad der ausgelesenen ``icon0.png`` (leer, wenn keine)
    arbeit: str = ""              #: Ordner mit dem ausgelesenen Cover - gehoert dem Fenster, wird beim Schliessen entfernt
    #: Nur bei einem Abbild: Forges Formatname (``exfat``, ``ffpkg``, ``ffpfs``, ``ffpfsc``).
    abbild: str = ""
    #: Forges Vorabbefunde zur Quelle (Fehler und Warnungen, je Zeile einer) - nur von Dump Forge gelesene Quellen.
    befunde: list = field(default_factory=list)
    #: Ein DLC oder Update (kein ``eboot.bin``, aber ein gueltiges ``param.json``) - baut nur zu einem Paket.
    zusatzinhalt: bool = False
    #: Ein Patch-Paket (``\x7fLIH``): wird nur gelesen, nie umgewandelt.
    patch: bool = False
    #: Nur bei einer von Dump Forge gelesenen Quelle: ``forge_cli.QuellFakten`` (AMPR, Packs, DLC, PlayGo), sonst ``None``.
    fakten: object = None
    #: Die Groesse eines Spielordners ist noch nicht gezaehlt (``ordner_lesen(groesse=False)``): ``groesse`` ist 0 und gilt nicht.
    groesse_offen: bool = False
    #: Das Zaehlen scheiterte ganz (Ordner nicht lesbar, keine Datei gezaehlt): ``groesse`` ist 0 und gilt nicht - die Anzeige sagt
    #: "unbekannt".
    groesse_unbekannt: bool = False
    #: Das Zaehlen traf nicht lesbare Eintraege, einige Dateien waren aber zu zaehlen: ``groesse`` ist eine untere Schranke ("mind. ...").
    #: Die Platzpruefung rechnet mit ihr (frueher, mit ``os.walk``, galt dieselbe Teilsumme still als echte Groesse).
    groesse_unvollstaendig: bool = False

    def __post_init__(self) -> None:
        # Die Kennung geht in Datei- und Ordnernamen (``anzeigename``, ``forge_cli.dateiname_fuer``) und damit in Pfade, die das Fenster
        # anlegt, ersetzt und bei Fehlern wieder loescht. Was keine Title-ID ist - etwa ein ``X\..\..\Y`` aus einer manipulierten
        # param.json -, bleibt weg: Der Name entsteht dann ohne Kennung, und nie ausserhalb des Ziels (Pruefung 18.11.2026; die Pruefung
        # ``TITLE_ID`` im frueheren Bau von LibProsperoPkg war mit diesem entfallen).
        if not TITLE_ID_NAME.fullmatch(self.title_id or ""):
            self.title_id = ""

    @property
    def ist_ordner(self) -> bool:
        """Ein Spielordner (Dump) statt eines Pakets."""
        return self.typ == TYP_ORDNER

    @property
    def ist_abbild(self) -> bool:
        """Ein Abbild (``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat``) statt eines Pakets oder Spielordners."""
        return self.typ == TYP_ABBILD

    @property
    def ist_quelle(self) -> bool:
        """Etwas, aus dem ein Paket erst gebaut wird (Spielordner oder Abbild) - kein fertiges Paket."""
        return self.typ in (TYP_ORDNER, TYP_ABBILD)

    @property
    def debug(self) -> bool:
        return self.typ.lower().endswith("debug") or self.typ.lower().startswith("fulldebug")

    @property
    def version(self) -> str:
        return str(self.param.get("contentVersion", "") or "")


def titel_aus_param(param: dict) -> str:
    """Der Titel aus ``localizedParameters`` (Standardsprache zuerst, dann en-US, dann irgendeiner)."""
    lokal = param.get("localizedParameters")
    if not isinstance(lokal, dict):
        return ""
    reihenfolge = [str(lokal.get("defaultLanguage", "") or ""), "en-US"] + [k for k in lokal if isinstance(lokal[k], dict)]
    for sprache in reihenfolge:
        eintrag = lokal.get(sprache)
        if isinstance(eintrag, dict) and str(eintrag.get("titleName", "") or "").strip():
            return str(eintrag["titleName"]).strip()
    return ""


def lesen(werkzeug: str, paket: str, arbeitsordner: str | None = None, *, passcode: str = "",
         popen_extra: dict | None = None) -> PaketInfo:
    """Liest ein Paket fuer die Anzeige: Kopfdaten, ``param.json`` und das Cover ``icon0.png``.

    ``param.json`` und ``icon0.png`` werden einzeln in einen kleinen Ordner herausgeholt (0,3 s gemessen an einem
    939-MB-Paket); das Paket selbst wird nicht entpackt. ``arbeitsordner`` ist die Ablage fuer das Cover, sonst ein
    eigener Ordner unter dem Temp-Ordner (``ps5conv_pkgcover_*``); das Cover bleibt dort liegen, bis es nicht mehr
    gebraucht wird. Ein falscher ``passcode`` liest den aeusseren Kopf trotzdem, aber weder param.json noch Cover.
    """
    kopf = inspect(werkzeug, paket, popen_extra)
    info = PaketInfo(pfad=paket, groesse=int(kopf.get("size_bytes", 0) or 0), typ=str(kopf.get("package_type", "") or ""),
                     content_id=str(kopf.get("content_id", "") or ""), title_id=str(kopf.get("title_id", "") or ""),
                     drm_typ=int(kopf.get("drm_type", 0) or 0))
    try:
        ordner = tempfile.mkdtemp(prefix="ps5conv_pkgcover_", dir=arbeitsordner or None)
    except OSError:
        return info
    info.arbeit = ordner
    liste = os.path.join(ordner, "teile.txt")
    try:
        Path(liste).write_text("sce_sys/param.json\nsce_sys/icon0.png\n", encoding="utf-8")
    except OSError:
        return info
    rc, _aus = laufen(werkzeug, ["extract-inner", paket, os.path.join(ordner, "teile"), "--members", liste]
                      + _passcode_args(passcode), popen_extra=popen_extra)
    teile = os.path.join(ordner, "teile", "sce_sys")
    param_pfad = os.path.join(teile, "param.json")
    if os.path.isfile(param_pfad):
        try:
            info.param = json.loads(Path(param_pfad).read_text(encoding="utf-8-sig"))
            info.titel = titel_aus_param(info.param)
        except (OSError, ValueError):
            pass
    icon = os.path.join(teile, "icon0.png")
    if os.path.isfile(icon):
        info.icon = icon
    return info


def ordner_ist_spiel(ordner: str) -> bool:
    """Liegt in ``ordner`` ein Spiel (``sce_sys/param.json``)?"""
    return os.path.isfile(os.path.join(ordner, "sce_sys", "param.json"))


#: Die Bilder in ``sce_sys``, die ein Paket als Eintraege traegt (die ``.dds`` daneben sind Rohdaten, kein PNG).
SCE_SYS_BILDER = ("icon0.png", "pic0.png", "pic1.png", "pic2.png")
_PNG_KOPF = b"\x89PNG\r\n\x1a\n"

#: Arten eines beschaedigten PNG (:func:`png_fehler`) - die Oberflaeche macht daraus Text.
PNG_KOPF_FEHLT, PNG_KETTE_DEFEKT, PNG_ENDE_DEFEKT = "kopf", "kette", "ende"


def png_fehler(daten: bytes) -> str:
    """Prueft ein PNG wie ein Leser: Kennung, Kette der Datenbloecke mit CRC-32, ``IEND``, nichts dahinter.

    Returns:
        ``""`` fuer ein ganzes PNG, sonst :data:`PNG_KOPF_FEHLT` (keine PNG-Kennung - so sah ein beschaedigtes ``pic2.png`` in einem
        echten Dump aus: 532 Zufallsbytes), :data:`PNG_KETTE_DEFEKT` (ein Datenblock ueber das Dateiende hinaus oder mit falscher
        Pruefsumme, also abgeschnitten oder verfaelscht) oder :data:`PNG_ENDE_DEFEKT` (``IEND`` fehlt, oder es folgen Bytes danach).
    """
    if daten[:8] != _PNG_KOPF:
        return PNG_KOPF_FEHLT
    pos = 8
    while pos + 12 <= len(daten):
        laenge, = struct.unpack(">I", daten[pos:pos + 4])
        art = daten[pos + 4:pos + 8]
        if laenge > 0x7FFFFFFF or pos + 12 + laenge > len(daten):       # die PNG-Norm erlaubt hoechstens 2^31-1 Bytes je Block
            return PNG_KETTE_DEFEKT
        crc, = struct.unpack(">I", daten[pos + 8 + laenge:pos + 12 + laenge])
        if zlib.crc32(daten[pos + 4:pos + 8 + laenge]) & 0xFFFFFFFF != crc:
            return PNG_KETTE_DEFEKT
        pos += 12 + laenge
        if art == b"IEND":
            return "" if pos == len(daten) else PNG_ENDE_DEFEKT
    return PNG_ENDE_DEFEKT                       # die Kette endet ohne IEND (an einer Blockgrenze abgeschnitten)


#: Groessere Bilder werden nicht beurteilt (wie beim Abbild: :data:`programm_sdk.SCE_SYS_HOECHSTENS`).
BILD_HOECHSTENS = 8 * 1024 * 1024


def _bilder_im_ordner(ordner: str) -> "dict[str, bytes]":
    """Die Bilder aus ``<ordner>/sce_sys`` als ``{name klein: Inhalt}``; die Schreibweise der Namen zaehlt nicht (Linux, macOS)."""
    sce_sys = os.path.join(ordner, "sce_sys")
    try:
        namen = os.listdir(sce_sys)
    except OSError:
        return {}
    gefunden: dict[str, bytes] = {}
    for name in namen:
        schluessel = name.lower()
        if schluessel not in SCE_SYS_BILDER or schluessel in gefunden:
            continue
        pfad = os.path.join(sce_sys, name)
        try:
            if not os.path.isfile(pfad) or os.path.getsize(pfad) > BILD_HOECHSTENS:
                continue
            with open(pfad, "rb") as datei:
                gefunden[schluessel] = datei.read()
        except OSError:
            continue
    return gefunden


def bilder_befunde(quelle: str, mkpfs_ordner: str = "") -> "list[tuple[str, int, str]]":
    """Die beschaedigten PNG in ``sce_sys`` (:data:`SCE_SYS_BILDER`) als ``(Name, Groesse, Art)``; nur lesend.

    ``quelle`` ist ein Spielordner oder (seit 23.11.2026) ein Abbild (``.ffpkg``, ``.exfat``, ``.ffpfs``, ``.ffpfsc``), aus dem die Bilder
    gelesen werden, ohne es zu entpacken (:func:`programm_sdk.sce_sys_dateien_in_abbild`). Dump Forge packt so eine Datei unveraendert ins
    Paket und sagt nichts dazu (gemessen 22.11.2026 mit Forge 0.5.7: 532 Zufallsbytes als ``pic2.png``, mit und ohne ``pic2.dds``
    daneben, ebenso ein abgeschnittenes PNG). Nicht lesbare und zu grosse Dateien werden uebergangen: Das Lesen soll den Bau nie
    aufhalten.
    """
    if os.path.isdir(quelle):
        bilder = _bilder_im_ordner(quelle)
    else:
        from ps5_validator.utils import programm_sdk                # spaet: braucht MkPFS erst hier
        bilder = programm_sdk.sce_sys_dateien_in_abbild(quelle, SCE_SYS_BILDER, mkpfs_ordner)
    befunde: list[tuple[str, int, str]] = []
    for name in SCE_SYS_BILDER:
        daten = bilder.get(name)
        if daten is None:
            continue
        art = png_fehler(daten)
        if art:
            befunde.append((name, len(daten), art))
    return befunde


#: Nach so vielen gezaehlten Dateien meldet ``ordner_groesse`` den Zwischenstand (``fortschritt``).
GROESSE_MELDESCHRITT = 1000


class GroesseAbgebrochen(Exception):
    """:func:`ordner_groesse` wurde ueber ``abbruch`` beendet - es gibt keine Summe."""


class GroesseUnvollstaendig(OSError):
    """:func:`ordner_groesse` traf nicht lesbare Eintraege, zaehlte aber ``dateien`` Dateien: ``summe`` ist nur eine untere Schranke.

    Eine ``OSError``, damit jeder Aufrufer, der "nicht lesbar" schon abfaengt, weiter funktioniert; wer die Teilsumme nutzen will
    (Platzpruefung, Anzeige "mind. ..."), faengt diese Klasse vorher.
    """

    def __init__(self, text: str, summe: int, dateien: int) -> None:
        super().__init__(text)
        self.summe = int(summe)
        self.dateien = int(dateien)


def ordner_groesse(ordner: str, melden: _Zeile | None = None, fortschritt: "Callable[[int], None] | None" = None,
                   abbruch: "Callable[[], bool] | None" = None) -> int:
    """Die Summe der Dateigroessen unter ``ordner``; ``melden`` bekommt am Ende eine Zeile (Dateizahl).

    Gezaehlt wird mit ``os.scandir``: ``DirEntry.stat()`` liefert die Groesse unter Windows aus den Verzeichnisdaten, ohne einen
    weiteren Aufruf je Datei. Die fruehere Fassung (``os.walk`` und ``os.path.getsize`` je Datei) brauchte fuer Ghost of Yotei
    (84.218 Dateien, 150,75 GB) 348 s; ``scandir`` zaehlt dieselben 84.218 Dateien und dieselben Bytes in rund 14 s (gemessen
    19.11.2026, Verzeichnisdaten schon im Cache). Verknuepfungen und NTFS-Verbindungen zu Ordnern werden nicht verfolgt und nicht
    gezaehlt (``os.walk`` folgte einer Verbindung, die auf einen Elternordner zeigt, bis zur Pfadgrenze). ``melden`` bekommt eine
    Warnung, wenn der Ordner Verknuepfungen, Verbindungen oder andere Reparsepunkte enthaelt: Dump Forge lehnt ihn dann ab.

    ``fortschritt`` bekommt alle :data:`GROESSE_MELDESCHRITT` Dateien die bisherige Zahl, damit die Anzeige zeigen kann, dass etwas
    geschieht. ``abbruch`` wird je Verzeichnis gefragt; liefert es ``True``, endet das Zaehlen mit :class:`GroesseAbgebrochen`.

    Raises:
        GroesseUnvollstaendig: Verzeichnisse oder Dateien waren nicht lesbar (Zugriff verweigert, ``System Volume Information`` in der
            Laufwerkswurzel), einige Dateien waren aber zu zaehlen: Die Summe waere zu klein und saehe doch wie eine echte Groesse aus -
            sie steht deshalb nur in der Ausnahme (``summe``, untere Schranke). ``melden`` bekommt vorher eine Warnung mit der Zahl
            der Fehler. Eine ``OSError``.
        OSError: Es war nichts zu zaehlen und etwas nicht lesbar (Laufwerk getrennt, Ordner ohne Zugriff): keine Groesse.
        GroesseAbgebrochen: ``abbruch`` lieferte ``True``.
    """
    def beobachten(_summe: int, dateien: int) -> None:
        if fortschritt is not None and dateien % GROESSE_MELDESCHRITT == 0:
            fortschritt(dateien)

    ergebnis = file_io.groesse_summieren(ordner, beobachter=beobachten, abbruch=abbruch)
    if ergebnis.abgebrochen:
        raise GroesseAbgebrochen(ordner)
    if ergebnis.verknuepfungen and melden:
        # Dump Forge lehnt einen Ordner mit Verknuepfung oder Junction ab (``symlink (not followed)``, gemessen 19.11.2026): Der Fehler kam
        # bisher erst nach STARTEN, englisch. Hier steht er vorher.
        melden("[WARNUNG] %s: %d symbolische Verknuepfung(en), Junction(s) oder Reparsepunkt(e) (z. B. OneDrive-Platzhalter) im Ordner (%s%s) - "
               "Dump Forge wandelt so einen Ordner nicht um; entferne sie vor dem Umwandeln"
               % (os.path.basename(ordner), ergebnis.verknuepfungen, ", ".join(ergebnis.beispiele),
                  ", ..." if ergebnis.verknuepfungen > len(ergebnis.beispiele) else ""))
    if ergebnis.fehler:
        text = "%d Eintraege unter %s nicht lesbar" % (ergebnis.fehler, ordner)
        if melden:
            melden("[WARNUNG] %s: %d Eintraege nicht lesbar - die Groesse ist unvollstaendig%s"
                   % (os.path.basename(ordner), ergebnis.fehler,
                      " (mindestens %.2f GB in %d Dateien)" % (ergebnis.summe / 1024 ** 3, ergebnis.dateien)
                      if ergebnis.dateien else ""))
        if ergebnis.dateien:
            raise GroesseUnvollstaendig(text, ergebnis.summe, ergebnis.dateien)
        raise OSError(text)
    if melden:
        melden("[info] %s: %d Dateien, %.2f GB" % (os.path.basename(ordner), ergebnis.dateien, ergebnis.summe / 1024 ** 3))
    return ergebnis.summe


def ordner_lesen(ordner: str, arbeitsordner: str | None = None, melden: _Zeile | None = None,
                 groesse: bool = True) -> PaketInfo:
    """Liest einen Spielordner fuer die Anzeige: ``param.json``, Cover (als Kopie) und Groesse.

    Das Cover wird in einen eigenen Ordner kopiert (``PaketInfo.arbeit``); nur dieser wird beim Schliessen des
    Fensters entfernt - der Spielordner selbst wird nie angefasst.

    Args:
        groesse: ``False`` zaehlt die Dateien nicht (``PaketInfo.groesse_offen``): Titel und Cover sind sofort da, die
            Groesse holt der Aufrufer mit :func:`ordner_groesse` nach. Bei einem Spiel mit zehntausenden Dateien dauert
            das Zaehlen Minuten (Ghost of Yotei: 348 s) - so lange erschien das Spiel auf Seite 7 sonst gar nicht.

    Raises:
        Fehler: keine lesbare ``sce_sys/param.json``.
    """
    pfad = os.path.join(ordner, "sce_sys", "param.json")
    try:
        param = json.loads(Path(pfad).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise Fehler("param.json nicht lesbar: %s" % exc) from exc
    if not isinstance(param, dict):
        raise Fehler("param.json hat nicht die erwartete Form")
    gezaehlt, unbekannt, teilweise = 0, False, False
    if groesse:
        try:
            gezaehlt = ordner_groesse(ordner, melden)
        except GroesseUnvollstaendig as exc:                  # Teilsumme: nur als untere Schranke (``groesse_unvollstaendig``)
            gezaehlt, teilweise = exc.summe, True
        except OSError:                                       # nichts zu zaehlen: keine Groesse (``groesse_unbekannt``)
            unbekannt = True
    info = PaketInfo(pfad=ordner, groesse=gezaehlt, typ=TYP_ORDNER,
                     content_id=str(param.get("contentId", "") or ""), title_id=str(param.get("titleId", "") or ""),
                     titel=titel_aus_param(param), param=param, groesse_offen=not groesse, groesse_unbekannt=unbekannt,
                     groesse_unvollstaendig=teilweise)
    icon = os.path.join(ordner, "sce_sys", "icon0.png")
    if os.path.isfile(icon):
        try:
            info.arbeit = tempfile.mkdtemp(prefix="ps5conv_pkgcover_", dir=arbeitsordner or None)
            kopie = os.path.join(info.arbeit, "icon0.png")
            shutil.copyfile(icon, kopie)
            info.icon = kopie
        except OSError:
            pass
    return info


def baum(werkzeug: str, paket: str, popen_extra: dict | None = None, *, passcode: str = "",
         abbruch: _Abbruch | None = None) -> list[dict]:
    """Der Inhalt des Spiels (``list-inner``): ``[{"path": ..., "type": "file"|"dir", "size": ...}, ...]``."""
    rc, aus = laufen(werkzeug, ["list-inner", paket] + _passcode_args(passcode), popen_extra=popen_extra,
                     abbruch=abbruch)
    if rc == -1:
        raise Fehler("abgebrochen")
    if rc != 0:
        raise Fehler(_fehlertext(aus))
    eintraege = _json_aus(aus).get("entries", [])
    return [e for e in eintraege if isinstance(e, dict) and e.get("path")]


def mitglieder_extrahieren(werkzeug: str, paket: str, ziel: str, pfade: "list[str]", *,
                            passcode: str = "", zeile: "_Zeile | None" = None,
                            abbruch: "_Abbruch | None" = None,
                            popen_extra: "dict | None" = None,
                            arbeitsordner: str | None = None) -> None:
    """Entpackt nur die genannten Pfade aus dem Paket (``extract-inner --members``).

    ``pfade`` ist eine Liste relativer Pfade (wie von :func:`baum` geliefert), z. B.
    ``["/app0/eboot.bin", "/sce_sys/param.json"]``. Ein Verzeichnispfad entpackt den
    ganzen Teilbaum.

    ``arbeitsordner``: wo die (sofort wieder geloeschte) Mitgliederliste entsteht - wie
    bei den anderen Zwischendateien dieses Moduls der konfigurierte Arbeitsordner statt
    des System-Temp, leer/``None`` faellt auf System-Temp zurueck (Nutzerwunsch
    17.10.2026: alle temporaeren Dateien dorthin, nicht nur die groesseren).

    Raises:
        Fehler: Fehler des Werkzeugs oder beim Abbruch (Text ``"abgebrochen"``).
    """
    import tempfile
    os.makedirs(ziel, exist_ok=True)
    fd, liste = tempfile.mkstemp(prefix="ps5conv_mitglieder_", suffix=".txt", dir=arbeitsordner or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(pfade) + "\n")
        rc, aus = laufen(werkzeug, ["extract-inner", paket, ziel, "--members", liste]
                         + _passcode_args(passcode), zeile=zeile, abbruch=abbruch, popen_extra=popen_extra)
    finally:
        try:
            os.unlink(liste)
        except OSError:
            pass
    if rc == -1:
        raise Fehler("abgebrochen")
    if rc != 0:
        raise Fehler(_fehlertext(aus))


def extrahieren(werkzeug: str, paket: str, ziel: str, *, passcode: str = "", zeile: _Zeile | None = None,
                fortschritt: Callable[[int, str], None] | None = None, abbruch: _Abbruch | None = None,
                popen_extra: dict | None = None, arbeitsordner: str | None = None,
                platz_pruefen: Callable[[int], str] | None = None) -> str:
    """Entpackt das ganze Spiel (``/app0`` samt ``sce_sys``) nach ``ziel``.

    Der volle Entpack des Werkzeugs (``extract-inner`` ohne ``--members``) meldet keinen Fortschritt. Deshalb wird
    erst der Inhalt gelistet (``list-inner``) und dann alles ueber ``--members`` entpackt, das je Datei meldet.
    Gemessen am 09.10.2026 an einem 939-MB-Paket: beide Wege 53 s, 118 von 118 Dateien, alle SHA-256 gleich. Scheitert
    der Weg ueber ``--members``, folgt der volle Entpack.

    Returns:
        Die Schlusszeile des Werkzeugs (``OK - extracted N file(s) ...``).

    Raises:
        Fehler: das Werkzeug meldet einen Fehler oder bricht ohne ``OK`` ab; ``abgebrochen`` beim Abbruch.
    """
    Path(ziel).mkdir(parents=True, exist_ok=True)
    beginn = time.monotonic()
    stand: dict = {"p": 0, "datei": "", "zuletzt": beginn, "dateien": [], "gesamt": 0}
    ende = threading.Event()                          # weckt den Herzschlag sofort, wenn der Aufruf endet

    def fertige_dateien() -> int:
        """Wie viele Dateien schon vollstaendig im Ziel liegen - ohne die gerade geschriebene.

        Die laufende Datei zaehlt nie mit: Windows meldet ihre Groesse schon vor dem Schreiben voll.
        """
        dateien = stand["dateien"]
        if not dateien or len(dateien) > 20000:
            return 0
        anzahl = 0
        for rel, groesse in dateien:
            if rel == stand["datei"]:
                continue
            try:
                if os.path.getsize(os.path.join(ziel, rel)) >= groesse:
                    anzahl += 1
            except OSError:
                continue
        return anzahl

    def zeile_bauen(mit_zeit: bool) -> str:
        """``<Datei> · 24.2 GB / 110.1 GB · 109/194 · m:ss`` - die Menge folgt dem Prozentwert des Werkzeugs."""
        teile = [stand["datei"] or "\u2026"]
        if stand["gesamt"] >= _MENGE_AB:
            teile.append("%s / %s" % (menge_kurz(int(stand["gesamt"] * stand["p"] / 100)), menge_kurz(stand["gesamt"])))
            teile.append("%d/%d" % (fertige_dateien(), len(stand["dateien"])))
        if mit_zeit:
            dauer = int(time.monotonic() - beginn)
            teile.append("%d:%02d" % (dauer // 60, dauer % 60))
        return " \u00b7 ".join(teile)

    def jede(text: str) -> None:
        treffer = _FORTSCHRITT.match(text)
        if treffer and fortschritt:
            # "[####] 42% extract (Media/a.dat)" - der Dateiname steht in Klammern. Der Wert des Werkzeugs ist
            # bytegenau (geschriebene Bytes / Gesamtbytes); die Anzeige laeuft nur vorwaerts.
            datei = re.search(r"\((.*)\)\s*$", treffer.group(2))
            stand["p"] = max(stand["p"], min(100, int(treffer.group(1))))
            stand["datei"] = datei.group(1) if datei else ""
            stand["zuletzt"] = time.monotonic()
            fortschritt(stand["p"], zeile_bauen(False) if stand["gesamt"] >= _MENGE_AB else stand["datei"])
        elif zeile:
            zeile(text)

    def herzschlag() -> None:
        """Meldet sich, solange das Werkzeug schweigt - mit dem letzten Stand und der Zeit seit dem Start.

        Bis zum 14.10.2026 kam der Prozentwert zwischen zwei Meldungen des Werkzeugs aus der Groesse der Dateien im
        Ziel. Windows meldet die gerade geschriebene Datei aber schon vor dem Schreiben voll: Die Anzeige sprang vor
        und beim naechsten Wert des Werkzeugs wieder zurueck. Jetzt bleibt der Wert der des Werkzeugs (nichts wird
        erfunden), das Lebenszeichen zeigt Datei, Menge und Zeit.
        """
        while not ende.wait(_HERZSCHLAG):
            if time.monotonic() - stand["zuletzt"] >= _HERZSCHLAG:
                try:
                    fortschritt(stand["p"], zeile_bauen(True))
                except Exception:  # noqa: BLE001 - ein Rueckruf darf das Entpacken nie beenden
                    return

    if fortschritt is not None:
        threading.Thread(target=herzschlag, daemon=True, name="ps5pkg-herzschlag").start()
    liste = ""
    passcode_args = _passcode_args(passcode)
    argumente = ["extract-inner", paket, ziel] + passcode_args
    platz_meldung = ""
    try:
        if zeile:
            zeile("[info] Paketinhalt wird gelesen - bei einem grossen Paket auf einer Festplatte kann das eine Minute "
                  "dauern ...")
        eintraege = baum(werkzeug, paket, popen_extra, passcode=passcode, abbruch=abbruch)
        stand["dateien"] = [(e["path"], int(e.get("size") or 0)) for e in eintraege if e.get("type", "file") == "file"]
        stand["gesamt"] = sum(g for _p, g in stand["dateien"])
        # Erst jetzt ist die entpackte Groesse bekannt - ein komprimiertes Paket waechst um ein Vielfaches (LEGO Batman:
        # 31,8 GB Paket, 110 GB entpackt). Reicht der Platz nicht, endet es hier statt nach Minuten mitten im Schreiben.
        # (Nicht hier werfen: das except darunter faengt Fehler ab und entpackt dann am Stueck.)
        if platz_pruefen is not None and stand["gesamt"]:
            platz_meldung = platz_pruefen(stand["gesamt"]) or ""
        if zeile:
            zeile("[info] Paketinhalt gelesen: %d Eintraege in %d s" % (len(eintraege), int(time.monotonic() - beginn)))
        if eintraege:
            handle, liste = tempfile.mkstemp(prefix="ps5conv_teile_", suffix=".txt", dir=arbeitsordner or None)
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write("\n".join(e["path"] for e in eintraege) + "\n")
            argumente = ["extract-inner", paket, ziel, "--members", liste] + passcode_args
    except (Fehler, OSError) as exc:
        if abbruch and abbruch():
            ende.set()
            raise Fehler("abgebrochen") from exc
        if zeile:
            zeile("[info] kein Fortschritt je Datei moeglich (%s) - voller Entpack" % exc)
        liste = ""
    except BaseException:
        ende.set()                                    # der Herzschlag darf nie ueber den Aufruf hinaus weiterlaufen
        raise
    if abbruch and abbruch():
        ende.set()
        if liste:
            try:
                os.remove(liste)
            except OSError:
                pass
        raise Fehler("abgebrochen")
    if platz_meldung:
        ende.set()
        if liste:
            try:
                os.remove(liste)
            except OSError:
                pass
        raise Fehler(platz_meldung)
    try:
        rc, aus = laufen(werkzeug, argumente, zeile=jede, abbruch=abbruch, popen_extra=popen_extra)
        if rc == -1:
            raise Fehler("abgebrochen")
        ok = [z for z in aus.splitlines() if z.startswith("OK")]
        if (rc != 0 or not ok) and liste:
            if zeile:
                zeile("[info] Entpacken je Datei gescheitert (%s) - voller Entpack" % _fehlertext(aus))
            rc, aus = laufen(werkzeug, ["extract-inner", paket, ziel] + passcode_args, zeile=jede, abbruch=abbruch,
                             popen_extra=popen_extra)
            if rc == -1:
                raise Fehler("abgebrochen")
            ok = [z for z in aus.splitlines() if z.startswith("OK")]
        if rc != 0 or not ok:
            raise Fehler(_fehlertext(aus))
        return ok[-1]
    finally:
        ende.set()
        if liste:
            try:
                os.remove(liste)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# PlayGo-Erkennung (seit v1.9.83)
# ---------------------------------------------------------------------------

_PLAYGO_MERKMALE: tuple[str, ...] = (
    "sce_sys/playgo-scenario.json",
    "sce_sys/playgo-chunk.dat",
    "sce_sys/playgo_chunk.dat",
)


def playgo_erklaert_ordner(pfad: str) -> str:
    """Prueft einen Dump-Ordner auf PlayGo-Abhaengigkeit.

    Gibt das erste gefundene Merkmal zurueck (relativer Pfad),
    oder "" wenn keines vorhanden ist.
    """
    for merkmal in _PLAYGO_MERKMALE:
        kandidat = os.path.join(pfad, *merkmal.split("/"))
        if os.path.isfile(kandidat):
            return merkmal
    return ""


def _playgo_merkmal_in(pfade: "list[str]") -> str:
    """Gibt das erste PlayGo-Merkmal zurueck, das in der Pfadliste enthalten ist."""
    for merkmal in _PLAYGO_MERKMALE:
        m = merkmal.lower()
        for p in pfade:
            p_norm = p.lstrip("/").replace("\\", "/").lower()
            if p_norm == m or p_norm.endswith("/" + m.split("/")[-1]):
                return merkmal
    return ""


def _playgo_in_baumtext(ausgabe: str) -> str:
    """Sucht PlayGo-Merkmale in der Textausgabe von 'mkpfs tree'."""
    ausgabe_lower = ausgabe.lower()
    for merkmal in _PLAYGO_MERKMALE:
        dateiname = merkmal.split("/")[-1].lower()
        if dateiname in ausgabe_lower:
            return merkmal
    return ""


def _playgo_in_ffpkg(pfad: str) -> str:
    """Sucht PlayGo-Merkmale per Stichproben-Scan im Rohdaten-Strom einer .ffpkg-Datei.

    Liest Fenster von 256 KB aus den ersten 64 MB - kein Mount/Dokan noetig.
    Dateinamen der PlayGo-Merkmale tauchen als Byte-Strings in der UFS2-Struktur auf.
    """
    _FENSTER = 256 * 1024
    _MAX_FRONT = 64 * 1024 * 1024
    _SCHRITT = 2 * 1024 * 1024

    merkmale_bytes = [m.split("/")[-1].encode() for m in _PLAYGO_MERKMALE]
    try:
        groesse = os.path.getsize(pfad)
        with open(pfad, "rb") as fh:
            versatz = 0
            while versatz < min(groesse, _MAX_FRONT):
                fh.seek(versatz)
                chunk = fh.read(_FENSTER)
                if not chunk:
                    break
                for i, dateiname in enumerate(merkmale_bytes):
                    if dateiname in chunk:
                        return _PLAYGO_MERKMALE[i]
                versatz += _SCHRITT
    except Exception:  # noqa: BLE001 - Lesefehler heisst "kein PlayGo-Merkmal gefunden"
        pass
    return ""


def playgo_erklaert_archiv(
    pfad: str,
    werkzeug: str = "",
    wurzeln: "list[str] | None" = None,
) -> str:
    """Prueft ein Archiv ohne Entpacken auf PlayGo-Abhaengigkeit.

    Unterstuetzt .pkg (via list-inner), .ffpfsc/.ffpfs/.exfat (via mkpfs tree)
    und .ffpkg (Raw-Byte-Scan, kein Dokan/Admin noetig).
    Gibt das erste gefundene Merkmal zurueck, oder "" wenn nicht gefunden oder Fehler.
    """
    from ps5_validator.utils import exfat_werkzeuge as ewz

    ext = os.path.splitext(pfad)[1].lower()
    try:
        if ext == ".pkg":
            if not werkzeug or not os.path.isfile(werkzeug):
                return ""
            eintraege = baum(werkzeug, pfad)
            return _playgo_merkmal_in([e.get("path", "") for e in eintraege])
        if ext in (".ffpfsc", ".ffpfs", ".exfat"):
            if not wurzeln:
                return ""
            eltern = ewz.mkpfs_eltern_suchen(wurzeln)
            if not eltern:
                return ""
            _ok, ausgabe = ewz._mkpfs_ausfuehren(eltern, ["tree", pfad], timeout=15)
            return _playgo_in_baumtext(ausgabe)
        if ext == ".ffpkg":
            return _playgo_in_ffpkg(pfad)
    except Exception:  # noqa: BLE001 - Archivfehler heisst "kein PlayGo-Merkmal gefunden"
        return ""
    return ""
