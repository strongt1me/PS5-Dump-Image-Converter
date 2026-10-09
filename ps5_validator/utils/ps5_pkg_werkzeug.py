# -*- coding: utf-8 -*-
"""Die Huelle um ``ffpfsc-pkg-tool`` - lesen, pruefen, entpacken und bauen von PS5-Paketen (seit v1.9.71).

Das Werkzeug stammt aus dem Quelltext von **ps5-fpkg-converter 0.0.2** (GPL-3.0-or-later; darin die Engine von
ps5-ultrapack, MIT) und liegt, fuer jede Plattform einzeln gebaut, unter ``PS5-PKG-Tool/<Plattform>/``. Es ist ein
.NET-Programm (net10.0, abhaengig von der installierten Laufzeit - die braucht das Programm ohnehin) und kapselt
LibProsperoPkg 1.2.0. Befehle, die hier gebraucht werden: ``inspect``, ``validate``, ``extract-inner`` (ganz oder
mit ``--members``) und ``build`` (aus einem Spielordner ein Debug-Paket, :func:`bauen`).

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#: Ordner im Projekt (und im Bau), darin je Plattform ein Unterordner.
ORDNER = "PS5-PKG-Tool"

_Zeile = Callable[[str], None]
_Abbruch = Callable[[], bool]

#: ``PaketInfo.typ`` eines Spielordners.
TYP_ORDNER = "Ordner"

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


def _umgebung() -> dict[str, str]:
    env = dict(os.environ)
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
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(prozess.pid)], capture_output=True, check=False)
        else:
            prozess.kill()
    except OSError:
        pass
    try:
        prozess.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


def laufen(werkzeug: str, argumente: list[str], *, zeile: _Zeile | None = None, abbruch: _Abbruch | None = None,
           popen_extra: dict | None = None) -> tuple[int, str]:
    """Startet das Werkzeug und liest seine Ausgabe zeilenweise (stdout und stderr zusammen).

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
    try:
        prozess = subprocess.Popen([werkzeug, *argumente], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=_umgebung(), bufsize=0, **(popen_extra or {}))
    except OSError as exc:
        raise Fehler("Das Werkzeug laesst sich nicht starten: %s" % exc) from exc
    assert prozess.stdout is not None
    gesammelt: list[str] = []
    rest = b""
    try:
        while True:
            if abbruch and abbruch():
                _beenden(prozess)
                return -1, "".join(gesammelt)
            stueck = prozess.stdout.read(4096)
            if not stueck:
                break
            rest += stueck
            while True:
                stellen = [i for i in (rest.find(b"\n"), rest.find(b"\r")) if i >= 0]
                if not stellen:
                    break
                i = min(stellen)
                text = rest[:i].decode("utf-8", errors="replace").strip()
                rest = rest[i + 1:]
                if text:
                    gesammelt.append(text + "\n")
                    if zeile:
                        zeile(text)
        if rest.strip():
            text = rest.decode("utf-8", errors="replace").strip()
            gesammelt.append(text + "\n")
            if zeile:
                zeile(text)
        return prozess.wait(), "".join(gesammelt)
    finally:
        if prozess.poll() is None:
            _beenden(prozess)


def _json_aus(ausgabe: str) -> dict:
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


def inspect(werkzeug: str, paket: str, popen_extra: dict | None = None) -> dict:
    """Kopfdaten eines Pakets (``inspect --json``): Typ, Content-ID, Title-ID, Eintraege."""
    rc, aus = laufen(werkzeug, ["inspect", paket, "--json"], popen_extra=popen_extra)
    if rc != 0:
        raise Fehler(_fehlertext(aus))
    return _json_aus(aus)


