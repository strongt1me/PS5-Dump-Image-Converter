# -*- coding: utf-8 -*-
"""Direct Stream - mitgeliefert und im Programm selbst gestartet (seit v1.9.63).

DIRECT STREAM FOR PLAYSTATION 5 (Fassung 2.8.5, MIT-Lizenz) holt HTTP/HTTPS-
Downloads mit mehreren Stroemen gleichzeitig und schickt sie ueber FTP direkt
in den Speicher der Konsole - ohne die Datei vorher auf der Platte abzulegen.
Auch lokale Dateien lassen sich hochladen; dazu kommen ein Geschwindigkeitstest
und ein Dateibrowser fuer den Speicher der Konsole. Das Werkzeug ist ein
kleiner Webserver aus der Standardbibliothek (``ps5_streamer.py`` und
``transfer_core.py``) mit einer Oberflaeche aus HTML und JavaScript (``web/``).
Es liegt unveraendert bei; Herkunft und Stand stehen in
``DirectStream-2.8.5/UPSTREAM.md``.

**Warum im selben Prozess.** Der Server lauscht nur auf 127.0.0.1 (eigener,
zufaelliger Port, dazu eine Sitzungsmarke in der Adresse), hat weder Fenster
noch Eingabe, und seine beiden Module tragen eindeutige Namen. Ein eigener
Prozess braeuchte in der fertigen Programmdatei einen zweiten internen Modus
samt zweitem Entpacken (bei PS5 Wee Tools gemessen: 11 bis 18 s, einmal 37 s).
So startet der Server sofort, und das Programm bestimmt, wann er endet:
Beim Beenden wird er angehalten, und die Warteschlange ist gespeichert - eine
unterbrochene Uebertragung laesst sich spaeter fortsetzen.

**Warum nicht ``main()``.** ``main()`` verlangt, der Prozess zu sein: Sperre
fuer eine einzige Instanz, ``signal.signal`` (nur im Hauptfaden erlaubt),
Browser oeffnen, ``session.json`` schreiben. Gebraucht werden hier nur die
beiden Klassen ``Handler`` und ``Manager``; :func:`starten` baut den Server so
auf, wie ``main()`` es tut.

**Wohin es schreibt.** In ``<Einstellungsordner>/DirectStream/``: ``state.json``
mit den Einstellungen und der Warteschlange. Das FTP-Kennwort bleibt im
Arbeitsspeicher (so will es das Werkzeug).

Dieses Modul bindet ``i18n`` nicht ein und kennt keine Oberflaeche.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import mimetypes
import os
import re
import secrets
import sys
import threading
import urllib.parse
from pathlib import Path
from types import ModuleType

from . import direct_stream_texte

logger = logging.getLogger(__name__)

#: Der mitgelieferte Ordner (siehe dort UPSTREAM.md und herkunft.json).
ORDNER = "DirectStream-2.8.5"
#: Der Einstieg des Werkzeugs und sein Kern (``ps5_streamer`` importiert ihn).
EINSTIEG = "ps5_streamer.py"
KERN = "transfer_core.py"
#: Der Datenordner im Einstellungsordner des Programms.
DATENORDNER_NAME = "DirectStream"
#: Der Server lauscht nur hier - nie auf einer Adresse des Netzwerks.
ADRESSE = "127.0.0.1"
#: Die Zustandsdatei des Werkzeugs im Datenordner.
ZUSTAND = "state.json"
#: Zielordner auf der PS5, wenn noch keiner gespeichert ist. Das Werkzeug bringt
#: ``/data/ShadowMount`` mit; ShadowMount+ durchsucht aber ``/data/homebrew``
#: immer - was dort ankommt, sieht die Konsole sofort (Nutzerwunsch 06.10.2026).
ZIELORDNER = "/data/homebrew"
#: Pakete gehen in einen eigenen Ordner (Nutzer 06.10.2026: "Wenn Pakete (pkg)
#: hochgeladen werden, sollen diese in den Ordner data/pkg") - aber nur, solange
#: :data:`ZIELORDNER` eingestellt ist; einen selbst gewaehlten Ordner (etwa einen
#: USB-Datentraeger) laesst die Regel in Ruhe (:func:`zielordner_fuer`).
PAKET_ORDNER = "/data/pkg"
PAKET_ENDUNGEN = (".pkg",)
#: Was "Datei waehlen" und "Ordner hinzufuegen" anbieten: die Endungen des
#: Werkzeugs plus die Abbildformate des Programms (Nutzer 06.10.2026).
AUSWAHL_ENDUNGEN = (".pkg", ".ffpkg", ".ffpfsc", ".ffpfs", ".exfat", ".bin", ".iso", ".tar")
#: Hoechstens so viele Dateien aus einem Ordner - wie beim Werkzeug.
AUSWAHL_HOECHSTENS = 100
#: Die Typen, die die Oberflaeche braucht. Das Werkzeug fragt ``mimetypes``,
#: und unter Windows liest das die Registry - die kennt ``.js`` und ``.css``
#: nicht immer richtig. Der Server schickt ``nosniff``: Ein falscher Typ
#: heisst, dass der Browser das Skript nicht ausfuehrt, die Seite also leer
#: bleibt.
MIME_TYPEN = ((".js", "text/javascript"), (".css", "text/css"),
              (".html", "text/html"), (".svg", "image/svg+xml"),
              (".json", "application/manifest+json"))

#: Module, die einmal je Ordner geladen werden (Schluessel: Pfad des Einstiegs).
_geladen: dict[str, ModuleType] = {}


class DirectStreamFehler(Exception):
    """Direct Stream laesst sich nicht laden oder starten."""


def fassung_lesen(wurzel: str) -> str:
    """``VERSION`` aus ``ps5_streamer.py`` - gelesen, nicht importiert.

    Ein Import fuehrte das Werkzeug aus; ein Diagnosebericht soll nichts
    starten. Ohne Ordner gibt es nichts zu lesen - ein leerer Pfad duerfte
    nicht relativ zum Arbeitsverzeichnis suchen.
    """
    if not wurzel:
        return ""
    try:
        with open(os.path.join(wurzel, EINSTIEG), encoding="utf-8",
                  errors="replace") as datei:
            treffer = re.search(r"^VERSION\s*=\s*['\"]([^'\"]+)['\"]",
                                datei.read(), re.MULTILINE)
    except OSError:
        return ""
    return treffer.group(1) if treffer else ""


def datenordner(einstellungsordner: str) -> str:
    """Wohin Direct Stream schreibt: ``<Einstellungsordner>/DirectStream``."""
    return os.path.join(einstellungsordner, DATENORDNER_NAME)


def _datei_laden(name: str, pfad: str) -> ModuleType:
    """Laedt ein Modul aus einer Datei und traegt es unter ``name`` ein.

    Eingetragen wird *vor* der Ausfuehrung: ``transfer_core`` legt eine
    ``@dataclass`` an, und die schlaegt ihr Modul in ``sys.modules`` nach.
    """
    spec = importlib.util.spec_from_file_location(name, pfad)
    if spec is None or spec.loader is None:
        raise DirectStreamFehler("%s ist kein Python-Modul" % pfad)
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


def module_laden(wurzel: str) -> ModuleType:
    """Laedt ``ps5_streamer`` (und mit ihm ``transfer_core``) aus dem Ordner.

    Einmal je Ordner; ein zweiter Aufruf liefert dasselbe Modul. Scheitert das
    Laden, bleibt in ``sys.modules`` nichts Halbfertiges zurueck.

    Raises:
        DirectStreamFehler: Eine der beiden Dateien fehlt oder laesst sich
            nicht ausfuehren.
    """
    einstieg = os.path.join(wurzel, EINSTIEG)
    kern = os.path.join(wurzel, KERN)
    schluessel = os.path.normcase(os.path.abspath(einstieg))
    if schluessel in _geladen:
        return _geladen[schluessel]
    for pfad in (einstieg, kern):
        if not os.path.isfile(pfad):
            raise DirectStreamFehler("Datei fehlt: %s" % pfad)
    namen = ("transfer_core", "ps5_streamer")
    vorher = {name: sys.modules.get(name) for name in namen}
    try:
        _datei_laden("transfer_core", kern)
        modul = _datei_laden("ps5_streamer", einstieg)
    except Exception as exc:  # noqa: BLE001 - jede Ursache gehoert in die Meldung
        for name, alt in vorher.items():
            if alt is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = alt
        raise DirectStreamFehler("%s: %s" % (type(exc).__name__, exc)) from exc
    _transfer_umleiten(modul)
    _geladen[schluessel] = modul
    return modul


def zielordner_fuer(name: str, ordner: str) -> str:
    """Wohin eine Datei auf der PS5 geht: Pakete nach :data:`PAKET_ORDNER`, sonst ``ordner``.

    Nur, wenn ``ordner`` die Vorgabe des Programms ist - ein selbst gewaehlter
    Zielordner gilt fuer alles.
    """
    if (str(ordner or "").rstrip("/") == ZIELORDNER
            and str(name or "").lower().endswith(PAKET_ENDUNGEN)):
        return PAKET_ORDNER
    return ordner


def _transfer_umleiten(modul: ModuleType) -> None:
    """Legt sich um ``transfer`` des Werkzeugs: Der Zielordner kommt je Datei aus :func:`zielordner_fuer`.

    Das Werkzeug kennt nur einen Zielordner fuer alle Auftraege und liest ihn
    allein in ``transfer`` (``settings["folder"]``: Ordner anlegen, freien
    Platz pruefen, hochladen). ``ps5_streamer`` ruft ``transfer`` ueber seinen
    eigenen Namensraum - dort wird ersetzt, die Datei bleibt unveraendert. Die
    Ziel-Pruefung des Werkzeugs beim Fortsetzen vergleicht die Einstellungen,
    nicht den Ordner je Datei; ein fortgesetztes Paket geht deshalb wieder
    nach :data:`PAKET_ORDNER`.
    """
    original = getattr(modul, "transfer", None)
    if original is None or getattr(original, "_ps5conv_umgeleitet", False):
        return

    def transfer(job, cfg, *args, **kwargs):
        ordner = zielordner_fuer(job.get("name", ""), cfg.get("folder", ""))
        if ordner != cfg.get("folder"):
            cfg = dict(cfg, folder=ordner)
        return original(job, cfg, *args, **kwargs)

    transfer._ps5conv_umgeleitet = True  # type: ignore[attr-defined]
    transfer.__wrapped__ = original  # type: ignore[attr-defined]
    modul.transfer = transfer


def _auswahl_dialog(art: str, sprache: str) -> tuple[list[str], str, bool]:
    """Datei- oder Ordnerauswahl wie im Werkzeug - mit den Abbildformaten des Programms.

    Returns:
        ``(dateien, ordner, nicht_moeglich)`` - wie die Werte, die das Werkzeug
        in ``/api/pick`` ermittelt.
    """
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    de = sprache == "de"
    titel_datei = "Dateien für die PS5 wählen" if de else "Choose files to send to PS5"
    titel_ordner = "Ordner mit Paketen oder Abbildern wählen" if de else "Choose folder containing packages or images"
    muster = ";".join("*" + e for e in AUSWAHL_ENDUNGEN)
    dateien: list[str] = []
    ordner = ""
    try:
        if sys.platform == "win32":
            if art == "folder":
                befehl = ("Add-Type -AssemblyName System.Windows.Forms; $f = New-Object "
                          "System.Windows.Forms.FolderBrowserDialog; $f.Description = '%s'; "
                          "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
                          "{ Write-Output $f.SelectedPath }" % titel_ordner.replace("'", "''"))
            else:
                filter_text = ("%s (%s)|%s|%s (*.*)|*.*" % (
                    "Pakete und Abbilder" if de else "Packages and images", muster, muster,
                    "Alle Dateien" if de else "All files"))
                befehl = ("Add-Type -AssemblyName System.Windows.Forms; $f = New-Object "
                          "System.Windows.Forms.OpenFileDialog; $f.Title = '%s'; $f.Multiselect = $true; "
                          "$f.Filter = '%s'; if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
                          "{ $f.FileNames | ForEach-Object { Write-Output $_ } }"
                          % (titel_datei.replace("'", "''"), filter_text.replace("'", "''")))
            lauf = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", befehl],
                                  capture_output=True, text=True, timeout=600,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif sys.platform == "darwin":
            if art == "folder":
                skript = 'POSIX path of (choose folder with prompt "%s")' % titel_ordner
            else:
                skript = ('set chosen to choose file with prompt "%s" with multiple selections allowed\n'
                          'set outPaths to ""\nrepeat with aFile in chosen\n'
                          '  set outPaths to outPaths & (POSIX path of aFile) & linefeed\nend repeat\n'
                          'return outPaths' % titel_datei)
            lauf = subprocess.run(["/usr/bin/osascript", "-e", skript], capture_output=True, text=True,
                                  timeout=600)
        elif shutil.which("zenity"):
            if art == "folder":
                befehl_z = ["zenity", "--file-selection", "--directory", "--title=" + titel_ordner]
            else:
                befehl_z = ["zenity", "--file-selection", "--multiple", "--separator=\n",
                            "--title=" + titel_datei,
                            "--file-filter=%s | %s" % (titel_datei, " ".join("*" + e for e in AUSWAHL_ENDUNGEN)),
                            "--file-filter=* | *"]
            lauf = subprocess.run(befehl_z, capture_output=True, text=True, timeout=600)
        else:
            return [], "", True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Direct Stream: Auswahl nicht moeglich: %s", exc)
        return [], "", True
    zeilen = [z.strip() for z in (lauf.stdout or "").splitlines() if z.strip()] if lauf.returncode == 0 else []
    if art == "folder":
        ordner = zeilen[0] if zeilen else ""
    else:
        dateien = zeilen
    return dateien, ordner, False


def ordner_durchsuchen(ordner: str) -> list[str]:
    """Die Dateien eines Ordners mit :data:`AUSWAHL_ENDUNGEN` - hoechstens :data:`AUSWAHL_HOECHSTENS`."""
    gefunden: list[str] = []
    if not ordner or not os.path.isdir(ordner):
        return gefunden
    for stamm, _unter, namen in os.walk(ordner):
        for name in sorted(namen):
            if name.lower().endswith(AUSWAHL_ENDUNGEN):
                gefunden.append(os.path.join(stamm, name))
                if len(gefunden) >= AUSWAHL_HOECHSTENS:
                    return gefunden
    return gefunden


def vorbelegen(modul: ModuleType, ordner: str, host: str, ftp_port: int = 0) -> bool:
    """Traegt Adresse, FTP-Port und Zielordner ein - nur, wo noch nichts steht.

    Das Werkzeug fragt beim ersten Start nach der Adresse der PS5; das Programm
    kennt sie schon (Suche beim Start, Einstellungen). Eine bereits gespeicherte
    Adresse bleibt unberuehrt: Wer in den Einstellungen der Seite etwas anderes
    gewaehlt hat (eine zweite Konsole), soll es nicht bei jedem Start
    zurueckbekommen. Ebenso der Zielordner: :data:`ZIELORDNER` gilt nur, solange
    keiner gespeichert ist - auch ohne bekannte Adresse. Eine beschaedigte
    ``state.json`` wird nicht angefasst; der Manager meldet sie selbst.

    Geschrieben wird ueber die eigenen Funktionen des Werkzeugs
    (``validated_settings``, ``atomic_json``), damit die Datei so aussieht,
    wie es sie selbst anlegt - samt Rechten und ohne Kennwort.

    Args:
        modul: Das geladene ``ps5_streamer``.
        ordner: Der Datenordner.
        host: Adresse der Konsole; leer heisst: keine Adresse eintragen.
        ftp_port: Port des FTP-Servers der Konsole; 0 laesst den Vorgabewert.

    Returns:
        True, wenn die **Adresse** eingetragen wurde (das Protokoll nennt sie dann).
    """
    host = (host or "").strip()
    pfad = os.path.join(ordner, ZUSTAND)
    zustand: dict = {}
    if os.path.isfile(pfad):
        try:
            with open(pfad, encoding="utf-8") as datei:
                zustand = json.loads(datei.read())
        except (OSError, ValueError):
            return False
        if not isinstance(zustand, dict):
            return False
    einstellungen = zustand.get("settings")
    if not isinstance(einstellungen, dict):
        einstellungen = {}
    adresse_eintragen = bool(host) and not str(einstellungen.get("host") or "").strip()
    ordner_eintragen = "folder" not in einstellungen
    if not (adresse_eintragen or ordner_eintragen):
        return False
    neu = dict(modul.DEFAULTS)
    # Der Zielordner des Programms, nicht der des Werkzeugs - aber nur, wo noch
    # keiner gespeichert ist (wer ihn auf der Seite geaendert hat, behaelt ihn).
    neu["folder"] = ZIELORDNER
    neu.update({k: v for k, v in einstellungen.items() if k in modul.DEFAULTS})
    if adresse_eintragen:
        neu["host"] = host
        if ftp_port:
            neu["port"] = int(ftp_port)
    try:
        neu = modul.validated_settings(neu)
    except Exception as exc:  # noqa: BLE001 - eine untaugliche Adresse bleibt draussen
        logger.debug("Direct Stream: Adresse %r nicht vorbelegt: %s", host, exc)
        if not adresse_eintragen or not ordner_eintragen:
            return False
        # Die Adresse taugt nicht - der Zielordner kommt trotzdem hinein.
        vorbelegen(modul, ordner, "", 0)
        return False
    neu.pop("password", None)
    zustand["version"] = modul.VERSION
    zustand["settings"] = neu
    zustand.setdefault("jobs", [])
    try:
        modul.atomic_json(Path(pfad), zustand)
    except OSError as exc:
        logger.debug("Direct Stream: state.json nicht geschrieben: %s", exc)
        return False
    return adresse_eintragen


def _mime_typen_festlegen() -> None:
    """Setzt die Typen der Oberflaeche fest (siehe :data:`MIME_TYPEN`)."""
    for endung, typ in MIME_TYPEN:
        mimetypes.add_type(typ, endung)


def handler_klasse(modul: ModuleType) -> type:
    """``Handler`` des Werkzeugs, der die Seite in der Sprache des Programms ausliefert.

    Nur zwei Pfade weichen ab: ``/`` liefert ``index.html`` mit dem Skript aus
    :mod:`direct_stream_texte` im Kopf, und unter
    :data:`direct_stream_texte.SKRIPT_PFAD` liegt dieses Skript. Gleiche
    Herkunft, also erlaubt es die Inhaltsrichtlinie des Werkzeugs
    (``script-src 'self'``); dieselbe Pruefung von Host und Herkunft
    (``allowed``) gilt auch hier. Alles andere bleibt beim Original.

    Die Sprache steht am Server (``server.sprache``, :attr:`Sitzung.sprache`)
    und gilt ab der naechsten geladenen Seite - ein Sprachwechsel im Programm
    braucht keinen Neustart des Servers, der eine Uebertragung abbraeche.
    """
    seite_pfad = Path(modul.BASE) / "web" / "index.html"
    skripte: dict[str, bytes] = {}

    class Handler(modul.Handler):
        def do_GET(self):  # noqa: N802 - Name von BaseHTTPRequestHandler
            pfad = urllib.parse.urlsplit(self.path).path
            if pfad not in ("/", direct_stream_texte.SKRIPT_PFAD):
                super().do_GET()
                return
            if not self.allowed(False):
                return
            sprache = "de" if getattr(self.server, "sprache", "") == "de" else "en"
            if pfad == "/":
                seite = direct_stream_texte.seite_einrichten(
                    seite_pfad.read_text(encoding="utf-8"), sprache)
                self.send(200, seite.encode("utf-8"), "text/html; charset=utf-8")
                return
            if sprache not in skripte:
                skripte[sprache] = direct_stream_texte.skript(sprache).encode("utf-8")
            self.send(200, skripte[sprache], "text/javascript; charset=utf-8")

        def do_POST(self):  # noqa: N802 - Name von BaseHTTPRequestHandler
            """``/api/pick`` mit den Abbildformaten des Programms - alles andere wie das Werkzeug."""
            if urllib.parse.urlsplit(self.path).path != "/api/pick":
                super().do_POST()
                return
            if not self.allowed(True):
                return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected a JSON request.")
                laenge = int(self.headers.get("Content-Length", 0))
                if not 0 < laenge <= 512 * 1024:
                    raise ValueError("Invalid request size.")
                daten = json.loads(self.rfile.read(laenge))
                if not isinstance(daten, dict):
                    raise ValueError("Invalid request.")
            except (ValueError, TypeError) as exc:
                self.send(400, {"error": str(exc)})
                return
            art = "folder" if daten.get("type") == "folder" else "file"
            sprache = "de" if getattr(self.server, "sprache", "") == "de" else "en"
            dateien, ordner, nicht_moeglich = _auswahl_dialog(art, sprache)
            if art == "folder":
                ergebnis = {"paths": ordner_durchsuchen(ordner), "path": ordner,
                            "picker_unsupported": nicht_moeglich and not ordner}
            else:
                ergebnis = {"paths": dateien, "path": dateien[0] if dateien else "",
                            "picker_unsupported": nicht_moeglich and not dateien}
            self.send(200, ergebnis)

    return Handler


class Sitzung:
    """Ein laufender Direct-Stream-Server im Programm.

    Ihn legt :func:`starten` an. Der Server laeuft in einem eigenen Faden
    (``daemon``: das Programmende wartet nicht auf ihn - :meth:`beenden` ist
    der geordnete Weg). Beendet ihn die Oberflaeche selbst ("Quit app"), endet
    der Faden ebenfalls; :attr:`laeuft` sagt es, und der naechste Knopfdruck
    startet eine neue Sitzung.
    """

    def __init__(self, modul: ModuleType, server, ordner: str,
                 vorbelegt: bool = False) -> None:
        self._modul = modul
        self._server = server
        #: Der Datenordner dieser Sitzung.
        self.ordner = ordner
        #: Wurde Adresse und Port der Konsole eingetragen (:func:`vorbelegen`)?
        self.vorbelegt = vorbelegt
        self._faden = threading.Thread(target=self._lauf, name="direct-stream",
                                       daemon=True)
        self._faden.start()

    def _lauf(self) -> None:
        """Bedient Anfragen, bis jemand ``shutdown`` ruft - dann aufraeumen.

        Wie das ``finally`` in ``main()``: Der Manager haelt seine Warteschlange
        an und speichert sie, danach geht der Anschluss zu.
        """
        try:
            self._server.serve_forever(poll_interval=0.2)
        finally:
            try:
                self._server.manager.stop()
            except Exception:  # noqa: BLE001 - Aufraeumen darf nichts mehr verhindern
                logger.exception("Direct Stream: Warteschlange nicht angehalten")
            try:
                self._server.server_close()
            except OSError:
                pass

    @property
    def port(self) -> int:
        """Der Anschluss auf 127.0.0.1."""
        return int(self._server.server_port)

    @property
    def marke(self) -> str:
        """Die Sitzungsmarke - ohne sie antwortet der Server auf keine Anfrage der API."""
        return str(self._server.token)

    @property
    def url(self) -> str:
        """Die Adresse der Oberflaeche - mit der Marke im Fragment, wie ``main()`` sie ausgibt."""
        return "http://%s:%d/#session=%s" % (ADRESSE, self.port, self.marke)

    @property
    def sprache(self) -> str:
        """Die Sprache der Seite (``"de"`` oder sonst englisch neutral) - gilt ab dem naechsten Laden."""
        return str(getattr(self._server, "sprache", "en"))

    @sprache.setter
    def sprache(self, wert: str) -> None:
        self._server.sprache = wert

    @property
    def zielordner(self) -> str:
        """Der Zielordner auf der PS5, wie er in den Einstellungen des Werkzeugs steht."""
        return str((getattr(self._server.manager, "settings", {}) or {}).get("folder", ""))

    def zielordner_setzen(self, ordner: str) -> None:
        """Stellt den Zielordner um - ueber ``configure`` des Werkzeugs, also mit dessen Pruefung.

        Das Werkzeug lehnt das ab, solange uebertragen oder gemessen wird
        (``TransferError``) - die Meldung geht an den Aufrufer. Adresse, Port,
        Kennwort und die uebrigen Einstellungen bleiben, wie sie sind.
        """
        manager = self._server.manager
        einstellungen = dict(getattr(manager, "settings", {}) or {})
        einstellungen["folder"] = str(ordner)
        einstellungen["password"] = getattr(manager, "password", "") or ""
        manager.configure(einstellungen)

    @property
    def laeuft(self) -> bool:
        return self._faden.is_alive()

    def stand(self) -> dict:
        """Was die Oberflaeche abfragt (``/api/state``): Einstellungen, Auftraege, Meldungen."""
        return self._server.manager.snapshot()

    def uebertraegt(self) -> bool:
        """Laeuft gerade ein Auftrag? Dann unterbricht das Beenden eine Uebertragung.

        Gezaehlt wird nur der Auftrag in Arbeit; ein Geschwindigkeitstest oder
        eine wartende Warteschlange geht beim Beenden nichts verloren.
        """
        manager = self._server.manager
        try:
            with manager.lock:
                return manager.current is not None
        except Exception:  # noqa: BLE001 - im Zweifel nicht ausbremsen
            return False

    def beenden(self, frist: float = 6.0) -> bool:
        """Haelt den Server an und wartet auf den Faden.

        ``shutdown`` kehrt erst zurueck, wenn die Bedienschleife verlassen ist;
        es laeuft deshalb in einem eigenen Faden, damit eine haengende Beendigung
        das Programmende nicht aufhaelt. Ein laufender Auftrag wird abgebrochen
        (die unvollstaendige Datei bleibt auf der Konsole, der Stand in der
        Warteschlange), der Manager speichert.

        Returns:
            True, wenn der Server innerhalb der Frist zu ist.
        """
        if self._faden.is_alive():
            halt = threading.Thread(target=self._server.shutdown,
                                    name="direct-stream-halt", daemon=True)
            halt.start()
            self._faden.join(frist)
        return not self._faden.is_alive()


def starten(wurzel: str, ordner: str, *, host: str = "", ftp_port: int = 0,
            sprache: str = "en") -> Sitzung:
    """Startet Direct Stream: Server auf 127.0.0.1, eigener Port, frische Marke.

    Args:
        wurzel: Der mitgelieferte Ordner (:data:`ORDNER`).
        ordner: Der Datenordner (:func:`datenordner`); wird angelegt.
        host: Adresse der Konsole fuer die Einstellungen (:func:`vorbelegen`).
        ftp_port: Port des FTP-Servers der Konsole.
        sprache: Sprache des Programms; ``"de"`` zeigt die Seite deutsch,
            alles andere englisch ohne Mac-Bezug (:func:`handler_klasse`).

    Raises:
        DirectStreamFehler: Der Ordner ist unvollstaendig oder das Werkzeug
            laesst sich nicht laden.
        OSError: Der Datenordner oder der Anschluss ist nicht zu bekommen.
    """
    modul = module_laden(wurzel)
    os.makedirs(ordner, exist_ok=True)
    try:
        os.chmod(ordner, 0o700)
    except OSError:
        pass
    vorbelegt = vorbelegen(modul, ordner, host, ftp_port)
    _mime_typen_festlegen()
    server = modul.ThreadingHTTPServer((ADRESSE, 0), handler_klasse(modul))
    server.daemon_threads = True
    server.sprache = sprache
    server.token = secrets.token_urlsafe(32)
    try:
        server.manager = modul.Manager(ordner)
    except Exception:
        server.server_close()
        raise
    return Sitzung(modul, server, ordner, vorbelegt)