def pruefen(werkzeug: str, paket: str, *, zeile: _Zeile | None = None, abbruch: _Abbruch | None = None,
            popen_extra: dict | None = None) -> dict:
    """Die Pruefliste des Werkzeugs (``validate --json``): ``{"pass": n, "warn": n, "fail": n, "results": [...]}``."""
    rc, aus = laufen(werkzeug, ["validate", paket, "--json"], zeile=zeile, abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise Fehler("abgebrochen")
    try:
        return _json_aus(aus)
    except Fehler:
        raise Fehler(_fehlertext(aus)) from None


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

    @property
    def ist_ordner(self) -> bool:
        """Ein Spielordner (Dump) statt eines Pakets."""
        return self.typ == TYP_ORDNER

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


def lesen(werkzeug: str, paket: str, arbeitsordner: str | None = None, *, popen_extra: dict | None = None) -> PaketInfo:
    """Liest ein Paket fuer die Anzeige: Kopfdaten, ``param.json`` und das Cover ``icon0.png``.

    ``param.json`` und ``icon0.png`` werden einzeln in einen kleinen Ordner herausgeholt (0,3 s gemessen an einem
    939-MB-Paket); das Paket selbst wird nicht entpackt. ``arbeitsordner`` ist die Ablage fuer das Cover, sonst ein
    eigener Ordner unter dem Temp-Ordner (``ps5conv_pkgcover_*``); das Cover bleibt dort liegen, bis es nicht mehr
    gebraucht wird.
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
    rc, _aus = laufen(werkzeug, ["extract-inner", paket, os.path.join(ordner, "teile"), "--members", liste],
                      popen_extra=popen_extra)
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


def ordner_groesse(ordner: str, melden: _Zeile | None = None) -> int:
    """Die Summe der Dateigroessen unter ``ordner``; ``melden`` bekommt am Ende eine Zeile (Dateizahl)."""
    summe = anzahl = 0
    for wurzel, _ordner, dateien in os.walk(ordner):
        for name in dateien:
            try:
                summe += os.path.getsize(os.path.join(wurzel, name))
                anzahl += 1
            except OSError:
                continue
    if melden:
        melden("[info] %s: %d Dateien, %.2f GB" % (os.path.basename(ordner), anzahl, summe / 1024 ** 3))
    return summe


def ordner_lesen(ordner: str, arbeitsordner: str | None = None, melden: _Zeile | None = None) -> PaketInfo:
    """Liest einen Spielordner fuer die Anzeige: ``param.json``, Cover (als Kopie) und Groesse.

    Das Cover wird in einen eigenen Ordner kopiert (``PaketInfo.arbeit``); nur dieser wird beim Schliessen des
    Fensters entfernt - der Spielordner selbst wird nie angefasst.

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
    info = PaketInfo(pfad=ordner, groesse=ordner_groesse(ordner, melden), typ=TYP_ORDNER,
                     content_id=str(param.get("contentId", "") or ""), title_id=str(param.get("titleId", "") or ""),
                     titel=titel_aus_param(param), param=param)
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


#: Die Phasen eines Baus und ihr Anteil am Balken (von, bis in Prozent) - so meldet ``build`` sich im Text.
_BAU_PHASEN = (
    (re.compile(r"\[stage\] copy (\d+)%"), 0, 10),
    (re.compile(r"\[inner\]\s+read \d+/\d+ \(\s*(\d+)%\)"), 10, 25),
    (re.compile(r"\[inner\]\s+data\s+(\d+)%"), 25, 80),
    (re.compile(r"Writing and hashing outer-PFS data.*?:\s*(\d+)%"), 80, 93),
    (re.compile(r"\[finalize\].*?:\s*(\d+)%"), 93, 99),
)


def bau_fortschritt(zeile: str) -> tuple[int, str] | None:
    """Prozent des ganzen Baus (0 bis 99) und eine kurze Beschreibung aus einer Zeile von ``build``, sonst ``None``."""
    for muster, von, bis in _BAU_PHASEN:
        treffer = muster.search(zeile)
        if treffer:
            anteil = min(100, int(treffer.group(1)))
            datei = re.search(r"\):\s*(\S.*?)(?: -> |$)", zeile)
            return von + (bis - von) * anteil // 100, (datei.group(1) if datei else zeile.split("] ", 1)[-1])[:140]
    return None


#: So sieht eine Content-ID aus: ``UP8016-PPSA19015_00-0489895718491618`` (36 Zeichen).
CONTENT_ID = re.compile(r"^[A-Z]{2}\d{4}-[A-Z]{4}\d{5}_\d{2}-[A-Za-z0-9]{16}$")
TITLE_ID = re.compile(r"^[A-Z]{4}\d{5}$")


def bauen(werkzeug: str, quelle: str, ziel: str, *, content_id: str, title_id: str, titel: str = "",
          version: str = "01.000.000", stufe: int = 0, kerne: int = 0, fake_signieren: bool = True,
          ampr_index: bool = True, temp: str | None = None, zeile: _Zeile | None = None,
          fortschritt: Callable[[int, str], None] | None = None, abbruch: _Abbruch | None = None,
          popen_extra: dict | None = None) -> str:
    """Baut aus einem Spielordner ein Debug-Paket (``build``) und gibt den Pfad der ``.pkg`` zurueck.

    Die Voreinstellungen sind die, die der Autor des Werkzeugs an einer Konsole belegt hat (PS5 mit Firmware 11.60 und
    kstuff-lite 1.13): Kraken-Schicht ueber dem inneren Abbild und der **eingebaute** Kraken-Kodierer - mit gespeicherten
    Bloecken installiert sich das Paket, startet aber nicht (CE-100096-6). ``stufe`` ist die Kraken-Stufe (-4 bis 9),
    ``kerne`` die Zahl der Arbeiter (0 = einer je Kern). ``temp`` nimmt die Kopie des Spielordners und die
    Zwischendateien auf (das Werkzeug arbeitet nie am Original).

    Raises:
        Fehler: ungueltige Kennung, Fehler des Werkzeugs, kein ``OK`` am Ende; ``abgebrochen`` beim Abbruch.
    """
    if not CONTENT_ID.match(content_id):
        raise Fehler("Ungueltige Content-ID: %r" % content_id)
    if not TITLE_ID.match(title_id):
        raise Fehler("Ungueltige Title-ID: %r" % title_id)
    Path(ziel).mkdir(parents=True, exist_ok=True)
    argumente = ["build", quelle, ziel, "--content-id", content_id, "--title-id", title_id, "--version", version,
                 "--mode", "kraken", "--kraken-backend", "builtin", "--level", str(int(stufe))]
    if titel:
        argumente += ["--title", titel]
    if temp:
        argumente += ["--temp", temp]
    if kerne and int(kerne) > 0:
        argumente += ["--parallelism", str(int(kerne))]
    if not fake_signieren:
        argumente.append("--no-fake-sign")
    if not ampr_index:
        argumente.append("--no-ampr-index")

    def jede(text: str) -> None:
        gemeldet = bau_fortschritt(text)
        if gemeldet and fortschritt:
            fortschritt(gemeldet[0], gemeldet[1])
        elif zeile and not text.startswith(("[inner]   read ", "[inner]   data ")):
            zeile(text)

    rc, aus = laufen(werkzeug, argumente, zeile=jede, abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise Fehler("abgebrochen")
    ok = [z for z in aus.splitlines() if z.startswith("OK")]
    if rc != 0 or not ok:
        raise Fehler(_fehlertext(aus))
    treffer = re.match(r"OK\s*[-\u2014]\s*wrote\s+(.+?)\s+\(([\d,. ]+) B\)\s*$", ok[-1])
    return treffer.group(1) if treffer else ok[-1]


def baum(werkzeug: str, paket: str, popen_extra: dict | None = None) -> list[dict]:
    """Der Inhalt des Spiels (``list-inner``): ``[{"path": ..., "type": "file"|"dir", "size": ...}, ...]``."""
    rc, aus = laufen(werkzeug, ["list-inner", paket], popen_extra=popen_extra)
    if rc != 0:
        raise Fehler(_fehlertext(aus))
    eintraege = _json_aus(aus).get("entries", [])
    return [e for e in eintraege if isinstance(e, dict) and e.get("path")]


def extrahieren(werkzeug: str, paket: str, ziel: str, *, zeile: _Zeile | None = None,
                fortschritt: Callable[[int, str], None] | None = None, abbruch: _Abbruch | None = None,
                popen_extra: dict | None = None, arbeitsordner: str | None = None) -> str:
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

    def jede(text: str) -> None:
        treffer = _FORTSCHRITT.match(text)
        if treffer and fortschritt:
            # "[####] 42% extract (Media/a.dat)" - der Dateiname steht in Klammern
            datei = re.search(r"\((.*)\)\s*$", treffer.group(2))
            fortschritt(min(100, int(treffer.group(1))), datei.group(1) if datei else "")
        elif zeile:
            zeile(text)

    liste = ""
    argumente = ["extract-inner", paket, ziel]
    try:
        eintraege = baum(werkzeug, paket, popen_extra)
        if eintraege:
            handle, liste = tempfile.mkstemp(prefix="ps5conv_teile_", suffix=".txt", dir=arbeitsordner or None)
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write("\n".join(e["path"] for e in eintraege) + "\n")
            argumente = ["extract-inner", paket, ziel, "--members", liste]
    except (Fehler, OSError) as exc:
        if zeile:
            zeile("[info] kein Fortschritt je Datei moeglich (%s) - voller Entpack" % exc)
        liste = ""
    try:
        rc, aus = laufen(werkzeug, argumente, zeile=jede, abbruch=abbruch, popen_extra=popen_extra)
        if rc == -1:
            raise Fehler("abgebrochen")
        ok = [z for z in aus.splitlines() if z.startswith("OK")]
        if (rc != 0 or not ok) and liste:
            if zeile:
                zeile("[info] Entpacken je Datei gescheitert (%s) - voller Entpack" % _fehlertext(aus))
            rc, aus = laufen(werkzeug, ["extract-inner", paket, ziel], zeile=jede, abbruch=abbruch,
                             popen_extra=popen_extra)
            if rc == -1:
                raise Fehler("abgebrochen")
            ok = [z for z in aus.splitlines() if z.startswith("OK")]
        if rc != 0 or not ok:
            raise Fehler(_fehlertext(aus))
        return ok[-1]
    finally:
        if liste:
            try:
                os.remove(liste)
            except OSError:
                pass
